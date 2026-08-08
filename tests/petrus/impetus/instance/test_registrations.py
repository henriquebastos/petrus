"""
Behavioral tests for the delivery registration lifecycle and the
AWAITING status leg.

A registration is the runtime's standing capability to deliver an external
event to a source transition, identified by its source and a caller-chosen
key [DR 2026-07-08 termination-instance-status-rule, amended by DR
source-transition-ingress]. One registration per source auto-opens at
instantiation under the "default" key; a handler's result envelope opens and
closes registrations — the ``HandlerResult`` envelope, handlers drive the
lifecycle — and ``seal`` is the runtime-policy close-all (Navigator rulings,
slices 8 and 10b). Open and close are recorded process facts, because status
can flip on a registration close with zero net activity. Armed = opened and
not yet closed; ``deliver`` requires at least one armed registration. When
quiescent: COMPLETED if the declared condition holds, else AWAITING if any
registration is armed, else STUCK (condition declared) or TERMINATED
(neutral collapse).
"""

from __future__ import annotations

# Pip imports
import pytest

# Internal imports
from petrus.impetus.binding import HandlerResult
from petrus.impetus.history import (
    InstanceCreated,
    FiringCompleted,
    DeliveryRegistration,
    DeliveryRegistrationClosed,
    DeliveryRegistrationOpened,
    TokensInitialized,
    TokensProduced,
    replay_marking,
)
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.instance import Instance, Status
from petrus.impetus.petrinet import Arc, Cel, Net, NetPath, Place, Transition

EVENT, DONE = NetPath("event"), NetPath("done")
WEBHOOK, SETTLE = NetPath("webhook"), NetPath("settle")


def _webhook_net(completion: Cel | None = None) -> Net:
    """webhook (source) -> event -> settle -> done."""
    return Net(
        places=[Place(EVENT), Place(DONE)],
        transitions=[Transition(WEBHOOK), Transition(SETTLE)],
        arcs=[Arc(WEBHOOK, EVENT), Arc(EVENT, SETTLE), Arc(SETTLE, DONE)],
        completion=completion,
    )


class TestDeliveryRegistrationIdentity:
    def test_a_source_spelling_normalizes_to_its_netpath_identity(self):
        # DeliveryRegistration is an identity value: the same registration spelled two
        # ways must compare equal, so the spelling resolves at construction.
        assert DeliveryRegistration("webhook", "sub") == DeliveryRegistration(WEBHOOK, "sub")

    def test_an_empty_key_is_rejected(self):
        with pytest.raises(ValueError, match=r"DeliveryRegistration requires a non-empty string key"):
            DeliveryRegistration(WEBHOOK, "")

    def test_a_non_string_key_is_rejected(self):
        with pytest.raises(ValueError, match=r"DeliveryRegistration requires a non-empty string key"):
            DeliveryRegistration(WEBHOOK, 7)


class TestDeliveryRegistrationLifecycle:
    def test_construction_opens_one_default_registration_per_source_in_stable_order(self):
        # Initial tokens precede the registration opens; sources record in
        # path-sorted order regardless of declaration order. occurrence=None
        # spells the birthplace honestly: no firing caused an instantiation
        # open.
        b_src, a_src, p, q = NetPath("b_src"), NetPath("a_src"), NetPath("p"), NetPath("q")
        net = Net(
            places=[Place(p), Place(q)],
            transitions=[Transition(b_src), Transition(a_src)],
            arcs=[Arc(b_src, p), Arc(a_src, q)],
        )
        instance = Instance(net, Marking({p: (Token.black(),)}))
        assert instance.history.records == (
            InstanceCreated(instance.instance_id),
            TokensInitialized(p, (Token.black(),)),
            DeliveryRegistrationOpened(a_src, "default", occurrence=None),
            DeliveryRegistrationOpened(b_src, "default", occurrence=None),
        )

    def test_seal_records_the_registration_close(self):
        instance = Instance(_webhook_net())
        instance.seal(WEBHOOK)
        assert instance.history.records[-1] == DeliveryRegistrationClosed(WEBHOOK, "default", occurrence=None)

    def test_sealing_with_no_armed_registration_is_rejected(self):
        instance = Instance(_webhook_net())
        instance.seal(WEBHOOK)
        with pytest.raises(ValueError, match=r"cannot seal source transition webhook: no armed delivery registration"):
            instance.seal(WEBHOOK)

    def test_sealing_a_non_source_transition_is_rejected(self):
        # The rejection discriminates like its sibling deliver(): a real
        # transition that merely has input arcs is a concept error, not a typo.
        instance = Instance(_webhook_net())
        with pytest.raises(ValueError, match=r"cannot seal transition settle: it has input arcs"):
            instance.seal(SETTLE)

    def test_sealing_an_unknown_transition_is_rejected(self):
        instance = Instance(_webhook_net())
        with pytest.raises(ValueError, match=r"cannot seal nowhere: not a transition of this net"):
            instance.seal("nowhere")

    def test_delivery_with_no_armed_registration_is_rejected(self):
        instance = Instance(_webhook_net())
        instance.seal(WEBHOOK)
        with pytest.raises(
            ValueError, match=r"cannot deliver to source transition webhook: no armed delivery registration"
        ):
            instance.deliver(WEBHOOK, Token("X"))


class TestArmedProjection:
    """The armed registrations made public: which doors deliver() can land on — the read an Engine sensor observation decides by."""

    def test_armed_exposes_each_armed_source_with_its_open_keys(self):
        instance = Instance(_webhook_net())

        assert instance.armed == {WEBHOOK: frozenset({"default"})}

    def test_a_sealed_source_leaves_the_projection(self):
        # The name is the whole contract: armed holds exactly the doors a
        # delivery can land on, so a fully sealed instance reads empty and
        # the natural boolean read (`if instance.armed`) never lies —
        # source-ness stays the net's question, not this projection's.
        instance = Instance(_webhook_net())
        instance.seal(WEBHOOK)

        assert instance.armed == {}
        assert not instance.armed

    def test_armed_is_structurally_read_only(self):
        # A read-only mapping of frozen values [convention 2]: neither layer
        # takes a write, and the instance never moves through a snapshot.
        instance = Instance(_webhook_net())

        snapshot = instance.armed
        with pytest.raises(TypeError):
            snapshot[WEBHOOK] = frozenset({"smuggled"})
        with pytest.raises(AttributeError):
            snapshot[WEBHOOK].add("smuggled")

        assert instance.armed == {WEBHOOK: frozenset({"default"})}


class TestHandlerDrivenLifecycle:
    """DeliveryRegistration open/close effects ride the handler-result envelope."""

    REQUESTS, EVENTS = NetPath("requests"), NetPath("events")
    SUBSCRIBE = NetPath("subscribe")

    def net(self) -> Net:
        """requests -> subscribe (handled) -> events <- webhook (source)."""
        return Net(
            places=[Place(self.REQUESTS), Place(self.EVENTS)],
            transitions=[Transition(self.SUBSCRIBE, handler="hook"), Transition(WEBHOOK)],
            arcs=[Arc(self.REQUESTS, self.SUBSCRIBE), Arc(self.SUBSCRIBE, self.EVENTS), Arc(WEBHOOK, self.EVENTS)],
        )

    def instance(self, hook) -> Instance:
        return Instance(self.net(), Marking({self.REQUESTS: (Token.black(),)}), handlers={"hook": hook})

    def test_a_handler_result_opens_a_registration_on_a_source(self):
        # Subscribe-on-result: a scheduled transition's handler arms a second
        # registration on the webhook source; the open is a recorded fact
        # correlated to the firing that caused it.
        instance = self.instance(lambda b, outputs: HandlerResult(opens=(DeliveryRegistration(WEBHOOK, "sub"),)))
        firing = instance.step()
        assert DeliveryRegistrationOpened(WEBHOOK, "sub", occurrence=firing.occurrence) in instance.history.records

    def test_two_registrations_close_independently(self):
        # Unsubscribe-on-final: the webhook's own handler closes only the
        # subscription it is done with; the default registration keeps the
        # source deliverable and the instance AWAITING.
        def hook(binding, outputs):
            if binding.transition == self.SUBSCRIBE:
                return HandlerResult(opens=(DeliveryRegistration(WEBHOOK, "sub"),))
            final = binding.tokens[0].color == "Final"
            return HandlerResult(
                {self.EVENTS: binding.tokens}, closes=(DeliveryRegistration(WEBHOOK, "sub"),) if final else ()
            )

        net = Net(
            places=[Place(self.REQUESTS), Place(self.EVENTS)],
            transitions=[Transition(self.SUBSCRIBE, handler="hook"), Transition(WEBHOOK, handler="hook")],
            arcs=[Arc(self.REQUESTS, self.SUBSCRIBE), Arc(WEBHOOK, self.EVENTS)],
        )
        instance = Instance(net, Marking({self.REQUESTS: (Token.black(),)}), handlers={"hook": hook})
        instance.run()
        firing = instance.deliver(WEBHOOK, Token("Final"))
        assert DeliveryRegistrationClosed(WEBHOOK, "sub", occurrence=firing.occurrence) in instance.history.records
        assert instance.status is Status.AWAITING
        instance.deliver(WEBHOOK, Token("X"))  # the default registration still delivers

    def test_a_handler_closing_the_last_registration_stops_delivery(self):
        # The source's own handler unsubscribes the default registration: the
        # instance no longer waits and delivery is refused — handlers, not
        # only runtime policy, can let the net terminate.
        hook = lambda b, outputs: HandlerResult(  # noqa: E731
            {self.EVENTS: b.tokens}, closes=(DeliveryRegistration(WEBHOOK, "default"),)
        )
        net = Net(
            places=[Place(self.EVENTS)],
            transitions=[Transition(WEBHOOK, handler="hook")],
            arcs=[Arc(WEBHOOK, self.EVENTS)],
        )
        instance = Instance(net, handlers={"hook": hook})
        instance.deliver(WEBHOOK, Token("X"))
        assert instance.status is Status.TERMINATED
        with pytest.raises(ValueError, match=r"no armed delivery registration"):
            instance.deliver(WEBHOOK, Token("X"))

    def test_a_handler_open_rearms_a_sealed_source(self):
        # Seal is close-all, not a permanent state (a Navigator ruling): a
        # later result envelope re-arms the source, and delivery resumes.
        instance = self.instance(lambda b, outputs: HandlerResult(opens=(DeliveryRegistration(WEBHOOK, "sub"),)))
        instance.seal(WEBHOOK)
        assert instance.status is Status.RUNNING  # subscribe is still enabled
        instance.step()
        assert instance.status is Status.AWAITING
        instance.deliver(WEBHOOK, Token("X"))
        assert instance.marking.place(self.EVENTS) == (Token("X"),)

    def test_seal_closes_every_armed_registration(self):
        # The runtime-policy close-all: one close record per armed
        # registration, key-sorted, occurrence=None — no firing caused them.
        instance = self.instance(lambda b, outputs: HandlerResult(opens=(DeliveryRegistration(WEBHOOK, "sub"),)))
        instance.step()
        instance.seal(WEBHOOK)
        assert instance.history.records[-2:] == (
            DeliveryRegistrationClosed(WEBHOOK, "default", occurrence=None),
            DeliveryRegistrationClosed(WEBHOOK, "sub", occurrence=None),
        )
        assert instance.status is Status.TERMINATED

    def test_closes_apply_before_opens_so_one_result_refreshes_a_key(self):
        # The ruled apply order: a handler may close and re-open the same key
        # in one result envelope — the close records before the open.
        instance = self.instance(
            lambda b, outputs: HandlerResult(
                closes=(DeliveryRegistration(WEBHOOK, "default"),), opens=(DeliveryRegistration(WEBHOOK, "default"),)
            )
        )
        firing = instance.step()
        assert instance.history.records[-3:] == (
            DeliveryRegistrationClosed(WEBHOOK, "default", occurrence=firing.occurrence),
            DeliveryRegistrationOpened(WEBHOOK, "default", occurrence=firing.occurrence),
            FiringCompleted(self.SUBSCRIBE, occurrence=firing.occurrence),
        )
        assert instance.status is Status.AWAITING

    def test_the_committed_effects_follow_the_movements_as_their_own_records(self):
        # The envelope's effects commit inside the atomic completion boundary
        # — after the token movements, before the terminal record — each as
        # its own occurrence-correlated fact; the handler's deterministic
        # projection is represented directly by these records, with no
        # separate result record [DR 2026-07-14 activity-invocation-runtime-
        # seam: the handler is a bridge, not a third durable lifecycle].
        instance = self.instance(
            lambda b, outputs: HandlerResult(
                {self.EVENTS: (Token("X"),)}, opens=(DeliveryRegistration(WEBHOOK, "sub"),)
            )
        )
        firing = instance.step()
        assert instance.history.records[-3:] == (
            TokensProduced(self.EVENTS, (Token("X"),), occurrence=firing.occurrence),
            DeliveryRegistrationOpened(WEBHOOK, "sub", occurrence=firing.occurrence),
            FiringCompleted(self.SUBSCRIBE, occurrence=firing.occurrence),
        )

    def test_a_tokens_only_envelope_is_the_bare_mapping(self):
        # The bare mapping stays legal sugar: both spellings of an effect-free
        # result leave identical history and marking.
        bare = self.instance(lambda b, outputs: {self.EVENTS: (Token("X"),)})
        wrapped = self.instance(lambda b, outputs: HandlerResult({self.EVENTS: (Token("X"),)}))
        bare.step()
        wrapped.step()
        # records[1:]: the identity facts differ by minted id, deliberately.
        assert bare.history.records[1:] == wrapped.history.records[1:]
        assert bare.marking == wrapped.marking

    def test_registration_records_are_inert_during_replay(self):
        instance = self.instance(
            lambda b, outputs: HandlerResult(
                {self.EVENTS: (Token("X"),)}, opens=(DeliveryRegistration(WEBHOOK, "sub"),)
            )
        )
        instance.step()
        instance.seal(WEBHOOK)
        assert replay_marking(instance.history) == instance.marking


class TestEffectValidation:
    """Invalid delivery-registration effects fail loud before anything is appended."""

    REQUESTS, EVENTS = NetPath("requests"), NetPath("events")
    SUBSCRIBE = NetPath("subscribe")

    def begun(self):
        """An in-flight occurrence on the handled ``subscribe`` transition."""
        net = Net(
            places=[Place(self.REQUESTS), Place(self.EVENTS)],
            transitions=[Transition(self.SUBSCRIBE, handler="hook"), Transition(WEBHOOK)],
            arcs=[Arc(self.REQUESTS, self.SUBSCRIBE), Arc(WEBHOOK, self.EVENTS)],
        )
        instance = Instance(net, Marking({self.REQUESTS: (Token.black(),)}), handlers={"hook": lambda b, outputs: {}})
        [binding] = instance.candidates()
        return instance, instance.begin(binding)

    def test_closing_a_registration_that_is_not_armed_is_rejected(self):
        instance, occurrence = self.begun()
        with pytest.raises(
            ValueError,
            match=r"cannot complete firing occurrence 1 \(subscribe\): "
            r"close of delivery registration 'sub' on webhook: not armed",
        ):
            instance.complete(occurrence, HandlerResult(closes=(DeliveryRegistration(WEBHOOK, "sub"),)))

    def test_opening_an_already_armed_registration_is_rejected(self):
        instance, occurrence = self.begun()
        with pytest.raises(
            ValueError,
            match=r"cannot complete firing occurrence 1 \(subscribe\): "
            r"open of delivery registration 'default' on webhook: already armed",
        ):
            instance.complete(occurrence, HandlerResult(opens=(DeliveryRegistration(WEBHOOK, "default"),)))

    def test_an_effect_on_an_unknown_transition_is_rejected(self):
        instance, occurrence = self.begun()
        with pytest.raises(
            ValueError,
            match=r"cannot complete firing occurrence 1 \(subscribe\): "
            r"delivery-registration effect on nowhere: not a transition of this net",
        ):
            instance.complete(occurrence, HandlerResult(opens=(DeliveryRegistration("nowhere", "sub"),)))

    def test_an_effect_on_a_non_source_transition_is_rejected(self):
        instance, occurrence = self.begun()
        with pytest.raises(
            ValueError,
            match=r"cannot complete firing occurrence 1 \(subscribe\): delivery-registration effect on transition subscribe: "
            r"it has input arcs — only a source transition has delivery registrations",
        ):
            instance.complete(occurrence, HandlerResult(opens=(DeliveryRegistration(self.SUBSCRIBE, "sub"),)))

    def test_a_non_registration_effect_is_rejected(self):
        # The seam where handler-owned data enters the kernel checks its
        # elements, like deliver() does for tokens.
        instance, occurrence = self.begun()
        with pytest.raises(
            ValueError,
            match=r"cannot complete firing occurrence 1 \(subscribe\): "
            r"every delivery-registration effect must be a DeliveryRegistration",
        ):
            instance.complete(occurrence, HandlerResult(opens=((WEBHOOK, "sub"),)))

    def test_effects_on_a_pure_projection_are_legal_recorded_facts(self):
        # The retired rule's replacement, pinned: effects no longer "ride an
        # observed result" — they are canonical records in the completion
        # batch, so a pure deterministic projection may carry them (a source
        # transition's projection legitimately closes its own registration
        # [DR 2026-07-14 source-delivery-projection-and-identity]).
        p, q, t = NetPath("p"), NetPath("q"), NetPath("t")
        net = Net(
            places=[Place(p), Place(q)],
            transitions=[Transition(t), Transition(WEBHOOK)],
            arcs=[Arc(p, t), Arc(t, q), Arc(WEBHOOK, q)],
        )
        instance = Instance(net, Marking({p: (Token.black(),)}))
        [binding] = instance.candidates()
        occurrence = instance.begin(binding)

        firing = instance.complete(occurrence, HandlerResult(closes=(DeliveryRegistration(WEBHOOK, "default"),)))

        assert DeliveryRegistrationClosed(WEBHOOK, "default", occurrence=firing.occurrence) in instance.history.records
        assert WEBHOOK not in instance.armed

    def test_a_rejected_effect_leaves_nothing_appended_and_the_occurrence_in_flight(self):
        # Fail loud BEFORE the first append (a Navigator ruling): the history
        # takes no partial fact, and the runtime still owns the occurrence — it
        # can fail() it with the error as a value.
        instance, occurrence = self.begun()
        before = instance.history.records
        with pytest.raises(ValueError, match=r"not armed"):
            instance.complete(occurrence, HandlerResult(closes=(DeliveryRegistration(WEBHOOK, "sub"),)))
        assert instance.history.records == before
        assert instance.in_flight == (occurrence,)
        instance.fail(occurrence, "ValueError('close of an unarmed registration')")
        assert instance.in_flight == ()


class TestAwaitingStatus:
    def test_quiescent_with_an_armed_registration_is_awaiting(self):
        # Nothing enabled, no condition declared — but the runtime may still
        # deliver, so the instance waits instead of collapsing to TERMINATED.
        instance = Instance(_webhook_net())
        assert instance.is_quiescent
        assert instance.status is Status.AWAITING

    def test_running_outranks_awaiting(self):
        instance = Instance(_webhook_net(), Marking({EVENT: (Token.black(),)}))
        assert instance.status is Status.RUNNING

    def test_completion_outranks_an_armed_registration(self):
        # ES-006 S4: work done under a standing subscription is COMPLETED —
        # a never-closed registration cannot mask completion.
        instance = Instance(_webhook_net(Cel("size(done) == 1")), Marking({EVENT: (Token.black(),)}))
        instance.run()
        assert instance.status is Status.COMPLETED

    def test_awaiting_when_the_declared_condition_does_not_hold(self):
        instance = Instance(_webhook_net(Cel("size(done) == 1")))
        assert instance.status is Status.AWAITING

    def test_seal_flips_status_with_zero_net_activity(self):
        # ES-006 S11: the runtime closes the registration (no answer is
        # coming) — status flips AWAITING -> STUCK on that append alone.
        instance = Instance(_webhook_net(Cel("size(done) == 1")))
        before = instance.marking
        assert instance.status is Status.AWAITING
        instance.seal(WEBHOOK)
        assert instance.status is Status.STUCK
        assert instance.marking == before

    def test_sealed_with_no_condition_collapses_to_terminated(self):
        instance = Instance(_webhook_net())
        instance.seal(WEBHOOK)
        assert instance.status is Status.TERMINATED

    def test_one_armed_source_among_sealed_ones_keeps_the_instance_awaiting(self):
        # Waiting is any-armed, not all: sealing one of two sources leaves the
        # other's registration holding the instance in AWAITING.
        a_src, b_src, p, q = NetPath("a_src"), NetPath("b_src"), NetPath("p"), NetPath("q")
        net = Net(
            places=[Place(p), Place(q)],
            transitions=[Transition(a_src), Transition(b_src)],
            arcs=[Arc(a_src, p), Arc(b_src, q)],
        )
        instance = Instance(net)
        instance.seal(a_src)
        assert instance.status is Status.AWAITING
        instance.seal(b_src)
        assert instance.status is Status.TERMINATED
