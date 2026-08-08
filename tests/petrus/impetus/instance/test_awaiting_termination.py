"""
Impetus-native tests for the ``awaiting_termination`` fixture's scenario.

After ``begin`` fires, a sink place holds a token and nothing is enabled — yet
the instance is not done: an external resolution is still expected. The oracle
fixture (``awaiting_termination.json``) modeled the wait as an ``awaiting``
place role; Impetus derives the same verdict from the armed registration on
the ``resolve`` source transition [DR termination-instance-status-rule,
DR source-transition-ingress]. Two further ratified divergences: the oracle
clears ``isAwaiting`` the moment the awaiting place drains, where Impetus
waits for the registration to close (the runtime, not the marking, knows no
more events are coming); and the oracle merges ``finish``'s two consumed
tokens into one deposit, where Impetus forwards both
[DR output-production-per-arc-contract].
"""

from __future__ import annotations

# Internal imports
from petrus.impetus.history import replay_marking
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.instance import Instance, Status
from petrus.impetus.petrinet import Arc, Net, NetPath, Place, Transition

START, WAITING, PROGRESSED = NetPath("start"), NetPath("waiting"), NetPath("progressed")
RESOLUTION, DONE = NetPath("resolution"), NetPath("done")
BEGIN, RESOLVE, FINISH = NetPath("begin"), NetPath("resolve"), NetPath("finish")


def _net() -> Net:
    return Net(
        places=[Place(START), Place(WAITING), Place(PROGRESSED), Place(RESOLUTION), Place(DONE)],
        transitions=[Transition(BEGIN), Transition(RESOLVE), Transition(FINISH)],
        arcs=[
            Arc(START, BEGIN),
            Arc(BEGIN, WAITING),
            Arc(BEGIN, PROGRESSED),
            Arc(RESOLVE, RESOLUTION),
            Arc(WAITING, FINISH),
            Arc(RESOLUTION, FINISH),
            Arc(FINISH, DONE),
        ],
    )


def _seeded() -> Instance:
    return Instance(_net(), Marking({START: (Token.black(),)}))


class TestAwaitingTermination:
    def test_quiescent_with_parked_work_is_awaiting_not_terminated(self):
        # The fixture's payload step: a sink place (progressed) holds a token
        # and nothing is enabled, yet the instance is waiting, not done.
        instance = _seeded()
        instance.run()
        assert instance.marking == Marking({WAITING: (Token.black(),), PROGRESSED: (Token.black(),)})
        assert instance.is_quiescent
        assert instance.status is Status.AWAITING

    def test_external_resolution_reenables_the_join(self):
        instance = _seeded()
        instance.run()
        instance.deliver(RESOLVE, Token.black())
        assert instance.marking.place(RESOLUTION) == (Token.black(),)
        assert instance.enabled_transitions() == [FINISH]

    def test_resolution_drains_the_wait_and_the_seal_terminates(self):
        # finish forwards BOTH consumed tokens to done (the oracle merged them
        # into one); the instance stays AWAITING until the registration closes
        # — the runtime, not the marking, knows no more events are coming.
        instance = _seeded()
        instance.run()
        instance.deliver(RESOLVE, Token.black())
        instance.run()
        assert instance.marking == Marking({DONE: (Token.black(), Token.black()), PROGRESSED: (Token.black(),)})
        assert instance.status is Status.AWAITING
        instance.seal(RESOLVE)
        assert instance.status is Status.TERMINATED
        assert replay_marking(instance.history) == instance.marking
