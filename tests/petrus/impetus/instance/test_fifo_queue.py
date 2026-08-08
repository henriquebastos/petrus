"""
Impetus-native tests for FIFO token queues.

A place is an ordered queue: ``consume`` pops the front, ``deposit`` appends to
the back [marking.py]. Draining a multi-token place therefore takes tokens in
arrival order, and that order is observable both in what each firing consumes and
in how the sink place accumulates. This behavior is oracle-coincident (single
token per firing, single output arc), so ``fifo_queue.json`` is also driven
through golden replay; here the net is built inline to make the ordering intent
explicit.
"""

from __future__ import annotations

# Internal imports
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.instance import Instance
from petrus.impetus.petrinet import Arc, Net, NetPath, Place, Transition


class TestFifoDrain:
    """Three seq-tagged tokens drained one per firing, front to back."""

    QUEUE, TAKE, TAKEN = NetPath("queue"), NetPath("take"), NetPath("taken")

    def net(self) -> Net:
        return Net(
            places=[Place(self.QUEUE), Place(self.TAKEN)],
            transitions=[Transition(self.TAKE)],
            arcs=[Arc(self.QUEUE, self.TAKE), Arc(self.TAKE, self.TAKEN)],
        )

    def seeded(self) -> Instance:
        items = tuple(Token("Item", {"seq": n}) for n in (1, 2, 3))
        return Instance(self.net(), Marking({self.QUEUE: items}))

    def test_each_firing_consumes_the_front_token(self):
        instance = self.seeded()
        firing = instance.step()
        assert firing.consumed == (Token("Item", {"seq": 1}),)
        assert instance.marking.place(self.QUEUE) == (Token("Item", {"seq": 2}), Token("Item", {"seq": 3}))

    def test_sink_accumulates_in_arrival_order(self):
        instance = self.seeded()
        instance.run()
        assert instance.marking.place(self.TAKEN) == tuple(Token("Item", {"seq": n}) for n in (1, 2, 3))
