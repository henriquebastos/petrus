"""Test/application assembly around the current Petrus runtime.

No semantic branch, retry, repair, or publication decision lives here; those are
all in the compiled net. This module assembles the current ``Engine`` over a
``JsonlHistoryStore`` and an ``InlineDispatch`` of typed fake Activities, drives
``Engine.advance()`` in a bounded loop, and extracts typed values from the
marking for assertions.

``FakeProviderLedger`` is imported read-only from v1: it is domain-free (it keys
attempts and results by operation id), so reusing it keeps this experiment's
provider-idempotency boundary literally the same object v1 and B measured.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from petrus.engine import Engine
from petrus.impetus.history import Record
from petrus.impetus.history_store.jsonl import JsonlHistoryStore
from petrus.impetus.petrinet import NetPath, Token
from petrus.impetus.scope import LifecycleScope
from petrus.motus.dispatch import InlineDispatch

from harness import FakeProviderLedger
from inet_lowering import CompiledFlow
from inet_tokens import (
    CIObserved,
    HeadObserved,
    Published,
    RepairLanded,
    RerunAccepted,
    from_data,
    to_data,
)

INSTANCE = "readiness-inscription"

__all__ = [
    "INSTANCE",
    "FakeProviderLedger",
    "create",
    "deliver_ci",
    "deliver_head",
    "drain",
    "fired_branches",
    "load",
    "value_at",
    "values_at",
]


@dataclass(frozen=True)
class _FakeActivity:
    """One ledger-backed fake provider endpoint behind the Activity protocol."""

    ledger: FakeProviderLedger
    produce: Callable[[dict[str, object]], dict[str, object]]

    def __call__(self, invocation, *, context) -> dict[str, object]:
        del context
        [payload] = cast("dict[str, dict[str, object]]", invocation.input).values()
        operation = cast(str, payload["operation"])
        return self.ledger.execute(operation, lambda: self.produce(payload))


def _rerun_result(payload: dict[str, object]) -> dict[str, object]:
    return to_data(RerunAccepted(cast(str, payload["operation"]), cast(str, payload["head"])))


def _repair_result(payload: dict[str, object]) -> dict[str, object]:
    head = cast(str, payload["head"])
    return to_data(RepairLanded(cast(str, payload["operation"]), head, head + "r"))


def _publish_result(payload: dict[str, object]) -> dict[str, object]:
    return to_data(
        Published(cast(str, payload["operation"]), cast(str, payload["head"]), cast(int, payload["generation"]))
    )


def _dispatch(ledger: FakeProviderLedger) -> InlineDispatch:
    return InlineDispatch(
        {
            "rerun": _FakeActivity(ledger, _rerun_result),
            "repair": _FakeActivity(ledger, _repair_result),
            "publish": _FakeActivity(ledger, _publish_result),
        }
    )


def _compose(door, compiled: CompiledFlow, history_path: Path | str, ledger: FakeProviderLedger, **extra) -> Engine:
    return door(
        compiled.built.net,
        INSTANCE,
        history=JsonlHistoryStore(history_path),
        dispatch=_dispatch(ledger),
        handlers=dict(compiled.handlers),
        guards=dict(compiled.guards),
        activities=tuple(definition.declaration for definition in compiled.activities),
        **extra,
    )


def create(compiled: CompiledFlow, history_path: Path | str, ledger: FakeProviderLedger, *, marking=None) -> Engine:
    """Create the one Instance over a fresh durable JSONL History."""
    initial = compiled.initial_marking if marking is None else marking
    return _compose(Engine.create, compiled, history_path, ledger, marking=initial)


def load(compiled: CompiledFlow, history_path: Path | str, ledger: FakeProviderLedger) -> Engine:
    """Reconstruct the live composition over the committed JSONL History."""
    return _compose(Engine.load, compiled, history_path, ledger)


def drain(engine: Engine, limit: int = 64):
    """Drive ``Engine.advance()`` until it rests; bounded, never semantic."""
    firings = []
    for _ in range(limit):
        outcome = engine.advance()
        firings.extend(outcome.firings)
        if not outcome.ready:
            return tuple(firings)
    raise RuntimeError(f"drain exceeded {limit} advances without coming to rest")


def _deliver(
    engine: Engine,
    compiled: CompiledFlow,
    name: str,
    event: object,
    *,
    identity: str,
    scope: LifecycleScope | str,
):
    binding = compiled.ingress[name]
    if isinstance(scope, LifecycleScope) and scope.name != binding.scope_name:
        raise ValueError(f"ingress {name!r} delivers under scope {binding.scope_name!r}, got {scope.name!r}")
    if not isinstance(event, binding.event_type):
        raise ValueError(f"ingress {name!r} delivers {binding.event_type.__name__}, got {event!r}")
    token = Token(binding.event_type.__name__, to_data(event))
    return engine.deliver(binding.source, token, identity=identity, scope=scope)


def deliver_head(
    engine: Engine,
    compiled: CompiledFlow,
    event: HeadObserved,
    *,
    identity: str,
    scope: LifecycleScope | str,
):
    if isinstance(scope, LifecycleScope) and event.generation != scope.generation:
        raise ValueError(
            f"head observation claims generation {event.generation} but is delivered to "
            f"exact scope generation {scope.generation}"
        )
    return _deliver(engine, compiled, "head", event, identity=identity, scope=scope)


def deliver_ci(
    engine: Engine,
    compiled: CompiledFlow,
    event: CIObserved,
    *,
    identity: str,
    scope: LifecycleScope | str,
):
    return _deliver(engine, compiled, "ci", event, identity=identity, scope=scope)


def values_at[T](engine: Engine, place: str, annotation: type[T]) -> tuple[T, ...]:
    """Decode every token at one place into its typed value."""
    return tuple(from_data(annotation, token.data) for token in engine.marking.place(NetPath(place)))


def value_at[T](engine: Engine, place: str, annotation: type[T]) -> T:
    """Decode exactly one token at one place, failing loud otherwise."""
    values = values_at(engine, place, annotation)
    if len(values) != 1:
        raise ValueError(f"expected exactly one {annotation.__name__} at {place}, found {len(values)}")
    return values[0]


def fired_branches(records: tuple[Record, ...] | list[Record], prefix: str = "decide.") -> tuple[str, ...]:
    """Every decision branch that fired, in order, named from canonical History alone."""
    from petrus.impetus.history import FiringCompleted

    return tuple(
        str(record.transition).removeprefix(prefix)
        for record in records
        if isinstance(record, FiringCompleted) and str(record.transition).startswith(prefix)
    )


def published(engine: Engine) -> Published:
    return value_at(engine, "terminal.published", Published)


def compiled_filters(compiled: CompiledFlow) -> dict:
    """Compile the net's inline ``Cel`` arc filters the way ``Instance`` does.

    ``candidates(...)`` outside a live Instance needs them explicitly; without
    them a filtered arc raises a missing-implementation error instead of
    admitting tokens.
    """
    from petrus.impetus.binding.cel import compile_filter
    from petrus.impetus.petrinet import Cel

    return {
        uri: compile_filter(declaration)
        for uri, declaration in compiled.built.net.filter_declarations.items()
        if isinstance(declaration, Cel)
    }
