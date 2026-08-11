"""
Behavioral tests for the activity-invocation seam [DR 2026-07-14
activity-invocation-runtime-seam].

An impure transition binds an ``ActivityHandler`` — the server-side,
Petri-aware bridge: ``prepare(binding)`` deterministically produces one
Petri-agnostic ``ActivityInvocation`` before anything is appended, the begin
batch freezes it as ``ActivityRequested`` (the authoritative outbox), an
execution adapter runs the named activity and its terminal result is frozen
as ``ActivityCompleted`` — its own append, BEFORE deterministic projection —
and ``project(binding, result)`` maps the frozen result into the atomic
completion boundary (tokens, delivery-registration effects, the terminal
record). Exhausted execution is ``ActivityFailed`` + ``FiringFailed`` in one
batch, distinct from a typed business result. Purity is the binding's:
a plain callable bound to a named symbol is a pure deterministic projection
(no activity records — its effects ARE the projection); impure means exactly
"bound to an ActivityHandler" [DR 2026-07-14
source-delivery-projection-and-identity, the refined classification].

The two kill windows the decision names are pinned over a real durable
history: a history ending after the begin batch resumes with the invocation
reconstructed from ``ActivityRequested`` and never re-runs ``prepare``; a
history ending after ``ActivityCompleted`` resumes projection-pending and
never re-invokes the activity — a projection bug is fixed in code and retried
from the same frozen result [the decision's Deferred section].
"""

from __future__ import annotations

# Python imports
from dataclasses import FrozenInstanceError, dataclass, fields

# Pip imports
import pytest

# Internal imports
from petrus.motus.activity import (
    ActivityError,
    ActivityFailure,
    ActivityInvocation,
    DataclassPayloadConverter,
    ExecutionPolicy,
    RetryPolicy,
    activity,
)
from petrus.impetus.binding import DerivedActivityHandler, HandlerResult
from petrus.motus.dispatch import InlineDispatch
from petrus.engine import Engine
from petrus.impetus.history import (
    ActivityCompleted,
    ActivityFailed,
    ActivityRequested,
    CandidateSelected,
    DeliveryRegistration,
    DeliveryRegistrationClosed,
    DeliveryRegistrationOpened,
    FiringBegun,
    FiringCompleted,
    FiringFailed,
    Record,
    TokensConsumed,
    TokensInitialized,
    TokensProduced,
    TokensRead,
)
from petrus.impetus.history_store import InMemoryHistoryStore, JsonlHistoryStore
from petrus.impetus.instance import Instance
from petrus.impetus.instance.firing import (
    replay_in_flight,
    replay_projection_pending,
    replay_terminal_activity,
)
from petrus.impetus.petrinet import Arc, ArcMode, Binding, Marking, Net, NetPath, Place, Token, Transition

A, B, T, GATE = NetPath("a"), NetPath("b"), NetPath("t"), NetPath("gate")


@dataclass(frozen=True)
class PaymentInput:
    amount: int


@dataclass(frozen=True)
class ReceiptOutput:
    status: str
    amount: int


@dataclass(frozen=True)
class AccountInput:
    account: str


@dataclass(frozen=True)
class LimitInput:
    maximum: int


@dataclass(frozen=True)
class CheckedOutput:
    accepted: bool


class CustomInput:
    def __init__(self, value: int):
        self.value = value

    def __eq__(self, other):
        return isinstance(other, CustomInput) and self.value == other.value


class CustomOutput:
    def __init__(self, doubled: int):
        self.doubled = doubled


def test_activity_import_is_a_leaf_in_a_fresh_interpreter():
    """The canonical activity package loads without importing Petri or history concepts."""
    import subprocess
    import sys

    code = """
import sys
from petrus.motus.activity import Activity, ActivityFailure, ActivityInvocation, ExecutionPolicy
assert Activity is not None
assert ActivityFailure('boom').error == 'boom'
assert ActivityInvocation('work').policy == ExecutionPolicy()
assert not any(name == 'petrus.impetus.history' or name.startswith('petrus.impetus.history.') for name in sys.modules)
assert not any(name in sys.modules for name in (
    'petrus.impetus.petrinet',
    'petrus.impetus.petrinet.schema',
    'petrus.impetus.petrinet.marking',
    'petrus.impetus.petrinet.enabledness',
    'petrus.impetus.petrinet.firing',
))
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_canonical_activity_and_history_codec_imports_are_public():
    from petrus.motus.activity import Activity, ActivityFailure, ActivityInvocation, ExecutionPolicy
    from petrus.impetus.history.codec import LIFECYCLE_SCHEMA_VERSION, SCHEMA_VERSION, decode_record, encode_record
    from petrus.impetus.history_store import InMemoryHistoryStore

    assert Activity is not None
    assert ActivityFailure("boom").error == "boom"
    assert ActivityInvocation("work").policy == ExecutionPolicy()
    assert isinstance(InMemoryHistoryStore(), InMemoryHistoryStore)
    assert SCHEMA_VERSION == 4
    assert LIFECYCLE_SCHEMA_VERSION == 5
    assert callable(decode_record) and callable(encode_record)


class ChargeCard:
    """The reference ActivityHandler: prepare typed input off the binding, project the frozen provider result — counting both halves so re-runs betray themselves."""

    def __init__(self, correlation: str | None = None, idempotency: str | None = None):
        self.prepared = 0
        self.projected = 0
        self._correlation = correlation
        self._idempotency = idempotency

    def prepare(self, binding: Binding) -> ActivityInvocation:
        self.prepared += 1
        [payment] = binding.tokens
        return ActivityInvocation(
            "charge_card",
            input={"amount": payment.data["amount"]},
            correlation=self._correlation,
            idempotency=self._idempotency,
        )

    def project(self, binding: Binding, result):
        self.projected += 1
        return {B: (Token("Receipt", {"status": result["status"]}),)}


def _activity_net(handler: str | None = "charge") -> Net:
    """a -> t (activity-handled) -> b."""
    return Net(
        places=[Place(A), Place(B)],
        transitions=[Transition(T, handler=handler)],
        arcs=[Arc(A, T), Arc(T, B)],
    )


PAYMENT = Token("Payment", {"amount": 100})


def _instance(handler, marking: Marking | None = None, history=None) -> Instance:
    marking = marking if marking is not None else Marking({A: (PAYMENT,)})
    return Instance(_activity_net(), marking, handlers={"charge": handler}, history=history)


def _begun(handler, history=None):
    instance = _instance(handler, history=history)
    return instance, instance.begin(instance.candidates()[0])


def _advance_until_rest(engine: Engine):
    firings = []
    while True:
        outcome = engine.advance()
        firings.extend(outcome.firings)
        if not outcome.ready:
            return firings


def test_a_typed_activity_derives_its_ordinary_handler_from_the_net_shape():
    source, target, transition = NetPath("typed.source"), NetPath("typed.target"), NetPath("typed.work")
    net = Net(
        places=[Place(source, color="PaymentInput"), Place(target, color="ReceiptOutput")],
        transitions=[Transition(transition, handler="typed_work")],
        arcs=[Arc(source, transition), Arc(transition, target)],
    )
    received = []

    @activity(converter=DataclassPayloadConverter())
    def typed_work(payment: PaymentInput) -> ReceiptOutput:
        received.append(payment)
        return ReceiptOutput("captured", payment.amount)

    history = InMemoryHistoryStore()
    engine = Engine.create(
        net,
        "derived-activity-handler",
        history=history,
        dispatch=InlineDispatch({typed_work.declaration.name: typed_work}),
        marking=Marking({source: (Token("PaymentInput", {"amount": 100, "currency": "USD"}),)}),
        handlers={"typed_work": DerivedActivityHandler(net, transition, typed_work)},
        activities=(typed_work.declaration,),
    )

    _advance_until_rest(engine)

    assert received == [PaymentInput(100)]
    assert next(record for record in history if isinstance(record, ActivityRequested)).input == {
        "payment": {"amount": 100, "currency": "USD"}
    }
    assert next(record for record in history if isinstance(record, ActivityCompleted)).result == {
        "status": "captured",
        "amount": 100,
    }
    assert engine.marking == Marking({target: (Token("ReceiptOutput", {"status": "captured", "amount": 100}),)})


def test_a_derived_handler_passes_unique_consume_and_read_selections_as_typed_arguments():
    account, limit, target, transition = map(NetPath, ("account", "limit", "checked", "check"))
    net = Net(
        places=[Place(account), Place(limit), Place(target)],
        transitions=[Transition(transition, handler="check")],
        arcs=[
            Arc(account, transition, color="AccountInput"),
            Arc(limit, transition, ArcMode.READ, color="LimitInput"),
            Arc(transition, target, color="CheckedOutput"),
        ],
    )
    received = []

    @activity(converter=DataclassPayloadConverter())
    def check(subject: AccountInput, policy: LimitInput) -> CheckedOutput:
        received.append((subject, policy))
        return CheckedOutput(policy.maximum >= 10)

    engine = Engine.create(
        net,
        "derived-two-inputs",
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch({check.declaration.name: check}),
        marking=Marking(
            {
                account: (Token("AccountInput", {"account": "A-1"}),),
                limit: (Token("LimitInput", {"maximum": 10}),),
            }
        ),
        handlers={"check": DerivedActivityHandler(net, transition, check)},
        activities=(check.declaration,),
    )

    _advance_until_rest(engine)

    assert received == [(AccountInput("A-1"), LimitInput(10))]
    assert engine.marking == Marking(
        {
            limit: (Token("LimitInput", {"maximum": 10}),),
            target: (Token("CheckedOutput", {"accepted": True}),),
        }
    )


def test_a_derived_handler_distinguishes_two_typed_arcs_from_the_same_place():
    source, target, transition = map(NetPath, ("inputs", "checked", "check"))
    net = Net(
        places=[Place(source), Place(target)],
        transitions=[Transition(transition, handler="check")],
        arcs=[
            Arc(source, transition, color="AccountInput"),
            Arc(source, transition, color="LimitInput"),
            Arc(transition, target, color="CheckedOutput"),
        ],
    )
    received = []

    @activity(converter=DataclassPayloadConverter())
    def check(subject: AccountInput, policy: LimitInput) -> CheckedOutput:
        received.append((subject, policy))
        return CheckedOutput(policy.maximum >= 10)

    engine = Engine.create(
        net,
        "derived-same-place-inputs",
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch({check.declaration.name: check}),
        marking=Marking(
            {
                source: (
                    Token("AccountInput", {"account": "A-1"}),
                    Token("LimitInput", {"maximum": 10}),
                )
            }
        ),
        handlers={"check": DerivedActivityHandler(net, transition, check)},
        activities=(check.declaration,),
    )

    _advance_until_rest(engine)

    assert received == [(AccountInput("A-1"), LimitInput(10))]
    assert engine.marking == Marking({target: (Token("CheckedOutput", {"accepted": True}),)})


def test_a_derived_handler_projects_once_per_matching_output_arc():
    source, target, transition = map(NetPath, ("payment", "receipts", "charge"))
    net = Net(
        places=[Place(source), Place(target)],
        transitions=[Transition(transition, handler="charge")],
        arcs=[
            Arc(source, transition, color="PaymentInput"),
            Arc(transition, target, color="ReceiptOutput"),
            Arc(transition, target, color="ReceiptOutput"),
        ],
    )

    @activity(converter=DataclassPayloadConverter())
    def charge(payment: PaymentInput) -> ReceiptOutput:
        return ReceiptOutput("captured", payment.amount)

    engine = Engine.create(
        net,
        "derived-output-arcs",
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch({charge.declaration.name: charge}),
        marking=Marking({source: (Token("PaymentInput", {"amount": 100}),)}),
        handlers={"charge": DerivedActivityHandler(net, transition, charge)},
        activities=(charge.declaration,),
    )

    _advance_until_rest(engine)

    receipt = Token("ReceiptOutput", {"status": "captured", "amount": 100})
    assert engine.marking == Marking({target: (receipt, receipt)})


def test_a_derived_handler_refuses_a_typed_input_arc_no_activity_parameter_receives():
    payment, limit, target, transition = map(NetPath, ("payment", "limit", "receipt", "charge"))
    net = Net(
        places=[Place(payment), Place(limit), Place(target)],
        transitions=[Transition(transition, handler="charge")],
        arcs=[
            Arc(payment, transition, color="PaymentInput"),
            Arc(limit, transition, color="LimitInput"),
            Arc(transition, target, color="ReceiptOutput"),
        ],
    )

    @activity(converter=DataclassPayloadConverter())
    def charge(subject: PaymentInput) -> ReceiptOutput:
        return ReceiptOutput("captured", subject.amount)

    with pytest.raises(
        ValueError,
        match=r"cannot derive Activity handler for charge: typed input arc limit -> charge \(LimitInput\) "
        r"matches no Activity parameter",
    ):
        DerivedActivityHandler(net, transition, charge)


def test_activity_declaration_refuses_an_unresolved_annotation_in_its_own_vocabulary():
    def unresolved(payload: object) -> ReceiptOutput:
        del payload
        return ReceiptOutput("captured", 1)

    unresolved.__annotations__["payload"] = "MissingPayload"
    with pytest.raises(
        TypeError,
        match="Activity 'unresolved' cannot resolve its typed signature: name 'MissingPayload' is not defined",
    ):
        activity(unresolved)


def test_activity_declaration_refuses_an_untyped_parameter_before_it_can_be_registered():
    def untyped(payload) -> ReceiptOutput:
        del payload
        return ReceiptOutput("captured", 1)

    with pytest.raises(TypeError, match="Activity 'untyped' parameter 'payload' requires a type annotation"):
        activity(untyped)


def test_activity_declaration_does_not_silently_replace_an_explicit_empty_name():
    def typed(payload: PaymentInput) -> ReceiptOutput:
        return ReceiptOutput("captured", payload.amount)

    with pytest.raises(ValueError, match="ActivityDeclaration requires a non-empty string name"):
        activity(typed, name="")


def test_a_derived_handler_refuses_ambiguous_same_color_input_arcs():
    first, second, target, transition = map(NetPath, ("first", "second", "receipt", "charge"))
    net = Net(
        places=[Place(first), Place(second), Place(target)],
        transitions=[Transition(transition, handler="charge")],
        arcs=[
            Arc(first, transition, color="PaymentInput"),
            Arc(second, transition, color="PaymentInput"),
            Arc(transition, target, color="ReceiptOutput"),
        ],
    )

    @activity(converter=DataclassPayloadConverter())
    def charge(subject: PaymentInput) -> ReceiptOutput:
        return ReceiptOutput("captured", subject.amount)

    with pytest.raises(
        ValueError,
        match=r"parameter 'subject' \(PaymentInput\) requires exactly one matching input arc, found 2",
    ):
        DerivedActivityHandler(net, transition, charge)


def test_a_derived_handler_refuses_to_supply_one_typed_arc_to_two_parameters():
    source, target, transition = map(NetPath, ("payment", "receipt", "compare"))
    net = Net(
        places=[Place(source), Place(target)],
        transitions=[Transition(transition, handler="compare")],
        arcs=[
            Arc(source, transition, color="PaymentInput"),
            Arc(transition, target, color="ReceiptOutput"),
        ],
    )

    @activity(converter=DataclassPayloadConverter())
    def compare(first: PaymentInput, second: PaymentInput) -> ReceiptOutput:
        return ReceiptOutput("captured", first.amount + second.amount)

    with pytest.raises(
        ValueError,
        match=r"parameter 'second' \(PaymentInput\) matches input arc payment -> compare already used by parameter 'first'",
    ):
        DerivedActivityHandler(net, transition, compare)


def test_a_derived_handler_refuses_a_return_type_with_no_matching_output_arc():
    source, target, transition = map(NetPath, ("payment", "other", "charge"))
    net = Net(
        places=[Place(source), Place(target)],
        transitions=[Transition(transition, handler="charge")],
        arcs=[
            Arc(source, transition, color="PaymentInput"),
            Arc(transition, target, color="OtherOutput"),
        ],
    )

    @activity(converter=DataclassPayloadConverter())
    def charge(subject: PaymentInput) -> ReceiptOutput:
        return ReceiptOutput("captured", subject.amount)

    with pytest.raises(ValueError, match="return type ReceiptOutput matches no output arc"):
        DerivedActivityHandler(net, transition, charge)


def test_a_derived_handler_refuses_an_output_arc_the_return_type_cannot_supply():
    source, receipt, other, transition = map(NetPath, ("payment", "receipt", "other", "charge"))
    net = Net(
        places=[Place(source), Place(receipt), Place(other)],
        transitions=[Transition(transition, handler="charge")],
        arcs=[
            Arc(source, transition, color="PaymentInput"),
            Arc(transition, receipt, color="ReceiptOutput"),
            Arc(transition, other, color="OtherOutput"),
        ],
    )

    @activity(converter=DataclassPayloadConverter())
    def charge(subject: PaymentInput) -> ReceiptOutput:
        return ReceiptOutput("captured", subject.amount)

    with pytest.raises(
        ValueError,
        match=r"output arc charge -> other \(OtherOutput\) matches no Activity return",
    ):
        DerivedActivityHandler(net, transition, charge)


def test_a_derived_handler_refuses_a_weighted_input_until_collection_parameters_are_supported():
    source, target, transition = map(NetPath, ("payments", "receipt", "charge"))
    net = Net(
        places=[Place(source), Place(target)],
        transitions=[Transition(transition, handler="charge")],
        arcs=[
            Arc(source, transition, weight=2, color="PaymentInput"),
            Arc(transition, target, color="ReceiptOutput"),
        ],
    )

    @activity(converter=DataclassPayloadConverter())
    def charge(subject: PaymentInput) -> ReceiptOutput:
        return ReceiptOutput("captured", subject.amount)

    with pytest.raises(
        ValueError,
        match=r"parameter 'subject' \(PaymentInput\) matches weight-2 arc payments -> charge; "
        "collection parameters are not supported",
    ):
        DerivedActivityHandler(net, transition, charge)


def test_a_typed_activity_uses_a_user_payload_converter_without_changing_the_runtime():
    class CustomConverter:
        def decode(self, value, annotation):
            assert annotation is CustomInput
            return CustomInput(int(value))

        def encode(self, value, annotation):
            assert annotation is CustomOutput
            return {"doubled": value.doubled}

    source, target, transition = map(NetPath, ("custom.input", "custom.output", "custom.work"))
    net = Net(
        places=[Place(source), Place(target)],
        transitions=[Transition(transition, handler="custom_work")],
        arcs=[
            Arc(source, transition, color="CustomInput"),
            Arc(transition, target, color="CustomOutput"),
        ],
    )
    received = []

    @activity(converter=CustomConverter())
    def custom_work(item: CustomInput) -> CustomOutput:
        received.append(item)
        return CustomOutput(item.value * 2)

    engine = Engine.create(
        net,
        "custom-payload-converter",
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch({custom_work.declaration.name: custom_work}),
        marking=Marking({source: (Token("CustomInput", "7"),)}),
        handlers={"custom_work": DerivedActivityHandler(net, transition, custom_work)},
        activities=(custom_work.declaration,),
    )

    _advance_until_rest(engine)

    assert received == [CustomInput(7)]
    assert engine.marking == Marking({target: (Token("CustomOutput", {"doubled": 14}),)})


# ── the seam's value objects ─────────────────────────────────


class TestExecutionPolicy:
    def test_the_default_is_maximally_conservative(self):
        # One attempt, an exception is terminal — the ruled default when the
        # author declares nothing; nothing more until DS4 needs it (YAGNI).
        assert ExecutionPolicy() == ExecutionPolicy(attempts=1)

    @pytest.mark.parametrize("attempts", [True, 0])
    def test_invalid_attempt_counts_are_rejected_before_a_policy_can_be_serialized(self, attempts):
        # An invocation that may never execute is a wedge, not a policy.
        with pytest.raises(ValueError, match="attempts"):
            ExecutionPolicy(attempts=attempts)

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_retry_and_deadline_values_are_rejected_at_the_value_door(self, value):
        for construct in (
            lambda: RetryPolicy(initial_interval=value),
            lambda: ExecutionPolicy(start_to_close=value),
            lambda: ActivityFailure("failed", retry_after=value),
        ):
            with pytest.raises(ValueError):
                construct()

    def test_backoff_saturates_without_overflow_and_jitter_is_not_claimed(self):
        policy = RetryPolicy(initial_interval=1, coefficient=10, max_interval=60, max_attempts=10_000)
        assert policy.delay(10_000) == 60
        with pytest.raises(ValueError, match="jitter is unsupported"):
            RetryPolicy(jitter=0.1)
        with pytest.raises(ValueError, match="attempt number"):
            policy.delay(0)

        assert policy.delay(10**1000) == 60

    def test_backoff_handles_extreme_finite_values_without_ratio_or_power_overflow(self):
        assert RetryPolicy(initial_interval=1e9, max_interval=1e8).delay(1) == 1e8
        assert RetryPolicy(initial_interval=1e-308, coefficient=1, max_interval=1e9).delay(10**9) == 1e-308
        assert RetryPolicy(initial_interval=1e-308, coefficient=1e308, max_interval=1e9).delay(3) == 1e9
        assert RetryPolicy(initial_interval=1e-308, coefficient=10, max_interval=1e9).delay(316) <= 1e9

    @pytest.mark.parametrize(
        "construct",
        [
            lambda: RetryPolicy(initial_interval=1_000_000_001),
            lambda: RetryPolicy(max_interval=1_000_000_001),
            lambda: ExecutionPolicy(heartbeat_timeout=1_000_000_001),
            lambda: ExecutionPolicy(start_to_close=1_000_000_001),
            lambda: ExecutionPolicy(schedule_to_close=1_000_000_001),
            lambda: ActivityFailure("failed", retry_after=1_000_000_001),
        ],
    )
    def test_provider_neutral_durations_refuse_values_over_one_billion_seconds(self, construct):
        with pytest.raises(ValueError, match="at most 1000000000 seconds"):
            construct()


class TestActivityInvocation:
    def test_defaults_are_the_conservative_resolution(self):
        # No declared policy resolves to the conservative default — this
        # constructor default is the ruling's one home; None correlation and
        # idempotency mean "writer derives at begin".
        invocation = ActivityInvocation("charge_card")
        assert invocation.policy == ExecutionPolicy(attempts=1)
        assert invocation.correlation is None
        assert invocation.idempotency is None

    def test_an_empty_activity_name_is_rejected(self):
        with pytest.raises(ValueError, match="activity"):
            ActivityInvocation("")

    def test_an_empty_supplied_identity_is_rejected(self):
        # An empty correlation or idempotency identity can never correlate;
        # None is the honest "derive for me" spelling.
        with pytest.raises(ValueError, match="correlation"):
            ActivityInvocation("charge_card", correlation="")
        with pytest.raises(ValueError, match="idempotency"):
            ActivityInvocation("charge_card", idempotency="")


# ── purity is the binding's classification ───────────────────


class TestPurityClassification:
    def test_a_plain_callable_bound_to_a_symbol_is_a_pure_projection(self):
        # The refined rule [DR 2026-07-14 source-delivery-projection-and-
        # identity]: a plain callable is a deterministic projection — its
        # firing carries no activity records, exactly like passthrough's.
        net = _activity_net(handler="shape")
        instance = Instance(net, Marking({A: (PAYMENT,)}), handlers={"shape": lambda b, outputs: {B: b.tokens}})

        [firing] = instance.run()

        assert firing.records == (
            FiringBegun(T, occurrence=1),
            TokensConsumed(A, (PAYMENT,), occurrence=1),
            TokensProduced(B, (PAYMENT,), occurrence=1),
            FiringCompleted(T, occurrence=1),
        )

    def test_a_source_transition_must_not_bind_an_activity_handler(self):
        # Source transitions locally and atomically project delivered facts;
        # recoverable impure work belongs downstream [DR 2026-07-14
        # source-delivery-projection-and-identity] — fail-fast at construction.
        source = NetPath("src")
        net = Net(
            places=[Place(B)],
            transitions=[Transition(source, handler="charge")],
            arcs=[Arc(source, B)],
        )
        with pytest.raises(ValueError, match=r"source transition src.*projects.*downstream"):
            Instance(net, handlers={"charge": ChargeCard()})


# ── begin: prepare, resolve, freeze ──────────────────────────


class TestBeginFreezesTheRequest:
    def test_the_begin_batch_carries_the_activity_request_after_the_reads(self):
        # The canonical begin batch of an impure firing [the decision's
        # lifecycle]: initiation, boundary, consumes, reads, then the
        # authoritative outbox — one atomic batch, committed before any
        # adapter sees the invocation.
        config = Token("Config", {"mode": "strict"})

        class ReadingCharge(ChargeCard):
            def prepare(self, binding: Binding) -> ActivityInvocation:
                self.prepared += 1
                return ActivityInvocation("charge_card", input={"amount": 100})

        net = Net(
            places=[Place(A), Place(GATE), Place(B)],
            transitions=[Transition(T, handler="charge")],
            arcs=[Arc(A, T), Arc(GATE, T, mode=ArcMode.READ), Arc(T, B)],
        )
        instance = Instance(net, Marking({A: (PAYMENT,), GATE: (config,)}), handlers={"charge": ReadingCharge()})

        occurrence = instance.begin(instance.candidates()[0], at=3)

        assert instance.history.records[-5:] == (
            CandidateSelected(T, occurrence=1, instant=3),
            FiringBegun(T, occurrence=1, instant=3),
            TokensConsumed(A, (PAYMENT,), occurrence=1, instant=3),
            TokensRead(GATE, (config,), occurrence=1, instant=3),
            ActivityRequested(
                T,
                activity="charge_card",
                input={"amount": 100},
                policy=ExecutionPolicy(attempts=1),
                correlation="occurrence-1",
                idempotency="occurrence-1",
                occurrence=1,
                instant=3,
            ),
        )
        assert occurrence.invocation == ActivityInvocation(
            "charge_card",
            input={"amount": 100},
            correlation="occurrence-1",
            idempotency="occurrence-1",
        )

    def test_a_pure_occurrence_carries_no_invocation(self):
        instance = Instance(_activity_net(handler=None), Marking({A: (PAYMENT,)}))
        occurrence = instance.begin(instance.candidates()[0])
        assert occurrence.invocation is None

    def test_supplied_identities_travel_verbatim(self):
        # The handler's own correlation (the payment order) and idempotency
        # key are the recorded truth; the writer derives only what is None.
        handler = ChargeCard(correlation="order-77", idempotency="key-9")
        instance, occurrence = _begun(handler)

        [requested] = [r for r in instance.history if isinstance(r, ActivityRequested)]
        assert (requested.correlation, requested.idempotency) == ("order-77", "key-9")
        assert (occurrence.invocation.correlation, occurrence.invocation.idempotency) == ("order-77", "key-9")

    def test_a_failing_prepare_appends_nothing_and_burns_no_id(self):
        # prepare runs BEFORE anything is appended: its failure is a code
        # failure, not a net fact — the history takes no partial begin.
        class OnceBrokenPrepare(ChargeCard):
            def prepare(self, binding):
                if self.prepared == 0:
                    self.prepared += 1
                    raise RuntimeError("prepare exploded")
                return super().prepare(binding)

        instance = _instance(OnceBrokenPrepare())
        before = instance.history.records

        with pytest.raises(RuntimeError, match="prepare exploded"):
            instance.begin(instance.candidates()[0])

        assert instance.history.records == before
        assert instance.in_flight == ()
        assert instance.begin(instance.candidates()[0], at=1).id == 1  # the failed prepare burned no id

    def test_a_prepare_returning_a_non_invocation_is_refused_before_append(self):
        # The seam where handler-owned data enters the kernel checks its
        # shape, like deliver() checks tokens [convention 28].
        class WrongShape(ChargeCard):
            def prepare(self, binding):
                return {"activity": "charge_card"}

        instance = _instance(WrongShape())
        before = instance.history.records

        with pytest.raises(ValueError, match="ActivityInvocation"):
            instance.begin(instance.candidates()[0])

        assert instance.history.records == before

    def test_a_supplied_identity_in_the_reserved_namespace_is_refused(self):
        # The writer derives "occurrence-{id}" when the handler supplies
        # nothing [convention 65, the DS1a reservation]: a supplied identity
        # inside that namespace would collide with a later derived one.
        for handler in (ChargeCard(correlation="occurrence-2"), ChargeCard(idempotency="occurrence-2")):
            instance = _instance(handler)
            before = instance.history.records
            with pytest.raises(ValueError, match=r"occurrence-.*reserved"):
                instance.begin(instance.candidates()[0])
            assert instance.history.records == before


# ── the frozen terminal activity fact ────────────────────────


class TestRecordActivityCompletion:
    def test_the_result_freezes_as_its_own_append_before_projection(self):
        instance, occurrence = _begun(ChargeCard())

        instance.record_activity_completion(occurrence, {"status": "captured"}, at=5)

        assert instance.history.records[-1] == ActivityCompleted(T, {"status": "captured"}, occurrence=1, instant=5)
        assert instance.in_flight == (occurrence,)  # frozen, not yet projected

    def test_a_pure_occurrence_takes_no_activity_completion(self):
        instance = Instance(_activity_net(handler=None), Marking({A: (PAYMENT,)}))
        occurrence = instance.begin(instance.candidates()[0])

        with pytest.raises(ValueError, match="pure"):
            instance.record_activity_completion(occurrence, {"status": "captured"})

    def test_an_identical_re_record_is_acknowledged_without_a_second_append(self):
        # K6 at the writer: the first terminal activity fact wins; an
        # identical redelivery is acknowledged quietly, appending nothing.
        instance, occurrence = _begun(ChargeCard())
        instance.record_activity_completion(occurrence, {"status": "captured"})
        before = instance.history.records

        instance.record_activity_completion(occurrence, {"status": "captured"})

        assert instance.history.records == before
        assert [r for r in instance.history if isinstance(r, ActivityCompleted)] == [
            ActivityCompleted(T, {"status": "captured"}, occurrence=1)
        ]

    def test_a_different_late_result_is_an_operational_conflict(self):
        instance, occurrence = _begun(ChargeCard())
        instance.record_activity_completion(occurrence, {"status": "captured"})

        with pytest.raises(ValueError, match="different result"):
            instance.record_activity_completion(occurrence, {"status": "declined"})

    def test_nested_boolean_and_integer_results_are_distinct(self):
        instance, occurrence = _begun(ChargeCard())
        instance.record_activity_completion(occurrence, {"nested": [{"value": True}]})

        with pytest.raises(ValueError, match="different result"):
            instance.record_activity_completion(occurrence, {"nested": [{"value": 1}]})

    def test_an_ended_pure_occurrence_still_reads_as_already_ended(self):
        # The ended-occurrence acknowledgement door below serves activity
        # facts only; an ended occurrence with no terminal activity fact
        # keeps the honest lifecycle rejection.
        instance = Instance(_activity_net(handler=None), Marking({A: (PAYMENT,)}))
        occurrence = instance.begin(instance.candidates()[0])
        instance.complete(occurrence, {B: (PAYMENT,)})

        with pytest.raises(ValueError, match="already ended"):
            instance.record_activity_completion(occurrence, {"status": "captured"})


class TestEndedOccurrenceAcknowledgement:
    """
    The result-ingress door on an ENDED occurrence [ruled into DS2 at the
    DS1b adjudication]: at-least-once adapters redeliver after
    acknowledgement loss, and the firing may have completed meanwhile. The
    writer answers from the terminal-result index — a projection of the
    ``ActivityCompleted``/``ActivityFailed`` records, live and rebuilt at
    resume: a canonical-value-equal result returns the prior acknowledgement
    quietly with no append; a different late result is an operational
    conflict; an ``ActivityFailed`` terminal refuses any late result — a
    failed occurrence cannot retroactively succeed [DR 2026-07-14
    source-delivery-projection-and-identity: "a different late result is an
    operational conflict"].
    """

    def test_an_identical_late_re_record_returns_the_prior_acknowledgement_quietly(self):
        instance, occurrence = _begun(ChargeCard())
        instance.record_activity_completion(occurrence, {"status": "captured"})
        instance.complete(occurrence)
        before = instance.history.records

        instance.record_activity_completion(occurrence, {"status": "captured"})

        assert instance.history.records == before
        assert instance.in_flight == ()

    def test_the_late_acknowledgement_compares_canonical_values(self):
        # A tuple-form redelivery acknowledges against its frozen list form:
        # the door canonicalizes before it judges [convention 66].
        instance, occurrence = _begun(ChargeCard())
        instance.record_activity_completion(occurrence, {"status": "captured", "codes": [1, 2]})
        instance.complete(occurrence)
        before = instance.history.records

        instance.record_activity_completion(occurrence, {"status": "captured", "codes": (1, 2)})

        assert instance.history.records == before

    def test_a_different_late_result_after_the_end_is_an_operational_conflict(self):
        instance, occurrence = _begun(ChargeCard())
        instance.record_activity_completion(occurrence, {"status": "captured"})
        instance.complete(occurrence)

        with pytest.raises(ValueError, match="different result.*operational conflict"):
            instance.record_activity_completion(occurrence, {"status": "declined"})

    def test_a_late_result_after_a_terminal_failure_is_an_operational_conflict(self):
        # ActivityFailed is the terminal fact: a late success cannot
        # retroactively rewrite it, identical-looking or not.
        instance, occurrence = _begun(ChargeCard())
        instance.fail(occurrence, "provider down")

        with pytest.raises(ValueError, match="cannot retroactively succeed"):
            instance.record_activity_completion(occurrence, {"status": "captured"})

    def test_the_terminal_result_index_rebuilds_at_resume(self, tmp_path):
        # The index is a projection of the terminal activity records — a
        # redelivery after a crash-and-resume still acknowledges quietly,
        # and a different one still conflicts.
        path = tmp_path / "history.jsonl"
        instance, occurrence = _begun(ChargeCard(), history=JsonlHistoryStore(path))
        instance.record_activity_completion(occurrence, {"status": "captured"})
        instance.complete(occurrence)
        del instance  # the kill

        resumed = Instance.resume(_activity_net(), JsonlHistoryStore(path), handlers={"charge": ChargeCard()})
        before = resumed.history.records

        resumed.record_activity_completion(occurrence, {"status": "captured"})

        assert resumed.history.records == before
        with pytest.raises(ValueError, match="different result.*operational conflict"):
            resumed.record_activity_completion(occurrence, {"status": "declined"})

    def test_replay_terminal_activity_projects_only_ended_occurrences(self):
        # The fold behind the index: an in-flight frozen result is
        # projection-pending (replay_projection_pending's), never the ended
        # index's; an ended completion and an ended failure both are.
        completed = InMemoryHistoryStore()
        completed.extend(
            [
                CandidateSelected(T, occurrence=1),
                FiringBegun(T, occurrence=1),
                ActivityRequested(
                    T,
                    activity="charge_card",
                    input=None,
                    policy=ExecutionPolicy(),
                    correlation="occurrence-1",
                    idempotency="occurrence-1",
                    occurrence=1,
                ),
                ActivityCompleted(T, {"status": "captured"}, occurrence=1),
            ]
        )
        assert replay_terminal_activity(completed) == {}  # frozen but in flight

        completed.append(FiringCompleted(T, occurrence=1))
        assert replay_terminal_activity(completed) == {1: {"status": "captured"}}

        failed = InMemoryHistoryStore()
        failed.extend(
            [
                CandidateSelected(T, occurrence=1),
                FiringBegun(T, occurrence=1),
                ActivityFailed(T, "provider down", occurrence=1),
                FiringFailed(T, "provider down", occurrence=1),
            ]
        )
        assert replay_terminal_activity(failed) == {1: ActivityFailure("provider down")}


class TestTerminalActivityReplayDivergence:
    """
    The fold owns its divergence rules [convention 64]: the live writer
    appends exactly one terminal activity fact per occurrence (the first
    wins, K6) and always BEFORE the firing's terminal boundary — a trace
    that disagrees, in any combination, refuses loud rather than silently
    overwriting the index the ended-acknowledgement door answers from.
    """

    @staticmethod
    def _history(*records):
        history = InMemoryHistoryStore()
        history.extend(list(records))
        return history

    @pytest.mark.parametrize(
        "first, second",
        [
            (
                ActivityCompleted(T, {"status": "captured"}, occurrence=1),
                ActivityFailed(T, "provider down", occurrence=1),
            ),
            (
                ActivityFailed(T, "provider down", occurrence=1),
                ActivityCompleted(T, {"status": "captured"}, occurrence=1),
            ),
            (
                ActivityFailed(T, "provider down", occurrence=1),
                ActivityFailed(T, "still down", occurrence=1),
            ),
            (
                ActivityCompleted(T, {"status": "captured"}, occurrence=1),
                ActivityCompleted(T, {"status": "declined"}, occurrence=1),
            ),
        ],
    )
    def test_a_second_terminal_activity_fact_is_replay_divergence(self, first, second):
        history = self._history(
            CandidateSelected(T, occurrence=1),
            FiringBegun(T, occurrence=1),
            first,
            second,
            FiringFailed(T, "provider down", occurrence=1),
        )
        with pytest.raises(ValueError, match="replay divergence: a second terminal activity fact"):
            replay_terminal_activity(history)

    def test_a_terminal_activity_fact_after_the_firing_ended_is_replay_divergence(self):
        history = self._history(
            CandidateSelected(T, occurrence=1),
            FiringBegun(T, occurrence=1),
            FiringCompleted(T, occurrence=1),
            ActivityCompleted(T, {"status": "captured"}, occurrence=1),
        )
        with pytest.raises(ValueError, match="replay divergence.*after its firing ended"):
            replay_terminal_activity(history)

    def test_an_activity_failure_after_a_frozen_completion_is_replay_divergence(self):
        # The lifecycle sort's natural half: the live writer refuses to
        # fail() a frozen-completed occurrence, so an open occurrence whose
        # trace holds both is not material to rebuild from.
        history = self._history(
            CandidateSelected(T, occurrence=1),
            FiringBegun(T, occurrence=1),
            ActivityRequested(
                T,
                activity="charge_card",
                input=None,
                policy=ExecutionPolicy(),
                correlation="occurrence-1",
                idempotency="occurrence-1",
                occurrence=1,
            ),
            ActivityCompleted(T, {"status": "captured"}, occurrence=1),
            ActivityFailed(T, "provider down", occurrence=1),
        )
        with pytest.raises(ValueError, match="second terminal activity fact"):
            replay_in_flight(history)


# ── complete: project the frozen result ──────────────────────


class TestCompleteProjectsTheFrozenResult:
    def test_complete_projects_the_frozen_result_and_commits_the_boundary(self):
        handler = ChargeCard()
        instance, occurrence = _begun(handler)
        instance.record_activity_completion(occurrence, {"status": "captured"})

        firing = instance.complete(occurrence)

        assert handler.projected == 1
        assert instance.marking == Marking({B: (Token("Receipt", {"status": "captured"}),)})
        assert instance.history.records[-2:] == (
            TokensProduced(B, (Token("Receipt", {"status": "captured"}),), occurrence=1),
            FiringCompleted(T, occurrence=1),
        )
        assert firing.occurrence == occurrence.id
        assert instance.in_flight == ()

    def test_complete_without_a_frozen_result_fails_loud(self):
        instance, occurrence = _begun(ChargeCard())

        with pytest.raises(ValueError, match="no terminal activity fact.*record_activity_completion first"):
            instance.complete(occurrence)

        assert instance.in_flight == (occurrence,)

    def test_complete_on_an_impure_occurrence_takes_no_result_argument(self):
        # The frozen ActivityCompleted is the one source of the result; a
        # caller-supplied one could silently diverge from the recorded fact.
        instance, occurrence = _begun(ChargeCard())
        instance.record_activity_completion(occurrence, {"status": "captured"})

        with pytest.raises(ValueError, match="takes no result"):
            instance.complete(occurrence, {B: (Token("Receipt"),)})

    def test_a_pure_complete_requires_its_handlers_result(self):
        instance = Instance(_activity_net(handler=None), Marking({A: (PAYMENT,)}))
        occurrence = instance.begin(instance.candidates()[0])

        with pytest.raises(ValueError, match="pure firing completes with its handler's result"):
            instance.complete(occurrence)

    def test_a_projection_bug_is_fixed_in_code_and_retried_from_the_same_frozen_result(self):
        # The decision's Deferred posture, live: projection raising leaves
        # the occurrence in flight with its frozen result — never re-invoked,
        # never failed — and the fixed code completes from the same fact.
        class FlakyProjection(ChargeCard):
            def __init__(self):
                super().__init__()
                self.broken = True

            def project(self, binding, result):
                if self.broken:
                    raise KeyError("statuss")  # the bug
                return super().project(binding, result)

        handler = FlakyProjection()
        instance, occurrence = _begun(handler)
        instance.record_activity_completion(occurrence, {"status": "captured"})

        with pytest.raises(KeyError):
            instance.complete(occurrence)

        assert instance.in_flight == (occurrence,)
        handler.broken = False  # the fix, redeployed
        instance.complete(occurrence)
        assert instance.marking == Marking({B: (Token("Receipt", {"status": "captured"}),)})
        assert [r for r in instance.history if isinstance(r, ActivityCompleted)] == [
            ActivityCompleted(T, {"status": "captured"}, occurrence=1)
        ]


# ── fail: exhausted execution ────────────────────────────────


class _BatchRecordingHistory(InMemoryHistoryStore):
    """Records the size of every committed batch — the one-append-batch pin."""

    def __init__(self):
        super().__init__()
        self.batches: list[int] = []
        self.committed_batches: list[tuple[Record, ...]] = []

    def extend(self, records):
        records = tuple(records)
        self.batches.append(len(records))
        self.committed_batches.append(records)
        super().extend(records)

    def append(self, record):
        self.batches.append(1)
        self.committed_batches.append((record,))
        super().append(record)


def test_activity_success_preserves_the_three_distinct_append_boundaries():
    history = _BatchRecordingHistory()
    source = NetPath("source")

    class EffectfulCharge(ChargeCard):
        def project(self, binding, result):
            return HandlerResult(
                super().project(binding, result),
                closes=(DeliveryRegistration(source, "default"),),
                opens=(DeliveryRegistration(source, "new"),),
            )

    net = Net(
        places=[Place(A), Place(B), Place(GATE)],
        transitions=[Transition(T, handler="charge"), Transition(source)],
        arcs=[Arc(A, T), Arc(GATE, T, mode=ArcMode.READ), Arc(T, B)],
    )
    instance = Instance(
        net,
        Marking({A: (PAYMENT,), GATE: (Token.black(),)}),
        handlers={"charge": EffectfulCharge()},
        history=history,
    )
    occurrence = instance.begin(instance.candidates()[0])

    instance.record_activity_completion(occurrence, {"status": "captured"}, at=2)
    instance.complete(occurrence, at=3)

    assert tuple(type(record) for record in history.committed_batches[-3]) == (
        CandidateSelected,
        FiringBegun,
        TokensConsumed,
        TokensRead,
        ActivityRequested,
    )
    assert tuple(type(record) for record in history.committed_batches[-2]) == (ActivityCompleted,)
    assert tuple(type(record) for record in history.committed_batches[-1]) == (
        TokensProduced,
        DeliveryRegistrationClosed,
        DeliveryRegistrationOpened,
        FiringCompleted,
    )


class TestFail:
    def test_an_impure_failure_commits_activity_failed_and_firing_failed_in_one_batch(self):
        # Exhausted execution is one semantic fact [convention 45]: the
        # terminal activity fact and the firing's terminal boundary land
        # whole or not at all.
        history = _BatchRecordingHistory()
        instance, occurrence = _begun(ChargeCard(), history=history)

        instance.fail(occurrence, "TimeoutError('provider gone')", at=4)

        assert instance.history.records[-2:] == (
            ActivityFailed(T, "TimeoutError('provider gone')", occurrence=1, instant=4),
            FiringFailed(T, "TimeoutError('provider gone')", occurrence=1, instant=4),
        )
        assert history.batches[-2:] == [1, 1]
        assert instance.in_flight == ()

    def test_a_pure_failure_stays_firing_failed_alone(self):
        instance = Instance(_activity_net(handler=None), Marking({A: (PAYMENT,)}))
        occurrence = instance.begin(instance.candidates()[0])

        instance.fail(occurrence, "boom")

        assert not [r for r in instance.history if isinstance(r, ActivityFailed)]
        assert isinstance(instance.history.records[-1], FiringFailed)

    def test_a_pure_firing_rejects_activity_failure_freeze(self):
        instance = Instance(_activity_net(handler=None), Marking({A: (PAYMENT,)}))
        occurrence = instance.begin(instance.candidates()[0])

        with pytest.raises(ValueError, match="pure firing.*no activity"):
            instance.record_activity_failure(occurrence, ActivityFailure("boom"))

    def test_fail_refuses_a_completed_activity(self):
        # A completed activity's projection failure is fixed by code and a
        # projection retry, never by failing the firing [the decision's
        # Deferred section]: the external work already happened.
        instance, occurrence = _begun(ChargeCard())
        instance.record_activity_completion(occurrence, {"status": "captured"})

        with pytest.raises(ValueError, match="already completed.*projection"):
            instance.fail(occurrence, "operator gave up")

        assert instance.in_flight == (occurrence,)


# ── the inline drivers refuse what they cannot run ───────────


class TestStepRefusesActivityTransitions:
    def test_step_fails_loud_naming_the_adapter_it_lacks(self):
        # step()/run() execute bound handlers here, now — but an activity
        # needs an execution adapter, and the instance holds none: refusing
        # beats silently beginning an occurrence nothing will complete.
        instance = _instance(ChargeCard())
        before = instance.history.records

        with pytest.raises(ValueError, match="Dispatch"):
            instance.step()

        assert instance.history.records == before
        assert instance.in_flight == ()


# ── InlineDispatch: the first execution adapter ───────────────


class TestInlineDispatch:
    def test_registry_is_snapshotted_and_the_adapter_remains_frozen(self):
        def activity(invocation, *, context):
            del context
            return invocation.input

        activities = {"charge_card": activity}
        adapter = InlineDispatch(activities)

        activities["refund"] = activity

        assert tuple(adapter.activities) == ("charge_card",)
        with pytest.raises(FrozenInstanceError):
            adapter.activities = {}

    def test_classified_retries_are_immediate_and_never_sleep(self, monkeypatch):
        calls = []

        def flaky(invocation, *, context):
            calls.append((invocation, context.epoch))
            if len(calls) < 3:
                raise ActivityError("temporary", kind="Unavailable", retryable=True, retry_after=60)
            return "done"

        monkeypatch.setattr("time.sleep", lambda _seconds: pytest.fail("InlineDispatch must never sleep for backoff"))
        invocation = ActivityInvocation(
            "flaky",
            policy=ExecutionPolicy(attempts=3, initial_interval=30),
            correlation="operation",
            idempotency="effect",
        )

        assert InlineDispatch({"flaky": flaky})(invocation) == "done"
        assert [epoch for _, epoch in calls] == ["1", "2", "3"]
        assert all(call == invocation for call, _ in calls)

    def test_generic_exception_keeps_precise_retryable_metadata_when_budget_exhausts(self):
        def broken(invocation, *, context):
            del invocation, context
            raise LookupError("missing account")

        dispatch = InlineDispatch({"broken": broken})
        dispatch.dispatch(7, ActivityInvocation("broken", policy=ExecutionPolicy(attempts=2)))

        assert dispatch.collect() == ((7, ActivityFailure("missing account", kind="LookupError", retryable=True)),)

    def test_value_shape_preserves_the_prior_dataclass_contract(self):
        def activity(invocation, *, context):
            del context
            return invocation.input

        adapter = InlineDispatch({"charge_card": activity})

        assert adapter == InlineDispatch({"charge_card": activity})
        assert [field.name for field in fields(adapter)] == ["activities", "_completed"]
        assert repr(adapter).startswith("InlineDispatch(activities=mappingproxy(")

    def test_executes_the_named_activity_with_the_whole_invocation(self):
        adapter = InlineDispatch(
            {
                "charge_card": lambda invocation, *, context: {
                    "status": "captured",
                    "amount": invocation.input["amount"],
                }
            }
        )

        result = adapter(ActivityInvocation("charge_card", input={"amount": 100}))

        assert result == {"status": "captured", "amount": 100}

    def test_an_unknown_activity_fails_loud(self):
        with pytest.raises(ValueError, match="no activity implementation.*'charge_card'"):
            InlineDispatch({})(ActivityInvocation("charge_card"))

    def test_the_conservative_policy_makes_an_exception_terminal(self):
        calls = []

        def flaky(invocation, *, context):
            del context
            calls.append(invocation)
            raise TimeoutError("provider gone")

        with pytest.raises(TimeoutError):
            InlineDispatch({"charge_card": flaky})(ActivityInvocation("charge_card"))

        assert len(calls) == 1  # attempts=1: no hidden retry

    def test_a_declared_attempts_policy_is_honored(self):
        # The resolved policy travels with the invocation and the adapter
        # enforces it: attempt 1 fails, attempt 2 answers.
        answers = [TimeoutError("blip"), {"status": "captured"}]

        def flaky(invocation, *, context):
            del invocation, context
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        adapter = InlineDispatch({"charge_card": flaky})
        result = adapter(ActivityInvocation("charge_card", policy=ExecutionPolicy(attempts=2)))

        assert result == {"status": "captured"}


# ── the Engine drives the whole seam ─────────────────────────


class TestEngineDrivesActivities:
    def _open(self, activity, handler=None):
        handler = handler if handler is not None else ChargeCard()
        history = InMemoryHistoryStore()
        engine = Engine.create(
            _activity_net(),
            "activity-seam-test",
            history=history,
            dispatch=InlineDispatch({"charge_card": activity}),
            marking=Marking({A: (PAYMENT,)}),
            handlers={"charge": handler},
        )
        return engine, history

    def test_an_activity_firing_records_the_canonical_lifecycle(self):
        engine, history = self._open(lambda invocation, *, context: {"status": "captured"})

        [firing] = _advance_until_rest(engine)

        kinds = [type(r).__name__ for r in history]
        assert kinds == [
            "InstanceCreated",
            "TokensInitialized",
            "CandidateSelected",
            "FiringBegun",
            "TokensConsumed",
            "ActivityRequested",
            "ActivityCompleted",
            "TokensProduced",
            "FiringCompleted",
        ]
        assert firing.transition == T

    def test_a_typed_decline_is_a_business_result_never_a_firing_failure(self):
        # Business facts versus execution faults [session 3]: the provider
        # answered — "declined" is a completed activity, projected and routed
        # by ordinary arcs; FiringFailed never appears.
        declined, receipts = NetPath("declined"), NetPath("receipts")

        class RouteCharge(ChargeCard):
            def project(self, binding, result):
                token = Token("Receipt" if result["status"] == "captured" else "Decline", {"status": result["status"]})
                return {receipts if result["status"] == "captured" else declined: (token,)}

        net = Net(
            places=[Place(A), Place(receipts), Place(declined)],
            transitions=[Transition(T, handler="charge")],
            arcs=[
                Arc(A, T),
                Arc(T, receipts, color="Receipt"),
                Arc(T, declined, color="Decline"),
            ],
        )
        history = InMemoryHistoryStore()
        engine = Engine.create(
            net,
            "activity-decline-test",
            history=history,
            dispatch=InlineDispatch({"charge_card": lambda invocation, *, context: {"status": "declined"}}),
            marking=Marking({A: (PAYMENT,)}),
            handlers={"charge": RouteCharge()},
        )

        _advance_until_rest(engine)

        assert engine.marking == Marking({declined: (Token("Decline", {"status": "declined"}),)})
        assert any(isinstance(r, ActivityCompleted) for r in history)
        assert not any(isinstance(r, (ActivityFailed, FiringFailed)) for r in history)

    def test_an_exhausted_adapter_is_activity_failed_plus_firing_failed_and_no_business_token(self):
        def gone(invocation, *, context):
            raise TimeoutError("provider gone")

        engine, history = self._open(gone)

        with pytest.raises(RuntimeError, match="failed terminally"):
            _advance_until_rest(engine)

        assert isinstance(history.records[-2], ActivityFailed)
        assert isinstance(history.records[-1], FiringFailed)
        assert replay_in_flight(history) == ()

    def test_a_projection_error_leaves_the_occurrence_projection_pending(self):
        # The Engine never converts a projection failure into FiringFailed:
        # the activity completed — the frozen fact stands, the occurrence
        # stays in flight for a fixed projection to retry.
        class BrokenProjection(ChargeCard):
            def project(self, binding, result):
                raise KeyError("statuss")

        engine, history = self._open(lambda invocation, *, context: {"status": "captured"}, handler=BrokenProjection())

        with pytest.raises(KeyError):
            _advance_until_rest(engine)

        assert len(replay_in_flight(history)) == 1
        assert any(isinstance(r, ActivityCompleted) for r in history)
        assert not any(isinstance(r, (ActivityFailed, FiringFailed)) for r in history)


# ── the kill windows, over the durable record ────────────────


class PoisonedPrepare(ChargeCard):
    """A prepare that must never run again — resume rebuilds the invocation from the record, it never re-prepares."""

    def prepare(self, binding):
        raise AssertionError("resume re-ran prepare")


class TestKillWindowOne:
    """History ends after the begin batch: ActivityRequested, no terminal activity fact."""

    def _crashed(self, tmp_path):
        path = tmp_path / "history.jsonl"
        instance = _instance(ChargeCard(), history=JsonlHistoryStore(path))
        occurrence = instance.begin(instance.candidates()[0], at=2)
        del instance  # the process dies before dispatch acknowledged anything
        return path, occurrence

    def test_resume_rebuilds_the_occurrence_with_its_invocation_and_never_re_prepares(self, tmp_path):
        path, occurrence = self._crashed(tmp_path)

        resumed = Instance.resume(_activity_net(), JsonlHistoryStore(path), handlers={"charge": PoisonedPrepare()})

        [rebuilt] = resumed.in_flight
        assert rebuilt == occurrence
        assert rebuilt.invocation == ActivityInvocation(
            "charge_card",
            input={"amount": 100},
            correlation="occurrence-1",
            idempotency="occurrence-1",
        )

    def test_the_rebuilt_invocation_is_redispatchable_to_completion(self, tmp_path):
        path, _ = self._crashed(tmp_path)
        handler = ChargeCard()
        resumed = Instance.resume(_activity_net(), JsonlHistoryStore(path), handlers={"charge": handler})
        adapter = InlineDispatch({"charge_card": lambda invocation, *, context: {"status": "captured"}})

        [rebuilt] = resumed.in_flight
        resumed.record_activity_completion(rebuilt, adapter(rebuilt.invocation), at=9)
        resumed.complete(rebuilt, at=9)

        assert handler.prepared == 0  # the record supplied the invocation
        assert handler.projected == 1
        assert resumed.marking == Marking({B: (Token("Receipt", {"status": "captured"}),)})


class TestKillWindowTwo:
    """History ends after ActivityCompleted: the frozen result survives, projection is all that remains."""

    def _crashed(self, tmp_path):
        path = tmp_path / "history.jsonl"
        instance = _instance(ChargeCard(), history=JsonlHistoryStore(path))
        occurrence = instance.begin(instance.candidates()[0], at=2)
        instance.record_activity_completion(occurrence, {"status": "captured"}, at=3)
        del instance  # the process dies before projection committed
        return path

    def test_resume_is_projection_pending_and_the_activity_is_never_re_invoked(self, tmp_path):
        path = self._crashed(tmp_path)
        invocations = []

        def counting(invocation, *, context):
            invocations.append(invocation)
            return {"status": "captured"}

        handler = ChargeCard()
        resumed = Instance.resume(_activity_net(), JsonlHistoryStore(path), handlers={"charge": handler})
        adapter = InlineDispatch({"charge_card": counting})  # available, and never consulted

        [rebuilt] = resumed.in_flight
        firing = resumed.complete(rebuilt, at=9)  # projection only — nothing to dispatch on `adapter`

        assert invocations == []  # the frozen result was projected; the activity never ran again
        assert adapter.activities  # the double existed; the seam simply never needed it
        assert handler.prepared == 0
        assert handler.projected == 1
        assert firing.occurrence == 1
        assert resumed.marking == Marking({B: (Token("Receipt", {"status": "captured"}),)})

    def test_a_projection_bug_fixed_and_retried_completes_from_the_same_frozen_result(self, tmp_path):
        path = self._crashed(tmp_path)

        class Broken(ChargeCard):
            def project(self, binding, result):
                raise KeyError("statuss")

        broken = Instance.resume(_activity_net(), JsonlHistoryStore(path), handlers={"charge": Broken()})
        [rebuilt] = broken.in_flight
        with pytest.raises(KeyError):
            broken.complete(rebuilt)

        # Fix the code, redeploy (a fresh resume over the same file), retry
        # projection alone — the same frozen result, never a re-invocation.
        fixed = Instance.resume(_activity_net(), JsonlHistoryStore(path), handlers={"charge": ChargeCard()})
        [rebuilt] = fixed.in_flight
        fixed.complete(rebuilt, at=9)

        assert fixed.marking == Marking({B: (Token("Receipt", {"status": "captured"}),)})
        assert [r for r in fixed.history if isinstance(r, ActivityCompleted)] == [
            ActivityCompleted(T, {"status": "captured"}, occurrence=1, instant=3)
        ]


class FailureProjectingCharge(ChargeCard):
    def __init__(self, *, broken: bool = False):
        super().__init__()
        self.broken = broken
        self.failures = []

    def project_failure(self, binding, failure):
        if self.broken:
            raise RuntimeError("failure projection crashed")
        self.failures.append(failure)
        return {B: (Token("ActivityFailure", {"kind": failure.kind, "details": failure.details}),)}


class TestTerminalFailureProjection:
    def test_opt_in_failure_projection_routes_one_typed_terminal_token(self):
        handler = FailureProjectingCharge()
        instance, occurrence = _begun(handler)
        failure = ActivityFailure(
            "request rejected",
            kind="InvalidRequest",
            details={"field": "account"},
            retryable=False,
        )

        instance.record_activity_failure(occurrence, failure, at=2)
        firing = instance.complete(occurrence, at=3)

        assert handler.failures == [failure]
        assert firing.occurrence == 1
        assert instance.marking == Marking(
            {B: (Token("ActivityFailure", {"kind": "InvalidRequest", "details": {"field": "account"}}),)}
        )
        assert len([record for record in instance.history if isinstance(record, ActivityFailed)]) == 1
        assert len([record for record in instance.history if isinstance(record, FiringCompleted)]) == 1
        assert not [record for record in instance.history if isinstance(record, FiringFailed)]

    def test_equal_failure_redelivery_acknowledges_and_conflicts_are_refused(self):
        instance, occurrence = _begun(FailureProjectingCharge())
        failure = ActivityFailure("down", "Unavailable", {"region": "west"}, True, 3)
        instance.record_activity_failure(occurrence, failure)
        before = instance.history.records

        instance.record_activity_failure(occurrence, failure)
        assert instance.history.records == before
        with pytest.raises(ValueError, match="conflicting terminal activity report"):
            instance.record_activity_failure(occurrence, ActivityFailure("different", retryable=False))
        with pytest.raises(ValueError, match="terminal activity fact already exists"):
            instance.record_activity_completion(occurrence, {"status": "late-success"})

    def test_nested_boolean_and_integer_failure_details_are_distinct(self):
        instance, occurrence = _begun(FailureProjectingCharge())
        instance.record_activity_failure(occurrence, ActivityFailure("down", details={"nested": [True]}))

        with pytest.raises(ValueError, match="conflicting terminal activity report"):
            instance.record_activity_failure(occurrence, ActivityFailure("down", details={"nested": [1]}))
        with pytest.raises(ValueError, match="frozen result stands"):
            instance.fail(occurrence, ActivityFailure("down", details={"nested": [1]}))

    def test_failure_projection_crash_reloads_the_frozen_failure_without_another_attempt(self, tmp_path):
        path = tmp_path / "history.jsonl"
        broken = FailureProjectingCharge(broken=True)
        instance, occurrence = _begun(broken, history=JsonlHistoryStore(path))
        failure = ActivityFailure("down", "Unavailable", {"checkpoint": 2}, True, 5)
        instance.record_activity_failure(occurrence, failure, at=3)
        with pytest.raises(RuntimeError, match="projection crashed"):
            instance.complete(occurrence, at=4)
        del instance

        fixed = FailureProjectingCharge()
        resumed = Instance.resume(_activity_net(), JsonlHistoryStore(path), handlers={"charge": fixed})
        [rebuilt] = resumed.in_flight
        resumed.complete(rebuilt, at=5)

        assert fixed.prepared == 0
        assert fixed.failures == [failure]
        assert len([record for record in resumed.history if isinstance(record, ActivityFailed)]) == 1
        assert resumed.marking == Marking(
            {B: (Token("ActivityFailure", {"kind": "Unavailable", "details": {"checkpoint": 2}}),)}
        )

    def test_legacy_fail_and_halt_recovers_after_the_failure_freeze(self, tmp_path):
        path = tmp_path / "history.jsonl"
        instance, occurrence = _begun(ChargeCard(), history=JsonlHistoryStore(path))
        failure = ActivityFailure("down", "Unavailable", retryable=True)
        instance.record_activity_failure(occurrence, failure, at=3)
        del instance

        resumed = Instance.resume(_activity_net(), JsonlHistoryStore(path), handlers={"charge": ChargeCard()})
        [rebuilt] = resumed.in_flight
        resumed.fail(rebuilt, failure, at=4)

        assert len([record for record in resumed.history if isinstance(record, ActivityFailed)]) == 1
        assert len([record for record in resumed.history if isinstance(record, FiringFailed)]) == 1
        assert resumed.in_flight == ()

    def test_ended_failure_replay_preserves_classification_for_late_acknowledgement(self, tmp_path):
        path = tmp_path / "history.jsonl"
        instance, occurrence = _begun(ChargeCard(), history=JsonlHistoryStore(path))
        failure = ActivityFailure("down", "Unavailable", {"region": "west"}, True, 7)
        instance.record_activity_failure(occurrence, failure)
        instance.fail(occurrence, failure)
        resumed = Instance.resume(_activity_net(), JsonlHistoryStore(path), handlers={"charge": ChargeCard()})
        before = resumed.history.records

        resumed.record_activity_failure(occurrence, failure)

        assert resumed.history.records == before
        with pytest.raises(ValueError, match="conflicting terminal activity report"):
            resumed.record_activity_failure(occurrence, ActivityFailure("different"))


# ── replay guards: what the live writer could never write ────


def _begin_records(*, with_request=True):
    records = [
        CandidateSelected(T, occurrence=1, instant=1),
        FiringBegun(T, occurrence=1, instant=1),
        TokensConsumed(A, (PAYMENT,), occurrence=1, instant=1),
    ]
    if with_request:
        records.append(
            ActivityRequested(
                T,
                activity="charge_card",
                input=None,
                policy=ExecutionPolicy(),
                correlation="occurrence-1",
                idempotency="occurrence-1",
                occurrence=1,
                instant=1,
            )
        )
    return records


class TestActivityReplayGuards:
    def test_an_activity_request_with_no_begun_boundary_is_replay_divergence(self):
        history = InMemoryHistoryStore()
        history.extend(_begin_records()[3:])  # the request alone
        with pytest.raises(ValueError, match="replay divergence.*no begun boundary"):
            replay_in_flight(history)

    def test_a_second_activity_request_for_one_occurrence_is_replay_divergence(self):
        history = InMemoryHistoryStore()
        history.extend(_begin_records() + _begin_records()[3:])
        with pytest.raises(ValueError, match="replay divergence.*one activity"):
            replay_in_flight(history)

    def test_an_activity_completion_for_a_pure_occurrence_is_replay_divergence(self):
        history = InMemoryHistoryStore()
        history.extend(_begin_records(with_request=False) + [ActivityCompleted(T, "r", occurrence=1, instant=2)])
        with pytest.raises(ValueError, match="replay divergence.*no activity was requested"):
            replay_in_flight(history)

    def test_an_activity_failure_for_a_pure_occurrence_is_replay_divergence(self):
        history = InMemoryHistoryStore()
        history.extend(_begin_records(with_request=False) + [ActivityFailed(T, "boom", occurrence=1, instant=2)])
        with pytest.raises(ValueError, match="replay divergence.*no activity was requested"):
            replay_in_flight(history)

    def test_a_second_terminal_activity_fact_is_replay_divergence(self):
        history = InMemoryHistoryStore()
        history.extend(
            _begin_records()
            + [
                ActivityCompleted(T, "r", occurrence=1, instant=2),
                ActivityCompleted(T, "r", occurrence=1, instant=3),
            ]
        )
        with pytest.raises(ValueError, match="replay divergence.*terminal activity fact"):
            replay_in_flight(history)

    def test_an_activity_completion_alone_is_not_a_torn_batch(self):
        # ActivityCompleted commits alone by design — the projection-pending
        # shape is resumable, never refused.
        history = InMemoryHistoryStore()
        history.extend(_begin_records() + [ActivityCompleted(T, {"status": "ok"}, occurrence=1, instant=2)])

        [occurrence] = replay_in_flight(history)

        assert occurrence.invocation is not None
        assert replay_projection_pending(history) == {1: {"status": "ok"}}

    def test_an_activity_failure_without_its_firing_boundary_is_projection_pending(self):
        # V2 freezes ActivityFailed alone before deterministic failure
        # projection (or the legacy fail-and-halt boundary).
        history = InMemoryHistoryStore()
        history.extend(_begin_records() + [ActivityFailed(T, "boom", occurrence=1, instant=2)])
        assert replay_projection_pending(history) == {1: ActivityFailure("boom")}

    def test_resume_rejects_an_activity_request_on_a_purely_bound_transition(self):
        # Code-vs-record coherence at the door: the trace says an activity
        # was requested, the re-supplied binding cannot project it.
        history = InMemoryHistoryStore()
        history.extend([TokensInitialized(A, (PAYMENT,), instant=1)] + _begin_records())
        with pytest.raises(ValueError, match="not bound to an ActivityHandler"):
            Instance.resume(_activity_net(), history, handlers={"charge": lambda b, outputs: {}})

    def test_resume_rejects_an_activity_bound_occurrence_with_no_recorded_request(self):
        # The mirror: the live writer freezes ActivityRequested in every
        # impure begin batch, so a begun occurrence without one under an
        # ActivityHandler binding is a foreign or corrupted trace.
        history = InMemoryHistoryStore()
        history.extend([TokensInitialized(A, (PAYMENT,), instant=1)] + _begin_records(with_request=False))
        with pytest.raises(ValueError, match="no ActivityRequested"):
            Instance.resume(_activity_net(), history, handlers={"charge": ChargeCard()})


# ── canonical payload snapshots at the writer ────────────────


class TestCanonicalPayloadSnapshot:
    """
    The writer's two payload doors — begin's ``input`` and
    record_activity_completion's ``result`` — snapshot canonical: a JSON
    round trip, the durable spelling, taken before anything freezes or
    appends. The retained value IS the durable value: caller mutation cannot
    diverge live projection from the record, JSON-lossy shapes canonicalize
    once so K6's value equality survives a durable round trip, and net
    objects (never worker-visible, by ruling) fail loud at the door.
    """

    def test_mutating_the_input_after_begin_does_not_reach_the_record(self):
        payload = {"amount": 100}

        class SharedInput(ChargeCard):
            def prepare(self, binding):
                return ActivityInvocation("charge_card", input=payload)

        instance, occurrence = _begun(SharedInput())
        payload["amount"] = 999  # the caller's later mutation

        [requested] = [r for r in instance.history if isinstance(r, ActivityRequested)]
        assert requested.input == {"amount": 100}
        assert occurrence.invocation.input == {"amount": 100}

    def test_mutating_the_result_after_recording_does_not_reach_the_projection(self):
        handler = ChargeCard()
        instance, occurrence = _begun(handler)
        result = {"status": "captured"}
        instance.record_activity_completion(occurrence, result)
        result["status"] = "hacked"  # the caller's later mutation

        instance.complete(occurrence)

        assert instance.marking == Marking({B: (Token("Receipt", {"status": "captured"}),)})
        assert [r for r in instance.history if isinstance(r, ActivityCompleted)] == [
            ActivityCompleted(T, {"status": "captured"}, occurrence=1)
        ]

    def test_a_tuple_result_freezes_canonical_and_its_re_record_acknowledges(self):
        # The JSON-lossy shape canonicalizes at the door — a tuple becomes
        # its list form — so an identical redelivery in the tuple spelling
        # is VALUE-equal to the frozen fact and acknowledges quietly, never
        # a false operational conflict.
        instance, occurrence = _begun(ChargeCard())
        instance.record_activity_completion(occurrence, {"codes": (1, 2)})
        before = instance.history.records

        instance.record_activity_completion(occurrence, {"codes": (1, 2)})  # the redelivery, tuple form again

        assert instance.history.records == before
        assert instance.history.records[-1] == ActivityCompleted(T, {"codes": [1, 2]}, occurrence=1)

    def test_a_net_object_as_input_fails_loud_at_begin_appending_nothing(self):
        # The invocation is Petri-agnostic by ruling: a Token (or Binding, or
        # Marking) has no JSON spelling and is refused at the door.
        class LeakyPrepare(ChargeCard):
            def prepare(self, binding):
                return ActivityInvocation("charge_card", input=Token("Payment", {"amount": 100}))

        instance = _instance(LeakyPrepare())
        before = instance.history.records

        with pytest.raises(ValueError, match=r"invalid activity input.*JSON-faithful"):
            instance.begin(instance.candidates()[0])

        assert instance.history.records == before
        assert instance.in_flight == ()

    def test_a_net_object_as_result_fails_loud_at_the_record_appending_nothing(self):
        instance, occurrence = _begun(ChargeCard())
        before = instance.history.records

        with pytest.raises(ValueError, match=r"invalid activity result.*JSON-faithful"):
            instance.record_activity_completion(occurrence, Token("Receipt"))

        assert instance.history.records == before
        with pytest.raises(ValueError, match="no terminal activity fact"):
            instance.complete(occurrence)  # nothing froze


class TestK6AcrossResume:
    """K6 at the writer, across the durable round trip: the frozen result a resumed instance holds is the decoded record, and an identical redelivery acknowledges against it."""

    def _resumed_after_freeze(self, tmp_path, result):
        path = tmp_path / "history.jsonl"
        instance = _instance(ChargeCard(), history=JsonlHistoryStore(path))
        occurrence = instance.begin(instance.candidates()[0], at=2)
        instance.record_activity_completion(occurrence, result, at=3)
        del instance  # crash after the freeze
        return Instance.resume(_activity_net(), JsonlHistoryStore(path), handlers={"charge": ChargeCard()})

    def test_a_resumed_writer_acknowledges_an_identical_re_record_without_appending(self, tmp_path):
        resumed = self._resumed_after_freeze(tmp_path, {"status": "captured"})
        [rebuilt] = resumed.in_flight
        before = resumed.history.records

        resumed.record_activity_completion(rebuilt, {"status": "captured"})  # the adapter's redelivery

        assert resumed.history.records == before
        resumed.complete(rebuilt)
        assert resumed.marking == Marking({B: (Token("Receipt", {"status": "captured"}),)})

    def test_a_tuple_form_redelivery_acknowledges_against_the_decoded_frozen_result(self, tmp_path):
        # The canonical snapshot is what makes this hold: the record froze
        # the list form, resume seeded _frozen_results from the decoded
        # record, and the tuple-form redelivery canonicalizes to the same
        # value at the door — an acknowledgement, never a false conflict.
        resumed = self._resumed_after_freeze(tmp_path, {"codes": (1, 2)})
        [rebuilt] = resumed.in_flight
        before = resumed.history.records

        resumed.record_activity_completion(rebuilt, {"codes": (1, 2)})

        assert resumed.history.records == before

    def test_a_different_late_result_still_conflicts_across_the_resume(self, tmp_path):
        resumed = self._resumed_after_freeze(tmp_path, {"status": "captured"})
        [rebuilt] = resumed.in_flight

        with pytest.raises(ValueError, match="different result"):
            resumed.record_activity_completion(rebuilt, {"status": "declined"})


class TestBeginBatchOrderParity:
    """An open occurrence's begin records carry the live writer's internal batch order — consumes, then reads, then at most one activity request; a disordered batch is replay divergence (writer/replay parity, convention 64). Ended occurrences stay unaudited: the validation-layer posture."""

    def test_a_read_before_a_consume_is_replay_divergence(self):
        history = InMemoryHistoryStore()
        history.extend(
            [
                CandidateSelected(T, occurrence=1, instant=1),
                FiringBegun(T, occurrence=1, instant=1),
                TokensRead(GATE, (Token("Config"),), occurrence=1, instant=1),
                TokensConsumed(A, (PAYMENT,), occurrence=1, instant=1),
            ]
        )
        with pytest.raises(ValueError, match="replay divergence.*disordered begin batch"):
            replay_in_flight(history)

    def test_an_activity_request_before_a_read_is_replay_divergence(self):
        history = InMemoryHistoryStore()
        history.extend(
            [
                CandidateSelected(T, occurrence=1, instant=1),
                FiringBegun(T, occurrence=1, instant=1),
                TokensConsumed(A, (PAYMENT,), occurrence=1, instant=1),
                _begin_records()[-1],  # the ActivityRequested
                TokensRead(GATE, (Token("Config"),), occurrence=1, instant=1),
            ]
        )
        with pytest.raises(ValueError, match="replay divergence.*disordered begin batch"):
            replay_in_flight(history)
