"""Best-effort operational Timeline for private Motus execution evidence."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

_SECRET = re.compile(
    r"(?:secret|token|password|credential|authorization|auth.?headers?|cookie|private.?key|process.?env|reasoning)",
    re.I,
)
_SECRET_VALUE = re.compile(
    r"(?i)(?:bearer\s+)[A-Za-z0-9._~+/=-]+|(?:github_pat_|gh[opsu]_|sk-(?:or-)?)[A-Za-z0-9_-]{8,}"
)
_CORRELATION_FIELDS = frozenset(
    {
        "activity",
        "artifact_digest",
        "attachment_id",
        "attempt",
        "claimant",
        "delivery_id",
        "effect_id",
        "epoch",
        "head",
        "history_position",
        "identity",
        "input_artifact_digest",
        "instance",
        "lease_id",
        "net",
        "occurrence",
        "operation",
        "operation_id",
        "pull_request",
        "queue",
        "repository",
        "request_id",
        "run_attempt",
        "run_id",
        "transition",
        "worker",
    }
)


@dataclass(frozen=True)
class TimelineEvent:
    event_id: str
    event_kind: str
    schema_version: int
    producer: str
    producer_sequence: int
    observed_at: datetime
    phase: str
    outcome: str
    correlation: Mapping[str, str]
    causal_refs: tuple[str, ...]
    metadata: Mapping[str, Any]
    retention_policy: str


def _redact(value: Any, key: str = "") -> Any:
    if _SECRET.search(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _SECRET_VALUE.sub("[REDACTED]", value)
    return value


def _phase(event_kind: str) -> str:
    for suffix, phase in (
        ("_started", "start"),
        ("_finished", "finish"),
        ("_accepted", "accept"),
        ("_claimed", "claim"),
        ("_heartbeat", "heartbeat"),
        ("_completed", "complete"),
        ("_failed", "fail"),
        ("_destroyed", "destroy"),
    ):
        if event_kind.endswith(suffix):
            return phase
    return "observe"


class Timeline:
    """Write-only, non-canonical observations; runtime code has no read operation."""

    def __init__(self, path: Path, *, retain: int | None = None) -> None:
        if retain is not None and (isinstance(retain, bool) or not isinstance(retain, int) or retain <= 0):
            raise ValueError("Timeline retention must be a positive integer or None")
        self.path = path
        self._retain = retain
        self._sequences: dict[str, int] = {}
        self._line_count = 0
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.chmod(0o600)
            lines = path.read_text().splitlines()
            self._line_count = len(lines)
            for line in lines:
                record = json.loads(line)
                producer = str(record["producer"])
                sequence = int(record["producer_sequence"])
                self._sequences[producer] = max(sequence, self._sequences.get(producer, 0))

    def observe(
        self,
        event_kind: str,
        *,
        producer: str,
        phase: str,
        outcome: str,
        correlation: Mapping[str, str],
        causal_refs: tuple[str, ...] = (),
        metadata: Mapping[str, Any] | None = None,
        retention_policy: str = "operational",
    ) -> TimelineEvent:
        """Mint one producer-ordered observation without granting it runtime authority."""

        with self._lock:
            sequence = self._sequences.get(producer, 0) + 1
            event = TimelineEvent(
                str(uuid4()),
                event_kind,
                1,
                producer,
                sequence,
                datetime.now(UTC),
                phase,
                outcome,
                dict(correlation),
                tuple(causal_refs),
                dict(metadata or {}),
                retention_policy,
            )
            self._append(event)
            self._sequences[producer] = sequence
            return event

    def append(self, event: TimelineEvent) -> None:
        with self._lock:
            expected = self._sequences.get(event.producer, 0) + 1
            if event.producer_sequence != expected:
                raise ValueError(
                    f"Timeline producer {event.producer!r} expected sequence {expected}, got {event.producer_sequence}"
                )
            self._append(event)
            self._sequences[event.producer] = event.producer_sequence

    def _append(self, event: TimelineEvent) -> None:
        if (
            event.schema_version != 1
            or not all(
                isinstance(value, str) and value
                for value in (event.event_id, event.event_kind, event.producer, event.phase, event.outcome)
            )
            or event.observed_at.tzinfo is None
        ):
            raise ValueError("Timeline event has an invalid envelope")
        record = asdict(event)
        record["observed_at"] = event.observed_at.isoformat()
        record["correlation"] = _redact(record["correlation"])
        record["metadata"] = _redact(record["metadata"])
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, encoded.encode())
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self._line_count += 1
        slack = 0 if self._retain is None or self._retain < 100 else max(100, self._retain // 10)
        threshold = None if self._retain is None else self._retain + slack
        if threshold is not None and self._line_count > threshold:
            retain = self._retain
            assert retain is not None
            lines = self.path.read_bytes().splitlines(keepends=True)[-retain:]
            file_descriptor, temporary = tempfile.mkstemp(dir=self.path.parent)
            try:
                with os.fdopen(file_descriptor, "wb") as stream:
                    stream.writelines(lines)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
                self.path.chmod(0o600)
                self._line_count = len(lines)
            finally:
                Path(temporary).unlink(missing_ok=True)

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)


class TelemetryTimelineHandler(logging.Handler):
    """Mirror stdlib-routed telemetry into Timeline without gaining authority."""

    def __init__(self, timeline: Timeline, *, producer: str = "petrus.telemetry") -> None:
        super().__init__(logging.INFO)
        self.timeline = timeline
        self.producer = producer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = json.loads(record.getMessage())
            if not isinstance(payload, dict) or not isinstance(payload.get("event"), str):
                return
            event_kind = payload.pop("event")
            payload.pop("ts", None)
            correlation = {
                key: str(value)
                for key, value in payload.items()
                if key in _CORRELATION_FIELDS and value is not None and str(value)
            }
            metadata = {key: value for key, value in payload.items() if key not in _CORRELATION_FIELDS}
            outcome = str(payload.get("outcome", payload.get("status", "observed")))
            self.timeline.observe(
                event_kind,
                producer=self.producer,
                phase=_phase(event_kind),
                outcome=outcome,
                correlation=correlation,
                metadata=metadata,
                retention_policy="bounded-operational",
            )
        except Exception:
            # Logging is only the shadow of History. A malformed payload or
            # failed Timeline sink must never escape logging into execution.
            return
