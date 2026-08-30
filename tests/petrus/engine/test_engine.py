"""Provider-neutral one-Instance Engine composition."""

from __future__ import annotations

import inspect

import pytest

import petrus.engine as engine_module
from petrus.motus.activity import ActivityDeclaration, ActivityInvocation
from petrus.motus.dispatch import CancellationDisposition, InMemoryDispatch, InlineDispatch
from petrus.engine import Delivery, Engine, choose_conservative, choose_throughput
from petrus.impetus.history import (
    ActivityCompleted,
    ActivityRequested,
    CandidateSelected,
    ExternalEventDelivered,
    FiringCompleted,
    InstanceCreated,
    ScopeClosed,
    ScopeReset,
    ActivityTerminalQuarantined,
    TokensInitialized,
)
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.instance import Instance, Status
from petrus.impetus.petrinet import Arc, Delay, Marking, Net, NetPath, Place, Token, Transition
from petrus.impetus.selection import RoundRobin

A, B, T = NetPath("a"), NetPath("b"), NetPath("work")
SOURCE, OUTPUT = NetPath("source"), NetPath("output")


class Bridge:
    def __init__(self, activity: str = "activity"):
        self.activity = activity
        self.prepared = 0
        self.projected = 0

    def prepare(self, binding):
        self.prepared += 1
        return ActivityInvocation(self.activity, input=binding.tokens[0].data)

    def project(self, binding, result):
        self.projected += 1
        return {B: (Token("Done", result),)}


def activity_net() -> Net:
    return Net(
        places=[Place(A), Place(B)],
        transitions=[Transition(T, handler="bridge")],
        arcs=[Arc(A, T), Arc(T, B)],
    )


def source_net() -> Net:
    return Net(
        places=[Place(OUTPUT)],
        transitions=[Transition(SOURCE)],
        arcs=[Arc(SOURCE, OUTPUT)],
    )


def inline_dispatch() -> InlineDispatch:
    return InlineDispatch({"activity": lambda invocation, *, context: {"value": invocation.input}})


def advance_until_rest(engine: Engine):
    """Pump one-action Engine turns until it reports wait, sleep, or stop."""
    firings = []
    while True:
        outcome = engine.advance()
        firings.extend(outcome.firings)
        if not outcome.ready:
            return outcome.__class__(tuple(firings), outcome.waiting, next_maturation=outcome.next_maturation)


class TestNeutralEngineSurface:
    def test_engine_alone_owns_composed_source_delivery(self):
        assert "deliver" in Engine.__dict__
        assert "deliver" not in Instance.__dict__

    def test_engine_is_the_concrete_live_composition_with_only_universal_doors(self):
        assert not inspect.isabstract(Engine)
        assert {name for name in Engine.__dict__ if not name.startswith("_")} == {
            "accept_delivery",
            "advance",
            "active_scopes",
            "close",
            "close_scope",
            "complete_delivery",
            "create",
            "deliver",
            "history_page",
            "in_flight",
            "load",
            "marking",
            "net_document",
            "records",
            "reset_scope",
            "seal",
            "snapshot",
            "status",
            "open_scope",
            "wait",
        }
        assert not hasattr(Engine, "queue_for")
        with pytest.raises(TypeError, match=r"use Engine\.create\(\) or Engine\.load\(\)"):
            Engine()

    def test_engine_module_owns_configuration_outcome_and_policy_vocabulary(self):
        assert set(engine_module.__all__) == {
            "AcceptedDelivery",
            "AcceptDelivery",
            "AcceptResult",
            "Action",
            "AdvanceTime",
            "BeginCandidate",
            "Clock",
            "Delivery",
            "DriveOutcome",
            "DrivingPolicy",
            "Engine",
            "InFlightView",
            "Sensor",
            "SimulatedClock",
            "Snapshot",
            "Stop",
            "Wait",
            "choose_conservative",
            "choose_throughput",
        }
        assert "Coordinator" not in engine_module.__all__
        assert "Runner" not in engine_module.__all__

    def test_create_accepts_an_explicit_initial_semantic_instant_while_load_derives_it(self):
        history = InMemoryHistoryStore()
        created = Engine.create(source_net(), "real-time", history=history, dispatch=InMemoryDispatch(), at=17)

        assert created.records[0] == InstanceCreated("real-time", instant=17)
        created.close()

        loaded = Engine.load(source_net(), "real-time", history=history, dispatch=InMemoryDispatch())
        assert loaded.records == history.records
        loaded.close()

    def test_create_advance_close_and_load_preserve_one_canonical_history(self):
        history = InMemoryHistoryStore()
        handler = Bridge()
        engine = Engine.create(
            activity_net(),
            "neutral",
            history=history,
            dispatch=inline_dispatch(),
            marking=Marking({A: (Token("Input", 3),)}),
            handlers={"bridge": handler},
        )

        assert engine.records[:2] == (
            InstanceCreated("neutral"),
            TokensInitialized(A, (Token("Input", 3),)),
        )
        outcome = advance_until_rest(engine)
        assert outcome.waiting is False
        assert engine.marking == Marking({B: (Token("Done", {"value": 3}),)})
        assert engine.status is Status.TERMINATED
        records = engine.records
        engine.close()

        loaded_handler = Bridge()
        loaded = Engine.load(
            activity_net(),
            "neutral",
            history=history,
            dispatch=inline_dispatch(),
            handlers={"bridge": loaded_handler},
        )
        assert loaded.records == records
        assert loaded.marking == Marking({B: (Token("Done", {"value": 3}),)})
        assert loaded_handler.prepared == loaded_handler.projected == 0
        loaded.close()

    def test_advance_yields_after_each_whole_action(self):
        engine = Engine.create(
            activity_net(),
            "one-action",
            history=InMemoryHistoryStore(),
            dispatch=inline_dispatch(),
            marking=Marking({A: (Token("Input", 3),)}),
            handlers={"bridge": Bridge()},
        )

        begun = engine.advance()

        assert begun.ready is True
        assert begun.waiting is False
        assert len(engine.in_flight) == 1
        assert any(isinstance(record, ActivityRequested) for record in engine.records)
        assert not any(isinstance(record, ActivityCompleted) for record in engine.records)

        completed = engine.advance()

        assert completed.ready is True
        assert [firing.transition for firing in completed.firings] == [T]
        assert engine.marking == Marking({B: (Token("Done", {"value": 3}),)})

        stopped = engine.advance()

        assert stopped.ready is False
        assert stopped.waiting is False
        assert stopped.next_maturation is None
        engine.close()

    @pytest.mark.parametrize("policy", [choose_conservative, choose_throughput])
    def test_future_time_does_not_make_engine_hide_buffered_ingress(self, policy):
        class WallClock:
            def now(self):
                return 0

            def observe(self, instant):
                return None

        cursor = NetPath("cursor")
        tick = NetPath("tick")
        net = Net(
            places=[Place(cursor), Place(OUTPUT)],
            transitions=[Transition(tick, timers=(Delay(5),)), Transition(SOURCE)],
            arcs=[Arc(cursor, tick), Arc(tick, cursor), Arc(SOURCE, OUTPUT)],
        )
        parcels = iter(
            [
                (
                    Delivery(SOURCE, Token("External", 1), identity="evt-1"),
                    Delivery(SOURCE, Token("External", 2), identity="evt-2"),
                ),
            ]
        )
        engine = Engine.create(
            net,
            f"future-time-{policy.__name__}",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({cursor: (Token("Cursor"),)}),
            policy=policy,
            clock=WallClock(),
            sensor=lambda: next(parcels, ()),
        )

        first = engine.advance()
        second = engine.advance()

        assert [firing.transition for firing in first.firings + second.firings] == [SOURCE, SOURCE]
        assert second.ready is True
        assert engine.marking.place(OUTPUT) == (Token("External", 1), Token("External", 2))
        engine.close()


class TestLifecycleScopes:
    @staticmethod
    def net() -> Net:
        return Net(
            places=[Place(A), Place(B)],
            transitions=[Transition(SOURCE), Transition(T, handler="bridge")],
            arcs=[Arc(SOURCE, A), Arc(A, T), Arc(T, B)],
        )

    @staticmethod
    def create(history=None, dispatch=None) -> tuple[Engine, InMemoryDispatch]:
        custody = dispatch or InMemoryDispatch()
        return (
            Engine.create(
                TestLifecycleScopes.net(),
                "scoped-engine",
                history=history if history is not None else InMemoryHistoryStore(),
                dispatch=custody,
                handlers={"bridge": Bridge()},
            ),
            custody,
        )

    def test_close_commits_before_retiring_pending_dispatch_and_late_terminal_is_quarantined(self):
        engine, dispatch = self.create()
        scope = engine.open_scope("draft")
        engine.deliver(SOURCE, Token("Input", 3), identity="draft-3", scope=scope)
        assert engine.advance().ready is True
        [occurrence] = dispatch.pending

        closure = engine.close_scope(scope)

        assert closure.cancelled == (occurrence,)
        assert dispatch.pending == {}
        close_position = next(
            index for index, record in enumerate(engine.records, start=1) if isinstance(record, ScopeClosed)
        )
        assert dispatch._cancelled[occurrence].history_position == close_position
        dispatch.complete(occurrence, {"value": 3})
        engine.advance()
        assert isinstance(engine.records[-1], ActivityTerminalQuarantined)
        assert engine.records[-1].occurrence == occurrence

    def test_restart_acknowledges_exact_ended_terminal_redelivery_and_refuses_conflict(self):
        history = InMemoryHistoryStore()
        engine, dispatch = self.create(history=history)
        scope = engine.open_scope("draft")
        engine.deliver(SOURCE, Token("Input", 3), identity="draft-3", scope=scope)
        engine.advance()
        [occurrence] = dispatch.pending
        dispatch.complete(occurrence, {"value": 3})
        engine.advance()
        engine.close()

        class RedeliveryDispatch:
            def __init__(self):
                self.reports = [(occurrence, {"value": 3})]

            def dispatch(self, occurrence, invocation):
                raise AssertionError((occurrence, invocation))

            def collect(self):
                reports = tuple(self.reports)
                self.reports.clear()
                return reports

        redelivery = RedeliveryDispatch()
        resumed = Engine.load(
            self.net(),
            "scoped-engine",
            history=history,
            dispatch=redelivery,
            handlers={"bridge": Bridge()},
        )
        before = history.records

        resumed.advance()

        assert history.records == before
        redelivery.reports.append((occurrence, {"value": 4}))
        with pytest.raises(ValueError, match="different result.*operational conflict"):
            resumed.advance()

    def test_restart_acknowledges_exact_quarantined_terminal_and_refuses_conflict(self):
        history = InMemoryHistoryStore()
        engine, dispatch = self.create(history=history)
        scope = engine.open_scope("draft")
        engine.deliver(SOURCE, Token("Input", 3), identity="draft-3", scope=scope)
        engine.advance()
        [occurrence] = dispatch.pending
        engine.close_scope(scope)
        engine.close()

        class RedeliveryDispatch(InMemoryDispatch):
            def __init__(self):
                super().__init__()
                self.reports = [(occurrence, {"value": 3})]

            def collect(self):
                reports = tuple(self.reports)
                self.reports.clear()
                return reports

        redelivery = RedeliveryDispatch()
        resumed = Engine.load(
            self.net(),
            "scoped-engine",
            history=history,
            dispatch=redelivery,
            handlers={"bridge": Bridge()},
        )
        resumed.advance()
        before = history.records
        redelivery.reports.append((occurrence, {"value": 3}))

        resumed.advance()

        assert history.records == before
        redelivery.reports.append((occurrence, {"value": 4}))
        with pytest.raises(ValueError, match="conflicting terminal activity report"):
            resumed.advance()

    def test_reset_is_one_canonical_record_with_no_unscoped_generation_gap(self):
        engine, dispatch = self.create()
        first = engine.open_scope("draft")
        engine.deliver(SOURCE, Token("Input", 3), identity="draft-3", scope=first)
        engine.advance()
        before = len(engine.records)

        second = engine.reset_scope(first)

        assert second.name == first.name and second.generation == first.generation + 1
        assert engine.active_scopes == {"draft": second}
        assert len(engine.records) == before + 1
        assert isinstance(engine.records[-1], ScopeReset)
        assert dispatch.pending == {}

    def test_restart_repairs_a_committed_cancellation_instruction_idempotently(self):
        history = InMemoryHistoryStore()
        engine, _ = self.create(history=history)
        scope = engine.open_scope("draft")
        engine.deliver(SOURCE, Token("Input", 3), identity="draft-3", scope=scope)
        engine.advance()
        closure = engine.close_scope(scope)
        engine.close()

        class RecordingDispatch(InMemoryDispatch):
            def __init__(self):
                super().__init__()
                self.instructions = []

            def cancel(self, instruction):
                self.instructions.append(instruction)
                return super().cancel(instruction)

        repaired = RecordingDispatch()
        resumed = Engine.load(
            self.net(),
            "scoped-engine",
            history=history,
            dispatch=repaired,
            handlers={"bridge": Bridge()},
        )

        resumed.advance()

        assert [instruction.occurrence for instruction in repaired.instructions] == list(closure.cancelled)
        assert repaired.cancel(repaired.instructions[0]) is CancellationDisposition.ACKNOWLEDGED

    @pytest.mark.parametrize("operation", ["close", "reset"])
    def test_post_commit_cancellation_failure_poisoning_is_repaired_after_restart(self, operation):
        class FailingDispatch(InMemoryDispatch):
            def cancel(self, instruction):
                raise RuntimeError(f"injected {operation} cancellation failure")

        history = InMemoryHistoryStore()
        engine, dispatch = self.create(history=history, dispatch=FailingDispatch())
        scope = engine.open_scope("draft")
        engine.deliver(SOURCE, Token("Input", 3), identity="draft-3", scope=scope)
        engine.advance()
        [occurrence] = dispatch.pending

        with pytest.raises(RuntimeError, match=f"injected {operation} cancellation failure"):
            getattr(engine, f"{operation}_scope")(scope)

        terminal = history.records[-1]
        assert isinstance(terminal, ScopeClosed if operation == "close" else ScopeReset)
        assert terminal.cancelled == (occurrence,)

        class RecordingDispatch(InMemoryDispatch):
            def __init__(self):
                super().__init__()
                self.instructions = []

            def cancel(self, instruction):
                self.instructions.append(instruction)
                return super().cancel(instruction)

        repaired = RecordingDispatch()
        resumed = Engine.load(
            self.net(),
            "scoped-engine",
            history=history,
            dispatch=repaired,
            handlers={"bridge": Bridge()},
        )
        resumed.advance()

        assert [instruction.occurrence for instruction in repaired.instructions] == [occurrence]
        if operation == "reset":
            assert resumed.active_scopes == {"draft": terminal.opened}

    def test_scope_close_append_failure_never_notifies_dispatch(self):
        class RefusingHistory(InMemoryHistoryStore):
            def append(self, record):
                if isinstance(record, ScopeClosed):
                    raise OSError("close refused")
                super().append(record)

        class RecordingDispatch(InMemoryDispatch):
            instructions = []

            def cancel(self, instruction):
                self.instructions.append(instruction)
                return super().cancel(instruction)

        dispatch = RecordingDispatch()
        engine, _ = self.create(history=RefusingHistory(), dispatch=dispatch)
        scope = engine.open_scope("draft")
        engine.deliver(SOURCE, Token("Input", 3), identity="draft-3", scope=scope)
        engine.advance()

        with pytest.raises(OSError, match="close refused"):
            engine.close_scope(scope)

        assert dispatch.instructions == []

    def test_unsupported_dispatch_is_refused_before_canonical_close(self):
        class LegacyDispatch:
            def __init__(self):
                self.pending = []

            def dispatch(self, occurrence, invocation):
                self.pending.append((occurrence, invocation))

            def collect(self):
                return ()

        history = InMemoryHistoryStore()
        engine, _ = self.create(history=history, dispatch=LegacyDispatch())
        scope = engine.open_scope("draft")
        engine.deliver(SOURCE, Token("Input", 3), identity="draft-3", scope=scope)
        engine.advance()
        before = len(history)

        with pytest.raises(TypeError, match="does not implement.*cancellation"):
            engine.close_scope(scope)

        assert len(history) == before

    def test_sensor_delivery_preserves_exact_scope_provenance(self):
        holder = []
        engine = Engine.create(
            self.net(),
            "scoped-sensor",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            handlers={"bridge": Bridge()},
            sensor=lambda: tuple(holder),
        )
        scope = engine.open_scope("draft")
        holder.append(Delivery(SOURCE, Token("Input", 3), identity="sensor-3", scope=scope))

        engine.advance()

        assert engine.marking == Marking({A: (Token("Input", 3),)})
        engine.close_scope(scope)
        assert not engine.marking


class TestNeutralEngineSurfaceContinued:
    def test_direct_identifier_delivery_enables_a_separate_fetch_activity(self):
        fetched = NetPath("fetched")
        fetch = NetPath("fetch")

        class Fetch:
            def prepare(self, binding):
                return ActivityInvocation("fetch", input={"id": binding.tokens[0].data})

            def project(self, binding, result):
                return {fetched: (Token("Fetched", result),)}

        net = Net(
            places=[Place(OUTPUT), Place(fetched)],
            transitions=[Transition(SOURCE), Transition(fetch, handler="fetch")],
            arcs=[Arc(SOURCE, OUTPUT), Arc(OUTPUT, fetch), Arc(fetch, fetched)],
        )
        engine = Engine.create(
            net,
            "identifier-fetch",
            history=InMemoryHistoryStore(),
            dispatch=InlineDispatch({"fetch": lambda invocation, *, context: {"body": invocation.input["id"]}}),
            handlers={"fetch": Fetch()},
        )

        engine.deliver(SOURCE, Token("ExternalId", "evt-7"), identity="webhook-7")
        assert any(
            isinstance(record, ExternalEventDelivered) and record.identity == "webhook-7" for record in engine.records
        )

        assert engine.advance().ready is True
        assert engine.advance().ready is True
        assert engine.advance().ready is False
        assert engine.marking == Marking({fetched: (Token("Fetched", {"body": "evt-7"}),)})
        engine.close()

    def test_create_load_and_identity_preconditions_refuse_without_mutation(self):
        empty = InMemoryHistoryStore()
        with pytest.raises(ValueError, match="does not exist"):
            Engine.load(
                activity_net(), "missing", history=empty, dispatch=inline_dispatch(), handlers={"bridge": Bridge()}
            )
        assert empty.records == ()

        recorded = InMemoryHistoryStore()
        created = Engine.create(
            activity_net(), "recorded", history=recorded, dispatch=inline_dispatch(), handlers={"bridge": Bridge()}
        )
        before = recorded.records
        with pytest.raises(ValueError, match="already exists"):
            Engine.create(
                activity_net(), "recorded", history=recorded, dispatch=inline_dispatch(), handlers={"bridge": Bridge()}
            )
        with pytest.raises(ValueError, match="storage key and recorded identity must match exactly"):
            Engine.load(
                activity_net(), "different", history=recorded, dispatch=inline_dispatch(), handlers={"bridge": Bridge()}
            )
        assert recorded.records == before
        created.close()

    def test_activity_policy_resolution_belongs_to_engine_and_snapshots_declarations(self):
        declarations = [ActivityDeclaration("activity", heartbeat_timeout=7)]
        engine = Engine.create(
            activity_net(),
            "policy",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("Input", 3),)}),
            handlers={"bridge": Bridge()},
            activities=declarations,
            default_heartbeat_timeout=4,
        )
        declarations.clear()

        assert advance_until_rest(engine).waiting is True
        requested = next(record for record in engine.records if isinstance(record, ActivityRequested))
        assert requested.policy.heartbeat_timeout == 7
        engine.close()

    def test_wait_is_bounded_without_provider_notification_and_in_memory_work_can_be_pumped(self):
        history = InMemoryHistoryStore()
        dispatch = InMemoryDispatch()
        engine = Engine.create(
            activity_net(),
            "pumped",
            history=history,
            dispatch=dispatch,
            marking=Marking({A: (Token("Input", 3),)}),
            handlers={"bridge": Bridge()},
        )

        assert advance_until_rest(engine).waiting is True
        assert engine.wait(0) is False
        (occurrence,) = dispatch.pending
        dispatch.complete(occurrence, {"value": 3})
        assert advance_until_rest(engine).waiting is False
        assert engine.status is Status.TERMINATED
        engine.close()

    def test_deliver_seal_and_close_are_isolated_between_two_neutral_engines(self):
        left_history = InMemoryHistoryStore()
        right_history = InMemoryHistoryStore()
        left = Engine.create(source_net(), "left", history=left_history, dispatch=InMemoryDispatch())
        right = Engine.create(source_net(), "right", history=right_history, dispatch=InMemoryDispatch())

        left.deliver(SOURCE, Token("Input", "left"), identity="left-event")
        left.seal(SOURCE)
        assert left.marking == Marking({OUTPUT: (Token("Input", "left"),)})
        assert right.marking == Marking()
        assert left.records != right.records

        left.close()
        right.deliver(SOURCE, Token("Input", "right"), identity="right-event")
        assert right.marking == Marking({OUTPUT: (Token("Input", "right"),)})
        right.seal(SOURCE)
        right.close()

    def test_a_writing_failure_poisons_the_whole_engine_and_fresh_load_recovers(self):
        class RaisingDispatch(InMemoryDispatch):
            def dispatch(self, occurrence, invocation):
                raise RuntimeError("dispatch unavailable")

        history = InMemoryHistoryStore()
        engine = Engine.create(
            activity_net(),
            "poison",
            history=history,
            dispatch=RaisingDispatch(),
            marking=Marking({A: (Token("Input", 3),)}),
            handlers={"bridge": Bridge()},
        )
        with pytest.raises(RuntimeError, match="dispatch unavailable"):
            engine.advance()
        for door in (
            lambda: engine.advance(),
            lambda: engine.wait(0),
            lambda: engine.marking,
            lambda: engine.records,
        ):
            with pytest.raises(RuntimeError, match=r"fresh Engine\.load"):
                door()

        resumed = Engine.load(
            activity_net(), "poison", history=history, dispatch=inline_dispatch(), handlers={"bridge": Bridge()}
        )
        assert advance_until_rest(resumed).waiting is False
        assert resumed.marking == Marking({B: (Token("Done", {"value": 3}),)})
        resumed.close()

    def test_close_is_hosting_only_idempotent_and_hands_out_no_mutable_collaborator(self):
        history = InMemoryHistoryStore()
        engine = Engine.create(
            activity_net(), "closed", history=history, dispatch=inline_dispatch(), handlers={"bridge": Bridge()}
        )
        records = history.records
        for handle in ("coordinator", "dispatch", "instance", "history", "resources"):
            assert not hasattr(engine, handle)

        engine.close()
        engine.close()
        assert history.records == records
        for door in (
            lambda: engine.advance(),
            lambda: engine.wait(0),
            lambda: engine.marking,
            lambda: engine.records,
        ):
            with pytest.raises(RuntimeError, match="Engine is closed"):
                door()


class _TransactionalHistory:
    """Hermetic read-own-writes History with explicit commit/rollback fate."""

    def __init__(self):
        self.committed = []
        self.pending = []
        self.commits = 0
        self.refuse = set()
        self.rollbacks = 0

    @property
    def records(self):
        return tuple(self.committed + self.pending)

    def append(self, record):
        self.pending.append(record)

    def extend(self, records):
        self.pending.extend(records)

    def __iter__(self):
        return iter(self.records)

    def __len__(self):
        return len(self.records)

    def commit(self):
        self.commits += 1
        if self.commits in self.refuse:
            raise RuntimeError(f"commit {self.commits} refused")
        self.committed.extend(self.pending)
        self.pending.clear()

    def rollback(self):
        self.rollbacks += 1
        self.pending.clear()


def _joined_engine(
    history,
    dispatch,
    *,
    create=True,
    bridge=None,
    selection=RoundRobin((T,)),
    commit=None,
    release=lambda: None,
):
    return Engine._open(
        activity_net(),
        "joined-test",
        history=history,
        dispatch=dispatch,
        create=create,
        marking=Marking({A: (Token("Input", 3),)}) if create else None,
        handlers={"bridge": bridge or Bridge()},
        selection=selection,
        resources=engine_module._EngineResources(
            commit=commit or history.commit,
            rollback=history.rollback,
            release=release,
        ),
    )


class TestPrivateJoinedTransactionFate:
    """Engine's defining module owns its private joined-resource invariants."""

    def test_commit_refusal_rolls_back_and_never_installs_the_selection(self):
        history = _TransactionalHistory()
        history.refuse.add(3)  # construction, reconcile, then begin boundary
        released = []
        engine = _joined_engine(history, InMemoryDispatch(), release=lambda: released.append(True))

        with pytest.raises(RuntimeError, match="commit 3 refused"):
            engine.advance()

        assert not any(isinstance(record, CandidateSelected) for record in history.committed)
        assert history.pending == []
        assert history.rollbacks == 1
        assert released == [True]
        assert engine._coordinator._selection_state is None

    def test_dispatch_failure_rolls_back_the_uncommitted_begin_and_releases_hosting(self):
        class RaisingDispatch(InMemoryDispatch):
            def dispatch(self, occurrence, invocation):
                raise RuntimeError("dispatch failed")

        history = _TransactionalHistory()
        released = []
        engine = _joined_engine(history, RaisingDispatch(), release=lambda: released.append(True))

        with pytest.raises(RuntimeError, match="dispatch failed"):
            engine.advance()

        assert not any(isinstance(record, CandidateSelected) for record in history.committed)
        assert history.pending == []
        assert history.rollbacks == 1
        assert released == [True]
        assert engine._coordinator._selection_state is None

    def test_selection_installs_only_after_the_begin_commit_returns(self):
        history = _TransactionalHistory()
        observed = []
        holder = []

        def commit():
            if holder and any(isinstance(record, CandidateSelected) for record in history.pending):
                observed.append(holder[0]._coordinator._selection_state)
            history.commit()

        engine = _joined_engine(history, InMemoryDispatch(), commit=commit)
        holder.append(engine)

        assert engine.advance().ready is True

        assert observed == [None]
        assert engine._coordinator._selection_state == 0
        assert any(isinstance(record, CandidateSelected) for record in history.committed)

    def test_second_boundary_commit_failure_keeps_the_frozen_terminal_but_not_projection(self):
        history = _TransactionalHistory()
        dispatch = InMemoryDispatch()
        engine = _joined_engine(history, dispatch)
        assert engine.advance().ready is True
        dispatch.complete(1, {"value": 3})
        history.refuse.add(5)  # freeze is commit 4; projection boundary is commit 5

        with pytest.raises(RuntimeError, match="commit 5 refused"):
            engine.advance()

        assert sum(isinstance(record, ActivityCompleted) for record in history.committed) == 1
        assert not any(isinstance(record, FiringCompleted) for record in history.committed)
        assert history.pending == []

        resumed = _joined_engine(history, InMemoryDispatch(), create=False, selection=RoundRobin((T,)))
        outcome = resumed.advance()
        assert [firing.transition for firing in outcome.firings] == [T]
        assert resumed.marking == Marking({B: (Token("Done", {"value": 3}),)})

    def test_terminal_result_freezes_before_projection_failure_and_fresh_load_retries_projection_only(self):
        class BrokenProjection(Bridge):
            def project(self, binding, result):
                raise KeyError("projection bug")

        history = _TransactionalHistory()
        dispatch = InMemoryDispatch()
        engine = _joined_engine(history, dispatch, bridge=BrokenProjection())
        assert engine.advance().ready is True
        dispatch.complete(1, {"value": 3})

        with pytest.raises(KeyError, match="projection bug"):
            engine.advance()

        assert sum(isinstance(record, ActivityCompleted) for record in history.committed) == 1
        assert not any(isinstance(record, FiringCompleted) for record in history.committed)

        resumed = _joined_engine(history, InMemoryDispatch(), create=False)
        outcome = resumed.advance()
        assert [firing.transition for firing in outcome.firings] == [T]
        assert resumed.marking == Marking({B: (Token("Done", {"value": 3}),)})
