"""
Impetus-native tests for the ``environment_signal`` fixture's scenario.

A request parks a token awaiting settlement; the outside world delivers a
``WebhookEvent`` to the ``webhook`` source transition; the join transition
``settle`` then consumes both. Three deliberate divergences from the oracle
fixture (``environment_signal.json``), all ratified:

1. The oracle fires the environment transition via ``fire(t, token=payload)``
   (recorded as ``fire_env``); Impetus delivers through the ingress API and
   records the external event before the firing [DR source-transition-ingress].
2. The oracle's ``isAwaiting`` keys on ``awaiting`` place roles, so it stays
   false here; Impetus derives AWAITING from the armed registration on the
   ``webhook`` source [DR termination-instance-status-rule].
3. The oracle merges settle's consumed tokens into one deposit (``done``
   receives only the WebhookEvent); Impetus forwards each consumed token
   per arc, never merging [DR output-production-per-arc-contract].
"""

from __future__ import annotations

# Internal imports
from petrus.impetus.history import replay_marking
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.instance import Instance, Status
from petrus.impetus.petrinet import Arc, Net, NetPath, Place, Transition

START, PENDING, EVENT, DONE = NetPath("start"), NetPath("pending_settlement"), NetPath("event"), NetPath("done")
REQUEST, WEBHOOK, SETTLE = NetPath("request"), NetPath("webhook"), NetPath("settle")
WEBHOOK_EVENT = Token("WebhookEvent", {"event_id": "evt_001", "status": "succeeded"})


def _net() -> Net:
    return Net(
        places=[Place(START), Place(PENDING), Place(EVENT), Place(DONE)],
        transitions=[Transition(REQUEST), Transition(WEBHOOK), Transition(SETTLE)],
        arcs=[
            Arc(START, REQUEST),
            Arc(REQUEST, PENDING),
            Arc(WEBHOOK, EVENT),
            Arc(PENDING, SETTLE),
            Arc(EVENT, SETTLE),
            Arc(SETTLE, DONE),
        ],
    )


def _seeded() -> Instance:
    return Instance(_net(), Marking({START: (Token.black(),)}))


class TestEnvironmentSignal:
    def test_the_net_quiesces_awaiting_the_webhook(self):
        instance = _seeded()
        instance.run()
        assert instance.marking == Marking({PENDING: (Token.black(),)})
        assert instance.status is Status.AWAITING

    def test_delivery_injects_the_event_and_reenables_the_net(self):
        instance = _seeded()
        instance.run()
        instance.deliver(WEBHOOK, WEBHOOK_EVENT)
        assert instance.marking.place(EVENT) == (WEBHOOK_EVENT,)
        assert instance.enabled_transitions() == [SETTLE]
        assert instance.status is Status.RUNNING

    def test_settlement_consumes_the_delivered_event_and_forwards_it(self):
        # done receives both consumed tokens in input-arc order — the black
        # trigger and the delivered event (the oracle merged them into one).
        instance = _seeded()
        instance.run()
        instance.deliver(WEBHOOK, WEBHOOK_EVENT)
        instance.run()
        assert instance.marking == Marking({DONE: (Token.black(), WEBHOOK_EVENT)})

    def test_sealing_the_webhook_lets_the_instance_terminate(self):
        instance = _seeded()
        instance.run()
        instance.deliver(WEBHOOK, WEBHOOK_EVENT)
        instance.run()
        assert instance.status is Status.AWAITING  # the registration is still armed
        instance.seal(WEBHOOK)
        assert instance.status is Status.TERMINATED
        assert replay_marking(instance.history) == instance.marking
