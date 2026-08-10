"""
Behavioral tests for the asynchronous coordinator — the session-3 drive loop
made real [ES-012 session 3, §Asynchronous coordination and composable
policy]: dispatch acknowledgement and activity completion are different
EVENTS in one deterministic loop, never different threads. The coordinator
observes a snapshot, computes the invariant-preserving action vocabulary
(``AcceptResult``, ``AcceptDelivery``, ``BeginCandidate``, ``AdvanceTime``,
``Wait``, ``Stop``), a driving policy chooses one action, and the coordinator
— the only component allowed to — applies it against the single writer.

Two policies ship: the conservative default serializes activity advancement
(commit each arrived result before anything else, one candidate at a time,
candidates before time before sensed ingress), and the throughput policy is
the concurrency demonstrator — it begins every structurally independent
candidate before accepting results, and skips a candidate whose consumed
selections collide by value with an in-flight occurrence's (value-aliasing:
the offered twin of a spent selection is evidence the policy cannot tell
apart, so it waits for results instead). Policies need not replay
deterministically: ``CandidateSelected`` records the committed choice, and
replay reconstructs that fact rather than rerunning the policy [session 3].

Reconcile-then-drive closes session-3 gap 4: on start, before any new
candidate, the coordinator redispatches every in-flight invocation without a
frozen result (never re-running ``prepare``), completes each
projection-pending occurrence by projection alone (never re-invoking the
activity), and drives pure in-flight occurrences to terminal.
"""

from __future__ import annotations

# Pip imports
import pytest

# Internal imports
from petrus.engine import (
    AcceptDelivery,
    AcceptResult,
    AdvanceTime,
    BeginCandidate,
    Delivery,
    DriveOutcome,
    Engine,
    InFlightView,
    SimulatedClock,
    Snapshot,
    Stop,
    Wait,
    choose_conservative,
    choose_throughput,
)
from petrus.motus.activity import ActivityFailure, ActivityInvocation
from petrus.impetus.binding import HandlerResult
from petrus.motus.dispatch import InlineDispatch, InMemoryDispatch
from petrus.impetus.history import (
    ActivityCompleted,
    ActivityFailed,
    ActivityRequested,
    CandidateSelected,
    DeliveryRegistration,
    ExternalEventDelivered,
    FiringFailed,
    TimerMatured,
)
from petrus.impetus.history.codec import encode_record
from petrus.impetus.history_store import InMemoryHistoryStore, JsonlHistoryStore
from petrus.impetus.instance import Instance
from petrus.impetus.petrinet import Arc, Delay, Marking, Net, NetPath, Place, Token, Transition
from petrus.impetus.selection import First, Priority, RoundRobin, SelectionPipeline

A1, T1, B1 = NetPath("a1"), NetPath("t1"), NetPath("b1")
A2, T2, B2 = NetPath("a2"), NetPath("t2"), NetPath("b2")
A, T, B, SRC = NetPath("a"), NetPath("t"), NetPath("b"), NetPath("src")


def _begin(binding):
    return BeginCandidate(binding, First().propose((binding,), None))


class Bridge:
    """A minimal counting ActivityHandler: prepare names its activity off the binding's first token, project deposits the result to one place."""

    def __init__(self, activity: str, out: NetPath):
        self.activity = activity
        self.out = out
        self.prepared = 0
        self.projected = 0

    def prepare(self, binding) -> ActivityInvocation:
        self.prepared += 1
        return ActivityInvocation(self.activity, input=binding.tokens[0].data)

    def project(self, binding, result):
        self.projected += 1
        return {self.out: (Token("Done", result),)}


def _independent_net() -> Net:
    """a1 -> t1 -> b1 and a2 -> t2 -> b2: two structurally independent impure transitions."""
    return Net(
        places=[Place(A1), Place(B1), Place(A2), Place(B2)],
        transitions=[Transition(T1, handler="one"), Transition(T2, handler="two")],
        arcs=[Arc(A1, T1), Arc(T1, B1), Arc(A2, T2), Arc(T2, B2)],
    )


def _independent_instance(history=None):
    handlers = {"one": Bridge("work_one", B1), "two": Bridge("work_two", B2)}
    marking = Marking({A1: (Token("X", {"n": 1}),), A2: (Token("Y", {"n": 2}),)})
    return Instance(_independent_net(), marking, handlers=handlers, history=history), handlers


def _activity_net(handler: str | None = "charge") -> Net:
    """a -> t (activity-handled) -> b."""
    return Net(
        places=[Place(A), Place(B)],
        transitions=[Transition(T, handler=handler)],
        arcs=[Arc(A, T), Arc(T, B)],
    )


# ── the adapter contract ─────────────────────────────────────


class TestInMemoryDispatch:
    def test_dispatch_acknowledges_and_the_invocation_waits_in_the_pool(self):
        pool = InMemoryDispatch()
        invocation = ActivityInvocation("work", input=1, correlation="c", idempotency="i")

        pool.dispatch(7, invocation)

        assert pool.pending == {7: invocation}
        assert pool.collect() == ()  # dispatched, not completed: different events

    def test_completions_collect_in_completion_order_and_drain(self):
        pool = InMemoryDispatch()
        pool.dispatch(1, ActivityInvocation("work", correlation="c", idempotency="i"))
        pool.dispatch(2, ActivityInvocation("work", correlation="c2", idempotency="i2"))

        pool.complete(2, {"ok": True})
        pool.complete(1, {"ok": False})

        assert pool.collect() == ((2, {"ok": True}), (1, {"ok": False}))
        assert pool.collect() == ()  # drained
        assert pool.pending == {}

    def test_fail_completes_with_an_activity_failure(self):
        pool = InMemoryDispatch()
        pool.dispatch(1, ActivityInvocation("work", correlation="c", idempotency="i"))

        pool.fail(1, "boom")

        assert pool.collect() == ((1, ActivityFailure("boom")),)

    def test_completing_an_undispatched_occurrence_fails_loud(self):
        with pytest.raises(ValueError, match="not pending"):
            InMemoryDispatch().complete(9, {})

    def test_a_second_dispatch_of_a_pending_occurrence_fails_loud(self):
        pool = InMemoryDispatch()
        invocation = ActivityInvocation("work", correlation="c", idempotency="i")
        pool.dispatch(1, invocation)

        with pytest.raises(ValueError, match="already pending"):
            pool.dispatch(1, invocation)


class TestInlineDispatch:
    def test_dispatch_executes_immediately_and_completion_waits_for_collect(self):
        # InlineDispatch expressed as dispatch + immediate completion: even
        # when execution is inline, acknowledgement and completion stay
        # different events.
        adapter = InlineDispatch({"work": lambda invocation, *, context: {"echo": invocation.input}})

        adapter.dispatch(1, ActivityInvocation("work", input=5, correlation="c", idempotency="i"))

        assert adapter.collect() == ((1, {"echo": 5}),)
        assert adapter.collect() == ()

    def test_a_raising_runtime_completes_with_an_activity_failure(self):
        def explode(invocation, *, context):
            raise RuntimeError("provider down")

        adapter = InlineDispatch({"work": explode})
        adapter.dispatch(1, ActivityInvocation("work", correlation="c", idempotency="i"))

        assert adapter.collect() == ((1, ActivityFailure("provider down", kind="RuntimeError", retryable=True)),)


# ── the two policies ─────────────────────────────────────────


def _binding_of(instance, index: int = 0):
    return instance.candidates()[index]


def _views(instance) -> tuple[InFlightView, ...]:
    """The detached in-flight views a coordinator would hand the policy — built the same way, from writer state."""
    return tuple(
        InFlightView(o.id, o.binding.transition, o.binding.consumed, o.invocation is not None)
        for o in instance.in_flight
    )


def _drive_until_rest(engine: Engine) -> DriveOutcome:
    """Test host: pump one-action turns until Engine reports wait, sleep, or stop."""
    firings = []
    while True:
        outcome = engine.advance()
        firings.extend(outcome.firings)
        if not outcome.ready:
            return DriveOutcome(tuple(firings), outcome.waiting, next_maturation=outcome.next_maturation)


def _independent_engine(
    dispatch,
    *,
    history=None,
    policy=choose_conservative,
    selection=SelectionPipeline(),
    clock=None,
    sensor=None,
):
    handlers = {"one": Bridge("work_one", B1), "two": Bridge("work_two", B2)}
    store = history if history is not None else InMemoryHistoryStore()
    engine = Engine.create(
        _independent_net(),
        "coordinator-test",
        history=store,
        dispatch=dispatch,
        marking=Marking({A1: (Token("X", {"n": 1}),), A2: (Token("Y", {"n": 2}),)}),
        handlers=handlers,
        policy=policy,
        selection=selection,
        clock=clock,
        sensor=sensor,
    )
    return engine, handlers, store


class TestConservativePolicy:
    def test_an_arrived_result_outranks_everything(self):
        instance, _ = _independent_instance()
        binding = _binding_of(instance)
        occurrence = instance.begin(binding)
        accept = AcceptResult(occurrence.id, {"ok": True})
        snapshot = Snapshot(
            (accept, _begin(_binding_of(instance)), AdvanceTime(9), Wait(), Stop()),
            _views(instance),
        )

        assert choose_conservative(snapshot) == accept

    def test_one_candidate_at_a_time_waits_on_an_outstanding_result(self):
        # Conservative semantics never have a second candidate begun
        # while a dispatched result is outstanding, so the conservative
        # policy waits rather than beginning independent work.
        instance, _ = _independent_instance()
        occurrence = instance.begin(_binding_of(instance))
        assert occurrence is not None
        snapshot = Snapshot((_begin(_binding_of(instance)), Wait(), Stop()), _views(instance))

        assert choose_conservative(snapshot) == Wait()

    def test_ingress_interrupts_once_then_candidate_and_time_make_progress(self):
        instance, _ = _independent_instance()
        begin = _begin(_binding_of(instance))
        deliver = AcceptDelivery(Delivery(SRC, Token("X")))

        assert choose_conservative(Snapshot((begin, AdvanceTime(9), deliver, Stop()), ())) == deliver
        assert choose_conservative(Snapshot((begin, deliver, Stop()), (), previous=deliver)) == begin
        assert choose_conservative(Snapshot((AdvanceTime(9), deliver, Stop()), (), previous=deliver)) == AdvanceTime(9)
        assert choose_conservative(Snapshot((deliver, Stop()), ())) == deliver
        assert choose_conservative(Snapshot((Stop(),), ())) == Stop()

    def test_wait_does_not_block_buffered_ingress_even_after_a_delivery(self):
        deliver = AcceptDelivery(Delivery(SRC, Token("X")))

        snapshot = Snapshot((deliver, Wait(), Stop()), (), previous=deliver)

        assert choose_conservative(snapshot) == deliver


class TestThroughputPolicy:
    def test_begins_independent_work_before_accepting_results(self):
        instance, _ = _independent_instance()
        occurrence = instance.begin(_binding_of(instance))
        begin = _begin(_binding_of(instance))  # t2: structurally independent of in-flight t1
        snapshot = Snapshot((AcceptResult(occurrence.id, {"ok": True}), begin, Wait(), Stop()), _views(instance))

        assert choose_throughput(snapshot) == begin

    def test_skips_a_candidate_whose_selections_collide_with_in_flight_work(self):
        # Value-aliasing under concurrency [DS1 pinned invariant, DS2
        # acceptance]: with two identical candidates sharing a token, the
        # policy that began the first cannot tell the offered twin from the
        # spent selection — it skips the collision and waits for results.
        dup, other = Token("X", {"n": 1}), Token("Y")
        net = Net(
            places=[Place(A), Place(B)],
            transitions=[Transition(T, handler="charge")],
            arcs=[Arc(A, T, weight=2), Arc(T, B)],
        )
        instance = Instance(net, Marking({A: (dup, dup, other)}), handlers={"charge": Bridge("work", B)})
        bindings = instance.candidates()
        assert bindings[1] == bindings[2]  # the aliased pair, sharing `other`
        instance.begin(bindings[1])
        snapshot = Snapshot((_begin(bindings[2]), Wait(), Stop()), _views(instance))

        assert choose_throughput(snapshot) == Wait()

    def test_ingress_interrupts_once_then_existing_candidate_precedence_resumes(self):
        instance, _ = _independent_instance()
        begin = _begin(_binding_of(instance))
        deliver = AcceptDelivery(Delivery(SRC, Token("X")))
        result = AcceptResult(1, {"ok": True})

        assert choose_throughput(Snapshot((result, begin, deliver, Stop()), ())) == deliver
        assert choose_throughput(Snapshot((result, begin, deliver, Stop()), (), previous=deliver)) == begin

    def test_a_hand_forced_second_begin_of_the_aliased_twin_fails_loud(self):
        # The DS1 invariant exercised under concurrency: the first alias is
        # still IN FLIGHT when the twin is forced past the policy's skip.
        dup, other = Token("X", {"n": 1}), Token("Y")
        net = Net(
            places=[Place(A), Place(B)],
            transitions=[Transition(T, handler="charge")],
            arcs=[Arc(A, T, weight=2), Arc(T, B)],
        )
        instance = Instance(net, Marking({A: (dup, dup, other)}), handlers={"charge": Bridge("work", B)})
        bindings = instance.candidates()
        first = instance.begin(bindings[1])

        with pytest.raises(ValueError, match="stale selection"):
            instance.begin(bindings[2])

        assert instance.in_flight == (first,)


# ── the coordinator loop ─────────────────────────────────────


class TestOneActionDrive:
    def test_each_drive_applies_at_most_one_normal_action(self):
        pool = InMemoryDispatch()
        engine, _, _ = _independent_engine(pool, policy=choose_throughput)

        first = engine.advance()

        assert first == DriveOutcome((), waiting=False, ready=True, next_maturation=None)
        assert len(engine.in_flight) == 1
        assert len(pool.pending) == 1

        second = engine.advance()

        assert second.ready is True
        assert len(engine.in_flight) == 2
        assert len(pool.pending) == 2

        third = engine.advance()

        assert third == DriveOutcome((), waiting=True, ready=False, next_maturation=None)

    def test_a_future_wall_clock_maturation_returns_without_waiting(self):
        class WallClock:
            def __init__(self):
                self.at = 0
                self.observations = []

            def now(self):
                return self.at

            def observe(self, instant):
                self.observations.append(instant)
                return None if self.at < instant else self.at

        net = Net(
            places=[Place(A), Place(B)],
            transitions=[Transition(T, timers=(Delay(5),))],
            arcs=[Arc(A, T), Arc(T, B)],
        )
        clock = WallClock()
        engine = Engine.create(
            net,
            "future-maturation-test",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("X"),)}),
            clock=clock,
        )

        sleeping = engine.advance()

        assert sleeping == DriveOutcome((), waiting=False, ready=False, next_maturation=5)
        assert clock.observations == [5]
        assert not any(isinstance(record, TimerMatured) for record in engine.records)

        clock.at = 7
        awakened = engine.advance()

        assert awakened == DriveOutcome((), waiting=False, ready=True, next_maturation=None)
        assert TimerMatured(maturation_instant=5, instant=7) in engine.records

    @pytest.mark.parametrize("policy", [choose_conservative, choose_throughput])
    def test_a_future_timer_cannot_hide_buffered_ingress_after_an_ingress_turn(self, policy):
        class WallClock:
            def __init__(self):
                self.observations = []

            def now(self):
                return 0

            def observe(self, instant):
                self.observations.append(instant)
                return None

        cursor = NetPath("cursor")
        tick = NetPath("tick")
        net = Net(
            places=[Place(cursor), Place(A)],
            transitions=[Transition(tick, timers=(Delay(5),)), Transition(SRC)],
            arcs=[Arc(cursor, tick), Arc(tick, cursor), Arc(SRC, A)],
        )
        parcels = iter(
            [
                (
                    Delivery(SRC, Token("X", {"n": 1}), identity="evt_1"),
                    Delivery(SRC, Token("X", {"n": 2}), identity="evt_2"),
                ),
            ]
        )
        clock = WallClock()
        engine = Engine.create(
            net,
            f"buffered-ingress-{policy.__name__}",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({cursor: (Token("Cursor"),)}),
            policy=policy,
            clock=clock,
            sensor=lambda: next(parcels, ()),
        )

        first = engine.advance()
        second = engine.advance()

        assert [firing.transition for firing in first.firings + second.firings] == [SRC, SRC]
        assert second.ready is True
        assert [token.data["n"] for token in engine.marking.place(A)] == [1, 2]
        assert clock.observations == [5]


class TestConcurrentInFlight:
    def test_independent_occurrences_interleave_and_results_commit_in_arrival_order(self):
        # DS2 acceptance 1: both requests freeze before either result
        # exists; the pool pumps out of order; results commit in arrival
        # order at the single writer.
        pool = InMemoryDispatch()
        engine, handlers, history = _independent_engine(pool, policy=choose_throughput, selection=RoundRobin((T2, T1)))

        outcome = _drive_until_rest(engine)  # begins both, dispatches both, returns control on Wait

        assert outcome == DriveOutcome((), waiting=True)
        assert len(engine.in_flight) == 2
        requested = [r for r in history if isinstance(r, ActivityRequested)]
        assert [r.activity for r in requested] == ["work_two", "work_one"]
        assert not any(isinstance(r, ActivityCompleted) for r in history)
        one, two = engine.in_flight
        assert set(pool.pending) == {one.id, two.id}

        pool.complete(two.id, {"n": 1})  # completion order != begin order
        pool.complete(one.id, {"n": 2})
        outcome = _drive_until_rest(engine)

        assert [f.occurrence for f in outcome.firings] == [two.id, one.id]  # arrival order
        assert outcome.waiting is False  # quiescent, nothing outstanding
        completions = [r for r in history if isinstance(r, ActivityCompleted)]
        assert [r.occurrence for r in completions] == [two.id, one.id]
        assert engine.marking == Marking({B1: (Token("Done", {"n": 1}),), B2: (Token("Done", {"n": 2}),)})
        assert engine.in_flight == ()

    def test_a_terminal_activity_failure_is_recorded_as_one_batch_and_halts_the_drive(self):
        pool = InMemoryDispatch()
        engine, _, history = _independent_engine(pool, policy=choose_conservative)
        assert _drive_until_rest(engine).waiting is True
        [occurrence] = engine.in_flight
        pool.fail(occurrence.id, "provider down")

        with pytest.raises(RuntimeError, match="provider down"):
            engine.advance()

        assert history.records[-2:] == (
            ActivityFailed(T1, "provider down", occurrence=occurrence.id, instant=0),
            FiringFailed(T1, "provider down", occurrence=occurrence.id, instant=0),
        )


class TestSelectionDurability:
    class RefusingHistory(InMemoryHistoryStore):
        refuse = False

        def extend(self, records):
            if self.refuse:
                raise OSError("disk full")
            super().extend(records)

    class RaisingDispatch(InMemoryDispatch):
        def dispatch(self, occurrence, invocation):
            raise RuntimeError("dispatch failed")

    def test_no_enabled_bindings_bypasses_selection(self):
        class Spy:
            calls = 0

            def propose(self, candidates, state):
                self.calls += 1
                raise AssertionError("selection must not see an empty enabled offer")

            def fold_committed(self, state, transition):
                return state

        selection = Spy()
        engine = Engine.create(
            _independent_net(),
            "empty-selection-test",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking(),
            handlers={"one": Bridge("work_one", B1), "two": Bridge("work_two", B2)},
            selection=selection,
        )

        assert engine.advance().waiting is False
        assert selection.calls == 0

    def test_round_robin_choice_is_recorded_before_dispatch(self):
        engine, _, history = _independent_engine(InMemoryDispatch(), selection=RoundRobin((T1, T2)))

        assert engine.advance().ready is True

        [selected] = [record for record in history if isinstance(record, CandidateSelected)]
        assert selected.transition == T1

    def test_round_robin_resume_matches_uninterrupted_with_an_orphan_selection(self):
        pool = InMemoryDispatch()
        turns = 0

        def begin_once(snapshot):
            nonlocal turns
            turns += 1
            if turns == 1:
                return next(action for action in snapshot.actions if isinstance(action, BeginCandidate))
            return Stop()

        history = InMemoryHistoryStore()
        first, handlers, _ = _independent_engine(
            pool,
            history=history,
            policy=begin_once,
            selection=RoundRobin((T1, T2)),
        )
        first.advance()
        first.advance()
        first.close()
        history.append(CandidateSelected(T1, occurrence=999))
        reconstructed_choice = []

        def capture_reconstructed(snapshot):
            reconstructed_choice.extend(action for action in snapshot.actions if isinstance(action, BeginCandidate))
            return Stop()

        resumed = Engine.load(
            _independent_net(),
            "coordinator-test",
            history=history,
            dispatch=InMemoryDispatch(),
            handlers=handlers,
            policy=capture_reconstructed,
            selection=RoundRobin((T1, T2)),
        )
        resumed.advance()

        assert [action.binding.transition for action in reconstructed_choice] == [T2]

    def test_backend_owned_dispatch_failure_leaves_the_durable_selection_for_reload(self):
        engine, _, history = _independent_engine(self.RaisingDispatch(), selection=RoundRobin((T1, T2)))

        with pytest.raises(RuntimeError, match="dispatch failed"):
            engine.advance()

        assert [record.transition for record in history if isinstance(record, CandidateSelected)] == [T1]

    def test_backend_owned_dispatch_failure_installs_the_already_durable_begin(self):
        engine, handlers, history = _independent_engine(self.RaisingDispatch(), selection=RoundRobin((T1, T2)))

        with pytest.raises(RuntimeError, match="dispatch failed"):
            engine.advance()

        next_choice = []

        def capture(snapshot):
            next_choice.extend(action for action in snapshot.actions if isinstance(action, BeginCandidate))
            return Stop()

        resumed = Engine.load(
            _independent_net(),
            "coordinator-test",
            history=history,
            dispatch=InMemoryDispatch(),
            handlers=handlers,
            policy=capture,
            selection=RoundRobin((T1, T2)),
        )
        resumed.advance()
        assert [action.binding.transition for action in next_choice] == [T2]

    def test_backend_owned_pure_completion_failure_installs_like_replay(self):
        def explode(binding, outputs):
            raise RuntimeError("completion failed")

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _activity_net(handler="explode"),
            "pure-failure-test",
            history=history,
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("X"),)}),
            handlers={"explode": explode},
            selection=RoundRobin((T,)),
        )

        with pytest.raises(RuntimeError, match="completion failed"):
            engine.advance()

        assert [record.transition for record in history if isinstance(record, CandidateSelected)] == [T]

    def test_refused_append_leaves_no_candidate_selection(self):
        history = self.RefusingHistory()
        engine, _, _ = _independent_engine(InMemoryDispatch(), history=history, selection=RoundRobin((T1, T2)))
        before = history.records
        history.refuse = True
        with pytest.raises(OSError, match="disk full"):
            engine.advance()
        assert history.records == before

    def test_other_action_discards_proposal_and_engines_isolate_shared_selection_policy(self):
        shared = RoundRobin((T1, T2))
        stopped, _, stopped_history = _independent_engine(
            InMemoryDispatch(), policy=lambda snapshot: Stop(), selection=shared
        )
        assert stopped.advance().waiting is False
        assert not any(isinstance(record, CandidateSelected) for record in stopped_history)

        choices = [[], []]

        def capture(index):
            def policy(snapshot):
                choices[index].extend(action for action in snapshot.actions if isinstance(action, BeginCandidate))
                return Stop()

            return policy

        first, _, _ = _independent_engine(InMemoryDispatch(), policy=capture(0), selection=shared)
        second, _, _ = _independent_engine(InMemoryDispatch(), policy=capture(1), selection=shared)
        first.advance()
        second.advance()
        assert [actions[0].binding.transition for actions in choices] == [T1, T1]

    def test_all_filtered_appends_no_history_and_emits_decline_telemetry(self):
        history = InMemoryHistoryStore()
        engine, _, _ = _independent_engine(
            InMemoryDispatch(),
            history=history,
            selection=SelectionPipeline(filters=(lambda _: False,)),
        )
        before = history.records

        assert engine.advance().waiting is False

        assert history.records == before

    def test_a_completion_for_an_occurrence_never_dispatched_is_refused_loud(self):
        class Rogue:
            def dispatch(self, occurrence, invocation):
                pass

            def collect(self):
                return ((99, {"ok": True}),)

        engine, _, _ = _independent_engine(Rogue(), policy=choose_conservative)

        with pytest.raises(ValueError, match="not in flight"):
            engine.advance()

    def test_a_policy_choosing_an_action_the_coordinator_did_not_offer_is_refused(self):
        def rogue(snapshot: Snapshot):
            return AdvanceTime(99)

        engine, _, _ = _independent_engine(InMemoryDispatch(), policy=rogue)
        with pytest.raises(ValueError, match="did not offer"):
            engine.advance()

    def test_the_policy_observes_detached_views_never_live_occurrences(self):
        # The observation surface hands out no path to the writer's
        # canonical state: a policy sees InFlightView values — id,
        # transition, consumed selections, the purity judgment — never a
        # FiringOccurrence with its recorded invocation.
        observed: list[Snapshot] = []

        def watching(snapshot: Snapshot):
            observed.append(snapshot)
            return choose_conservative(snapshot)

        engine, _, _ = _independent_engine(InMemoryDispatch(), policy=watching)
        _drive_until_rest(engine)

        with_work = [s for s in observed if s.in_flight]
        assert with_work
        for snapshot in with_work:
            [view] = snapshot.in_flight
            assert view == InFlightView(view.occurrence, T1, ((A1, (Token("X", {"n": 1}),)),), True)


class _Scripted:
    """An adapter scripted round by round: dispatch acknowledges, each collect returns the next scripted batch — how a redelivering transport is played back deterministically."""

    def __init__(self, *rounds):
        self.rounds = list(rounds)
        self.dispatched: list[int] = []

    def dispatch(self, occurrence, invocation):
        self.dispatched.append(occurrence)

    def collect(self):
        return self.rounds.pop(0) if self.rounds else ()


class TestLateCompletionsThroughCollect:
    def test_an_identical_redelivery_for_an_ended_occurrence_is_acknowledged_and_the_drive_continues(self):
        # The collect resolution routes by occurrence id at the writer: a
        # completed occurrence's identical late result goes through the
        # ended-acknowledgement door — quiet prior ack, no append, the loop
        # keeps driving [ruled at the DS2 adjudication, rejecting the
        # strict-ingest posture].
        adapter = _Scripted((), ((1, {"n": 1}),), ((1, {"n": 1}),))
        engine, _, history = _independent_engine(adapter, policy=choose_conservative)

        outcome = _drive_until_rest(engine)

        assert [f.occurrence for f in outcome.firings] == [1]  # exactly one completion committed
        completions = [r for r in history if isinstance(r, ActivityCompleted)]
        assert [r.occurrence for r in completions] == [1]  # the redelivery appended nothing
        # ...and the loop kept driving past the acknowledgement: t2 was
        # begun and dispatched behind it, its own result now outstanding.
        assert adapter.dispatched == [1, 2]
        assert [o.id for o in engine.in_flight] == [2]
        assert outcome.waiting is True

    def test_a_different_late_result_for_an_ended_occurrence_conflicts_loud(self):
        adapter = _Scripted((), ((1, {"n": 1}),), ((1, {"n": 999}),))
        engine, _, _ = _independent_engine(adapter, policy=choose_conservative)

        with pytest.raises(ValueError, match="different result.*operational conflict"):
            _drive_until_rest(engine)


class TestConservativePolicyParity:
    def test_a_representative_net_produces_the_same_history_under_equivalent_selection(self):
        # A multi-step net — a timed pure step feeding an impure activity —
        # commits record-for-record identical History under the conservative
        # policy whether selection is the default or an explicit priority.
        def net():
            return Net(
                places=[Place(A), Place(NetPath("staged")), Place(B)],
                transitions=[
                    Transition(NetPath("prep"), handler="prep", timers=(Delay(5),)),
                    Transition(T, handler="charge"),
                ],
                arcs=[
                    Arc(A, NetPath("prep")),
                    Arc(NetPath("prep"), NetPath("staged")),
                    Arc(NetPath("staged"), T),
                    Arc(T, B),
                ],
            )

        def prep(binding, outputs):
            return {NetPath("staged"): (Token("Staged", binding.tokens[0].data),)}

        def handlers():
            return {"prep": prep, "charge": Bridge("charge_card", B)}

        activities = {"charge_card": lambda invocation, *, context: {"status": "captured"}}
        marking = Marking({A: (Token("X", {"amount": 10}),)})

        baseline_history = InMemoryHistoryStore()
        baseline = Engine.create(
            net(),
            "parity",
            history=baseline_history,
            dispatch=InlineDispatch(activities),
            marking=marking,
            handlers=handlers(),
            policy=choose_conservative,
            clock=SimulatedClock(0),
        )
        baseline_outcome = _drive_until_rest(baseline)

        priority_history = InMemoryHistoryStore()
        priority = Engine.create(
            net(),
            "parity",
            history=priority_history,
            dispatch=InlineDispatch(activities),
            marking=marking,
            handlers=handlers(),
            policy=choose_conservative,
            selection=Priority({T: 99}),
            clock=SimulatedClock(0),
        )
        outcome = _drive_until_rest(priority)

        assert [encode_record(r) for r in priority_history] == [encode_record(r) for r in baseline_history]
        assert len(outcome.firings) == len(baseline_outcome.firings) == 2
        assert outcome.waiting is False
        assert priority.in_flight == ()


class TestSensedIngress:
    def _source_net(self) -> Net:
        return Net(
            places=[Place(A)],
            transitions=[Transition(SRC)],
            arcs=[Arc(SRC, A)],
        )

    def test_sensed_deliveries_land_in_fifo_order_at_quiescence(self):
        script = [
            (
                Delivery(SRC, Token("X", {"n": 1}), identity="evt_1"),
                Delivery(SRC, Token("X", {"n": 2}), identity="evt_2"),
            ),
            (),
        ]

        def sensor():
            return script.pop(0)

        engine = Engine.create(
            self._source_net(),
            "sensed-fifo-test",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            sensor=sensor,
        )
        outcome = _drive_until_rest(engine)

        assert [f.transition for f in outcome.firings] == [SRC, SRC]
        assert engine.marking == Marking({A: (Token("X", {"n": 1}), Token("X", {"n": 2}))})

    def test_a_sensed_redelivery_acknowledges_without_a_firing_or_an_append(self):
        script = [(Delivery(SRC, Token("X", {"n": 1}), identity="evt_1"),)] * 2 + [()]

        def sensor():
            return script.pop(0)

        engine = Engine.create(
            self._source_net(),
            "sensed-redelivery-test",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            sensor=sensor,
        )
        outcome = _drive_until_rest(engine)

        assert len(outcome.firings) == 1  # the redelivery acknowledged, never fired
        assert engine.marking == Marking({A: (Token("X", {"n": 1}),)})

    @pytest.mark.parametrize("policy", [choose_conservative, choose_throughput])
    def test_sensed_ingress_and_standing_internal_work_alternate(self, policy):
        cursor = NetPath("cursor")
        spin = NetPath("spin")
        net = Net(
            places=[Place(cursor), Place(A)],
            transitions=[Transition(spin), Transition(SRC)],
            arcs=[Arc(cursor, spin), Arc(spin, cursor), Arc(SRC, A)],
        )
        parcels = iter(
            [
                (Delivery(SRC, Token("X", {"n": 1}), identity="evt_1"),),
                (Delivery(SRC, Token("X", {"n": 2}), identity="evt_2"),),
                (Delivery(SRC, Token("X", {"n": 3}), identity="evt_3"),),
            ]
        )

        def sensor():
            return next(parcels, ())

        engine = Engine.create(
            net,
            f"sensed-alternation-{policy.__name__}",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({cursor: (Token("Cursor"),)}),
            policy=policy,
            sensor=sensor,
        )
        transitions = []
        for _ in range(5):
            outcome = engine.advance()
            transitions.extend(firing.transition for firing in outcome.firings)

        assert transitions == [SRC, spin, SRC, spin, SRC]
        assert [record.identity for record in engine.records if isinstance(record, ExternalEventDelivered)] == [
            "evt_1",
            "evt_2",
            "evt_3",
        ]

    def test_a_delivery_buffered_behind_a_source_close_is_held_not_applied(self):
        hook = lambda binding, outputs: HandlerResult(  # noqa: E731
            {A: binding.tokens}, closes=(DeliveryRegistration(SRC, "default"),)
        )
        net = Net(
            places=[Place(A)],
            transitions=[Transition(SRC, handler="hook")],
            arcs=[Arc(SRC, A)],
        )
        sensor_calls = 0

        def sensor():
            nonlocal sensor_calls
            sensor_calls += 1
            return (
                Delivery(SRC, Token("X", {"n": 1}), identity="evt_1"),
                Delivery(SRC, Token("X", {"n": 2}), identity="evt_2"),
            )

        engine = Engine.create(
            net,
            "source-close-buffer-test",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            handlers={"hook": hook},
            sensor=sensor,
        )

        assert [f.transition for f in engine.advance().firings] == [SRC]
        stopped = engine.advance()

        assert stopped == DriveOutcome((), waiting=False, ready=False, next_maturation=None)
        assert sensor_calls == 1
        assert [record.identity for record in engine.records if isinstance(record, ExternalEventDelivered)] == ["evt_1"]


# ── reconcile-then-drive ─────────────────────────────────────


class TestReconcileThenDrive:
    def test_an_outstanding_invocation_is_redispatched_never_re_prepared(self, tmp_path):
        # Kill window 1: begun, invocation frozen, no terminal activity fact
        # — the outbox scan redispatches the RECORDED invocation to the
        # adapter; prepare never re-runs.
        path = tmp_path / "history.jsonl"
        handler = Bridge("charge_card", B)
        instance = Instance(
            _activity_net(),
            Marking({A: (Token("X", {"n": 1}),)}),
            handlers={"charge": handler},
            history=JsonlHistoryStore(path),
            instance_id="reconcile-request-test",
        )
        original = instance.begin(instance.candidates()[0])
        del instance  # the kill

        fresh = Bridge("charge_card", B)
        pool = InMemoryDispatch()
        resumed = Engine.load(
            _activity_net(),
            "reconcile-request-test",
            history=JsonlHistoryStore(path),
            dispatch=pool,
            handlers={"charge": fresh},
            policy=choose_conservative,
        )

        outcome = resumed.advance()  # reconciles, then waits on the redispatched result

        assert outcome == DriveOutcome((), waiting=True)
        assert pool.pending == {original.id: original.invocation}
        assert fresh.prepared == 0  # never re-run

        pool.complete(original.id, {"status": "captured"})
        outcome = resumed.advance()

        assert [f.occurrence for f in outcome.firings] == [original.id]
        assert outcome.waiting is False
        assert fresh.projected == 1
        assert resumed.marking == Marking({B: (Token("Done", {"status": "captured"}),)})
        assert resumed.in_flight == ()

    def test_a_projection_pending_occurrence_completes_by_projection_alone(self, tmp_path):
        # Kill window 2: the result froze, the process died before
        # projection — reconcile completes from the frozen fact and the
        # adapter is never consulted for it.
        path = tmp_path / "history.jsonl"
        handler = Bridge("charge_card", B)
        instance = Instance(
            _activity_net(),
            Marking({A: (Token("X", {"n": 1}),)}),
            handlers={"charge": handler},
            history=JsonlHistoryStore(path),
            instance_id="reconcile-projection-test",
        )
        occurrence = instance.begin(instance.candidates()[0])
        instance.record_activity_completion(occurrence, {"status": "captured"})
        del instance  # the kill

        fresh = Bridge("charge_card", B)
        pool = InMemoryDispatch()
        resumed = Engine.load(
            _activity_net(),
            "reconcile-projection-test",
            history=JsonlHistoryStore(path),
            dispatch=pool,
            handlers={"charge": fresh},
            policy=choose_conservative,
        )

        outcome = resumed.advance()

        assert [f.occurrence for f in outcome.firings] == [occurrence.id]
        assert pool.pending == {}  # never redispatched
        assert fresh.prepared == 0 and fresh.projected == 1
        assert [r for r in resumed.records if isinstance(r, ActivityCompleted)] == [
            ActivityCompleted(T, {"status": "captured"}, occurrence=occurrence.id)
        ]
        assert resumed.marking == Marking({B: (Token("Done", {"status": "captured"}),)})

    def test_pure_in_flight_is_driven_to_terminal_and_the_drive_continues(self, tmp_path):
        # A pure occurrence killed mid-flight completes on reconcile — its
        # handler re-executes over the recorded binding — and normal driving
        # continues behind it to quiescence.
        path = tmp_path / "history.jsonl"
        chain = Net(
            places=[Place(A), Place(NetPath("mid")), Place(B)],
            transitions=[Transition(T), Transition(NetPath("t2"))],
            arcs=[Arc(A, T), Arc(T, NetPath("mid")), Arc(NetPath("mid"), NetPath("t2")), Arc(NetPath("t2"), B)],
        )
        token = Token("X")
        instance = Instance(
            chain,
            Marking({A: (token,)}),
            history=JsonlHistoryStore(path),
            instance_id="reconcile-pure-test",
        )
        occurrence = instance.begin(instance.candidates()[0])
        del instance  # the kill

        resumed = Engine.load(
            chain,
            "reconcile-pure-test",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            policy=choose_conservative,
        )
        outcome = resumed.advance()

        assert [f.occurrence for f in outcome.firings][0] == occurrence.id  # reconciled first
        assert len(outcome.firings) == 2  # then t2 fired behind it
        assert resumed.marking == Marking({B: (token,)})
        assert resumed.in_flight == ()
