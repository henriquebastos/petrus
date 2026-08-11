"""
Behavioral tests for ``TokenQueue`` — the pair-holding FIFO queue at one place.

The queue is the one home of queue semantics [ES-012 session-2 ruling]: it
holds ``(token, entry instant)`` pairs, owns front-most-equal-occurrence
removal, and keeps positions indexing both halves — the alignment contract
enabledness depends on (a selection's positions must index the entry
instants). ``Marking`` is its time-blind view; ``entry_instants`` its time
view; the live instance maintains the same structure incrementally.
"""

from __future__ import annotations

# Python imports
from collections.abc import Sequence

# Pip imports
import pytest

# Internal imports
from petrus.impetus.petrinet import Token, TokenNotPresent, TokenQueue
from petrus.impetus.scope import LifecycleScope


class TestDeposit:
    def test_deposit_appends_to_the_back_and_is_immutable(self):
        queue = TokenQueue()

        first = queue.deposit(Token("A"), 1)
        second = first.deposit(Token("B"), 2)

        assert second.tokens == (Token("A"), Token("B")), "FIFO: deposits append to the back"
        assert first.tokens == (Token("A"),), "original queue must be untouched"
        assert not queue, "the empty original must stay empty"

    def test_positions_index_tokens_and_instants_alike(self):
        # The alignment contract: enabledness returns queue positions that
        # must index the entry instants — one structure keeps them aligned
        # by construction.
        queue = TokenQueue().deposit(Token("A"), 3).deposit(Token("B"), 7)

        assert queue[0] == Token("A")
        assert queue[1] == Token("B")
        assert queue.instants == (3, 7)


class TestRemove:
    def test_remove_takes_the_front_most_equal_occurrence(self):
        # Equal tokens are indistinguishable values: removal matches the
        # FRONT-MOST equal occurrence, so the rest keeps its queue order.
        queue = TokenQueue().deposit(Token.black(), 1).deposit(Token.black(), 2)

        remaining = queue.remove((Token.black(),))

        assert remaining.tokens == (Token.black(),)
        assert remaining.instants == (2,), "the front occurrence left; its instant left with it"

    def test_remove_matches_on_the_token_half_mid_queue(self):
        queue = TokenQueue().deposit(Token("A"), 1).deposit(Token("B"), 2).deposit(Token("C"), 3)

        remaining = queue.remove((Token("B"),))

        assert remaining.tokens == (Token("A"), Token("C")), "the rest keeps its queue order"
        assert remaining.instants == (1, 3), "instants travel with their tokens"
        assert queue.tokens == (Token("A"), Token("B"), Token("C")), "original queue must be untouched"

    def test_removals_apply_in_request_order(self):
        queue = TokenQueue().deposit(Token("A"), 1).deposit(Token("A"), 2).deposit(Token("B"), 3)

        remaining = queue.remove((Token("A"), Token("A")))

        assert remaining.tokens == (Token("B"),)
        assert remaining.instants == (3,)

    def test_removing_a_token_not_present_fails_loud(self):
        # A queue that silently under-delivers would be a footgun — the
        # fail-loud half of the remove contract, and the rejection carries
        # the token so seams can re-address it.
        queue = TokenQueue().deposit(Token("A"), 1)

        with pytest.raises(TokenNotPresent, match="not present") as caught:
            queue.remove((Token("B"),))

        assert caught.value.token == Token("B")
        assert isinstance(caught.value, ValueError), "callers catching ValueError keep working"
        assert queue.tokens == (Token("A"),), "a failed removal leaves the queue untouched"

    def test_removing_more_occurrences_than_present_fails_loud(self):
        queue = TokenQueue().deposit(Token.black(), 1)
        with pytest.raises(TokenNotPresent, match="not present"):
            queue.remove((Token.black(), Token.black()))


class TestSequenceSurface:
    def test_the_sequence_surface_is_the_token_half(self):
        queue = TokenQueue().deposit(Token("A"), 1).deposit(Token("B"), 2)

        assert isinstance(queue, Sequence)
        assert len(queue) == 2
        assert list(queue) == [Token("A"), Token("B")]
        assert Token("B") in queue
        assert queue.index(Token("B")) == 1

    def test_slicing_keeps_the_pairs_together(self):
        queue = TokenQueue().deposit(Token("A"), 1).deposit(Token("B"), 2).deposit(Token("C"), 3)

        tail = queue[1:]

        assert isinstance(tail, TokenQueue)
        assert tail.tokens == (Token("B"), Token("C"))
        assert tail.instants == (2, 3)

    def test_truthiness_reflects_emptiness(self):
        assert not TokenQueue()
        assert TokenQueue().deposit(Token.black(), 0)


class TestAdmittedBy:
    def test_positions_of_admitted_tokens_front_to_back(self):
        # Positions, not tokens: a selection's positions also index the
        # entry instants — the alignment contract. The admission judgment
        # arrives bound (enabledness owns the rule; the queue owns the scan).
        queue = TokenQueue().deposit(Token("A"), 1).deposit(Token("B"), 2).deposit(Token("A"), 3)

        assert queue.admitted_by(lambda token: token.color == "A") == (0, 2)

    def test_limit_stops_the_scan_where_the_caller_needs_no_more(self):
        queue = TokenQueue().deposit(Token("A"), 1).deposit(Token("A"), 2).deposit(Token("A"), 3)

        assert queue.admitted_by(lambda token: True, limit=2) == (0, 1)

    def test_limit_one_accepts_exactly_the_first_admitted_token(self):
        queue = TokenQueue().deposit(Token("no"), 1).deposit(Token("yes"), 2).deposit(Token("yes"), 3)

        assert queue.admitted_by(lambda token: token.color == "yes", limit=1) == (1,)

    def test_nothing_admitted_is_an_empty_owned_value(self):
        queue = TokenQueue().deposit(Token("A"), 1)

        assert queue.admitted_by(lambda token: False) == ()

    def test_a_non_positive_limit_is_rejected(self):
        # limit=0 would fall through the stop condition and silently mean
        # "all of them" — over-delivering on the words "needs no more". A
        # caller who needs none should not scan [convention 3].
        queue = TokenQueue().deposit(Token("A"), 1)

        with pytest.raises(ValueError, match="positive limit"):
            queue.admitted_by(lambda token: True, limit=0)


class TestValueSemantics:
    def test_equality_compares_both_halves(self):
        # The queue IS the pair structure: same tokens at different entry
        # instants are different queues (time-blind comparison is the
        # Marking view's job, not this value's).
        at_one = TokenQueue().deposit(Token("A"), 1)
        assert at_one == TokenQueue().deposit(Token("A"), 1)
        assert at_one != TokenQueue().deposit(Token("A"), 2)
        assert at_one != TokenQueue().deposit(Token("B"), 1)

    def test_construction_from_pairs_round_trips(self):
        queue = TokenQueue([(Token("A"), 1), (Token("B"), 2)])
        assert queue == TokenQueue().deposit(Token("A"), 1).deposit(Token("B"), 2)

    def test_durable_provenance_does_not_change_the_established_public_value_or_repr_surface(self):
        token = Token("A")
        enriched = TokenQueue([(token, 1, 17, LifecycleScope("draft", 2))])

        assert enriched == TokenQueue([(token, 1)])
        assert repr(enriched) == "TokenQueue([(Token('A', None), 1)])"
        assert enriched.identities == (17,)
        assert enriched.scopes == (LifecycleScope("draft", 2),)

    def test_a_time_blind_queue_records_no_instants(self):
        # The marking's spelling: queue work on the token half alone, every
        # entry instant None — unrecorded, never the epoch.
        queue = TokenQueue.time_blind((Token("A"), Token("B")))
        assert queue.tokens == (Token("A"), Token("B"))
        assert queue.instants == (None, None)
