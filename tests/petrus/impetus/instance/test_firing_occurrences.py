"""
Behavioral tests for the durable firing-occurrence seam — begin/complete/fail.

The seam is the net-runtime half of ADR 0012: ``begin`` accounts input tokens
and records the occurrence, an execution runtime runs the handler however it
likes, and ``complete``/``fail`` commit the terminal outcome. Everything fires
through the seam — ``step`` and ``deliver`` are inline drivers over it — and
every record of one firing carries its occurrence id, minted at the initiation
record (a Navigator ruling: the pipeline's "selected firing occurrence" IS the
durable record of the chosen candidate). Failure is not net semantics: ``fail``
records the terminal fact and nothing else — no restore, no retry.
"""

from __future__ import annotations

# Python imports
import pytest

# Internal imports
from petrus.impetus.petrinet import Binding
from petrus.impetus.binding import HandlerResult
from petrus.impetus.history import (
    ActivityCompleted,
    InstanceCreated,
    ActivityRequested,
    CandidateSelected,
    ExternalEventDelivered,
    FiringBegun,
    FiringCompleted,
    FiringFailed,
    DeliveryRegistration,
    TokensConsumed,
    TokensInitialized,
    TokensProduced,
    replay_marking,
)
from petrus.impetus.petrinet import Marking, Token, TokenQueue
from petrus.impetus.instance import Instance, Status
from petrus.impetus.petrinet import Arc, ArcMode, Net, NetPath, Place, Transition

A, B, T = NetPath("a"), NetPath("b"), NetPath("t")


def _line_net(handler: str | None = None):
    """a -> t -> b, optionally with a user handler symbol on t."""
    return Net(
        places=[Place(A), Place(B)],
        transitions=[Transition(T, handler=handler)],
        arcs=[Arc(A, T), Arc(T, B)],
    )


def _begin_one(instance):
    """Begin the head binding — what the conservative scheduler would choose."""
    return instance.begin(instance.candidates()[0])


# ── begin ────────────────────────────────────────────────────


class TestBegin:
    def test_begin_accounts_tokens_and_records_the_occurrence(self):
        # Accounting at begin is ADR 0007's duplicate-worker protection: the
        # tokens leave the marking before any handler runs, and the selection,
        # the occurrence boundary, and the movements all carry one occurrence id.
        token = Token("X")
        instance = Instance(_line_net(), Marking({A: (token,)}), at=3)

        occurrence = _begin_one(instance)

        assert instance.marking == Marking()
        assert instance.history.records == (
            InstanceCreated(instance.instance_id, instant=3),
            TokensInitialized(A, (token,), instant=3),
            CandidateSelected(T, occurrence=1, instant=3),
            FiringBegun(T, occurrence=1, instant=3),
            TokensConsumed(A, (token,), occurrence=1, instant=3),
        )
        assert occurrence.id == 1
        assert occurrence.binding.transition == T
        assert instance.in_flight == (occurrence,)

    def test_occurrence_ids_are_minted_monotonically(self):
        instance = Instance(_line_net(), Marking({A: (Token("X"), Token("X"))}))

        first = _begin_one(instance)
        second = _begin_one(instance)

        assert (first.id, second.id) == (1, 2)
        assert instance.in_flight == (first, second)

    def test_an_in_flight_occurrence_keeps_the_instance_running(self):
        # The ratified quiescence definition's third leg: no firing occurrence
        # begun without ending. With the only token out with a worker, nothing
        # is enabled — but the instance is working, not done.
        instance = Instance(_line_net(), Marking({A: (Token("X"),)}))

        _begin_one(instance)

        assert not instance.is_quiescent
        assert instance.status is Status.RUNNING

    def test_begin_rejects_a_delivered_binding(self):
        # A delivered binding is a source firing; deliver() is its door.
        source = NetPath("src")
        net = Net(places=[Place(B)], transitions=[Transition(source)], arcs=[Arc(source, B)])
        instance = Instance(net)

        with pytest.raises(ValueError, match="deliver"):
            instance.begin(Binding(source, (), delivered=(Token("X"),)))

    def test_begin_rejects_a_source_transition(self):
        # A source transition is never scheduled and never fires spontaneously
        # [DR source-transition-ingress]: an empty hand-built binding must not
        # slip a CandidateSelected for a source into the history.
        source = NetPath("src")
        net = Net(places=[Place(B)], transitions=[Transition(source)], arcs=[Arc(source, B)])
        instance = Instance(net)
        before = len(instance.history)

        with pytest.raises(ValueError, match="never scheduled"):
            instance.begin(Binding(source, ()))

        assert len(instance.history) == before

    def test_begin_rejects_a_foreign_transition(self):
        instance = Instance(_line_net(), Marking({A: (Token("X"),)}))

        with pytest.raises(ValueError, match="not a transition of this net"):
            instance.begin(Binding(NetPath("elsewhere"), ()))

    def test_begin_rejects_a_hand_built_binding_missing_its_consume_selection(self):
        # Writer/replay symmetry: resume rejects a rebuilt binding whose
        # selections disagree with the transition's arcs, so begin must
        # refuse to WRITE one — otherwise the writer appends a begin batch
        # its own resume refuses. Validated before anything is appended.
        instance = Instance(_line_net(), Marking({A: (Token("X"),)}))
        before = len(instance.history)

        with pytest.raises(ValueError, match="consume selections do not match the transition's consume arcs"):
            instance.begin(Binding(T, ()))

        assert len(instance.history) == before

    def test_begin_rejects_a_hand_built_binding_missing_its_read_selection(self):
        # The read half of the same shape rule: a read-arc transition's
        # binding must carry one read selection per read arc — resume would
        # reject the rebuilt occurrence, so begin refuses to mint it.
        gate = NetPath("gate")
        net = Net(
            places=[Place(A), Place(gate), Place(B)],
            transitions=[Transition(T)],
            arcs=[Arc(A, T), Arc(gate, T, mode=ArcMode.READ), Arc(T, B)],
        )
        instance = Instance(net, Marking({A: (Token("X"),), gate: (Token("Y"),)}))
        before = len(instance.history)

        with pytest.raises(ValueError, match="read selections do not match the transition's read arcs"):
            instance.begin(Binding(T, ((A, (Token("X"),)),)))

        assert len(instance.history) == before

    def test_begin_with_a_stale_selection_appends_nothing(self):
        # A driver may hold a binding whose tokens another occurrence already
        # consumed. The consume fails loud — naming the transition and the
        # concept, not just the missing token — and, validate before record,
        # the history takes no partial fact: no selection, no begun, no id.
        # (Distinct tokens: an equal token still in queue would re-satisfy
        # the selection by value.)
        instance = Instance(_line_net(), Marking({A: (Token("X"), Token("Y"))}))
        binding = instance.candidates()[0]
        instance.begin(binding)

        with pytest.raises(ValueError, match="stale selection"):
            instance.begin(binding)

        assert len(instance.history) == 5  # identity + initialized + the first occurrence's three
        assert len(instance.in_flight) == 1
        # The failed begin burned no id: the next fresh selection is occurrence 2.
        [fresh] = instance.candidates()
        assert instance.begin(fresh).id == 2


# ── complete ─────────────────────────────────────────────────


class TestComplete:
    def test_complete_deposits_per_arc_contract_and_ends_the_occurrence(self):
        token = Token("X")
        instance = Instance(_line_net(), Marking({A: (token,)}))
        occurrence = _begin_one(instance)

        firing = instance.complete(occurrence, {B: (token,)})

        assert instance.marking == Marking({B: (token,)})
        assert instance.in_flight == ()
        assert firing.occurrence == occurrence.id
        assert firing.produced == ((B, token),)
        assert instance.history.records[-2:] == (
            TokensProduced(B, (token,), occurrence=1, instant=0),
            FiringCompleted(T, occurrence=1, instant=0),
        )

    def test_a_user_handled_firing_is_a_pure_projection_recording_movements_only(self):
        # A plain callable bound to a symbol is a pure deterministic
        # projection [DR 2026-07-14 source-delivery-projection-and-identity]:
        # no activity records — a token no output arc admits simply drops
        # from the deposit (the validation run owns declaration typos).
        stray = Token("Y")
        instance = Instance(
            _line_net(handler="price"),
            Marking({A: (Token("X"),)}),
            handlers={"price": lambda binding, outputs: {B: (Token("X"),), "nowhere": (stray,)}},
        )
        occurrence = _begin_one(instance)

        instance.complete(occurrence, {B: (Token("X"),), "nowhere": (stray,)})

        assert not [r for r in instance.history if isinstance(r, (ActivityRequested, ActivityCompleted))]
        assert instance.marking == Marking({B: (Token("X"),)})

    def test_a_passthrough_firing_records_no_activity_records(self):
        # The no-symbol default is equally pure — its firing is
        # deterministic records only [event-history.md].
        instance = Instance(_line_net(), Marking({A: (Token("X"),)}))
        occurrence = _begin_one(instance)

        instance.complete(occurrence, {B: (Token("X"),)})

        assert not [r for r in instance.history if isinstance(r, (ActivityRequested, ActivityCompleted))]

    def test_complete_rejects_an_occurrence_this_instance_never_began(self):
        instance = Instance(_line_net(), Marking({A: (Token("X"),)}))
        other = Instance(_line_net(), Marking({A: (Token("X"),)}))
        foreign = _begin_one(other)

        with pytest.raises(ValueError, match="never began"):
            instance.complete(foreign, {})

    def test_complete_rejects_an_already_ended_occurrence(self):
        # Ended and never-begun are different misuses; the seam tells them apart.
        instance = Instance(_line_net(), Marking({A: (Token("X"),)}))
        occurrence = _begin_one(instance)
        instance.complete(occurrence, {})

        with pytest.raises(ValueError, match="already ended"):
            instance.complete(occurrence, {})


# ── fail ─────────────────────────────────────────────────────


class TestFail:
    def test_fail_records_the_terminal_failure_and_nothing_else(self):
        # Failure is not net semantics (a Navigator ruling): the consumed
        # tokens stay consumed — restoring them would claim work never
        # happened — and no retry is implied. The record is the whole commit.
        instance = Instance(_line_net(), Marking({A: (Token("X"),)}))
        occurrence = _begin_one(instance)

        instance.fail(occurrence, "TimeoutError('no quote')")

        assert instance.history.records[-1] == FiringFailed(
            T, error="TimeoutError('no quote')", occurrence=1, instant=0
        )
        assert instance.marking == Marking()
        assert instance.in_flight == ()

    def test_a_failed_occurrence_no_longer_blocks_quiescence(self):
        instance = Instance(_line_net(), Marking({A: (Token("X"),)}))
        occurrence = _begin_one(instance)

        instance.fail(occurrence, "boom")

        assert instance.is_quiescent
        assert instance.status is Status.TERMINATED

    def test_fail_discriminates_misuse_like_complete(self):
        instance = Instance(_line_net(), Marking({A: (Token("X"),)}))
        occurrence = _begin_one(instance)
        instance.fail(occurrence, "boom")

        with pytest.raises(ValueError, match="already ended"):
            instance.fail(occurrence, "boom")


# ── step through the seam ────────────────────────────────────


class TestStepThroughTheSeam:
    def test_step_is_one_occurrence_begun_and_completed(self):
        # The inline convenience is a miniature execution runtime: selection,
        # occurrence, movements, and completion — one id, one instant.
        token = Token("X")
        instance = Instance(_line_net(), Marking({A: (token,)}))

        firing = instance.step(at=7)

        assert firing.occurrence == 1
        assert instance.history.records == (
            InstanceCreated(instance.instance_id),
            TokensInitialized(A, (token,)),
            CandidateSelected(T, occurrence=1, instant=7),
            FiringBegun(T, occurrence=1, instant=7),
            TokensConsumed(A, (token,), occurrence=1, instant=7),
            TokensProduced(B, (token,), occurrence=1, instant=7),
            FiringCompleted(T, occurrence=1, instant=7),
        )

    def test_step_with_a_user_handler_records_the_pure_projection_lifecycle(self):
        instance = Instance(
            _line_net(handler="price"),
            Marking({A: (Token("X"),)}),
            handlers={"price": lambda binding, outputs: {B: (Token("Y"),)}},
        )

        instance.step()

        kinds = [type(r).__name__ for r in instance.history]
        assert kinds == [
            "InstanceCreated",
            "TokensInitialized",
            "CandidateSelected",
            "FiringBegun",
            "TokensConsumed",
            "TokensProduced",
            "FiringCompleted",
        ]

    def test_a_raising_handler_records_the_failure_and_propagates(self):
        # The terminal fact lands in history before the exception reaches the
        # caller — halt-on-failure is the inline driver's policy, loud.
        instance = Instance(
            _line_net(handler="price"),
            Marking({A: (Token("X"),)}),
            handlers={"price": lambda binding, outputs: (_ for _ in ()).throw(RuntimeError("quote service down"))},
        )

        with pytest.raises(RuntimeError, match="quote service down"):
            instance.step()

        failed = instance.history.records[-1]
        assert isinstance(failed, FiringFailed)
        assert "quote service down" in failed.error
        assert instance.marking == Marking()
        assert instance.in_flight == ()

    def test_a_result_the_commit_rejects_records_the_failure_and_propagates(self):
        # complete()'s rejection leaves the occurrence in flight for its driver
        # to fail — and step() is a driver: the lifecycle closes on this path
        # exactly as it does for a raising handler.
        instance = Instance(
            _line_net(handler="hook"),
            Marking({A: (Token("X"),)}),
            handlers={"hook": lambda binding, outputs: HandlerResult(closes=(DeliveryRegistration(T, "nope"),))},
        )

        with pytest.raises(ValueError, match="only a source transition has delivery registrations"):
            instance.step()

        failed = instance.history.records[-1]
        assert isinstance(failed, FiringFailed)
        assert "only a source transition" in failed.error
        assert instance.in_flight == ()


# ── deliver through the seam ─────────────────────────────────


class TestDeliverThroughTheSeam:
    SRC, OUT = NetPath("src"), NetPath("out")

    def _source_net(self, handler: str | None = None):
        return Net(
            places=[Place(self.OUT)],
            transitions=[Transition(self.SRC, handler=handler)],
            arcs=[Arc(self.SRC, self.OUT)],
        )

    def test_delivery_records_carry_one_occurrence(self):
        token = Token("X")
        instance = Instance(self._source_net())

        firing = instance.deliver(self.SRC, token, at=5)

        assert firing.occurrence == 1
        assert instance.history.records[-4:] == (
            ExternalEventDelivered(self.SRC, (token,), identity="occurrence-1", occurrence=1, instant=5),
            FiringBegun(self.SRC, occurrence=1, instant=5),
            TokensProduced(self.OUT, (token,), occurrence=1, instant=5),
            FiringCompleted(self.SRC, occurrence=1, instant=5),
        )

    def test_a_handled_delivery_is_a_local_atomic_projection(self):
        # A source transition locally and atomically projects the accepted
        # fact [DR 2026-07-14 source-delivery-projection-and-identity]: its
        # handler is a pure projection — no activity records, the transformed
        # tokens recorded as ordinary movements.
        instance = Instance(
            self._source_net(handler="ingest"),
            handlers={"ingest": lambda binding, outputs: {self.OUT: (Token("X"),)}},
        )

        instance.deliver(self.SRC, Token("Raw"))

        assert not [r for r in instance.history if isinstance(r, (ActivityRequested, ActivityCompleted))]
        assert instance.marking == Marking({self.OUT: (Token("X"),)})


# ── value aliasing ───────────────────────────────────────────


class TestValueAliasingPinnedInvariant:
    """
    Debt 2026-07-11T2130Z, closed per its stated alternative: candidate
    selections are BY VALUE, never by queue position — value-aliasing is a
    stated, pinned invariant of the conservative kernel, and positional
    identity waits for the non-conservative-scheduler turn. A scheduler or
    replay that needs to tell equal-token selections apart by position must
    fail here first.
    """

    def test_value_aliasing_is_a_pinned_invariant_selections_are_by_value_not_position(self):
        # (1) Two equal tokens at distinct positions yield IDENTICAL Binding
        # values: enumeration walks queue positions, bindings carry values.
        dup, other = Token("X", {"n": 1}), Token("Y")
        net = Net(
            places=[Place(A), Place(B)],
            transitions=[Transition(T)],
            arcs=[Arc(A, T, weight=2), Arc(T, B)],
        )
        instance = Instance(net, Marking({A: (dup, dup, other)}))
        bindings = instance.candidates()
        assert len(bindings) == 3  # C(3, 2): (dup, dup), then (dup, other) twice
        assert bindings[1] == bindings[2]  # distinct positions, one binding value

        # (2) Consume removes the front-most EQUAL occurrence — tokens are
        # values, so equal tokens are interchangeable and order is kept (the
        # front token's entry instant leaves with it).
        queue = TokenQueue(((dup, 1), (dup, 2)))
        assert queue.remove((dup,)).instants == (2,)

        # (3) Beginning the first (dup, other) alias consumes by value...
        first = instance.begin(bindings[1])
        assert instance.marking == Marking({A: (dup,)})

        # (4) ...and beginning its identical twin fails loud as a stale
        # selection: `other` is spent, and no positional identity exists to
        # claim the twin selected "the other one". Nothing partially begins.
        with pytest.raises(ValueError, match="stale selection"):
            instance.begin(bindings[2])
        assert instance.in_flight == (first,)


# ── replay ───────────────────────────────────────────────────


class TestReplayWithOccurrences:
    def test_replay_of_an_in_flight_tail_leaves_tokens_consumed(self):
        # An occurrence begun but not ended is exactly what a crash leaves in the
        # log; replay reconstructs the accounted (consumed) state, never the
        # pre-begin one — the tokens are out with a worker, not lost.
        token = Token("X")
        instance = Instance(_line_net(), Marking({A: (token,)}))
        _begin_one(instance)

        assert replay_marking(instance.history) == Marking()
        assert replay_marking(instance.history) == instance.marking
