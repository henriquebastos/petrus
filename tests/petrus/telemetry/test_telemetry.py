"""
Behavioral tests for the telemetry module itself — the emitter, the span, the
sinks, the capture swap. The kernel/driver instrumentation is tested in
``test_telemetry_instrumentation.py``.
"""

from __future__ import annotations

# Python imports
import json
import logging
from unittest import mock

# Pip imports
import pytest

# Internal imports
import petrus.telemetry as telemetry


def test_stdlib_logger_preserves_its_operational_identity():
    assert telemetry.python_logger.name == "impetus.telemetry"


def logged_payloads(caplog):
    return [json.loads(record.getMessage()) for record in caplog.records]


def make_logger():
    recorder = telemetry.TelemetryRecorder()
    return telemetry.get_logger("impetus", logger=recorder), recorder


# ── emit, bind, capture ──────────────────────────────────────


class TestTelemetryLoggerEmit:
    def test_json_logger_writes_namespaced_json_log_line_stamped_with_wall_clock_ts(self, caplog):
        # ts (wall-clock ms) rides only the routed line — the analysis-side
        # time axis; the logical event (the recorder) stays pure of it.
        log = telemetry.get_logger("impetus", logger=telemetry.JsonLogger(telemetry.python_logger))

        with caplog.at_level(logging.INFO, logger="impetus.telemetry"):
            log.emit("thing", occurrence=1)

        (payload,) = logged_payloads(caplog)
        assert isinstance(payload.pop("ts"), int)
        assert payload == {"event": "impetus_thing", "occurrence": 1}

    def test_json_logger_spells_non_json_values_as_strings(self, caplog):
        # The sink must never break a run: a payload value with no JSON
        # spelling (a NetPath, an exception, a Token) lands as its str form.
        log = telemetry.get_logger("impetus", logger=telemetry.JsonLogger(telemetry.python_logger))

        with caplog.at_level(logging.INFO, logger="impetus.telemetry"):
            log.emit("thing", error=ValueError("boom"))

        (payload,) = logged_payloads(caplog)
        assert payload["event"] == "impetus_thing"
        assert payload["error"] == "boom"

    def test_recorder_payloads_carry_no_wall_clock_ts(self):
        log, recorder = make_logger()

        log.emit("thing")

        assert recorder == [{"event": "impetus_thing"}]

    def test_injected_recorder_receives_bound_structured_payloads(self):
        log, recorder = make_logger()

        log.bind(instance="order-7").emit("thing", occurrence=1)

        assert recorder == [
            {"event": "impetus_thing", "instance": "order-7", "occurrence": 1},
        ]

    def test_capture_replaces_default_sink_for_existing_loggers(self):
        log = telemetry.get_logger("impetus")

        with telemetry.capture() as recorder:
            log.emit("thing", occurrence=1)

        assert recorder == [
            {"event": "impetus_thing", "occurrence": 1},
        ]

    def test_capture_restores_the_previous_sink_on_exit(self):
        log = telemetry.get_logger("impetus")
        outer = telemetry.TelemetryRecorder()

        with telemetry.capture(outer):
            with telemetry.capture() as inner:
                log.emit("thing")
            log.emit("after")

        assert [payload["event"] for payload in inner] == ["impetus_thing"]
        assert [payload["event"] for payload in outer] == ["impetus_after"]

    def test_capture_uses_provided_empty_recorder(self):
        log = telemetry.get_logger("impetus")
        recorder = telemetry.TelemetryRecorder()

        with telemetry.capture(recorder) as captured:
            log.emit("thing", occurrence=1)

        assert captured is recorder
        assert recorder == [
            {"event": "impetus_thing", "occurrence": 1},
        ]

    def test_bound_context_is_inherited_without_mutating_parent(self):
        log, recorder = make_logger()
        run_log = log.bind(run=7)

        run_log.emit("run_started")
        log.emit("unbound")

        assert recorder == [
            {"event": "impetus_run_started", "run": 7},
            {"event": "impetus_unbound"},
        ]

    def test_rebinding_existing_context_field_fails_loudly(self):
        log, _ = make_logger()
        log = log.bind(backend="jsonl")

        with pytest.raises(ValueError, match="backend"):
            log.bind(backend="postgres")

    def test_emit_cannot_override_bound_context_field(self):
        log, _ = make_logger()
        log = log.bind(backend="jsonl")

        with pytest.raises(ValueError, match="backend"):
            log.emit("thing", backend="postgres")

    def test_a_failing_sink_never_gates_execution(self):
        class BrokenSink:
            def info(self, payload):
                del payload
                raise OSError("observability unavailable")

        telemetry.get_logger("impetus", logger=BrokenSink()).emit("thing", occurrence=1)


# ── spans ────────────────────────────────────────────────────


class TestTelemetrySpan:
    def test_elapsed_time_before_span_entry_fails_with_lifecycle_error(self):
        log, _ = make_logger()

        with pytest.raises(RuntimeError, match="span has not started"):
            log.span("commit").elapsed_ms()

    def test_span_emits_started_and_finished_events_with_result_fields(self):
        log, recorder = make_logger()
        log = log.bind(backend="jsonl")

        with log.span("commit", batch=True) as span:
            span.set(records=2)

        assert recorder[0] == {
            "event": "impetus_commit_started",
            "backend": "jsonl",
            "batch": True,
        }
        assert recorder[1]["event"] == "impetus_commit_finished"
        assert recorder[1]["backend"] == "jsonl"
        assert recorder[1]["batch"] is True
        assert recorder[1]["records"] == 2
        assert recorder[1]["status"] == "success"
        assert recorder[1]["elapsed_ms"] >= 0

    def test_failed_span_emits_failed_status_and_reraises(self):
        log, recorder = make_logger()
        log = log.bind(backend="jsonl")

        with pytest.raises(RuntimeError, match="boom"):
            with log.span("commit") as span:
                span.set(records=1)
                raise RuntimeError("boom")

        finished = recorder[-1]
        assert finished["event"] == "impetus_commit_finished"
        assert finished["backend"] == "jsonl"
        assert finished["records"] == 1
        assert finished["status"] == "failed"
        assert finished["error_type"] == "RuntimeError"

    def test_child_span_inherits_parent_span_context(self):
        log, recorder = make_logger()
        log = log.bind(worker="worker-1")

        with log.span("drain", queues=2) as drain:
            with drain.span("activity", task="t-9") as activity:
                activity.set(outcome="completed")

        child_started = recorder[1]
        child_finished = recorder[2]
        assert child_started == {
            "event": "impetus_activity_started",
            "worker": "worker-1",
            "queues": 2,
            "task": "t-9",
        }
        assert child_finished["event"] == "impetus_activity_finished"
        assert child_finished["worker"] == "worker-1"
        assert child_finished["queues"] == 2
        assert child_finished["task"] == "t-9"
        assert child_finished["outcome"] == "completed"

    def test_span_emit_inherits_span_context(self):
        log, recorder = make_logger()
        log = log.bind(worker="worker-1")

        with log.span("drain", queues=2) as drain:
            drain.emit("drain_claimed", task="t-9")

        assert recorder[1] == {
            "event": "impetus_drain_claimed",
            "worker": "worker-1",
            "queues": 2,
            "task": "t-9",
        }

    def test_span_accumulate_time_sums_repeated_timing_fields(self, monkeypatch):
        clock_values = iter([0.0, 0.1, 0.3, 0.4, 0.7, 1.0])
        monkeypatch.setattr(telemetry.time, "perf_counter", lambda: next(clock_values))
        log, recorder = make_logger()

        with log.span("drive") as drive:
            with drive.accumulate_time("collect_ms"):
                pass
            with drive.accumulate_time("collect_ms"):
                pass

        finished = recorder[-1]
        assert finished["collect_ms"] == 500
        assert finished["elapsed_ms"] == 1000

    def test_span_accumulate_time_is_retained_when_block_fails(self, monkeypatch):
        clock_values = iter([0.0, 0.1, 0.4, 1.0])
        monkeypatch.setattr(telemetry.time, "perf_counter", lambda: next(clock_values))
        log, recorder = make_logger()

        with pytest.raises(RuntimeError, match="boom"):
            with log.span("drive") as drive:
                with drive.accumulate_time("collect_ms"):
                    raise RuntimeError("boom")

        finished = recorder[-1]
        assert finished["collect_ms"] == 300
        assert finished["elapsed_ms"] == 1000
        assert finished["status"] == "failed"

    def test_span_increments_counter_fields(self):
        log, recorder = make_logger()

        with log.span("drive") as drive:
            drive.increment("turns")
            drive.increment("turns", 2)

        assert recorder[-1]["turns"] == 3

    def test_span_milestone_emits_elapsed_time_since_span_started(self, monkeypatch):
        clock_values = iter([0.0, 0.25, 1.0])
        monkeypatch.setattr(telemetry.time, "perf_counter", lambda: next(clock_values))
        log, recorder = make_logger()

        with log.span("run") as run:
            run.milestone("first_firing", occurrence=1)

        assert recorder[1] == {
            "event": "impetus_run_first_firing",
            "occurrence": 1,
            "elapsed_ms": 250,
        }


# ── levels ───────────────────────────────────────────────────


class TestLevels:
    def test_default_level_is_facts(self):
        assert telemetry.level() == "facts"

    def test_unknown_level_is_refused_loud(self):
        with pytest.raises(ValueError, match="unknown telemetry level"):
            telemetry.set_level("verbose")

    def test_off_silences_every_emit(self):
        log = telemetry.get_logger("impetus")

        with telemetry.capture(level="off") as recorder:
            log.emit("thing")
            with log.span("run"):
                pass

        assert recorder == []

    def test_at_level_orders_the_ladder(self):
        with telemetry.capture(level="profile"):
            assert telemetry.at_level("facts")
            assert telemetry.at_level("profile")
            assert not telemetry.at_level("debug")

    def test_capture_restores_the_previous_level(self):
        with telemetry.capture(level="profile"):
            assert telemetry.level() == "profile"
        assert telemetry.level() == "facts"


# ── memory helpers ───────────────────────────────────────────


class TestMaxRss:
    def test_reports_positive_megabytes(self):
        assert telemetry.max_rss_mb() > 0


class TestCurrentRss:
    def test_parses_resident_pages_from_statm(self):
        # /proc/self/statm: size resident shared text lib data dt (in pages).
        # resident=262144 pages * 4096 B / 1024**2 = 1024.0 MB
        statm = "300000 262144 5000 100 0 50000 0"
        with mock.patch("builtins.open", mock.mock_open(read_data=statm)):
            with mock.patch.object(telemetry.os, "sysconf", return_value=4096):
                assert telemetry.current_rss_mb() == 1024.0

    def test_returns_none_when_statm_unavailable(self):
        # No /proc (macOS) or any read error -> None, never raises.
        with mock.patch("builtins.open", side_effect=OSError):
            assert telemetry.current_rss_mb() is None
