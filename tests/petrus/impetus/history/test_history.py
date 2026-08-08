"""Behavioral tests for the event history and replay-by-re-application."""

from __future__ import annotations

# Pip imports
import pytest

# Internal imports
from petrus.impetus.history import (
    CandidateSelected,
    ExternalEventDelivered,
    FiringBegun,
    FiringCompleted,
    DeliveryRegistrationClosed,
    DeliveryRegistrationOpened,
    TokensConsumed,
    TokensInitialized,
    TokensProduced,
    TokensRead,
    replay_marking,
)
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.petrinet import NetPath


class TestExternalEventDelivered:
    def test_identity_must_be_a_non_empty_string(self):
        # The record enforces its own precondition (the DeliveryRegistration
        # key precedent): an identity that can never tell deliveries apart is
        # refused at construction, so decode inherits the same rejection.
        for bad in ("", 7, None):
            with pytest.raises(ValueError, match="non-empty string identity"):
                ExternalEventDelivered(NetPath("src"), (Token("X"),), identity=bad, occurrence=1)


class TestReplayMarking:
    def test_rebuilds_marking_from_recorded_movements(self):
        a, b = NetPath("a"), NetPath("b")
        token = Token("X")
        history = [
            TokensInitialized(a, (token,)),
            TokensConsumed(a, (token,), occurrence=1),
            TokensProduced(b, (token,), occurrence=1),
        ]
        assert replay_marking(history) == Marking({b: (token,)})

    def test_empty_history_is_an_empty_marking(self):
        assert replay_marking([]) == Marking()

    def test_only_movement_records_affect_the_marking(self):
        # Non-movement records (selection/begin/completion, external events,
        # registration lifecycle) must be inert during replay: a delivered
        # event enters the marking only through the TokensProduced records of
        # the firing it initiated.
        a, b, t, src = NetPath("a"), NetPath("b"), NetPath("t"), NetPath("src")
        token = Token("X")
        with_lifecycle = [
            TokensInitialized(a, (token,)),
            DeliveryRegistrationOpened(src, "default", occurrence=None),
            ExternalEventDelivered(src, (Token("Y"),), identity="occurrence-1", occurrence=1),
            CandidateSelected(t, occurrence=2),
            FiringBegun(t, occurrence=2),
            TokensConsumed(a, (token,), occurrence=2),
            TokensProduced(b, (token,), occurrence=2),
            FiringCompleted(t, occurrence=2),
            DeliveryRegistrationClosed(src, "default", occurrence=None),
        ]
        assert replay_marking(with_lifecycle) == Marking({b: (token,)})

    def test_tokens_read_is_a_movement_category_record_yet_replay_inert(self):
        # Category 5's read fact describes tokens the firing observed WITHOUT
        # moving them: the read tokens never leave their queue, so the fold
        # deliberately applies TokensRead as nothing — the recorded selection
        # is for rebuilding bindings, never for the marking.
        a, gate = NetPath("a"), NetPath("gate")
        settings = Token("Config", {"mode": "strict"})
        history = [
            TokensInitialized(a, (Token("X"),)),
            TokensInitialized(gate, (settings,)),
            TokensConsumed(a, (Token("X"),), occurrence=1),
            TokensRead(gate, (settings,), occurrence=1),
        ]
        assert replay_marking(history) == Marking({gate: (settings,)})

    def test_a_diverging_consume_record_fails_loud(self):
        a = NetPath("a")
        history = [TokensInitialized(a, (Token("X"),)), TokensConsumed(a, (Token("WRONG"),), occurrence=1)]
        with pytest.raises(ValueError, match="replay divergence"):
            replay_marking(history)
