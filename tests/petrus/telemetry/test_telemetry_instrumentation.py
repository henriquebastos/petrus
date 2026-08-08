"""
Pins for the ES-020 instrumentation: the operational trace the kernel doors,
the driving loops, and the JSONL backend emit, observed through
``telemetry.capture()``.

The layering rule under test: the kernel emits one event per committed fact
batch, AFTER the append, stamped with the record's VIRTUAL instant (never a
wall clock); wall-clock spans appear only in the driving runtime and the
backends. Correlation with the semantic trace rides the same fields the
records carry — transition, occurrence, identity, instant.
"""

from __future__ import annotations

# Pip imports
import pytest

# Internal imports
import petrus.telemetry as telemetry
from petrus.motus.dispatch import InMemoryDispatch
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore, JsonlHistoryStore
from petrus.impetus.instance import Instance
from petrus.impetus.petrinet import Arc, Delay, Marking, Net, NetPath, Place, Token, Transition


def _fork_net():
    """a -> t -> {b, c}: one token fans out to two output places."""
    a, b, c, t = NetPath("a"), NetPath("b"), NetPath("c"), NetPath("t")
    return Net(
        places=[Place(a), Place(b), Place(c)],
        transitions=[Transition(t)],
        arcs=[Arc(a, t), Arc(t, b), Arc(t, c)],
    )


def _source_net():
    """s (source) -> b: an external event enters and lands on b."""
    s, b = NetPath("s"), NetPath("b")
    return Net(places=[Place(b)], transitions=[Transition(s)], arcs=[Arc(s, b)])


def _events(recorder, name):
    return [payload for payload in recorder if payload["event"] == name]


def _engine(net, instance: str, marking=None, handlers=None) -> Engine:
    return Engine.create(
        net,
        instance,
        history=InMemoryHistoryStore(),
        dispatch=InMemoryDispatch(),
        marking=marking,
        handlers=handlers,
    )


# ── the kernel doors: one event per committed fact batch ─────


class TestKernelDoorEvents:
    def test_construction_emits_instance_created(self):
        with telemetry.capture() as events:
            Instance(_fork_net(), Marking({NetPath("a"): (Token("X"),)}), at=5, instance_id="i-1")

        # records=2: the identity fact plus the one marked place.
        assert events == [
            {
                "event": "impetus_instance_created",
                "instance": "i-1",
                "places": 3,
                "transitions": 1,
                "records": 2,
                "instant": 5,
            },
        ]

    def test_step_emits_begun_then_completed_correlated_by_occurrence(self):
        instance = Instance(_fork_net(), Marking({NetPath("a"): (Token("X"),)}), instance_id="i-1")

        with telemetry.capture() as events:
            instance.step(at=7)

        begun, completed = events
        assert begun == {
            "event": "impetus_firing_begun",
            "instance": "i-1",
            "transition": "t",
            "occurrence": 1,
            "instant": 7,
            "impure": False,
        }
        assert completed["event"] == "impetus_firing_completed"
        assert completed["transition"] == "t"
        assert completed["occurrence"] == 1
        assert completed["instant"] == 7
        assert completed["records"] > 0

    def test_a_fruitless_step_emits_nothing(self):
        # The kernel's telemetry mirrors its append rule: a fruitless probe
        # appends nothing and is not a fact — so it emits nothing either.
        instance = Instance(_fork_net())

        with telemetry.capture() as events:
            assert instance.step() is None

        assert events == []

    def test_a_raising_handler_emits_firing_failed(self):
        def boom(binding, outputs):
            raise RuntimeError("handler broke")

        net = Net(
            places=[Place(NetPath("a")), Place(NetPath("b"))],
            transitions=[Transition(NetPath("t"), handler="boom")],
            arcs=[Arc(NetPath("a"), NetPath("t")), Arc(NetPath("t"), NetPath("b"))],
        )
        instance = Instance(net, Marking({NetPath("a"): (Token.black(),)}), handlers={"boom": boom})

        with telemetry.capture() as events:
            with pytest.raises(RuntimeError, match="handler broke"):
                instance.step()

        assert [payload["event"] for payload in events] == ["impetus_firing_begun", "impetus_firing_failed"]
        failed = events[1]
        assert failed["transition"] == "t"
        assert failed["occurrence"] == 1
        assert "RuntimeError" in failed["error"]

    def test_deliver_emits_acceptance_and_redelivery_answers_from_the_dedup(self):
        instance = Instance(_source_net(), instance_id="i-1")

        with telemetry.capture() as events:
            instance.deliver("s", Token("X"), identity="evt-1")
            instance.deliver("s", Token("X"), identity="evt-1")

        assert [payload["event"] for payload in events] == [
            "impetus_firing_begun",
            "impetus_delivery_accepted",
            "impetus_firing_completed",
            "impetus_delivery_redelivered",
        ]
        accepted = events[1]
        assert accepted == {
            "event": "impetus_delivery_accepted",
            "instance": "i-1",
            "source": "s",
            "identity": "evt-1",
            "occurrence": 1,
            "tokens": 1,
        }
        redelivered = events[3]
        assert redelivered == {
            "event": "impetus_delivery_redelivered",
            "instance": "i-1",
            "source": "s",
            "identity": "evt-1",
            "occurrence": 1,
        }

    def test_a_derived_identity_is_spelled_on_the_acceptance(self):
        instance = Instance(_source_net())

        with telemetry.capture() as events:
            instance.deliver("s", Token("X"))

        (accepted,) = _events(events, "impetus_delivery_accepted")
        assert accepted["identity"] == "occurrence-1"

    def test_seal_emits_the_closed_count(self):
        instance = Instance(_source_net(), instance_id="i-1")

        with telemetry.capture() as events:
            instance.seal("s", at=3)

        assert events == [
            {"event": "impetus_registrations_sealed", "instance": "i-1", "source": "s", "closed": 1, "instant": 3},
        ]

    def test_wake_emits_only_when_a_maturation_derives(self):
        net = Net(
            places=[Place(NetPath("a")), Place(NetPath("b"))],
            transitions=[Transition(NetPath("t"), timers=(Delay(10),))],
            arcs=[Arc(NetPath("a"), NetPath("t")), Arc(NetPath("t"), NetPath("b"))],
        )
        instance = Instance(net, Marking({NetPath("a"): (Token.black(),)}), instance_id="i-1")

        with telemetry.capture() as events:
            assert instance.wake(5) is None  # early: suppressed, no fact, no event
            instance.wake(10)

        assert events == [
            {"event": "impetus_timer_matured", "instance": "i-1", "maturation": 10, "instant": 10},
        ]

    def test_resume_emits_instance_resumed_under_the_recorded_identity(self):
        instance = Instance(_fork_net(), Marking({NetPath("a"): (Token("X"),)}), instance_id="i-1")
        instance.run()

        with telemetry.capture() as events:
            Instance.resume(_fork_net(), instance.history)

        assert events == [
            {
                "event": "impetus_instance_resumed",
                "instance": "i-1",
                "records": len(instance.history),
                "watermark": 0,
                "in_flight": 0,
            },
        ]


# ── the durable seam: one emit per commit, wall-clock priced ─


class TestJsonlCommitEvents:
    def test_every_durable_commit_emits_batch_size_bytes_and_latency(self, tmp_path):
        with telemetry.capture() as events:
            Instance(
                _fork_net(),
                Marking({NetPath("a"): (Token("X"),)}),
                history=JsonlHistoryStore(tmp_path / "history.jsonl"),
            ).run()

        commits = _events(events, "impetus_jsonl_commit")
        assert commits, "every append batch crosses the durable seam and emits"
        for commit in commits:
            assert commit["records"] > 0
            assert commit["bytes"] > 0
            assert commit["elapsed_ms"] >= 0


# ── the driving loops: wall-clock spans over the doors' facts ─


class TestEngineSpan:
    def test_advance_is_a_span_whose_counters_summarize_the_turn(self):
        engine = _engine(_fork_net(), "span", Marking({NetPath("a"): (Token("X"),)}))

        with telemetry.capture() as events:
            outcome = engine.advance()

        assert events[0]["event"] == "impetus_drive_started"
        finished = events[-1]
        assert finished["event"] == "impetus_drive_finished"
        assert finished["status"] == "success"
        assert finished["firings"] == len(outcome.firings) == 1
        assert finished["elapsed_ms"] >= 0
        # Between the span's edges: the kernel doors' own per-fact events.
        assert [payload["event"] for payload in events[1:-1]] == [
            "impetus_firing_begun",
            "impetus_firing_completed",
        ]

    def test_a_halting_advance_finishes_the_span_failed(self):
        def boom(binding, outputs):
            raise RuntimeError("handler broke")

        net = Net(
            places=[Place(NetPath("a")), Place(NetPath("b"))],
            transitions=[Transition(NetPath("t"), handler="boom")],
            arcs=[Arc(NetPath("a"), NetPath("t")), Arc(NetPath("t"), NetPath("b"))],
        )
        engine = _engine(net, "failed-span", Marking({NetPath("a"): (Token.black(),)}), {"boom": boom})

        with telemetry.capture() as events:
            with pytest.raises(RuntimeError, match="handler broke"):
                engine.advance()

        finished = events[-1]
        assert finished["event"] == "impetus_drive_finished"
        assert finished["status"] == "failed"
        assert finished["error_type"] == "RuntimeError"


class TestInstanceIdentity:
    def test_every_door_event_carries_the_minted_identity(self):
        # Identity is always on: an instance with no supplied id mints one,
        # and every event it emits is discriminable by it.
        instance = Instance(_fork_net(), Marking({NetPath("a"): (Token("X"),)}))

        with telemetry.capture() as events:
            instance.step()

        assert all(payload["instance"] == instance.instance_id for payload in events)

    def test_two_instances_mint_distinct_identities(self):
        first = Instance(_fork_net())
        second = Instance(_fork_net())
        assert first.instance_id != second.instance_id

    def test_the_driver_span_carries_the_instance_identity(self):
        engine = _engine(_fork_net(), "order-7", Marking({NetPath("a"): (Token("X"),)}))

        with telemetry.capture() as events:
            engine.advance()

        assert all(payload["instance"] == "order-7" for payload in events)

    def test_a_named_net_stamps_the_kind_beside_the_identity(self):
        net, marking = _fork_net(), Marking({NetPath("a"): (Token("X"),)})
        named = Net(
            places=list(net.places.values()),
            transitions=list(net.transitions.values()),
            arcs=net.arcs,
            name="order-fulfillment",
        )
        engine = _engine(named, "order-7", marking)

        with telemetry.capture() as events:
            engine.advance()

        assert all(payload["net"] == "order-fulfillment" for payload in events)
        assert all(payload["instance"] == "order-7" for payload in events)

    def test_resume_speaks_the_recorded_identity_not_a_resupplied_one(self):
        instance = Instance(_fork_net(), Marking({NetPath("a"): (Token("X"),)}), instance_id="order-7")

        resumed = Instance.resume(_fork_net(), instance.history)
        with telemetry.capture() as events:
            resumed.step()

        assert resumed.instance_id == "order-7"
        assert all(payload["instance"] == "order-7" for payload in events)

    def test_a_pre_identity_legacy_trace_resumes_unidentified(self):
        # A history from before the identity fact resumes without refusal and
        # emits without an instance field — absence is age, not corruption.
        instance = Instance(_fork_net(), Marking({NetPath("a"): (Token("X"),)}))
        legacy = InMemoryHistoryStore()
        legacy.extend(list(instance.history.records[1:]))  # strip InstanceCreated

        resumed = Instance.resume(_fork_net(), legacy)
        with telemetry.capture() as events:
            resumed.step()

        assert resumed.instance_id is None
        assert all("instance" not in payload for payload in events)


class TestPhaseTimings:
    def test_drive_finished_breaks_the_loop_down_by_phase(self):
        # The kernel is timed FROM its Engine: wall time stays outside the
        # semantic writer and the one-action turn reports each owned phase.
        engine = _engine(_fork_net(), "phase", Marking({NetPath("a"): (Token("X"),)}))

        with telemetry.capture() as events:
            engine.advance()

        finished = events[-1]
        assert finished["event"] == "impetus_drive_finished"
        for phase in ("observe_ms", "apply_ms", "begin_ms", "handler_ms", "commit_ms"):
            assert finished[phase] >= 0


class TestGauges:
    def test_profile_level_emits_state_gauges_each_firing(self):
        engine = _engine(_fork_net(), "gauges", Marking({NetPath("a"): (Token("X"),)}))

        with telemetry.capture(level="profile") as events:
            engine.advance()

        (gauges,) = _events(events, "impetus_gauges")
        assert gauges["history_records"] > 0
        assert gauges["places_occupied"] == 2  # the fan-out landed on b and c
        assert gauges["tokens_total"] == 2
        assert gauges["in_flight"] == 0
        assert gauges["max_rss_mb"] > 0

    def test_facts_level_gathers_no_gauges(self):
        engine = _engine(_fork_net(), "no-gauges", Marking({NetPath("a"): (Token("X"),)}))

        with telemetry.capture() as events:
            engine.advance()

        assert _events(events, "impetus_gauges") == []


class TestEngineOutcomeSpan:
    def test_drive_span_reports_actions_firings_and_waiting(self):
        engine = _engine(_fork_net(), "outcome-span", Marking({NetPath("a"): (Token("X"),)}))

        with telemetry.capture() as events:
            outcome = engine.advance()

        assert events[0]["event"] == "impetus_drive_started"
        finished = events[-1]
        assert finished["event"] == "impetus_drive_finished"
        assert finished["status"] == "success"
        assert finished["actions"] == 1  # the one BeginCandidate the policy chose
        assert finished["firings"] == len(outcome.firings) == 1
        assert finished["waiting"] is False
