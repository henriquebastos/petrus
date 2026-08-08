"""Behavioral tests for Token and the immutable Marking."""

from __future__ import annotations

# Pip imports
import pytest

# Internal imports
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.petrinet import NetPath


# ── Token ────────────────────────────────────────────────────


class TestToken:
    def test_black_token_has_no_color(self):
        t = Token.black()
        assert t.is_black
        assert t.color is None

    def test_black_token_equals_empty_token(self):
        assert Token.black() == Token()

    def test_colored_token_carries_color_and_data(self):
        t = Token("Payment", {"amount": 150})
        assert not t.is_black
        assert t.color == "Payment"
        assert t.data == {"amount": 150}

    def test_equality_is_by_value(self):
        assert Token("Payment", {"amount": 1}) == Token("Payment", {"amount": 1})
        assert Token("Payment", {"amount": 1}) != Token("Payment", {"amount": 2})


# ── Marking ──────────────────────────────────────────────────


class TestMarking:
    def test_from_counts_creates_black_tokens(self):
        p = NetPath("a")
        m = Marking.from_counts({p: 2})
        assert m.place(p) == (Token.black(), Token.black())

    def test_missing_place_is_empty(self):
        assert Marking().place(NetPath("nope")) == ()

    def test_empty_places_are_dropped(self):
        p = NetPath("a")
        assert Marking({p: ()}) == Marking()

    def test_consume_removes_the_requested_tokens_and_is_immutable(self):
        # Selection happens in enabledness; consume removes exactly the tokens
        # the binding selected -- which colored selection may pick mid-queue.
        p = NetPath("a")
        first, second, third = Token("A"), Token("B"), Token("C")
        m = Marking({p: (first, second, third)})

        after = m.consume(p, (second,))

        assert after.place(p) == (first, third), "the rest keeps its queue order"
        assert m.place(p) == (first, second, third), "original marking must be untouched"

    def test_consuming_equal_tokens_removes_one_occurrence_each(self):
        p = NetPath("a")
        m = Marking({p: (Token.black(), Token.black())})
        assert m.consume(p, (Token.black(),)).place(p) == (Token.black(),)
        assert m.consume(p, (Token.black(), Token.black())) == Marking()

    def test_consuming_the_last_token_drops_the_place(self):
        p = NetPath("a")
        after = Marking({p: (Token.black(),)}).consume(p, (Token.black(),))
        assert after == Marking()

    def test_deposit_appends_and_is_immutable(self):
        p = NetPath("a")
        m = Marking({p: (Token("A"),)})

        after = m.deposit(p, Token("B"))

        assert after.place(p) == (Token("A"), Token("B"))
        assert m.place(p) == (Token("A"),), "original marking must be untouched"

    def test_counts_reports_queue_lengths(self):
        a, b = NetPath("a"), NetPath("b")
        m = Marking({a: (Token.black(), Token.black()), b: (Token.black(),)})
        assert m.counts() == {a: 2, b: 1}

    def test_consuming_a_token_not_present_fails_loud(self):
        # A consume that silently under-delivers would be a footgun; the
        # binding's selection guarantees presence before firing.
        p = NetPath("a")
        with pytest.raises(ValueError, match="not present"):
            Marking({p: (Token("A"),)}).consume(p, (Token("B"),))

    def test_consuming_more_occurrences_than_present_fails_loud(self):
        p = NetPath("a")
        with pytest.raises(ValueError, match="not present"):
            Marking({p: (Token.black(),)}).consume(p, (Token.black(), Token.black()))

    def test_truthiness_reflects_emptiness(self):
        assert not Marking()
        assert Marking({NetPath("a"): (Token.black(),)})
