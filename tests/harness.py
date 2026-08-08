"""
Golden-trace replay harness.

Adapts the oracle's fixture format (``spec/traces/*.json``) into the Impetus
kernel's native types and drives a :class:`Instance` step by step. The kernel
core never sees this format — the harness is the only place that knows the
oracle JSON schema, so ``src/petrus`` stays free of fixture concerns.

Supports flat nets, black and single-typed tokens, all three input arc modes at
any weight, and guards (each fixture-declared predicate is reimplemented here as
a kernel guard). It raises loudly on multi-part merged tokens (oracle-only), on
fixture handler bindings (no harness reimplementation — handler behavior is
oracle-divergent and covered by Impetus-native tests), and on any guard
predicate this file does not reimplement, so later slices extend it visibly
rather than mis-parsing.
"""

from __future__ import annotations

# Python imports
import json
from pathlib import Path
from typing import Any

# Internal imports
from petrus.impetus.petrinet import Binding, Guard
from petrus.impetus.history import replay_marking
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.instance import Instance, Status
from petrus.impetus.petrinet import Arc, ArcMode, Net, NetPath, Place, Transition

TRACES = Path(__file__).resolve().parent.parent / "spec" / "traces"

# Fixture arc-kind vocabulary -> Impetus arc mode. Output arcs carry no kind and
# default to CONSUME, whose mode is unused on the output side.
KIND_TO_MODE = {"normal": ArcMode.CONSUME, "read": ArcMode.READ, "inhibitor": ArcMode.INHIBIT}

# Reimplementations of the fixtures' declaratively described guard predicates
# ("so a foreign binding can reimplement it exactly"), keyed by predicate source.
PREDICATES = {
    "data.amount >= 100": lambda data: data["amount"] >= 100,
    "data.amount < 100": lambda data: data["amount"] < 100,
}


def load_fixture(name: str) -> dict:
    """Load a fixture JSON by stem (e.g. ``"passthrough_chain"``)."""
    return json.loads((TRACES / f"{name}.json").read_text())


def token_from_parts(parts: list[dict]) -> Token:
    """Decode the fixture token encoding (list of typed parts) into a Token."""
    if not parts:
        return Token.black()
    if len(parts) == 1:
        return Token(parts[0]["type"], parts[0]["data"])
    raise NotImplementedError("multi-part merged tokens are oracle-only (a handler must emit a single-typed token)")


def token_to_parts(token: Token) -> list[dict]:
    """Encode a Token back into the fixture token encoding, for comparison."""
    if token.is_black:
        return []
    return [{"type": token.color, "data": token.data}]


def build_net(spec: dict[str, Any]) -> Net:
    """Build an Impetus Net from a fixture's ``net`` object."""
    places = [Place(NetPath(name)) for name in spec["places"]]

    transitions = []
    for name, tdef in spec["transitions"].items():
        if tdef.get("handler"):
            raise NotImplementedError(
                f"transition {name!r}: fixture handler bindings have no harness reimplementation — "
                f"handler behavior is oracle-divergent, covered by Impetus-native tests"
            )
        guards = (tdef["guard"],) if tdef.get("guard") else ()
        transitions.append(Transition(NetPath(name), guards=guards))

    arcs = []
    for a in spec["arcs"]:
        kind = a.get("kind", "normal")
        if kind not in KIND_TO_MODE:
            raise NotImplementedError(f"arc kind {kind!r} is not supported")
        arcs.append(Arc(NetPath(a["source"]), NetPath(a["target"]), KIND_TO_MODE[kind], a.get("weight", 1)))

    return Net(places, transitions, arcs)


def build_guards(fixture: dict) -> dict[str, Guard]:
    """
    Kernel guards for a fixture's declared guard bindings, reimplementing each
    described predicate exactly. Raises loudly on a predicate this harness does
    not reimplement.
    """
    guards = {}
    for name, gdef in fixture["bindings"]["guards"].items():
        if gdef["predicate"] not in PREDICATES:
            raise NotImplementedError(
                f"guard {name!r}: predicate {gdef['predicate']!r} has no harness reimplementation"
            )
        guards[name] = typed_guard(gdef["paramType"], PREDICATES[gdef["predicate"]])
    return guards


def typed_guard(param_type: str, predicate) -> Guard:
    """
    A guard evaluating ``predicate`` over the data of the peeked token of color
    ``param_type`` — the oracle's guard-argument extraction, reimplemented. No
    matching peeked token raises ``TypeError``, which the kernel surfaces and
    reads as not-satisfied (the oracle read it silently as not-enabled).
    """

    def guard(binding: Binding) -> bool:
        for token in binding.peeked:
            if token.color == param_type:
                return predicate(token.data)
        raise TypeError(f"guard requires a {param_type} token among the peeked tokens")

    return guard


def build_marking(fixture: dict, spec: dict[str, Any]) -> Marking:
    """Initial marking: ``initial`` black counts overlaid by ``seedMarking``."""
    queues = {
        NetPath(name): (Token.black(),) * pdef.get("initial", 0)
        for name, pdef in spec["places"].items()
        if pdef.get("initial", 0)
    }
    for entry in fixture["seedMarking"]:
        queues[NetPath(entry["place"])] = tuple(token_from_parts(p) for p in entry["tokens"])
    return Marking(queues)


def expected_marking(sparse: dict[str, list]) -> Marking:
    """Build a Marking from a fixture's sparse ``markingAfter`` object."""
    return Marking({NetPath(name): tuple(token_from_parts(p) for p in queue) for name, queue in sparse.items()})


def names(paths) -> list[str]:
    """Sorted string names for enabled-set comparison."""
    return sorted(str(p) for p in paths)


def assert_status_maps_to_oracle_flags(instance: Instance, *, is_terminated: bool, is_awaiting: bool) -> None:
    """
    Map Impetus' four-valued status onto a fixture's oracle booleans.

    Precondition — the fixture declares no completion condition and has no
    source transitions, so no registration ever opens (true for the coincident
    replay set): the oracle's ``isTerminated`` is exactly Impetus quiescence,
    and ``isAwaiting`` is always false (Impetus never reaches AWAITING without
    an armed registration).
    """
    assert instance.is_quiescent is is_terminated
    assert (instance.status is Status.AWAITING) is is_awaiting


def replay(fixture: dict) -> Instance:
    """
    Drive a Instance through a fixture's recorded walk, asserting the replay
    contract at each step: the selected transition, the consumed tokens, the
    resulting marking, the enabled set, and the derived termination flags. Then
    re-derive the marking from recorded movements alone. Returns the quiesced
    instance.

    For Petrus-coincident fixtures only — divergent fixtures are covered by
    Impetus-native tests, never oracle replay (see spec/traces/README.md).
    """
    instance = Instance(build_net(fixture["net"]), build_marking(fixture, fixture["net"]), guards=build_guards(fixture))

    initial = fixture["initial"]
    assert names(instance.enabled_transitions()) == initial["enabled"]
    assert instance.marking == expected_marking(initial["marking"])
    assert_status_maps_to_oracle_flags(
        instance, is_terminated=initial["isTerminated"], is_awaiting=initial["isAwaiting"]
    )

    for step in fixture["walk"]:
        firing = instance.step()
        assert firing is not None, "expected a firing but the instance was quiescent"
        assert str(firing.transition) == step["transition"]
        assert [token_to_parts(t) for t in firing.consumed] == step["consumed"]
        # The oracle records one produced token deposited to all output places;
        # each Impetus per-arc deposit must carry that same token (replay contract
        # item 2). Coincident fixtures forward a single token, so all deposits match.
        assert all(token_to_parts(tok) == step["produced"] for _, tok in firing.produced)
        assert instance.marking == expected_marking(step["markingAfter"])
        assert names(instance.enabled_transitions()) == step["enabledAfter"]
        assert_status_maps_to_oracle_flags(instance, is_terminated=step["isTerminated"], is_awaiting=step["isAwaiting"])

    assert instance.step() is None, "walk exhausted but instance is not quiescent"
    terminal = fixture["terminal"]
    assert_status_maps_to_oracle_flags(
        instance, is_terminated=terminal["isTerminated"], is_awaiting=terminal["isAwaiting"]
    )
    assert replay_marking(instance.history) == instance.marking
    return instance
