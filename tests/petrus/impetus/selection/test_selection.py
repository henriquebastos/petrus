"""Canonical Candidate Selection policy and committed-state replay."""

from __future__ import annotations

import pytest

from petrus.impetus.history import CandidateSelected, FiringBegun
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Binding, NetPath
from petrus.impetus.selection import First, Priority, RoundRobin, SelectionPipeline, SelectionProposal, fold_history


def _bindings(*names: str) -> tuple[Binding, ...]:
    return tuple(Binding(NetPath(name), ()) for name in names)


def test_first_proposes_immutably_and_empty_offer_bypasses_choice():
    policy = First()
    offered = _bindings("a", "b")

    proposal = policy.propose(offered, None)

    assert proposal is not None
    assert proposal.binding is offered[0]
    assert proposal.prior_state is None
    assert proposal.next_state is None
    assert policy.propose((), None) is None


def test_priority_is_stable_for_equal_and_unconfigured_transitions():
    offered = _bindings("a", "b", "c")

    proposal = Priority({"b": 10, "c": 10}).propose(offered, None)

    assert proposal is not None
    assert proposal.binding is offered[1]


def test_round_robin_proposes_next_state_without_mutating_prior_state():
    policy = RoundRobin((NetPath("a"), NetPath("b"), NetPath("c")))
    offered = _bindings("a", "b", "c")

    first = policy.propose(offered, None)
    again = policy.propose(offered, None)
    second = policy.propose(offered, first.next_state)

    assert first == again
    assert first.binding.transition == NetPath("a")
    assert second.binding.transition == NetPath("b")


def test_round_robin_validates_cursor_and_wraps_the_last_position_to_zero():
    policy = RoundRobin((NetPath("a"), NetPath("b"), NetPath("c")))

    at_zero = policy.propose(_bindings("a"), 0)
    proposal = policy.propose(_bindings("c"), 2)

    assert at_zero is not None
    assert at_zero.binding.transition == NetPath("a")
    assert proposal is not None
    assert proposal.next_state == 0


@pytest.mark.parametrize("state", [True, "1", -1, 3])
def test_round_robin_rejects_invalid_cursor_state(state):
    policy = RoundRobin((NetPath("a"), NetPath("b"), NetPath("c")))

    with pytest.raises(ValueError, match=f"invalid round-robin state: {state!r}"):
        policy.propose(_bindings("a"), state)


def test_pipeline_filters_then_stably_ranks_then_runs_one_strategy():
    calls: list[str] = []

    def admitted(binding):
        calls.append(f"filter:{binding.transition}")
        return binding.transition != NetPath("a")

    def rank(binding):
        calls.append(f"rank:{binding.transition}")
        return 0 if binding.transition == NetPath("c") else 1

    pipeline = SelectionPipeline(filters=(admitted,), rankers=(rank,))
    proposal = pipeline.propose(_bindings("a", "b", "c"), None)

    assert proposal is not None
    assert proposal.binding.transition == NetPath("c")
    assert calls == ["filter:a", "filter:b", "filter:c", "rank:b", "rank:c"]
    assert SelectionPipeline(filters=(lambda _: False,)).propose(_bindings("a"), None) is None


def test_all_filtered_bypasses_strategy_and_custom_strategy_is_boundary_checked():
    class Spy:
        def __init__(self, proposal=None):
            self.calls = 0
            self.proposal = proposal

        def propose(self, candidates, state):
            self.calls += 1
            return self.proposal

        def fold_committed(self, state, transition):
            return state

    offered = _bindings("a", "b")
    bypassed = Spy()
    assert SelectionPipeline(filters=(lambda _: False,), strategy=bypassed).propose(offered, None) is None
    assert bypassed.calls == 0

    with pytest.raises(ValueError, match="outside the admitted"):
        SelectionPipeline(
            filters=(lambda binding: binding is offered[0],), strategy=Spy(SelectionProposal(offered[1], None, 1))
        ).propose(offered, None)
    with pytest.raises(ValueError, match="prior state"):
        SelectionPipeline(strategy=Spy(SelectionProposal(offered[0], "wrong", 1))).propose(offered, None)


def test_multiple_filters_and_rankers_preserve_order_and_final_ties():
    offered = _bindings("a", "b", "c", "d")
    calls = []

    def filter_one(binding):
        calls.append(("f1", str(binding.transition)))
        return binding.transition != NetPath("a")

    def filter_two(binding):
        calls.append(("f2", str(binding.transition)))
        return True

    pipeline = SelectionPipeline(
        filters=(filter_one, filter_two),
        rankers=(lambda binding: binding.transition in (NetPath("b"), NetPath("c")), lambda binding: 0),
    )

    assert pipeline.propose(offered, None).binding is offered[3]
    assert calls == [("f1", "a"), ("f1", "b"), ("f2", "b"), ("f1", "c"), ("f2", "c"), ("f1", "d"), ("f2", "d")]


def test_replay_folds_only_exact_committed_selection_pairs_and_spends_orphans():
    policy = RoundRobin((NetPath("a"), NetPath("b")))
    history = InMemoryHistoryStore()
    history.extend(
        [
            CandidateSelected(NetPath("a"), occurrence=0, instant=0),
            FiringBegun(NetPath("a"), occurrence=0, instant=0),
        ]
    )
    history.append(CandidateSelected(NetPath("b"), occurrence=1, instant=0))

    state = fold_history(policy, None, history)

    assert policy.propose(_bindings("a", "b"), state).binding.transition == NetPath("b")


def test_replay_threads_accumulated_policy_state_through_committed_pairs():
    class TransitionTrail:
        def fold_committed(self, state, transition):
            return (*state, transition)

    records = (
        CandidateSelected(NetPath("a"), occurrence=1, instant=0),
        FiringBegun(NetPath("a"), occurrence=1, instant=0),
        CandidateSelected(NetPath("b"), occurrence=2, instant=0),
        FiringBegun(NetPath("b"), occurrence=2, instant=0),
    )

    assert fold_history(TransitionTrail(), (), records) == (NetPath("a"), NetPath("b"))


@pytest.mark.parametrize(
    "records",
    [
        (
            CandidateSelected(NetPath("a"), occurrence=0, instant=0),
            CandidateSelected(NetPath("a"), occurrence=0, instant=0),
        ),
        (
            CandidateSelected(NetPath("a"), occurrence=0, instant=0),
            FiringBegun(NetPath("b"), occurrence=0, instant=0),
        ),
        (
            CandidateSelected(NetPath("a"), occurrence=0, instant=0),
            FiringBegun(NetPath("a"), occurrence=0, instant=0),
            FiringBegun(NetPath("a"), occurrence=0, instant=0),
        ),
    ],
)
def test_replay_refuses_duplicate_or_mismatched_selection_lifecycle(records):
    with pytest.raises(ValueError, match="selection replay divergence"):
        fold_history(First(), None, records)
