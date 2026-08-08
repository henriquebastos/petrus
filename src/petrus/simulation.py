"""Bounded production of portable, implementation-free simulation results."""

from __future__ import annotations

import json
from typing import Any, cast

from petrus.engine import Engine, SimulatedClock
from petrus.impetus.dsl import BuiltNet
from petrus.impetus.history.codec import encode_record
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.observation import definition
from petrus.impetus.observation import marking as project_marking
from petrus.impetus.petrinet import ArcMode, Cel, Delay, Marking, NetPath, Token, Until

MAX_PLACES = 128
MAX_TRANSITIONS = 128
MAX_ARCS = 512
MAX_INITIAL_TOKENS = 512
MAX_INITIAL_PAYLOAD_BYTES = 1_000_000
MAX_ACTIONS = 256
MAX_RETAINED_TOKENS = 4_096
MAX_RETAINED_PAYLOAD_BYTES = 4_194_304
MAX_HISTORY_RECORDS = 50_000
MAX_HISTORY_PAYLOAD_BYTES = 4_194_304
MAX_RESULT_BYTES = 4_194_304
MAX_CANDIDATE_OFFERS = 10_000
MAX_CEL_BYTES = 4_096
MAX_DEFINITION_BYTES = 1_000_000
MAX_REQUEST_BODY_BYTES = 1_048_576
CONNECTION_TIMEOUT_SECONDS = 5


class SimulationProfileError(ValueError):
    """The requested run is outside ``implementation-free-v1``."""


class _ForbiddenDispatch:
    def dispatch(self, occurrence, invocation) -> None:
        del occurrence, invocation
        raise SimulationProfileError("implementation-free-v1 forbids Dispatch use")

    def collect(self):
        return ()


# Complexity exception: this is the profile's single field-complete admission boundary.
def _strict_detach(value: object, subject: str) -> object:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise SimulationProfileError(f"{subject} must be strict JSON-faithful: {error}") from None


def _encoded_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def _check_cel(value: Cel, subject: str) -> None:
    size = len(value.expression.encode())
    if size > MAX_CEL_BYTES:
        raise SimulationProfileError(
            f"implementation-free-v1 CEL expression limit is {MAX_CEL_BYTES} UTF-8 bytes; {subject} has {size}"
        )


def _admit(  # noqa: C901
    built: BuiltNet, initial_marking: Marking, max_actions: int
) -> tuple[list[dict[str, object]], Marking]:
    if not isinstance(built, BuiltNet):
        raise TypeError(f"simulation requires an application-owned BuiltNet, got {built!r}")
    if not isinstance(initial_marking, Marking):
        raise TypeError(f"simulation requires a Python Marking, got {initial_marking!r}")
    if isinstance(max_actions, bool) or not isinstance(max_actions, int) or not 1 <= max_actions <= MAX_ACTIONS:
        raise SimulationProfileError(
            f"max_actions must be an integer from 1 through {MAX_ACTIONS}, got {max_actions!r}"
        )
    net = built.net
    for label, actual, limit in (
        ("places", len(net.places), MAX_PLACES),
        ("transitions", len(net.transitions), MAX_TRANSITIONS),
        ("arcs", len(net.arcs), MAX_ARCS),
    ):
        if actual > limit:
            raise SimulationProfileError(f"implementation-free-v1 {label} limit is {limit}, found {actual}")
    if built.handlers:
        raise SimulationProfileError("implementation-free-v1 forbids BuiltNet handler implementations")
    if built.guards:
        raise SimulationProfileError("implementation-free-v1 forbids BuiltNet guard implementations")
    for transition in net.transitions.values():
        if transition.handler is not None:
            raise SimulationProfileError(
                f"implementation-free-v1 requires transition {transition.path} handler to be absent"
            )
        for guard in transition.guards:
            if not isinstance(guard, Cel):
                raise SimulationProfileError(
                    f"implementation-free-v1 requires transition {transition.path} guards to be inline Cel"
                )
            _check_cel(guard, f"transition {transition.path} guard")
        for timer in transition.timers:
            if not isinstance(timer, Delay | Until):
                raise SimulationProfileError(
                    f"implementation-free-v1 requires transition {transition.path} timers to be Delay or Until"
                )
            value = timer.duration if isinstance(timer, Delay) else timer.instant
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise SimulationProfileError(
                    f"implementation-free-v1 requires transition {transition.path} {type(timer).__name__} "
                    f"value to be an exact non-boolean non-negative integer, got {value!r}"
                )
    for position, arc in enumerate(net.arcs):
        if isinstance(arc.weight, bool) or not isinstance(arc.weight, int) or arc.weight != 1:
            raise SimulationProfileError(
                f"implementation-free-v1 requires arc {position} weight to be exact non-boolean integer 1, "
                f"got {arc.weight!r}"
            )
        if arc.filter is not None and not isinstance(arc.filter, Cel):
            raise SimulationProfileError(f"implementation-free-v1 requires arc {position} filter to be inline Cel")
        if isinstance(arc.filter, Cel):
            _check_cel(arc.filter, f"arc {position} filter")
    for path in net.transitions:
        selecting = [
            arc
            for arc in net.arcs
            if arc.target == path and arc.source in net.places and arc.mode in (ArcMode.CONSUME, ArcMode.READ)
        ]
        if len(selecting) > 1:
            raise SimulationProfileError(
                f"implementation-free-v1 allows transition {path} at most one selecting input arc, "
                f"found {len(selecting)}"
            )
        if selecting and selecting[0].mode is not ArcMode.CONSUME:
            raise SimulationProfileError(
                f"implementation-free-v1 requires transition {path}'s selecting input arc to consume"
            )
        outputs = [arc for arc in net.arcs if arc.source == path and arc.target in net.places]
        if len(outputs) > 1:
            raise SimulationProfileError(
                f"implementation-free-v1 allows transition {path} at most one output arc, found {len(outputs)}"
            )
    if net.completion is not None and not isinstance(net.completion, Cel):
        raise SimulationProfileError("implementation-free-v1 requires completion to be inline Cel")
    if isinstance(net.completion, Cel):
        _check_cel(net.completion, "completion")

    try:
        projected_definition = definition(net)
        definition_size = _encoded_size(projected_definition)
    except (TypeError, ValueError) as error:
        raise SimulationProfileError(f"canonical definition must be strict JSON-faithful: {error}") from None
    if definition_size > MAX_DEFINITION_BYTES:
        raise SimulationProfileError(
            f"implementation-free-v1 canonical definition limit is {MAX_DEFINITION_BYTES} bytes, "
            f"found {definition_size}"
        )

    token_count = sum(len(tokens) for _, tokens in initial_marking)
    if token_count > MAX_INITIAL_TOKENS:
        raise SimulationProfileError(
            f"implementation-free-v1 initial token limit is {MAX_INITIAL_TOKENS}, found {token_count}"
        )
    queues: dict[NetPath, tuple[Token, ...]] = {}
    for place, tokens in initial_marking:
        if place not in net.places:
            raise SimulationProfileError(f"implementation-free-v1 initial marking names foreign place {place}")
        frozen_tokens = []
        for token in tokens:
            if type(token) is not Token:
                raise SimulationProfileError(
                    f"implementation-free-v1 requires every initial queue item to be exactly Token, got {token!r}"
                )
            if token.color is not None and (type(token.color) is not str or not token.color):
                raise SimulationProfileError(
                    f"implementation-free-v1 token color at {place} must be None or a nonempty exact str, "
                    f"got {token.color!r}"
                )
            expected = net.places[place].color
            if expected is not None and token.color != expected:
                raise SimulationProfileError(
                    f"implementation-free-v1 token color {token.color!r} does not match place {place} color {expected!r}"
                )
            data = _strict_detach(token.data, f"initial token data at {place}")
            frozen_tokens.append(Token(token.color, data))
        queues[NetPath(str(place))] = tuple(frozen_tokens)
    frozen_marking = Marking(queues)
    projected = project_marking(frozen_marking)
    payload_size = _encoded_size(projected)
    if payload_size > MAX_INITIAL_PAYLOAD_BYTES:
        raise SimulationProfileError(
            f"implementation-free-v1 initial token payload limit is {MAX_INITIAL_PAYLOAD_BYTES} bytes, "
            f"found {payload_size}"
        )
    initial_tokens = sum(len(tokens) for _, tokens in frozen_marking)
    maximum_incidence = max(
        (sum(arc.source == place and arc.target in net.transitions for arc in net.arcs) for place in net.places),
        default=0,
    )
    reachable_scan_bound = initial_tokens * maximum_incidence
    if reachable_scan_bound > MAX_CANDIDATE_OFFERS:
        raise SimulationProfileError(
            f"implementation-free-v1 reachable input-scan limit is {MAX_CANDIDATE_OFFERS}, "
            f"found bound {reachable_scan_bound} from {initial_tokens} initial tokens and maximum "
            f"place incidence {maximum_incidence}"
        )
    return projected, frozen_marking


def simulation_profile(built: BuiltNet) -> dict[str, object]:
    """Validate one fixed build and return its detached hosted-run profile."""
    _admit(built, Marking(), 1)
    projected_definition = definition(built.net)
    return {
        "format": "petrus-simulation-service-profile",
        "version": 1,
        "profile": "implementation-free-v1",
        "definition": projected_definition,
        "bounds": {
            "places": MAX_PLACES,
            "transitions": MAX_TRANSITIONS,
            "arcs": MAX_ARCS,
            "initial_tokens": MAX_INITIAL_TOKENS,
            "initial_payload_bytes": MAX_INITIAL_PAYLOAD_BYTES,
            "actions": MAX_ACTIONS,
            "retained_tokens": MAX_RETAINED_TOKENS,
            "retained_payload_bytes": MAX_RETAINED_PAYLOAD_BYTES,
            "history_records": MAX_HISTORY_RECORDS,
            "history_payload_bytes": MAX_HISTORY_PAYLOAD_BYTES,
            "result_bytes": MAX_RESULT_BYTES,
            "reachable_input_scans": MAX_CANDIDATE_OFFERS,
            "cel_bytes": MAX_CEL_BYTES,
            "definition_bytes": MAX_DEFINITION_BYTES,
            "request_body_bytes": MAX_REQUEST_BODY_BYTES,
            "connection_timeout_seconds": CONNECTION_TIMEOUT_SECONDS,
            "concurrent_simulations": 1,
        },
    }


def _input_scan_bound(built: BuiltNet, marking: Marking) -> int:
    """Bound every current input-arc queue scan without evaluating CEL."""
    net = built.net
    return sum(
        len(marking.place(arc.source)) for arc in net.arcs if arc.source in net.places and arc.target in net.transitions
    )


def _check_input_scans(built: BuiltNet, marking: Marking) -> None:
    scans = _input_scan_bound(built, marking)
    if scans > MAX_CANDIDATE_OFFERS:
        raise SimulationProfileError(
            f"implementation-free-v1 input-scan limit is {MAX_CANDIDATE_OFFERS} before advance, found {scans}"
        )


def _check_resources(engine: Engine) -> None:
    retained = sum(len(tokens) for _, tokens in engine.marking)
    if retained > MAX_RETAINED_TOKENS:
        raise SimulationProfileError(
            f"implementation-free-v1 retained token limit is {MAX_RETAINED_TOKENS}, found {retained}"
        )
    retained_payload = 0
    for place, tokens in engine.marking:
        retained_payload += len(str(place).encode())
        for token in tokens:
            retained_payload += _encoded_size({"color": token.color, "data": token.data})
            if retained_payload > MAX_RETAINED_PAYLOAD_BYTES:
                raise SimulationProfileError(
                    f"implementation-free-v1 retained token payload limit is "
                    f"{MAX_RETAINED_PAYLOAD_BYTES} bytes, found more than that limit"
                )
    records = len(engine.records)
    if records > MAX_HISTORY_RECORDS:
        raise SimulationProfileError(
            f"implementation-free-v1 History record limit is {MAX_HISTORY_RECORDS}, found {records}"
        )
    history_payload = 0
    for record in engine.records:
        history_payload += _encoded_size(encode_record(record))
        if history_payload > MAX_HISTORY_PAYLOAD_BYTES:
            raise SimulationProfileError(
                f"implementation-free-v1 History payload limit is {MAX_HISTORY_PAYLOAD_BYTES} bytes, "
                f"found more than that limit"
            )
    if engine.in_flight:
        raise SimulationProfileError("implementation-free-v1 forbids in-flight work")


def simulate(built: BuiltNet, initial_marking: Marking, *, max_actions: int) -> bytes:
    """Run one fresh bounded Engine and return canonical serialized result bytes."""
    projected_initial, frozen_marking = _admit(built, initial_marking, max_actions)
    history = InMemoryHistoryStore()
    engine: Engine | None = None
    try:
        engine = Engine.create(
            built.net,
            "simulation",
            history=history,
            dispatch=_ForbiddenDispatch(),
            marking=frozen_marking,
            clock=SimulatedClock(at=0),
            at=0,
        )
        _check_resources(engine)
        actions = 0
        reason = "action_limit"
        while actions < max_actions:
            _check_input_scans(built, engine.marking)
            outcome = engine.advance()
            if outcome.waiting:
                raise SimulationProfileError("implementation-free-v1 forbids waiting for external work")
            if not outcome.ready:
                reason = "rest"
                break
            actions += 1
            _check_resources(engine)
        snapshot = engine.snapshot()
        frontier = snapshot["frontier"]
        assert isinstance(frontier, int)
        result: dict[str, Any] = {
            "format": "petrus-simulation-result",
            "version": 1,
            "profile": "implementation-free-v1",
            "scenario": {"start_instant": 0, "initial_marking": projected_initial, "max_actions": max_actions},
            "outcome": {"actions_applied": actions, "reason": reason},
            "snapshot": snapshot,
            "history": engine.history_page(0, frontier),
        }
        assert result["snapshot"]["instance"] == result["history"]["instance"]
        assert result["snapshot"]["protocol"] == result["history"]["protocol"] == 1
        assert result["history"]["after"] == 0
        assert result["history"]["frontier"] == result["history"]["next"] == frontier
        records = cast(list[dict[str, Any]], result["history"]["records"])
        assert [entry["position"] for entry in records] == list(range(frontier))
        action_records = sum(entry["record"]["record"] in ("TimerMatured", "FiringCompleted") for entry in records)
        assert action_records == actions
        return _serialize_result(result)
    finally:
        if engine is not None:
            engine.close()


def _serialize_result(result: dict[str, object]) -> bytes:
    """Privately serialize the producer-owned result, enforcing 4 MiB."""
    try:
        payload = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    except (TypeError, ValueError) as error:
        raise SimulationProfileError(f"simulation result must be strict JSON-faithful: {error}") from None
    if len(payload) > MAX_RESULT_BYTES:
        raise SimulationProfileError(
            f"implementation-free-v1 serialized result limit is {MAX_RESULT_BYTES} bytes, found {len(payload)}"
        )
    return payload


__all__ = ["SimulationProfileError", "simulate", "simulation_profile"]
