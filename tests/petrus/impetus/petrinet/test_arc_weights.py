"""
Impetus-native tests for weighted consume arcs.

Input-arc weight is honored — a weight-N consume requires and removes N tokens
[spec/firing-semantics.md Enabledness]. Output-arc weight is ignored — deposit is
per-arc, weight never multiplies [traces/README.md observation 1]. Because the
default ``passthrough`` handler forwards *each* consumed token unchanged, never
merging [firing-semantics.md Default behavior], a weight-2 consume through one
output arc deposits TWO tokens — where the Petrus oracle deposits one merged
token. That divergence is the ratified Impetus contract, so ``arc_weights.json``
is oracle-fidelity, not replayed here; this file expresses the Impetus reading
with the net built inline.
"""

from __future__ import annotations

# Internal imports
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.instance import Instance
from petrus.impetus.petrinet import Arc, ArcMode, Net, NetPath, Place, Transition


class TestWeightedConsume:
    """A weight-2 consume arc feeding a single, weight-ignored output arc."""

    SRC, PACK, DST = NetPath("src"), NetPath("pack"), NetPath("dst")

    def net(self) -> Net:
        return Net(
            places=[Place(self.SRC), Place(self.DST)],
            transitions=[Transition(self.PACK)],
            arcs=[
                Arc(self.SRC, self.PACK, ArcMode.CONSUME, weight=2),
                Arc(self.PACK, self.DST, weight=2),  # output weight is ignored
            ],
        )

    def test_enabled_only_when_the_place_holds_at_least_the_weight(self):
        # Enablement needs >= weight tokens; one short is not enabled.
        net = self.net()
        short = Instance(net, Marking.from_counts({self.SRC: 1}))
        assert short.enabled_transitions() == []
        ready = Instance(net, Marking.from_counts({self.SRC: 2}))
        assert ready.enabled_transitions() == [self.PACK]

    def test_firing_consumes_exactly_the_weight(self):
        # Three present, weight two: one firing removes two, leaving one.
        instance = Instance(self.net(), Marking.from_counts({self.SRC: 3}))
        instance.step()
        assert instance.marking.place(self.SRC) == (Token.black(),)

    def test_deposits_one_token_per_consumed_token_never_merged(self):
        # The crux of the arc_weights divergence: 2 tokens consumed -> 2 tokens
        # deposited. The oracle merges them into 1; Impetus never merges.
        instance = Instance(self.net(), Marking.from_counts({self.SRC: 3}))
        instance.step()
        assert instance.marking.place(self.DST) == (Token.black(), Token.black())

    def test_strands_the_remainder_and_terminates(self):
        # After one firing src holds 1 (< weight 2): pack disables and the net
        # quiesces with a token stranded in src -- exactly the oracle's shape,
        # reached for the opposite reason (per-token deposit, not merge).
        instance = Instance(self.net(), Marking.from_counts({self.SRC: 3}))
        instance.run()
        assert instance.is_quiescent
        assert instance.marking == Marking({self.SRC: (Token.black(),), self.DST: (Token.black(),) * 2})
