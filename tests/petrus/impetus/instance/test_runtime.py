"""Behavioral tests for Instance — the integration path (step -> history -> status)."""

from __future__ import annotations

# Internal imports
from petrus.impetus.history import CandidateSelected, InstanceCreated, TokensInitialized, replay_marking
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.instance import Instance, Status
from petrus.impetus.petrinet import Arc, Delay, Net, NetPath, Place, Transition


def _fork_net():
    """a -> t -> {b, c}: one token fans out to two output places."""
    a, b, c, t = NetPath("a"), NetPath("b"), NetPath("c"), NetPath("t")
    return Net(
        places=[Place(a), Place(b), Place(c)],
        transitions=[Transition(t)],
        arcs=[Arc(a, t), Arc(t, b), Arc(t, c)],
    )


class TestInstance:
    def test_step_fans_out_and_reports_what_landed_where(self):
        token = Token("X")
        instance = Instance(_fork_net(), Marking({NetPath("a"): (token,)}))

        firing = instance.step()

        assert firing.produced == ((NetPath("b"), token), (NetPath("c"), token))
        assert instance.marking == Marking({NetPath("b"): (token,), NetPath("c"): (token,)})

    def test_runs_to_quiescence_and_reports_terminated(self):
        instance = Instance(_fork_net(), Marking({NetPath("a"): (Token.black(),)}))

        instance.run()

        assert instance.is_quiescent
        assert instance.status is Status.TERMINATED

    def test_step_records_the_selection_before_the_firing_lifecycle(self):
        # The selection record belongs to the selection site: step() appends
        # CandidateSelected (the scheduler chose), then the firing's records.
        # Delivery, by contrast, initiates with an external-event record.
        token = Token("X")
        instance = Instance(_fork_net(), Marking({NetPath("a"): (token,)}))

        firing = instance.step()

        assert instance.history.records == (
            InstanceCreated(instance.instance_id),
            TokensInitialized(NetPath("a"), (token,)),
            CandidateSelected(NetPath("t"), occurrence=1),
            *firing.records,
        )

    def test_history_replays_to_the_live_marking(self):
        instance = Instance(_fork_net(), Marking({NetPath("a"): (Token("X"),)}))
        instance.run()
        assert replay_marking(instance.history) == instance.marking


class _CountingHistory(InMemoryHistoryStore):
    """An InMemoryHistoryStore that counts full iterations — a fold over it walks every record through ``__iter__``."""

    def __init__(self):
        super().__init__()
        self.folds = 0

    def __iter__(self):
        self.folds += 1
        return super().__iter__()


class TestLiveStateIsNotRefolded:
    """
    Every state is a projection, always — and the live instance maintains the
    projection incrementally: the per-wave reads answer from the pair-queues,
    never by re-folding the full history (the O(history)-per-wave tax the
    ES-012 session-2 LIVE finding named). Resume is the one legitimate fold.
    """

    def test_candidates_answer_from_live_state_without_refolding_history(self):
        # A timed net makes the entry instants load-bearing: before the
        # pair-queues, each candidates() call re-folded the whole history
        # just to rebuild them.
        a, b, t = NetPath("a"), NetPath("b"), NetPath("t")
        net = Net(
            places=[Place(a), Place(b)],
            transitions=[Transition(t, timers=(Delay(5),))],
            arcs=[Arc(a, t), Arc(t, b)],
        )
        history = _CountingHistory()
        instance = Instance(net, Marking({a: (Token.black(),)}), history=history)

        history.folds = 0
        instance.candidates()
        instance.next_maturation
        instance.wake(at=5)
        instance.step()

        assert history.folds == 0, "the whole live wave answered from the pair-queues"
