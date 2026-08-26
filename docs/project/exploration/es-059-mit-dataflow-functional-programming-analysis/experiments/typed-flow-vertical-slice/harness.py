"""Test/application assembly around the current Petrus runtime.

This module contains no semantic branch, retry, repair, or publication
decision; those live in the compiled Net. It only assembles the current
``Engine`` over a ``JsonlHistoryStore`` and an ``InlineDispatch`` of typed
fake Activities, drives ``Engine.advance()`` in a bounded loop, and extracts
typed values from the marking for assertions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from petrus.engine import Engine
from petrus.impetus.history_store.jsonl import JsonlHistoryStore
from petrus.impetus.petrinet import NetPath, Token
from petrus.impetus.scope import LifecycleScope
from petrus.motus.dispatch import InlineDispatch

from domain import (
    CIObserved,
    HeadObserved,
    PublishAcknowledged,
    RepairLanded,
    RerunAccepted,
    from_data,
    to_data,
)
from lowering import CompiledFlow

INSTANCE = "readiness-slice"


class FakeProviderLedger:
    """The simulated external provider's idempotency boundary.

    Not canonical workflow state: it counts delivery attempts per operation id
    and answers an already-seen operation with the same recorded result. It is
    supplied independently of the Engine so a reconstructed runtime meets the
    same provider.
    """

    def __init__(self) -> None:
        self.attempts: dict[str, int] = {}
        self.results: dict[str, dict[str, object]] = {}

    def execute(self, operation: str, produce: Callable[[], dict[str, object]]) -> dict[str, object]:
        self.attempts[operation] = self.attempts.get(operation, 0) + 1
        if operation not in self.results:
            self.results[operation] = produce()
        return self.results[operation]

    def attempts_for(self, operation: str) -> int:
        return self.attempts.get(operation, 0)


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
        PublishAcknowledged(
            cast(str, payload["operation"]), cast(str, payload["head"]), cast(int, payload["generation"])
        )
    )


def _dispatch(ledger: FakeProviderLedger) -> InlineDispatch:
    return InlineDispatch(
        {
            "rerun": _FakeActivity(ledger, _rerun_result),
            "repair": _FakeActivity(ledger, _repair_result),
            "publish": _FakeActivity(ledger, _publish_result),
        }
    )


def _compose(
    door,
    compiled: CompiledFlow,
    history_path: Path | str,
    ledger: FakeProviderLedger,
    **extra,
) -> Engine:
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


def create(
    compiled: CompiledFlow,
    history_path: Path | str,
    ledger: FakeProviderLedger,
    *,
    marking=None,
) -> Engine:
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
    """Decode every token at one place into its typed domain value."""
    return tuple(from_data(annotation, token.data) for token in engine.marking.place(NetPath(place)))


def value_at[T](engine: Engine, place: str, annotation: type[T]) -> T:
    """Decode exactly one token at one place, failing loud otherwise."""
    values = values_at(engine, place, annotation)
    if len(values) != 1:
        raise ValueError(f"expected exactly one {annotation.__name__} at {place}, found {len(values)}")
    return values[0]
