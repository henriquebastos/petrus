"""
Impetus-native tests for read arcs.

A read arc requires matching token(s) to enable a transition but does not consume
them — the tokens are peeked, staying in place after firing [firing-semantics.md
Enabledness]. Read arcs participate in enablement only; they contribute nothing
to passthrough output [firing-semantics.md Default behavior]. This diverges from
the Petrus oracle, whose read tokens join the consumed list and merge into the
output token (``read_arc.json`` observation 3): there the ``Config`` payload
lands in ``done``; under Impetus only the consumed ``trigger`` token flows, so
``done`` receives the black token and ``config`` keeps ``Config``.

Since the CV3 schema-2 migration, a begin also RECORDS its read selections —
one ``TokensRead`` per read arc, the canonical category-5 fact — replay-inert
for the marking: the read tokens never leave their queue.
"""

from __future__ import annotations

# Pip imports
import pytest

# Internal imports
from petrus.impetus.history import FiringBegun, TokensConsumed, TokensRead, replay_marking
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.instance import Instance
from petrus.impetus.petrinet import Arc, ArcMode, Net, NetPath, Place, Transition


class TestReadArc:
    """A read arc (config) and a consume arc (trigger) feeding one transition."""

    CONFIG, TRIGGER, PROCESS, DONE = NetPath("config"), NetPath("trigger"), NetPath("process"), NetPath("done")
    SETTINGS = Token("Config", {"mode": "strict"})

    def net(self) -> Net:
        return Net(
            places=[Place(self.CONFIG), Place(self.TRIGGER), Place(self.DONE)],
            transitions=[Transition(self.PROCESS)],
            arcs=[
                Arc(self.CONFIG, self.PROCESS, ArcMode.READ),
                Arc(self.TRIGGER, self.PROCESS, ArcMode.CONSUME),
                Arc(self.PROCESS, self.DONE),
            ],
        )

    def seeded(self) -> Instance:
        return Instance(self.net(), Marking({self.CONFIG: (self.SETTINGS,), self.TRIGGER: (Token.black(),)}))

    def test_read_arc_requires_a_matching_token_to_enable(self):
        # trigger is ready, but with config empty the read arc is unsatisfied.
        instance = Instance(self.net(), Marking({self.TRIGGER: (Token.black(),)}))
        assert instance.enabled_transitions() == []

    def test_read_token_is_peeked_not_consumed(self):
        # After firing, config still holds its token -- read never removes.
        instance = self.seeded()
        instance.step()
        assert instance.marking.place(self.CONFIG) == (self.SETTINGS,)

    def test_read_selection_is_carried_in_the_binding(self):
        # The peeked token participates in the binding (ready for guards/filters/
        # timers) but is kept out of what passthrough forwards.
        [binding] = self.seeded().candidates()
        assert binding.read == ((self.CONFIG, (self.SETTINGS,)),)
        assert binding.tokens == (Token.black(),)  # only the consumed trigger flows

    def test_read_contributes_nothing_to_output(self):
        # The crux: only the consumed trigger token is forwarded. The oracle
        # merges Config into done; Impetus forwards only the black trigger token.
        instance = self.seeded()
        instance.step()
        assert instance.marking.place(self.DONE) == (Token.black(),)

    def test_begin_records_the_read_selection_in_the_begin_batch(self):
        # The recorded fact of what the read arc selected — after the
        # consumes, correlated to the same occurrence, in the one begin batch
        # (closes debt 2026-07-09T2330Z's recording half).
        instance = self.seeded()
        occurrence = instance.begin(instance.candidates()[0], at=1)
        assert instance.history.records[-3:] == (
            FiringBegun(self.PROCESS, occurrence=1, instant=1),
            TokensConsumed(self.TRIGGER, (Token.black(),), occurrence=1, instant=1),
            TokensRead(self.CONFIG, (self.SETTINGS,), occurrence=1, instant=1),
        )
        assert occurrence.records == instance.history.records[-3:]

    def test_a_binding_that_consumes_its_own_read_token_cannot_begin(self):
        # The ordering pin on begin's read validation: reads validate against
        # the POST-consume marking. One place feeds the transition through
        # both a consume and a read arc with one matching token — enumeration
        # assembles the overlap binding, and begin refuses it: the firing's
        # own consume falsifies the observation the read asserts. Nothing is
        # appended.
        instance = Instance(self._overlap_net(), Marking({NetPath("a"): (Token("X"),)}))
        [binding] = instance.candidates()
        before = len(instance.history)

        with pytest.raises(ValueError, match=r"cannot read .* from a: token not present"):
            instance.begin(binding)

        assert len(instance.history) == before

    def test_the_read_validates_against_the_surviving_token(self):
        # The passing counterpart: with two equal tokens the consume takes
        # one and the read observes the survivor — the begin batch records
        # both facts, and one token stays in place.
        a, t = NetPath("a"), NetPath("t")
        token = Token("X")
        instance = Instance(self._overlap_net(), Marking({a: (token, token)}))

        instance.begin(instance.candidates()[0], at=1)

        assert instance.history.records[-3:] == (
            FiringBegun(t, occurrence=1, instant=1),
            TokensConsumed(a, (token,), occurrence=1, instant=1),
            TokensRead(a, (token,), occurrence=1, instant=1),
        )
        assert instance.marking == Marking({a: (token,)})

    def _overlap_net(self) -> Net:
        """One place ``a`` feeding ``t`` through BOTH a consume and a read arc."""
        a, t, b = NetPath("a"), NetPath("t"), NetPath("b")
        return Net(
            places=[Place(a), Place(b)],
            transitions=[Transition(t)],
            arcs=[Arc(a, t), Arc(a, t, ArcMode.READ), Arc(t, b)],
        )

    def test_tokens_read_is_replay_inert_for_the_marking(self):
        # Read tokens never leave their queue: replaying the movements over
        # the recorded history — TokensRead included — rebuilds exactly the
        # live marking, with the config token still in place.
        instance = self.seeded()
        instance.step()
        assert any(isinstance(record, TokensRead) for record in instance.history)
        assert replay_marking(instance.history) == instance.marking
        assert replay_marking(instance.history).place(self.CONFIG) == (self.SETTINGS,)
