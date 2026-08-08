"""
Operational telemetry: the wall-clock shadow of the semantic trace.

The event history is Impetus's SEMANTIC trace — every fact, replayable,
appended by the single writer. What it deliberately cannot say is how the run
FELT from the outside: how long a durable commit took, how long an activity
ran on its substrate, how many turns a drive loop spent, how much memory the
process held. This module is that second, operational trace — structured JSON
events emitted beside the appends, correlated to the semantic one by the same
fields the records carry (transition path, occurrence id, delivery identity,
virtual instant), and NEVER consulted by any semantics: no kernel decision,
replay, or projection reads a telemetry event, and telemetry failure must
never break a run.

The layering rule keeps the shadow honest [ES-020]:

- **This module is layer zero.** It imports no other Petrus module, so any
  module may import it; the pure core (``schema``/``marking``/
  ``enabledness``) stays uninstrumented — pure functions have no operational
  story to tell.
- **The kernel emits facts, not timings.** ``Instance``'s appending doors
  emit one event per committed fact batch, stamped with the VIRTUAL instant
  the record carries — the kernel never reads a wall clock, and its telemetry
  does not either.
- **Wall-clock spans live where wall-clock exists:** ``Engine``'s private
  coordination, the history backends, the Dispatch adapters
  and the worker — the layers that already own real time.

Impetus is a library, so the one sink is the stdlib logger
``impetus.telemetry`` — one JSON line per event at INFO, routed (or ignored)
by whatever handlers the host application configures. With no handler
configured, emission is a no-op string format away from free.

Usage, at a module that instruments::

    import petrus.telemetry as telemetry

    log = telemetry.get_logger("impetus")
    log.emit("thing_happened", occurrence=7)
    with log.span("commit", records=3) as span:
        span.increment("bytes", 512)

Tests observe emission with ``capture()``, which swaps the process-default
sink for a recorder::

    with telemetry.capture() as events:
        instance.step()
    assert events[0]["event"] == "impetus_firing_begun"
"""

from __future__ import annotations

# Python imports
import json
import logging
import os
import resource
import sys
import time
from contextlib import contextmanager
from typing import Any, Protocol

python_logger = logging.getLogger("impetus.telemetry")

# The verbosity ladder, least to most: "off" silences every emit; "facts" is
# the default — the per-fact door events and the driver spans; "profile" adds
# what costs something to gather (per-turn gauges: history size, queue
# depths, RSS); "debug" is reserved for per-candidate detail. A site that
# emits above "facts" gates itself with ``at_level``; the ladder is a
# process-wide setting (``set_level`` / $IMPETUS_TELEMETRY_LEVEL), matching
# the process-wide default sink.
LEVELS = ("off", "facts", "profile", "debug")


def _validated_level(level: str) -> str:
    if level not in LEVELS:
        raise ValueError(f"unknown telemetry level {level!r}: one of {', '.join(LEVELS)}")
    return level


_level = _validated_level(os.environ.get("IMPETUS_TELEMETRY_LEVEL", "facts"))


def level() -> str:
    """The process-wide telemetry level."""
    return _level


def set_level(level: str) -> None:
    """Set the process-wide telemetry level — one of ``LEVELS``, refused loud otherwise."""
    global _level
    _level = _validated_level(level)


def at_level(minimum: str) -> bool:
    """Whether the process-wide level admits emission gated at ``minimum`` — how a profile-grade site asks before gathering what only it would pay for."""
    return LEVELS.index(_level) >= LEVELS.index(_validated_level(minimum))


class EventSink(Protocol):
    """Where emitted payloads land: the stdlib-logging sink in production, a ``TelemetryRecorder`` under ``capture()``."""

    def info(self, payload: dict[str, Any]) -> None: ...


class JsonLogger:
    """The production sink: one JSON line per event through a stdlib logger — handlers are the host application's routing surface."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def info(self, payload: dict[str, Any]) -> None:
        # ts (wall-clock ms) is stamped only on the routed line — it is the
        # analysis-side time axis. The logical event (the recorder, the
        # tests) stays pure of wall clocks, exactly like the kernel.
        self.logger.info(json.dumps({**payload, "ts": int(time.time() * 1000)}, default=str))


class TelemetryRecorder(list):
    """The test sink: a plain list of emitted payloads, asserted on directly."""

    def info(self, payload: dict[str, Any]) -> None:
        self.append(payload)


_default_sink: EventSink = JsonLogger(python_logger)


class TelemetryLogger:
    """
    A namespaced emitter with bound context. ``bind`` returns a child whose
    context every later event inherits; a field bound twice fails loud — a
    silent overwrite would let two sites disagree about one fact's value.
    ``logger=None`` resolves the process-default sink AT EMIT, so a module's
    import-time ``log`` still lands in a test's ``capture()`` recorder.
    """

    def __init__(self, namespace: str, logger: EventSink | None = None, context: dict[str, Any] | None = None):
        self.namespace = namespace
        self.logger = logger
        self.context = context or {}

    def bind(self, **fields: Any) -> TelemetryLogger:
        return TelemetryLogger(namespace=self.namespace, logger=self.logger, context=self.merged_fields(fields))

    def emit(self, name: str, **fields: Any) -> None:
        if _level == "off":
            return
        sink = _default_sink if self.logger is None else self.logger
        payload = {"event": self.event_name(name), **self.merged_fields(fields)}
        try:
            sink.info(payload)
        except Exception:
            # Operational observation has no semantic authority. Even a host-
            # supplied sink that is damaged, unavailable, or misconfigured may
            # lose evidence, but it may never stop History or execution.
            pass

    def span(self, name: str, **fields: Any) -> Span:
        return Span(logger=self, name=name, fields=fields)

    def merged_fields(self, fields: dict[str, Any]) -> dict[str, Any]:
        duplicate_fields = set(self.context) & set(fields)
        if duplicate_fields:
            names = ", ".join(sorted(duplicate_fields))
            raise ValueError(f"Telemetry context already has field(s): {names}.")
        return {**self.context, **fields}

    def event_name(self, name: str) -> str:
        return f"{self.namespace}_{name}"


class Span:
    """
    A timed operation: ``{name}_started`` on entry, ``{name}_finished`` on
    exit with ``status``/``elapsed_ms`` (and ``error_type`` when the block
    raised — the exception always propagates; telemetry observes, never
    swallows). Between the two, ``milestone`` marks progress with elapsed
    time, ``set``/``increment``/``accumulate_time`` build the result fields
    the finish event carries.
    """

    def __init__(self, logger: TelemetryLogger, name: str, fields: dict[str, Any]):
        self.logger = logger.bind(**fields)
        self.name = name
        self.result: dict[str, Any] = {}
        self.started_at: float | None = None

    def __enter__(self) -> Span:
        self.started_at = time.perf_counter()
        self.logger.emit(f"{self.name}_started")
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        fields = {**self.result, "status": "success", "elapsed_ms": self.elapsed_ms()}
        if exc_type is not None:
            fields["status"] = "failed"
            fields["error_type"] = exc_type.__name__
        self.logger.emit(f"{self.name}_finished", **fields)
        return False

    def emit(self, name: str, **fields: Any) -> None:
        self.logger.emit(name, **fields)

    def span(self, name: str, **fields: Any) -> Span:
        return self.logger.span(name, **fields)

    def elapsed_ms(self) -> int:
        if self.started_at is None:
            raise RuntimeError("span has not started")
        return elapsed_ms(self.started_at)

    def milestone(self, name: str, **fields: Any) -> None:
        self.emit(f"{self.name}_{name}", **fields, elapsed_ms=self.elapsed_ms())

    @contextmanager
    def accumulate_time(self, field: str):
        started_at = time.perf_counter()
        try:
            yield
        finally:
            self.result[field] = self.result.get(field, 0) + elapsed_ms(started_at)

    def increment(self, field: str, amount: int = 1) -> None:
        self.result[field] = self.result.get(field, 0) + amount

    def set(self, **fields: Any) -> None:
        self.result.update(fields)


def elapsed_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)


def max_rss_mb() -> float:
    """The process's peak resident set, in MB — ``ru_maxrss`` is bytes on Darwin, KB elsewhere."""
    max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024**2 if sys.platform == "darwin" else 1024
    return round(max_rss / divisor, 1)


def current_rss_mb() -> float | None:
    """The current resident set from ``/proc/self/statm``, in MB — ``None`` where /proc does not exist (macOS): absent, never wrong."""
    try:
        with open("/proc/self/statm") as statm:
            resident_pages = int(statm.read().split()[1])
        return round(resident_pages * os.sysconf("SC_PAGE_SIZE") / 1024**2, 1)
    except OSError, ValueError, IndexError:
        return None


@contextmanager
def capture(recorder: TelemetryRecorder | None = None, level: str | None = None):
    """Swap the process-default sink for a recorder, restore on exit — how a test observes any module's import-time logger without injection. ``level`` temporarily sets the process-wide level for the block (e.g. ``capture(level="profile")`` to observe the gauges)."""
    global _default_sink, _level
    recorder = TelemetryRecorder() if recorder is None else recorder
    previous_sink, previous_level = _default_sink, _level
    _default_sink = recorder
    if level is not None:
        set_level(level)
    try:
        yield recorder
    finally:
        _default_sink, _level = previous_sink, previous_level


def get_logger(namespace: str, logger: EventSink | None = None) -> TelemetryLogger:
    return TelemetryLogger(namespace=namespace, logger=logger)
