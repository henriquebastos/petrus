"""
Impetus-native tests for inhibitor arcs.

An inhibitor arc gates a transition on the *absence* of matching tokens: it is
satisfied when the place holds fewer than the arc's weight [firing-semantics.md
Enabledness; inhibitor_arc.json note "count < weight"]. It contributes nothing to
the firing binding or to output. Here ``blocker`` inhibits ``gate`` while also
feeding ``drain`` by a consume arc: ``gate`` is blocked until ``drain`` empties
``blocker``, then fires. Oracle-coincident (black tokens, single output arcs), so
``inhibitor_arc.json`` also drives golden replay; the net is inline here to make
the gating intent explicit.
"""

from __future__ import annotations

# Internal imports
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.instance import Instance
from petrus.impetus.petrinet import Arc, ArcMode, Net, NetPath, Place, Transition


class TestInhibitorGating:
    """``blocker`` inhibits ``gate`` and feeds ``drain``; ``trigger`` fires ``gate``."""

    BLOCKER, TRIGGER = NetPath("blocker"), NetPath("trigger")
    DRAIN, GATE = NetPath("drain"), NetPath("gate")
    DRAINED, GATED = NetPath("drained"), NetPath("gated_done")

    def net(self) -> Net:
        return Net(
            places=[Place(self.BLOCKER), Place(self.TRIGGER), Place(self.DRAINED), Place(self.GATED)],
            transitions=[Transition(self.DRAIN), Transition(self.GATE)],
            arcs=[
                Arc(self.BLOCKER, self.DRAIN, ArcMode.CONSUME),
                Arc(self.BLOCKER, self.GATE, ArcMode.INHIBIT),
                Arc(self.TRIGGER, self.GATE, ArcMode.CONSUME),
                Arc(self.DRAIN, self.DRAINED),
                Arc(self.GATE, self.GATED),
            ],
        )

    def seeded(self) -> Instance:
        return Instance(self.net(), Marking.from_counts({self.BLOCKER: 1, self.TRIGGER: 1}))

    def test_inhibited_while_the_place_is_occupied(self):
        # The crux: gate has its trigger token, but blocker's token gates it out.
        instance = self.seeded()
        assert instance.enabled_transitions() == [self.DRAIN]

    def test_becomes_enabled_once_the_inhibiting_place_drains(self):
        # drain consumes blocker; with blocker empty the inhibitor is satisfied
        # and gate becomes enabled.
        instance = self.seeded()
        instance.step()  # fire drain
        assert instance.enabled_transitions() == [self.GATE]

    def test_full_sequence_drains_then_gates_to_termination(self):
        instance = self.seeded()
        instance.run()
        assert instance.is_quiescent
        assert instance.marking == Marking({self.DRAINED: (Token.black(),), self.GATED: (Token.black(),)})
