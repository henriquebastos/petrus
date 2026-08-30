"""Engine execution, clock observation, and local Sensor behavior."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from petrus.motus.activity import ActivityInvocation, ExecutionPolicy
from petrus.motus.dispatch import InMemoryDispatch, InlineDispatch
from petrus.engine import AcceptDelivery, AcceptedDelivery, Delivery, DriveOutcome, Engine, SimulatedClock
from petrus.impetus.binding import HandlerResult
from petrus.impetus.history import (
    ActivityCompleted,
    ActivityFailed,
    ActivityRequested,
    ActivityTerminalQuarantined,
    CandidateSelected,
    DeliveryRegistration,
    DeliveryRegistrationClosed,
    DeliveryRegistrationOpened,
    ExternalEventDelivered,
    FiringBegun,
    FiringCompleted,
    FiringFailed,
    ScopeOpened,
    TimerMatured,
    TokensConsumed,
    TokensInitialized,
    TokensProduced,
)
from petrus.impetus.history_store import InMemoryHistoryStore, JsonlHistoryStore
from petrus.impetus.instance import PriorAcknowledgement, Status
from petrus.impetus.petrinet import Arc, Cel, Delay, Marking, Net, NetPath, Place, Token, Transition, Until
from petrus.impetus.scope import LifecycleScope

A, B, C, T = NetPath("a"), NetPath("b"), NetPath("c"), NetPath("t")
SRC = NetPath("src")


def _line_net(handler: str | None = None) -> Net:
    return Net(
        places=[Place(A), Place(B)],
        transitions=[Transition(T, handler=handler)],
        arcs=[Arc(A, T), Arc(T, B)],
    )


def _expiry_net(*timers) -> Net:
    return Net(
        places=[Place(A), Place(B)],
        transitions=[Transition(T, timers=timers)],
        arcs=[Arc(A, T), Arc(T, B)],
    )


def _ingress_net() -> Net:
    return Net(
        places=[Place(A), Place(B)],
        transitions=[Transition(SRC), Transition(T)],
        arcs=[Arc(SRC, A), Arc(A, T), Arc(T, B)],
    )


def _scripted(*rounds):
    remaining = list(rounds)

    def sensor():
        assert remaining, "sensor consulted past its script"
        return remaining.pop(0)

    return sensor


def _advance_until_rest(engine: Engine) -> DriveOutcome:
    firings = []
    while True:
        outcome = engine.advance()
        firings.extend(outcome.firings)
        if not outcome.ready:
            return DriveOutcome(tuple(firings), outcome.waiting, next_maturation=outcome.next_maturation)


class TestSimulatedClock:
    def test_now_starts_at_the_construction_instant(self):
        assert SimulatedClock().now() == 0
        assert SimulatedClock(at=7).now() == 7

    def test_observe_jumps_without_rewinding(self):
        clock = SimulatedClock(at=7)

        assert clock.observe(10) == 10
        assert clock.observe(4) == 10
        assert clock.now() == 10


class TestEngineDrivesTheSeam:
    def test_typed_place_rejects_an_incompatible_initial_token_before_history_is_written(self):
        net = Net(
            places=[Place(A, color="Expected")],
            transitions=[],
            arcs=[],
        )
        history = InMemoryHistoryStore()

        with pytest.raises(ValueError, match="initial marking.*place a.*Expected.*Other"):
            Engine.create(
                net,
                "invalid-initial-marking",
                history=history,
                dispatch=InMemoryDispatch(),
                marking=Marking({A: (Token("Other"),)}),
            )

        assert len(history) == 0

    def test_initial_token_color_subclass_is_refused_before_history_is_written(self):
        class ColorName(str):
            pass

        history = InMemoryHistoryStore()

        with pytest.raises(ValueError, match=r"TokensInitialized tokens.*color.*exact string"):
            Engine.create(
                Net(places=[Place(A)], transitions=[], arcs=[]),
                "token-color-subclass",
                history=history,
                dispatch=InMemoryDispatch(),
                marking=Marking({A: (Token(ColorName("Ready")),)}),
            )

        assert len(history) == 0

    def test_noncopyable_opaque_initial_token_remains_valid_for_the_in_memory_writer(self):
        class Opaque:
            def __deepcopy__(self, memo):
                del memo
                raise AssertionError("opaque token data must not be copied by writer validation")

        opaque = Opaque()
        history = InMemoryHistoryStore()
        engine = Engine.create(
            Net(places=[Place(A)], transitions=[], arcs=[]),
            "opaque-token-data",
            history=history,
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("Opaque", opaque),)}),
        )

        initialized = next(record for record in history if isinstance(record, TokensInitialized))
        assert initialized.tokens[0].data is opaque
        engine.close()

    def test_load_detaches_opaque_initial_token_data_exactly_once(self):
        copies = 0

        class OneCopy:
            def __deepcopy__(self, memo):
                del memo
                nonlocal copies
                copies += 1
                if copies > 1:
                    raise AssertionError("resume must detach its validated History tuple only once")
                return OneCopy()

        history = InMemoryHistoryStore()
        created = Engine.create(
            Net(places=[Place(A)], transitions=[], arcs=[]),
            "one-copy-token-data",
            history=history,
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("Opaque", OneCopy()),)}),
        )
        created.close()

        loaded = Engine.load(
            Net(places=[Place(A)], transitions=[], arcs=[]),
            "one-copy-token-data",
            history=history,
            dispatch=InMemoryDispatch(),
        )

        assert copies == 1
        loaded.close()

    def test_pumping_one_action_turns_drives_a_pure_chain_to_quiescence(self):
        token = Token("X")
        step = NetPath("step")
        net = Net(
            places=[Place(A), Place(B), Place(C)],
            transitions=[Transition(T), Transition(step)],
            arcs=[Arc(A, T), Arc(T, B), Arc(B, step), Arc(step, C)],
        )
        engine = Engine.create(
            net,
            "pure-chain",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (token,)}),
        )

        outcome = _advance_until_rest(engine)

        assert [firing.transition for firing in outcome.firings] == [T, step]
        assert [firing.occurrence for firing in outcome.firings] == [1, 2]
        assert engine.marking == Marking({C: (token,)})
        assert engine.status is Status.TERMINATED

    def test_an_activity_invocation_executes_through_inline_dispatch(self):
        consulted = []

        class Charge:
            def prepare(self, binding):
                return ActivityInvocation("charge", input={"n": 1})

            def project(self, binding, result):
                return {B: (Token("X", result),)}

        def recording(invocation, *, context):
            del context
            consulted.append(invocation)
            return {"ok": True}

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _line_net(handler="price"),
            "activity",
            history=history,
            dispatch=InlineDispatch({"charge": recording}),
            marking=Marking({A: (Token("X"),)}),
            handlers={"price": Charge()},
        )

        _advance_until_rest(engine)

        assert consulted == [
            ActivityInvocation(
                "charge",
                input={"n": 1},
                policy=consulted[0].policy,
                correlation="occurrence-1",
                idempotency="occurrence-1",
            )
        ]
        assert any(isinstance(record, ActivityCompleted) for record in history)
        assert engine.marking == Marking({B: (Token("X", {"ok": True}),)})

    def test_activity_scalar_subclass_is_refused_before_history_mutation_and_remains_loadable(self):
        class ActivityName(str):
            pass

        class Work:
            def prepare(self, binding):
                del binding
                return ActivityInvocation(ActivityName("work"))

            def project(self, binding, result):
                del binding, result
                return {B: (Token("Done"),)}

        net = _line_net(handler="worker")
        history = InMemoryHistoryStore()
        engine = Engine.create(
            net,
            "activity-scalar-subclass",
            history=history,
            dispatch=InMemoryDispatch(),
            handlers={"worker": Work()},
            marking=Marking({A: (Token("Ready"),)}),
        )
        initial = tuple(history)

        with pytest.raises(ValueError, match=r"ActivityRequested activity.*exact built-in string"):
            engine.advance()

        assert tuple(history) == initial
        engine.close()
        loaded = Engine.load(
            net,
            "activity-scalar-subclass",
            history=history,
            dispatch=InMemoryDispatch(),
            handlers={"worker": Work()},
        )
        assert loaded.records == initial

    def test_activity_policy_scalar_subclass_is_refused_before_history_mutation(self):
        class Attempts(int):
            def __deepcopy__(self, memo):
                del memo
                return int(self)

        class Work:
            def prepare(self, binding):
                del binding
                return ActivityInvocation("work", policy=ExecutionPolicy(attempts=Attempts(1)))

            def project(self, binding, result):
                del binding, result
                return {B: (Token("Done"),)}

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _line_net(handler="worker"),
            "activity-policy-subclass",
            history=history,
            dispatch=InMemoryDispatch(),
            handlers={"worker": Work()},
            marking=Marking({A: (Token("Ready"),)}),
        )
        initial = tuple(history)

        with pytest.raises(ValueError, match=r"ActivityRequested policy integer fields.*exact built-in type"):
            engine.advance()

        assert tuple(history) == initial

    def test_load_refuses_noncanonical_activity_input_before_dispatch(self):
        class Work:
            def prepare(self, binding):
                del binding
                return ActivityInvocation("work", input=[1, 2])

            def project(self, binding, result):
                del binding, result
                return {B: (Token("Done"),)}

        history = InMemoryHistoryStore()
        net = _line_net(handler="worker")
        engine = Engine.create(
            net,
            "noncanonical-activity-input",
            history=history,
            dispatch=InMemoryDispatch(),
            handlers={"worker": Work()},
            marking=Marking({A: (Token("Ready"),)}),
        )
        engine.advance()
        engine.close()
        request = next(record for record in history if isinstance(record, ActivityRequested))
        object.__setattr__(request, "input", (1, 2))
        malformed = tuple(history)

        with pytest.raises(ValueError, match=r"ActivityRequested input.*canonical JSON types"):
            Engine.load(
                net,
                "noncanonical-activity-input",
                history=history,
                dispatch=InMemoryDispatch(),
                handlers={"worker": Work()},
            )

        assert tuple(history) == malformed

    def test_a_pure_projection_never_touches_dispatch(self):
        class ForbiddenDispatch(InMemoryDispatch):
            def dispatch(self, occurrence, invocation):
                raise AssertionError("a pure projection reached Dispatch")

        price = lambda binding, outputs: {B: (Token("X"),)}  # noqa: E731
        engine = Engine.create(
            _line_net(handler="price"),
            "pure-projection",
            history=InMemoryHistoryStore(),
            dispatch=ForbiddenDispatch(),
            marking=Marking({A: (Token("X"),)}),
            handlers={"price": price},
        )

        _advance_until_rest(engine)

        assert engine.marking == Marking({B: (Token("X"),)})

    def test_firing_records_are_stamped_from_the_engine_clock(self):
        engine = Engine.create(
            _line_net(),
            "clock-stamp",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("X"),)}),
            clock=SimulatedClock(at=5),
        )

        outcome = _advance_until_rest(engine)

        [firing] = outcome.firings
        assert all(record.instant == 5 for record in firing.records)


class TestIdentifiedDeliveryPhases:
    """An identified source delivery has separate durable acceptance and completion phases."""

    def test_float_instant_survives_create_accept_load_and_exact_completion(self, tmp_path):
        path = tmp_path / "float-instant-delivery.jsonl"
        token = Token("X", {"event": 7})
        created = Engine.create(
            _ingress_net(),
            "float-instant-delivery",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            at=0.5,
        )
        accepted = created.accept_delivery(SRC, token, identity="event-7")
        created.close()

        loaded = Engine.load(
            _ingress_net(),
            "float-instant-delivery",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        reconstructed = loaded.accept_delivery(SRC, token, identity="event-7")
        completed = loaded.complete_delivery(reconstructed)

        assert reconstructed == accepted
        assert completed.occurrence == accepted.occurrence
        assert all(record.instant == 0.5 for record in loaded.records)

    def test_accepting_a_delivery_begins_without_completing_its_source_occurrence(self):
        history = InMemoryHistoryStore()
        token = Token("X", {"event": 7})
        engine = Engine.create(
            _ingress_net(),
            "accepted-delivery",
            history=history,
            dispatch=InMemoryDispatch(),
        )

        accepted = engine.accept_delivery(SRC, token, identity="event-7")

        assert (accepted.source, accepted.identity, accepted.occurrence) == (SRC, "event-7", 1)
        assert history.records[-2:] == (
            ExternalEventDelivered(SRC, (token,), identity="event-7", occurrence=1),
            FiringBegun(SRC, occurrence=1),
        )
        assert not any(isinstance(record, TokensProduced | FiringCompleted) for record in history.records)
        assert engine.marking == Marking()

    def test_returned_identity_composes_with_exact_unfinished_redelivery(self):
        history = InMemoryHistoryStore()
        token = Token("X", {"event": 7})
        engine = Engine.create(
            _ingress_net(),
            "returned-delivery-identity",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        accepted = engine.accept_delivery(SRC, token, identity="event-7")
        accepted_records = history.records

        reconstructed = engine.accept_delivery(SRC, token, identity=accepted.identity)

        assert reconstructed == accepted
        assert history.records == accepted_records

    def test_acceptance_is_visible_from_an_independently_reopened_durable_store(self, tmp_path):
        path = tmp_path / "accepted.jsonl"
        token = Token("X", {"event": 7})
        engine = Engine.create(
            _ingress_net(),
            "durable-acceptance",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )

        accepted = engine.accept_delivery(SRC, token, identity="event-7")

        assert accepted.occurrence == 1
        assert JsonlHistoryStore(path).records[-2:] == (
            ExternalEventDelivered(SRC, (token,), identity="event-7", occurrence=1),
            FiringBegun(SRC, occurrence=1),
        )

    def test_hostile_completion_store_refusal_leaves_the_accepted_occurrence_unfinished_for_fresh_retry(self):
        class HostileCommitRefusal(OSError):
            def __str__(self):
                raise AssertionError("completion refusal handling must not render the backend exception")

        refusal = HostileCommitRefusal()

        class RefuseOneCompletion(InMemoryHistoryStore):
            refuse_completion = False

            def extend(self, records):
                if self.refuse_completion and any(isinstance(record, FiringCompleted) for record in records):
                    self.refuse_completion = False
                    raise refusal
                super().extend(records)

        history = RefuseOneCompletion()
        token = Token("X", {"event": 7})
        engine = Engine.create(
            _ingress_net(),
            "refused-completion",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        accepted = engine.accept_delivery(SRC, token, identity="event-7")
        accepted_records = history.records
        history.refuse_completion = True

        with pytest.raises(HostileCommitRefusal) as raised:
            engine.complete_delivery(accepted)

        assert raised.value is refusal
        assert history.records == accepted_records
        assert not any(isinstance(record, FiringFailed) for record in history.records)
        resumed = Engine.load(
            _ingress_net(),
            "refused-completion",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        reconstructed = resumed.accept_delivery(SRC, token, identity="event-7")
        assert reconstructed == accepted
        assert resumed.complete_delivery(reconstructed).occurrence == accepted.occurrence

    def test_composed_delivery_requires_stable_identity_before_history_mutation(self):
        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "identified-composition",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        before = history.records

        with pytest.raises(TypeError, match="identity"):
            engine.deliver(SRC, Token("X"))

        assert history.records == before

        with pytest.raises(ValueError, match="stable delivery identity"):
            engine.deliver(SRC, Token("X"), identity=None)

        assert history.records == before

    def test_load_refuses_a_complete_line_prefix_that_tears_the_acceptance_batch(self, tmp_path):
        path = tmp_path / "torn-acceptance.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "torn-acceptance",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        assert json.loads(lines[-2])["record"] == "ExternalEventDelivered"
        assert json.loads(lines[-1])["record"] == "FiringBegun"
        path.write_text("\n".join(lines[:-1]) + "\n")

        with pytest.raises(ValueError, match=r"replay divergence.*event-7.*matching FiringBegun"):
            Engine.load(
                _ingress_net(),
                "torn-acceptance",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_a_construction_batch_truncated_after_identity(self, tmp_path):
        path = tmp_path / "torn-construction-after-identity.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "torn-construction-after-identity",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.close()
        [identity, *_] = path.read_text().splitlines()
        path.write_text(f"{identity}\n")
        torn = path.read_bytes()

        with pytest.raises(ValueError, match=r"replay divergence.*construction batch.*source registrations"):
            Engine.load(
                _ingress_net(),
                "torn-construction-after-identity",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

        assert path.read_bytes() == torn

    def test_load_refuses_a_construction_batch_truncated_between_source_registrations(self, tmp_path):
        second_source = NetPath("second-source")
        net = Net(
            places=[Place(A), Place(B)],
            transitions=[Transition(SRC), Transition(second_source)],
            arcs=[Arc(SRC, A), Arc(second_source, B)],
        )
        path = tmp_path / "torn-construction-between-registrations.jsonl"
        engine = Engine.create(
            net,
            "torn-construction-between-registrations",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.close()
        lines = path.read_text().splitlines()
        assert [json.loads(line)["record"] for line in lines] == [
            "InstanceCreated",
            "DeliveryRegistrationOpened",
            "DeliveryRegistrationOpened",
        ]
        path.write_text("\n".join(lines[:-1]) + "\n")
        torn = path.read_bytes()

        with pytest.raises(ValueError, match=r"replay divergence.*construction batch.*source registrations"):
            Engine.load(
                net,
                "torn-construction-between-registrations",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

        assert path.read_bytes() == torn

    def test_load_refuses_initial_token_color_the_live_constructor_rejects(self, tmp_path):
        net = Net(
            places=[Place(A, color="Expected"), Place(B)],
            transitions=[Transition(SRC)],
            arcs=[Arc(SRC, B)],
        )
        path = tmp_path / "invalid-initial-color.jsonl"
        engine = Engine.create(
            net,
            "invalid-initial-color",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("Expected"),)}),
        )
        engine.close()
        records = [json.loads(line) for line in path.read_text().splitlines()]
        initialized = next(record for record in records if record["record"] == "TokensInitialized")
        initialized["tokens"][0]["color"] = "Wrong"
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
        malformed = path.read_bytes()

        with pytest.raises(ValueError, match=r"initial marking.*requires color 'Expected'.*got 'Wrong'"):
            Engine.load(
                net,
                "invalid-initial-color",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

        assert path.read_bytes() == malformed

    def test_load_refuses_duplicate_initialization_for_one_place(self, tmp_path):
        path = tmp_path / "duplicate-initial-place.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "duplicate-initial-place",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            marking=Marking({B: (Token("Seed"),)}),
        )
        engine.close()
        records = [json.loads(line) for line in path.read_text().splitlines()]
        initialized = next(record for record in records if record["record"] == "TokensInitialized")
        records.insert(records.index(initialized) + 1, initialized.copy())
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
        malformed = path.read_bytes()

        with pytest.raises(ValueError, match=r"replay divergence.*place b.*initialized exactly once"):
            Engine.load(
                _ingress_net(),
                "duplicate-initial-place",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

        assert path.read_bytes() == malformed

    def test_load_refuses_initialization_for_an_unknown_place(self, tmp_path):
        path = tmp_path / "unknown-initial-place.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "unknown-initial-place",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            marking=Marking({B: (Token("Seed"),)}),
        )
        engine.close()
        records = [json.loads(line) for line in path.read_text().splitlines()]
        initialized = next(record for record in records if record["record"] == "TokensInitialized")
        initialized["place"] = "unknown"
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
        malformed = path.read_bytes()

        with pytest.raises(ValueError, match=r"replay divergence.*unknown place unknown.*initial marking"):
            Engine.load(
                _ingress_net(),
                "unknown-initial-place",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

        assert path.read_bytes() == malformed

    def test_load_refuses_initialization_after_the_construction_instant(self, tmp_path):
        path = tmp_path / "late-initial-tokens.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "late-initial-tokens",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            marking=Marking({B: (Token("Seed"),)}),
        )
        engine.close()
        records = [json.loads(line) for line in path.read_text().splitlines()]
        initialized = next(record for record in records if record["record"] == "TokensInitialized")
        initialized["instant"] = 1
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
        malformed = path.read_bytes()

        with pytest.raises(ValueError, match=r"replay divergence.*initial tokens.*instant 1.*construction instant 0"):
            Engine.load(
                _ingress_net(),
                "late-initial-tokens",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

        assert path.read_bytes() == malformed

    def test_load_refuses_initialization_after_source_free_construction_ended(self, tmp_path):
        net = Net(places=[Place(A)], transitions=[], arcs=[])
        path = tmp_path / "late-source-free-initialization.jsonl"
        engine = Engine.create(
            net,
            "late-source-free-initialization",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.open_scope("runtime")
        engine.close()
        JsonlHistoryStore(path).append(TokensInitialized(A, (Token("Forged"),)))
        malformed = path.read_bytes()

        with pytest.raises(ValueError, match=r"replay divergence.*TokensInitialized.*outside.*construction"):
            Engine.load(
                net,
                "late-source-free-initialization",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

        assert path.read_bytes() == malformed

    def test_load_refuses_a_history_record_subclass_before_reading_its_fields(self):
        class RedirectingRegistration(DeliveryRegistrationOpened):
            redirect = False

            def __getattribute__(self, name):
                if name in {"source", "key", "occurrence", "instant"} and object.__getattribute__(self, "redirect"):
                    raise AssertionError("registration record subclass field was read")
                return super().__getattribute__(name)

        canonical = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "strict-history-records",
            history=canonical,
            dispatch=InMemoryDispatch(),
        )
        engine.close()
        identity, registration = canonical.records
        hostile = RedirectingRegistration(
            registration.source,
            registration.key,
            occurrence=registration.occurrence,
            instant=registration.instant,
        )
        object.__setattr__(hostile, "redirect", True)
        malformed = InMemoryHistoryStore()
        malformed.extend([identity, hostile])

        with pytest.raises(ValueError, match=r"replay divergence.*record at position 1.*exact record type"):
            Engine.load(
                _ingress_net(),
                "strict-history-records",
                history=malformed,
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_an_acceptance_recorded_after_the_source_was_sealed(self, tmp_path):
        path = tmp_path / "unarmed-acceptance.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "unarmed-acceptance",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.seal(SRC)
        engine.close()
        JsonlHistoryStore(path).extend(
            (
                ExternalEventDelivered(SRC, (Token("X"),), identity="event-7", occurrence=1),
                FiringBegun(SRC, occurrence=1),
            )
        )

        with pytest.raises(ValueError, match=r"replay divergence.*event-7.*no armed delivery registration"):
            Engine.load(
                _ingress_net(),
                "unarmed-acceptance",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_a_delivery_authorized_by_a_forged_initial_registration(self, tmp_path):
        path = tmp_path / "forged-registration-reopen.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "forged-registration-reopen",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.seal(SRC)
        engine.close()
        JsonlHistoryStore(path).extend(
            (
                DeliveryRegistrationOpened(SRC, "default", occurrence=None),
                ExternalEventDelivered(SRC, (Token("X"),), identity="event-7", occurrence=1),
                FiringBegun(SRC, occurrence=1),
                FiringCompleted(SRC, occurrence=1),
            )
        )

        with pytest.raises(
            ValueError,
            match=r"replay divergence.*uncorrelated delivery registration.*only in the initial construction batch",
        ):
            Engine.load(
                _ingress_net(),
                "forged-registration-reopen",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_a_delivery_authorized_by_an_orphan_correlated_registration(self, tmp_path):
        path = tmp_path / "orphan-correlated-registration.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "orphan-correlated-registration",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.seal(SRC)
        engine.close()
        JsonlHistoryStore(path).extend(
            (
                DeliveryRegistrationOpened(SRC, "forged", occurrence=1),
                ExternalEventDelivered(SRC, (Token("X"),), identity="event-7", occurrence=2),
                FiringBegun(SRC, occurrence=2),
                FiringCompleted(SRC, occurrence=2),
            )
        )

        with pytest.raises(
            ValueError,
            match=r"replay divergence.*correlated delivery registration.*occurrence 1.*writer-valid completion batch",
        ):
            Engine.load(
                _ingress_net(),
                "orphan-correlated-registration",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_a_delivery_authorized_by_an_impossible_ended_firing(self, tmp_path):
        path = tmp_path / "impossible-ended-registration.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "impossible-ended-registration",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.seal(SRC)
        engine.close()
        JsonlHistoryStore(path).extend(
            (
                CandidateSelected(T, occurrence=1),
                FiringBegun(T, occurrence=1),
                DeliveryRegistrationOpened(SRC, "forged", occurrence=1),
                FiringCompleted(T, occurrence=1),
            )
        )
        malformed = path.read_bytes()

        with pytest.raises(
            ValueError,
            match=r"cannot resume firing occurrence 1 \(t\).*consume selections do not match",
        ):
            Engine.load(
                _ingress_net(),
                "impossible-ended-registration",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

        assert path.read_bytes() == malformed

    def test_load_refuses_a_late_begin_fact_that_retroactively_authorizes_delivery(self, tmp_path):
        path = tmp_path / "late-begin-registration.jsonl"
        seed = Token("Seed")
        engine = Engine.create(
            _ingress_net(),
            "late-begin-registration",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (seed,)}),
        )
        engine.seal(SRC)
        engine.close()
        JsonlHistoryStore(path).extend(
            (
                CandidateSelected(T, occurrence=1),
                FiringBegun(T, occurrence=1),
                TokensProduced(B, (Token("Projected"),), occurrence=1),
                DeliveryRegistrationOpened(SRC, "forged", occurrence=1),
                FiringCompleted(T, occurrence=1),
                TokensConsumed(A, (seed,), occurrence=1),
                ExternalEventDelivered(SRC, (Token("X"),), identity="event-7", occurrence=2),
                FiringBegun(SRC, occurrence=2),
            )
        )
        malformed = path.read_bytes()

        with pytest.raises(
            ValueError,
            match=r"replay divergence.*TokensConsumed.*occurrence 1.*after.*terminal",
        ):
            Engine.load(
                _ingress_net(),
                "late-begin-registration",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

        assert path.read_bytes() == malformed

    def test_load_refuses_an_interleaved_begin_batch_that_authorizes_delivery(self, tmp_path):
        path = tmp_path / "interleaved-begin-registration.jsonl"
        seed = Token("Seed")

        def rearm(binding, outputs):
            del binding, outputs
            return HandlerResult(
                tokens={B: (Token("Projected"),)},
                opens=(DeliveryRegistration(SRC, "forged"),),
            )

        net = Net(
            places=[Place(A), Place(B)],
            transitions=[Transition(SRC), Transition(T, handler="rearm")],
            arcs=[Arc(SRC, A), Arc(A, T), Arc(T, B)],
        )
        engine = Engine.create(
            net,
            "interleaved-begin-registration",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            handlers={"rearm": rearm},
            marking=Marking({A: (seed,)}),
        )
        engine.seal(SRC)
        engine.close()
        JsonlHistoryStore(path).extend(
            (
                CandidateSelected(T, occurrence=1),
                FiringBegun(T, occurrence=1),
                ScopeOpened(LifecycleScope("unrelated", 1)),
                TokensConsumed(A, (seed,), occurrence=1),
                TokensProduced(B, (Token("Projected"),), occurrence=1),
                DeliveryRegistrationOpened(SRC, "forged", occurrence=1),
                FiringCompleted(T, occurrence=1),
                ExternalEventDelivered(SRC, (Token("X"),), identity="event-7", occurrence=2),
                FiringBegun(SRC, occurrence=2),
            )
        )
        malformed = path.read_bytes()

        with pytest.raises(
            ValueError,
            match=r"replay divergence.*TokensConsumed.*occurrence 1.*contiguous begin batch",
        ):
            Engine.load(
                net,
                "interleaved-begin-registration",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
                handlers={"rearm": rearm},
            )

        assert path.read_bytes() == malformed

    @pytest.mark.parametrize("fact_kind", ["requested", "completed", "failed"])
    def test_load_refuses_each_foreign_activity_fact_that_authorizes_delivery(self, tmp_path, fact_kind):
        path = tmp_path / f"foreign-{fact_kind}-registration.jsonl"
        seed = Token("Seed")
        ghost = NetPath("ghost")

        class Rearm:
            def prepare(self, binding):
                del binding
                return ActivityInvocation("rearm", input={"event": 7})

            def project(self, binding, result):
                del binding, result
                return HandlerResult(
                    tokens={B: (Token("Projected"),)},
                    opens=(DeliveryRegistration(SRC, "forged"),),
                )

        net = Net(
            places=[Place(A), Place(B)],
            transitions=[Transition(SRC), Transition(T, handler="rearm")],
            arcs=[Arc(SRC, A), Arc(A, T), Arc(T, B)],
        )
        engine = Engine.create(
            net,
            f"foreign-{fact_kind}-registration",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            handlers={"rearm": Rearm()},
            marking=Marking({A: (seed,)}),
        )
        engine.seal(SRC)
        engine.close()
        invocation = ActivityInvocation("rearm", input={"event": 7})
        requested = ActivityRequested(
            ghost if fact_kind == "requested" else T,
            activity=invocation.activity,
            input=invocation.input,
            policy=invocation.policy,
            correlation="occurrence-1",
            idempotency="occurrence-1",
            occurrence=1,
        )
        if fact_kind == "failed":
            terminal = ActivityFailed(ghost, "failed", occurrence=1)
        else:
            terminal = ActivityCompleted(ghost if fact_kind == "completed" else T, {"ok": True}, occurrence=1)
        JsonlHistoryStore(path).extend(
            (
                CandidateSelected(T, occurrence=1),
                FiringBegun(T, occurrence=1),
                TokensConsumed(A, (seed,), occurrence=1),
                requested,
                terminal,
                TokensProduced(B, (Token("Projected"),), occurrence=1),
                DeliveryRegistrationOpened(SRC, "forged", occurrence=1),
                FiringCompleted(T, occurrence=1),
                ExternalEventDelivered(SRC, (Token("X"),), identity="event-7", occurrence=2),
                FiringBegun(SRC, occurrence=2),
            )
        )
        malformed = path.read_bytes()

        with pytest.raises(
            ValueError,
            match=rf"replay divergence.*Activity{fact_kind.title()}.*ghost.*begun transition t",
        ):
            Engine.load(
                net,
                f"foreign-{fact_kind}-registration",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
                handlers={"rearm": Rearm()},
            )

        assert path.read_bytes() == malformed

    def test_load_refuses_a_foreign_quarantined_activity_fact(self, tmp_path):
        path = tmp_path / "foreign-quarantined-activity.jsonl"
        ghost = NetPath("ghost")

        class Work:
            def prepare(self, binding):
                del binding
                return ActivityInvocation("work")

            def project(self, binding, result):
                del binding, result
                return {B: (Token("Done"),)}

        net = Net(
            places=[Place(A), Place(B)],
            transitions=[Transition(SRC), Transition(T, handler="work")],
            arcs=[Arc(SRC, A), Arc(A, T), Arc(T, B)],
        )
        engine = Engine.create(
            net,
            "foreign-quarantined-activity",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            handlers={"work": Work()},
        )
        scope = engine.open_scope("request")
        engine.deliver(SRC, Token("Ready"), identity="seed", scope=scope)
        engine.advance()
        engine.close_scope(scope)
        engine.close()
        occurrence = next(
            record.occurrence for record in JsonlHistoryStore(path) if isinstance(record, CandidateSelected)
        )
        JsonlHistoryStore(path).append(
            ActivityTerminalQuarantined(
                ghost,
                {"kind": "completed", "value": {"ok": True}},
                scope,
                occurrence=occurrence,
            )
        )
        malformed = path.read_bytes()

        with pytest.raises(
            ValueError,
            match=r"replay divergence.*ActivityTerminalQuarantined.*ghost.*begun transition t",
        ):
            Engine.load(
                net,
                "foreign-quarantined-activity",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
                handlers={"work": Work()},
            )

        assert path.read_bytes() == malformed

    def test_load_refuses_initial_tokens_recorded_after_registration_opened(self, tmp_path):
        path = tmp_path / "disordered-construction-prefix.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "disordered-construction-prefix",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            marking=Marking({B: (Token("Seed"),)}),
        )
        engine.accept_delivery(SRC, Token("X"), identity="event-7")
        engine.close()
        records = [json.loads(line) for line in path.read_text().splitlines()]
        initialized = next(index for index, record in enumerate(records) if record["record"] == "TokensInitialized")
        registration = next(
            index
            for index, record in enumerate(records)
            if record["record"] == "DeliveryRegistrationOpened" and record["occurrence"] is None
        )
        assert registration == initialized + 1
        records[initialized], records[registration] = records[registration], records[initialized]
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
        malformed = path.read_bytes()

        with pytest.raises(ValueError, match="replay divergence.*initial construction prefix"):
            Engine.load(
                _ingress_net(),
                "disordered-construction-prefix",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

        assert path.read_bytes() == malformed

    def test_load_refuses_a_queue_identity_subclass_before_reconstruction(self):
        class QueueIdentity(int):
            pass

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "queue-identity-subclass",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        scope = engine.open_scope("request")
        engine.deliver(SRC, Token("X"), identity="event-7", scope=scope)
        engine.close()
        produced = next(record for record in history if isinstance(record, TokensProduced))
        object.__setattr__(produced, "entries", (QueueIdentity(produced.entries[0]),))
        malformed = tuple(history)

        with pytest.raises(ValueError, match=r"TokensProduced entries.*exact positive integers"):
            Engine.load(
                _ingress_net(),
                "queue-identity-subclass",
                history=history,
                dispatch=InMemoryDispatch(),
            )

        assert tuple(history) == malformed

    def test_load_refuses_a_correlated_registration_separated_from_its_production(self, tmp_path):
        path = tmp_path / "separated-correlated-registration.jsonl"

        def open_registration(binding, outputs):
            del outputs
            return HandlerResult(
                {B: binding.tokens},
                opens=(DeliveryRegistration(SRC, "forged"),),
            )

        net = Net(
            places=[Place(A), Place(B), Place(C)],
            transitions=[Transition(T, handler="open"), Transition(SRC)],
            arcs=[Arc(A, T), Arc(T, B), Arc(SRC, C)],
        )
        engine = Engine.create(
            net,
            "separated-correlated-registration",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("Work"),)}),
            handlers={"open": open_registration},
        )
        engine.seal(SRC)
        engine.advance()
        engine.accept_delivery(SRC, Token("Event"), identity="event-7")
        engine.close()
        records = [json.loads(line) for line in path.read_text().splitlines()]
        production = next(
            index
            for index, record in enumerate(records)
            if record["record"] == "TokensProduced" and record["occurrence"] == 1
        )
        registration = next(
            index
            for index, record in enumerate(records)
            if record["record"] == "DeliveryRegistrationOpened"
            and record["occurrence"] == 1
            and record["key"] == "forged"
        )
        assert registration == production + 1
        records.insert(
            registration,
            {
                "record": "ScopeOpened",
                "schema": 5,
                "scope": {"name": "unrelated", "generation": 1},
                "instant": records[production]["instant"],
            },
        )
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
        malformed = path.read_bytes()

        with pytest.raises(
            ValueError,
            match=r"replay divergence.*correlated delivery registration.*occurrence 1.*writer-valid completion batch",
        ):
            Engine.load(
                net,
                "separated-correlated-registration",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
                handlers={"open": open_registration},
            )

        assert path.read_bytes() == malformed

    @pytest.mark.parametrize(
        ("event_occurrence", "begun_occurrence", "invalid_record"),
        [(1, True, "FiringBegun"), (0, 0, "ExternalEventDelivered")],
    )
    def test_load_refuses_noncanonical_acceptance_occurrences(
        self, tmp_path, event_occurrence, begun_occurrence, invalid_record
    ):
        path = tmp_path / "invalid-acceptance-occurrence.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "invalid-acceptance-occurrence",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        records = [json.loads(line) for line in path.read_text().splitlines()]
        records[-2]["occurrence"] = event_occurrence
        records[-1]["occurrence"] = begun_occurrence
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")

        with pytest.raises(ValueError, match=rf"{invalid_record} occurrence must be a positive integer"):
            Engine.load(
                _ingress_net(),
                "invalid-acceptance-occurrence",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_a_second_begin_for_one_delivery_occurrence(self, tmp_path):
        path = tmp_path / "duplicate-delivery-begin.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "duplicate-delivery-begin",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        assert json.loads(lines[-1])["record"] == "FiringBegun"
        path.write_text("\n".join((*lines, lines[-1])) + "\n")

        with pytest.raises(ValueError, match=r"replay divergence.*occurrence 1.*more than one FiringBegun"):
            Engine.load(
                _ingress_net(),
                "duplicate-delivery-begin",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_two_delivery_identities_that_share_one_occurrence(self, tmp_path):
        path = tmp_path / "aliased-delivery-occurrence.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "aliased-delivery-occurrence",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        second_delivery = json.loads(lines[-2])
        second_delivery["identity"] = "event-8"
        path.write_text("\n".join((*lines, json.dumps(second_delivery), lines[-1])) + "\n")

        with pytest.raises(ValueError, match=r"replay divergence.*occurrence 1.*initiated more than once"):
            Engine.load(
                _ingress_net(),
                "aliased-delivery-occurrence",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_an_empty_failure_for_an_accepted_delivery(self, tmp_path):
        path = tmp_path / "empty-delivery-failure.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "empty-delivery-failure",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        failed = {
            "record": "FiringFailed",
            "schema": 5,
            "transition": "src",
            "error": "",
            "occurrence": 1,
            "instant": 0,
        }
        path.write_text("\n".join((*lines, json.dumps(failed))) + "\n")

        with pytest.raises(
            ValueError,
            match=r"FiringFailed error must be a non-empty string of at most 4096 characters",
        ):
            Engine.load(
                _ingress_net(),
                "empty-delivery-failure",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_a_failure_with_a_string_subclass_before_redelivery_acknowledgement(self):
        class ShortenedOversizeFailure(str):
            def __len__(self):
                return 1

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "subclass-delivery-failure",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        forged = object.__new__(FiringFailed)
        object.__setattr__(forged, "transition", SRC)
        object.__setattr__(forged, "error", ShortenedOversizeFailure("x" * 4097))
        object.__setattr__(forged, "occurrence", 1)
        object.__setattr__(forged, "instant", 0)
        history.append(forged)
        malformed = history.records

        with pytest.raises(
            ValueError,
            match=r"FiringFailed error must be a non-empty string of at most 4096 characters",
        ):
            Engine.load(
                _ingress_net(),
                "subclass-delivery-failure",
                history=history,
                dispatch=InMemoryDispatch(),
            )

        assert history.records == malformed

    def test_load_refuses_a_mutated_delivery_identity_before_it_can_split_redelivery_authority(self):
        class AlternateHashIdentity(str):
            def __hash__(self):
                return hash(("alternate", str(self)))

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "mutated-delivery-identity",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        delivered = next(record for record in history.records if isinstance(record, ExternalEventDelivered))
        object.__setattr__(delivered, "identity", AlternateHashIdentity("event-7"))
        malformed = history.records

        with pytest.raises(
            ValueError,
            match=r"ExternalEventDelivered requires an exact non-empty string identity",
        ):
            Engine.load(
                _ingress_net(),
                "mutated-delivery-identity",
                history=history,
                dispatch=InMemoryDispatch(),
            )

        assert history.records == malformed

    def test_load_refuses_a_boolean_candidate_occurrence_before_lifecycle_folding(self):
        history = InMemoryHistoryStore()
        engine = Engine.create(
            _line_net(),
            "boolean-candidate-occurrence",
            history=history,
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("X"),)}),
        )
        engine.advance()
        engine.close()
        selected = next(record for record in history.records if isinstance(record, CandidateSelected))
        object.__setattr__(selected, "occurrence", True)
        malformed = history.records

        with pytest.raises(ValueError, match="CandidateSelected occurrence must be a positive integer"):
            Engine.load(
                _line_net(),
                "boolean-candidate-occurrence",
                history=history,
                dispatch=InMemoryDispatch(),
            )

        assert history.records == malformed

    def test_loaded_acceptance_is_detached_from_later_store_token_mutation(self):
        history = InMemoryHistoryStore()
        token = Token("X", {"event": 7})
        engine = Engine.create(
            _ingress_net(),
            "detached-replay-acceptance",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        accepted = engine.accept_delivery(SRC, token, identity="event-7")
        engine.close()
        resumed = Engine.load(
            _ingress_net(),
            "detached-replay-acceptance",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        delivered = next(record for record in history.records if isinstance(record, ExternalEventDelivered))
        delivered.tokens[0].data["event"] = 8
        mutated_records = history.records

        reconstructed = resumed.accept_delivery(SRC, token, identity="event-7")

        assert reconstructed == accepted
        assert history.records == mutated_records

    def test_load_refuses_an_ended_scheduled_source_before_movement_replay(self):
        history = InMemoryHistoryStore()
        net = Net(places=[Place(A)], transitions=[Transition(SRC)], arcs=[Arc(SRC, A)])
        engine = Engine.create(
            net,
            "ended-scheduled-source",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        engine.close()
        token = Token("X")
        history.extend(
            [
                CandidateSelected(SRC, occurrence=1),
                FiringBegun(SRC, occurrence=1),
                TokensProduced(A, (token,), occurrence=1),
                FiringCompleted(SRC, occurrence=1),
            ]
        )
        malformed = history.records

        with pytest.raises(ValueError, match="scheduled selection on a source transition"):
            Engine.load(
                net,
                "ended-scheduled-source",
                history=history,
                dispatch=InMemoryDispatch(),
            )

        assert history.records == malformed

    @pytest.mark.parametrize(
        ("terminal_record", "terminal_fields"),
        [("FiringCompleted", {}), ("FiringFailed", {"error": "boom"})],
    )
    def test_load_refuses_a_foreign_transition_terminal_for_an_accepted_delivery(
        self, tmp_path, terminal_record, terminal_fields
    ):
        path = tmp_path / "foreign-delivery-terminal.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "foreign-delivery-terminal",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        foreign_terminal = {
            "record": terminal_record,
            "schema": 5,
            "transition": "t",
            "occurrence": 1,
            "instant": 0,
            **terminal_fields,
        }
        path.write_text("\n".join((*lines, json.dumps(foreign_terminal))) + "\n")

        with pytest.raises(
            ValueError,
            match=r"replay divergence.*occurrence 1.*terminal transition t.*begun transition src",
        ):
            Engine.load(
                _ingress_net(),
                "foreign-delivery-terminal",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    @pytest.mark.parametrize(
        ("terminal_record", "terminal_fields"),
        [("FiringCompleted", {}), ("FiringFailed", {"error": "boom"})],
    )
    def test_load_refuses_a_boolean_terminal_occurrence(self, tmp_path, terminal_record, terminal_fields):
        path = tmp_path / "boolean-delivery-terminal.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "boolean-delivery-terminal",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        terminal = {
            "record": terminal_record,
            "schema": 5,
            "transition": "src",
            "occurrence": True,
            "instant": 0,
            **terminal_fields,
        }
        path.write_text("\n".join((*lines, json.dumps(terminal))) + "\n")

        with pytest.raises(ValueError, match=rf"{terminal_record} occurrence must be a positive integer"):
            Engine.load(
                _ingress_net(),
                "boolean-delivery-terminal",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    @pytest.mark.parametrize(
        ("terminal_record", "terminal_fields"),
        [("FiringCompleted", {}), ("FiringFailed", {"error": "boom"})],
    )
    def test_load_refuses_an_ended_delivery_recorded_on_a_non_source(self, tmp_path, terminal_record, terminal_fields):
        path = tmp_path / "ended-non-source-delivery.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "ended-non-source-delivery",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        records = [json.loads(line) for line in path.read_text().splitlines()]
        records[-2]["source"] = "t"
        records[-1]["transition"] = "t"
        records.append(
            {
                "record": terminal_record,
                "schema": 5,
                "transition": "t",
                "occurrence": 1,
                "instant": 0,
                **terminal_fields,
            }
        )
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")

        with pytest.raises(
            ValueError,
            match=r"accepted delivery identity 'event-7'.*transition t.*input arcs",
        ):
            Engine.load(
                _ingress_net(),
                "ended-non-source-delivery",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    @pytest.mark.parametrize(
        ("terminal_record", "terminal_fields"),
        [("FiringCompleted", {}), ("FiringFailed", {"error": "boom"})],
    )
    def test_load_refuses_an_ended_source_occurrence_with_an_activity_request(
        self, tmp_path, terminal_record, terminal_fields
    ):
        path = tmp_path / "ended-impure-source.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "ended-impure-source",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        records = [json.loads(line) for line in path.read_text().splitlines()]
        records.extend(
            [
                {
                    "record": "ActivityRequested",
                    "schema": 5,
                    "transition": "src",
                    "activity": "work",
                    "input": {"event": 7},
                    "policy": {
                        "attempts": 1,
                        "heartbeat_timeout": 30,
                        "initial_interval": 0,
                        "coefficient": 2,
                        "max_interval": 60,
                        "jitter": 0,
                        "start_to_close": None,
                        "schedule_to_close": None,
                    },
                    "correlation": "event-7",
                    "idempotency": "event-7",
                    "occurrence": 1,
                    "scope": None,
                    "instant": 0,
                },
                {
                    "record": terminal_record,
                    "schema": 5,
                    "transition": "src",
                    "occurrence": 1,
                    "instant": 0,
                    **terminal_fields,
                },
            ]
        )
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")

        with pytest.raises(
            ValueError,
            match=r"accepted delivery identity 'event-7'.*source occurrence 1.*ActivityRequested",
        ):
            Engine.load(
                _ingress_net(),
                "ended-impure-source",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_token_consumption_correlated_to_an_ended_source_occurrence(self, tmp_path):
        path = tmp_path / "ended-consuming-source.jsonl"
        seed = Token("Seed", 1)
        engine = Engine.create(
            _ingress_net(),
            "ended-consuming-source",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (seed,)}),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        records = [json.loads(line) for line in path.read_text().splitlines()]
        records.extend(
            [
                {
                    "record": "TokensConsumed",
                    "schema": 5,
                    "place": "a",
                    "tokens": [{"color": "Seed", "data": 1}],
                    "occurrence": 1,
                    "entries": [],
                    "scope": None,
                    "instant": 0,
                },
                {
                    "record": "FiringCompleted",
                    "schema": 5,
                    "transition": "src",
                    "occurrence": 1,
                    "instant": 0,
                },
            ]
        )
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")

        with pytest.raises(
            ValueError,
            match=r"accepted delivery identity 'event-7'.*source occurrence 1.*TokensConsumed",
        ):
            Engine.load(
                _ingress_net(),
                "ended-consuming-source",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_production_after_an_accepted_delivery_completed(self, tmp_path):
        path = tmp_path / "production-after-delivery-completion.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "production-after-delivery-completion",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        terminal = {
            "record": "FiringCompleted",
            "schema": 5,
            "transition": "src",
            "occurrence": 1,
            "instant": 0,
        }
        late_production = {
            "record": "TokensProduced",
            "schema": 5,
            "place": "a",
            "tokens": [{"color": "X", "data": {"event": 7}}],
            "occurrence": 1,
            "entries": [],
            "scope": None,
            "instant": 0,
        }
        path.write_text(
            "\n".join((*lines, json.dumps(late_production), json.dumps(terminal), json.dumps(late_production))) + "\n"
        )

        with pytest.raises(
            ValueError,
            match=r"accepted delivery identity 'event-7'.*TokensProduced after FiringCompleted",
        ):
            Engine.load(
                _ingress_net(),
                "production-after-delivery-completion",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_an_accepted_delivery_completion_effect_before_its_acceptance(self, tmp_path):
        path = tmp_path / "production-before-delivery-acceptance.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "production-before-delivery-acceptance",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        production = {
            "record": "TokensProduced",
            "schema": 5,
            "place": "a",
            "tokens": [{"color": "X", "data": {"event": 7}}],
            "occurrence": 1,
            "entries": [],
            "scope": None,
            "instant": 0,
        }
        terminal = {
            "record": "FiringCompleted",
            "schema": 5,
            "transition": "src",
            "occurrence": 1,
            "instant": 0,
        }
        path.write_text("\n".join((*lines[:-2], json.dumps(production), *lines[-2:], json.dumps(terminal))) + "\n")

        with pytest.raises(
            ValueError,
            match=r"accepted delivery identity 'event-7'.*contains TokensProduced before its acceptance pair",
        ):
            Engine.load(
                _ingress_net(),
                "production-before-delivery-acceptance",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_accepted_delivery_production_outside_the_source_output_arcs(self, tmp_path):
        path = tmp_path / "delivery-production-outside-output.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "delivery-production-outside-output",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        foreign_production = {
            "record": "TokensProduced",
            "schema": 5,
            "place": "b",
            "tokens": [{"color": "X", "data": {"event": 7}}],
            "occurrence": 1,
            "entries": [],
            "scope": None,
            "instant": 0,
        }
        terminal = {
            "record": "FiringCompleted",
            "schema": 5,
            "transition": "src",
            "occurrence": 1,
            "instant": 0,
        }
        path.write_text("\n".join((*lines, json.dumps(foreign_production), json.dumps(terminal))) + "\n")

        with pytest.raises(
            ValueError,
            match=r"accepted delivery identity 'event-7'.*production on b.*output arc",
        ):
            Engine.load(
                _ingress_net(),
                "delivery-production-outside-output",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_accepted_delivery_production_with_a_color_the_output_arc_does_not_admit(self, tmp_path):
        path = tmp_path / "delivery-production-wrong-color.jsonl"
        net = Net(
            places=[Place(A, color="Expected"), Place(B)],
            transitions=[Transition(SRC), Transition(T)],
            arcs=[Arc(SRC, A), Arc(A, T), Arc(T, B)],
        )
        engine = Engine.create(
            net,
            "delivery-production-wrong-color",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("Other", {"event": 7}), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        wrong_color = {
            "record": "TokensProduced",
            "schema": 5,
            "place": "a",
            "tokens": [{"color": "Other", "data": {"event": 7}}],
            "occurrence": 1,
            "entries": [],
            "scope": None,
            "instant": 0,
        }
        terminal = {
            "record": "FiringCompleted",
            "schema": 5,
            "transition": "src",
            "occurrence": 1,
            "instant": 0,
        }
        path.write_text("\n".join((*lines, json.dumps(wrong_color), json.dumps(terminal))) + "\n")

        with pytest.raises(
            ValueError,
            match=r"accepted delivery identity 'event-7'.*production on a.*not admitted.*output arc",
        ):
            Engine.load(
                net,
                "delivery-production-wrong-color",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_a_passthrough_completion_that_omits_its_output(self, tmp_path):
        path = tmp_path / "delivery-passthrough-output-omitted.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "delivery-passthrough-output-omitted",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        terminal = {
            "record": "FiringCompleted",
            "schema": 5,
            "transition": "src",
            "occurrence": 1,
            "instant": 0,
        }
        path.write_text("\n".join((*lines, json.dumps(terminal))) + "\n")
        malformed = path.read_bytes()

        with pytest.raises(ValueError, match=r"accepted delivery identity 'event-7'.*default passthrough.*productions"):
            Engine.load(
                _ingress_net(),
                "delivery-passthrough-output-omitted",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

        assert path.read_bytes() == malformed

    @pytest.mark.parametrize(
        ("accepted_data", "substituted_data"),
        [
            ({"event": 7}, {"event": 8}),
            (True, 1),
            (1, 1.0),
            (-0.0, 0.0),
        ],
        ids=("object-value", "boolean-for-integer", "integer-for-float", "negative-for-positive-zero"),
    )
    def test_load_refuses_a_passthrough_completion_that_substitutes_its_output(
        self, tmp_path, accepted_data, substituted_data
    ):
        path = tmp_path / "delivery-passthrough-output-substituted.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "delivery-passthrough-output-substituted",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", accepted_data), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        production = {
            "record": "TokensProduced",
            "schema": 5,
            "place": "a",
            "tokens": [{"color": "X", "data": substituted_data}],
            "occurrence": 1,
            "entries": [],
            "scope": None,
            "instant": 0,
        }
        terminal = {
            "record": "FiringCompleted",
            "schema": 5,
            "transition": "src",
            "occurrence": 1,
            "instant": 0,
        }
        path.write_text("\n".join((*lines, json.dumps(production), json.dumps(terminal))) + "\n")
        malformed = path.read_bytes()

        with pytest.raises(ValueError, match=r"accepted delivery identity 'event-7'.*default passthrough.*productions"):
            Engine.load(
                _ingress_net(),
                "delivery-passthrough-output-substituted",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

        assert path.read_bytes() == malformed

    def test_load_refuses_a_passthrough_completion_with_registration_effects(self, tmp_path):
        path = tmp_path / "delivery-passthrough-registration-effect.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "delivery-passthrough-registration-effect",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        production = {
            "record": "TokensProduced",
            "schema": 5,
            "place": "a",
            "tokens": [{"color": "X", "data": {"event": 7}}],
            "occurrence": 1,
            "entries": [],
            "scope": None,
            "instant": 0,
        }
        opened = {
            "record": "DeliveryRegistrationOpened",
            "schema": 5,
            "source": "src",
            "key": "forged",
            "occurrence": 1,
            "instant": 0,
        }
        terminal = {
            "record": "FiringCompleted",
            "schema": 5,
            "transition": "src",
            "occurrence": 1,
            "instant": 0,
        }
        path.write_text("\n".join((*lines, json.dumps(production), json.dumps(opened), json.dumps(terminal))) + "\n")
        malformed = path.read_bytes()

        with pytest.raises(
            ValueError,
            match=r"accepted delivery identity 'event-7'.*default passthrough.*delivery-registration effects",
        ):
            Engine.load(
                _ingress_net(),
                "delivery-passthrough-registration-effect",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

        assert path.read_bytes() == malformed

    def test_load_refuses_a_disordered_accepted_delivery_completion_batch(self, tmp_path):
        path = tmp_path / "disordered-delivery-completion.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "disordered-delivery-completion",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        opened = {
            "record": "DeliveryRegistrationOpened",
            "schema": 5,
            "source": "src",
            "key": "secondary",
            "occurrence": 1,
            "instant": 0,
        }
        production = {
            "record": "TokensProduced",
            "schema": 5,
            "place": "a",
            "tokens": [{"color": "X", "data": {"event": 7}}],
            "occurrence": 1,
            "entries": [],
            "scope": None,
            "instant": 0,
        }
        terminal = {
            "record": "FiringCompleted",
            "schema": 5,
            "transition": "src",
            "occurrence": 1,
            "instant": 0,
        }
        path.write_text("\n".join((*lines, json.dumps(opened), json.dumps(production), json.dumps(terminal))) + "\n")

        with pytest.raises(
            ValueError,
            match=r"replay divergence.*correlated delivery registration.*occurrence 1.*writer-valid completion batch",
        ):
            Engine.load(
                _ingress_net(),
                "disordered-delivery-completion",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_accepted_delivery_production_outside_its_lifecycle_scope(self, tmp_path):
        path = tmp_path / "delivery-production-wrong-scope.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "delivery-production-wrong-scope",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        scope = engine.open_scope("draft")
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7", scope=scope)
        engine.close()
        lines = path.read_text().splitlines()
        wrong_scope = {
            "record": "TokensProduced",
            "schema": 5,
            "place": "a",
            "tokens": [{"color": "X", "data": {"event": 7}}],
            "occurrence": 1,
            "entries": [],
            "scope": None,
            "instant": 0,
        }
        terminal = {
            "record": "FiringCompleted",
            "schema": 5,
            "transition": "src",
            "occurrence": 1,
            "instant": 0,
        }
        path.write_text("\n".join((*lines, json.dumps(wrong_scope), json.dumps(terminal))) + "\n")

        with pytest.raises(
            ValueError,
            match=r"accepted delivery identity 'event-7'.*production on a.*scope None.*draft",
        ):
            Engine.load(
                _ingress_net(),
                "delivery-production-wrong-scope",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_an_accepted_delivery_completion_batch_split_across_instants(self, tmp_path):
        path = tmp_path / "split-delivery-completion.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "split-delivery-completion",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        production = {
            "record": "TokensProduced",
            "schema": 5,
            "place": "a",
            "tokens": [{"color": "X", "data": {"event": 7}}],
            "occurrence": 1,
            "entries": [],
            "scope": None,
            "instant": 0,
        }
        terminal = {
            "record": "FiringCompleted",
            "schema": 5,
            "transition": "src",
            "occurrence": 1,
            "instant": 1,
        }
        path.write_text("\n".join((*lines, json.dumps(production), json.dumps(terminal))) + "\n")

        with pytest.raises(
            ValueError,
            match=r"accepted delivery identity 'event-7'.*completion batch changes instant from 0 to 1",
        ):
            Engine.load(
                _ingress_net(),
                "split-delivery-completion",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_interleaved_accepted_delivery_completion_batches(self, tmp_path):
        path = tmp_path / "interleaved-delivery-completions.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "interleaved-delivery-completions",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 1}), identity="event-1")
        engine.accept_delivery(SRC, Token("X", {"event": 2}), identity="event-2")
        engine.close()
        lines = path.read_text().splitlines()

        def production(event, occurrence):
            return {
                "record": "TokensProduced",
                "schema": 5,
                "place": "a",
                "tokens": [{"color": "X", "data": {"event": event}}],
                "occurrence": occurrence,
                "entries": [],
                "scope": None,
                "instant": 0,
            }

        def terminal(occurrence):
            return {
                "record": "FiringCompleted",
                "schema": 5,
                "transition": "src",
                "occurrence": occurrence,
                "instant": 0,
            }

        forged = (production(1, 1), production(2, 2), terminal(1), terminal(2))
        path.write_text("\n".join((*lines, *(json.dumps(record) for record in forged))) + "\n")

        with pytest.raises(
            ValueError,
            match=r"accepted delivery identity 'event-1'.*completion batch.*interrupted by TokensProduced.*occurrence 2",
        ):
            Engine.load(
                _ingress_net(),
                "interleaved-delivery-completions",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_a_boolean_accepted_delivery_production_occurrence(self, tmp_path):
        path = tmp_path / "boolean-delivery-production.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "boolean-delivery-production",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        production = {
            "record": "TokensProduced",
            "schema": 5,
            "place": "a",
            "tokens": [{"color": "X", "data": {"event": 7}}],
            "occurrence": True,
            "entries": [],
            "scope": None,
            "instant": 0,
        }
        terminal = {
            "record": "FiringCompleted",
            "schema": 5,
            "transition": "src",
            "occurrence": 1,
            "instant": 0,
        }
        path.write_text("\n".join((*lines, json.dumps(production), json.dumps(terminal))) + "\n")

        with pytest.raises(ValueError, match="TokensProduced occurrence must be a positive integer"):
            Engine.load(
                _ingress_net(),
                "boolean-delivery-production",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    @pytest.mark.parametrize(
        ("occurrence", "key", "message"),
        [
            (True, "secondary", "DeliveryRegistrationOpened occurrence must be a positive integer"),
            (1, "", "DeliveryRegistrationOpened requires a non-empty string key"),
            (1, 7, "DeliveryRegistrationOpened requires a non-empty string key"),
        ],
    )
    def test_load_refuses_malformed_registration_effects_in_an_accepted_delivery_completion(
        self, tmp_path, occurrence, key, message
    ):
        path = tmp_path / f"malformed-delivery-registration-{occurrence!s}-{key!s}.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "malformed-delivery-registration",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        engine.close()
        lines = path.read_text().splitlines()
        opened = {
            "record": "DeliveryRegistrationOpened",
            "schema": 5,
            "source": "src",
            "key": key,
            "occurrence": occurrence,
            "instant": 0,
        }
        terminal = {
            "record": "FiringCompleted",
            "schema": 5,
            "transition": "src",
            "occurrence": 1,
            "instant": 0,
        }
        path.write_text("\n".join((*lines, json.dumps(opened), json.dumps(terminal))) + "\n")

        with pytest.raises(ValueError, match=message):
            Engine.load(
                _ingress_net(),
                "malformed-delivery-registration",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_load_refuses_noncontiguous_scoped_entry_ids_in_an_accepted_delivery_completion(self, tmp_path):
        path = tmp_path / "noncontiguous-delivery-entries.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "noncontiguous-delivery-entries",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        scope = engine.open_scope("draft")
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7", scope=scope)
        engine.close()
        lines = path.read_text().splitlines()
        production = {
            "record": "TokensProduced",
            "schema": 5,
            "place": "a",
            "tokens": [{"color": "X", "data": {"event": 7}}],
            "occurrence": 1,
            "entries": [7],
            "scope": {"name": "draft", "generation": 1},
            "instant": 0,
        }
        terminal = {
            "record": "FiringCompleted",
            "schema": 5,
            "transition": "src",
            "occurrence": 1,
            "instant": 0,
        }
        path.write_text("\n".join((*lines, json.dumps(production), json.dumps(terminal))) + "\n")

        with pytest.raises(
            ValueError,
            match=r"accepted delivery identity 'event-7'.*queue-entry identities \(7,\).*expected \(1,\)",
        ):
            Engine.load(
                _ingress_net(),
                "noncontiguous-delivery-entries",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

    def test_completion_targets_only_the_accepted_source_occurrence(self):
        source_out = NetPath("source_out")

        class Work:
            def prepare(self, binding):
                return ActivityInvocation("work", input={"value": binding.tokens[0].data})

            def project(self, binding, result):
                return {B: (Token("Worked", result),)}

        net = Net(
            places=[Place(A), Place(B), Place(source_out)],
            transitions=[Transition(T, handler="work"), Transition(SRC)],
            arcs=[Arc(A, T), Arc(T, B), Arc(SRC, source_out)],
        )
        dispatch = InMemoryDispatch()
        engine = Engine.create(
            net,
            "targeted-completion",
            history=InMemoryHistoryStore(),
            dispatch=dispatch,
            marking=Marking({A: (Token("Work", 3),)}),
            handlers={"work": Work()},
        )
        engine.advance()
        delivered = Token("Event", 7)
        accepted = engine.accept_delivery(SRC, delivered, identity="event-7")

        completed = engine.complete_delivery(accepted)

        assert (completed.transition, completed.occurrence) == (SRC, 2)
        assert engine.marking == Marking({source_out: (delivered,)})
        assert [occurrence.id for occurrence in engine.in_flight] == [1]
        assert tuple(dispatch.pending) == (1,)
        assert [record.occurrence for record in engine.records if isinstance(record, FiringCompleted)] == [2]

    def test_fresh_completion_neither_reconciles_nor_advances_unrelated_work(self, tmp_path):
        candidate = NetPath("z")
        source_out = NetPath("source_out")
        candidate_calls = []

        class Work:
            def prepare(self, binding):
                return ActivityInvocation("work", input={"value": binding.tokens[0].data})

            def project(self, binding, result):
                return {B: (Token("Worked", result),)}

        def project_candidate(binding, outputs):
            candidate_calls.append(binding)
            return {B: outputs[B]}

        net = Net(
            places=[Place(A), Place(B), Place(C), Place(source_out)],
            transitions=[
                Transition(T, handler="work"),
                Transition(candidate, handler="candidate"),
                Transition(SRC),
            ],
            arcs=[
                Arc(A, T),
                Arc(T, B),
                Arc(C, candidate),
                Arc(candidate, B),
                Arc(SRC, source_out),
            ],
        )
        path = tmp_path / "targeted-reconstruction.jsonl"
        created = Engine.create(
            net,
            "targeted-reconstruction",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("Work", 3),), C: (Token("Candidate", 4),)}),
            handlers={"work": Work(), "candidate": project_candidate},
        )
        created.advance()
        delivered = Token("Event", 7)
        accepted = created.accept_delivery(SRC, delivered, identity="event-7")
        created.close()

        dispatch = InMemoryDispatch()
        loaded = Engine.load(
            net,
            "targeted-reconstruction",
            history=JsonlHistoryStore(path),
            dispatch=dispatch,
            handlers={"work": Work(), "candidate": project_candidate},
        )
        reconstructed = loaded.accept_delivery(SRC, delivered, identity="event-7")
        before_completion = loaded.records

        completed = loaded.complete_delivery(reconstructed)

        assert reconstructed == accepted
        assert (completed.transition, completed.occurrence) == (SRC, 2)
        assert loaded.records[len(before_completion) :] == (
            TokensProduced(source_out, (delivered,), occurrence=2),
            FiringCompleted(SRC, occurrence=2),
        )
        assert [occurrence.id for occurrence in loaded.in_flight] == [1]
        assert dispatch.pending == {}
        assert candidate_calls == []
        assert loaded.marking == Marking({C: (Token("Candidate", 4),), source_out: (delivered,)})

    def test_exact_redelivery_reconstructs_unfinished_acceptance_then_acknowledges_its_end(self):
        history = InMemoryHistoryStore()
        token = Token("X", {"event": 7})
        engine = Engine.create(
            _ingress_net(),
            "redelivered-acceptance",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        accepted = engine.accept_delivery(SRC, token, identity="event-7")
        accepted_records = history.records

        reconstructed = engine.accept_delivery(SRC, token, identity="event-7")

        assert reconstructed == accepted
        assert history.records == accepted_records

        engine.complete_delivery(reconstructed)
        completed_records = history.records
        acknowledged = engine.accept_delivery(SRC, token, identity="event-7")

        assert acknowledged == PriorAcknowledgement("event-7", accepted.occurrence)
        assert history.records == completed_records

    def test_identity_content_collision_fails_before_mutation(self):
        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "delivery-collision",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", {"event": 7}), identity="event-7")
        accepted_records = history.records

        with pytest.raises(ValueError) as conflict:
            engine.accept_delivery(SRC, Token("X", {"event": 8}), identity="event-7")

        assert str(conflict.value) == (
            "delivery identity conflict for 'event-7': recorded source NetPath('src'), scope None; "
            "attempted source NetPath('src'), scope None; canonical token content differs"
        )
        assert history.records == accepted_records

    def test_reserved_identity_subclass_is_rejected_before_mutation(self):
        class ReservedIdentity(str):
            def startswith(self, prefix, *bounds):
                del prefix, bounds
                return False

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "strict-delivery-identity",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        before = history.records

        with pytest.raises(ValueError, match="identity must be a non-empty string of the exact built-in type"):
            engine.accept_delivery(SRC, Token("X", {"event": 7}), identity=ReservedIdentity("occurrence-2"))

        assert history.records == before

    def test_changed_scope_subclass_is_rejected_before_redelivery_judgment(self):
        class EqualityScopeName(str):
            def __ne__(self, other):
                del other
                return False

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "strict-delivery-scope",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        token = Token("X", {"event": 7})
        engine.accept_delivery(SRC, token, identity="event-7", scope="expected")
        accepted_records = history.records

        with pytest.raises(TypeError, match="delivery scope must be an exact LifecycleScope, exact name string"):
            engine.accept_delivery(SRC, token, identity="event-7", scope=EqualityScopeName("changed"))

        assert history.records == accepted_records

    def test_changed_lifecycle_scope_subclass_is_rejected_before_redelivery_judgment(self):
        class EqualityScope(LifecycleScope):
            def __eq__(self, other):
                del other
                return True

            def __ne__(self, other):
                del other
                return False

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "strict-delivery-lifecycle-scope",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        token = Token("X", {"event": 7})
        scope = engine.open_scope("expected")
        engine.accept_delivery(SRC, token, identity="event-7", scope=scope)
        accepted_records = history.records

        with pytest.raises(TypeError, match="delivery scope must be an exact LifecycleScope, exact name string"):
            engine.accept_delivery(SRC, token, identity="event-7", scope=EqualityScope("changed", 2))

        assert history.records == accepted_records

    def test_changed_lifecycle_generation_subclass_is_rejected_before_redelivery_judgment(self):
        class EqualityGeneration(int):
            def __eq__(self, other):
                del other
                return True

            def __ne__(self, other):
                del other
                return False

            __hash__ = int.__hash__

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "strict-delivery-lifecycle-generation",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        token = Token("X", {"event": 7})
        scope = engine.open_scope("draft")
        engine.accept_delivery(SRC, token, identity="event-7", scope=scope)
        accepted_records = history.records

        with pytest.raises(ValueError, match="LifecycleScope generation must be a positive integer of the exact"):
            changed = LifecycleScope("draft", EqualityGeneration(2))
            engine.accept_delivery(SRC, token, identity="event-7", scope=changed)

        assert history.records == accepted_records

    def test_net_path_subclass_is_rejected_before_durable_acceptance(self, tmp_path):
        class AlternateSource(NetPath):
            def __str__(self):
                return "other"

        path = tmp_path / "strict-delivery-source.jsonl"
        engine = Engine.create(
            _ingress_net(),
            "strict-delivery-source",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        before = path.read_bytes()

        with pytest.raises(ValueError, match="delivery source must be an exact NetPath or built-in string"):
            engine.accept_delivery(
                AlternateSource("src"),
                Token("X", {"event": 7}),
                identity="event-7",
            )

        assert path.read_bytes() == before

    def test_seal_rejects_a_source_subclass_before_mutation(self):
        class RewritingSource(str):
            def split(self, separator=None, maximum=-1):
                del separator, maximum
                return ["src"]

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "strict-seal-source",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        before = history.records

        with pytest.raises(ValueError, match="seal source must be an exact NetPath or built-in string"):
            engine.seal(RewritingSource("unauthorized"))

        assert history.records == before

    def test_identity_source_collision_names_both_addresses_before_mutation(self):
        other_source = NetPath("other_source")
        net = Net(
            places=[Place(A), Place(B)],
            transitions=[Transition(SRC), Transition(other_source)],
            arcs=[Arc(SRC, A), Arc(other_source, B)],
        )
        history = InMemoryHistoryStore()
        engine = Engine.create(net, "source-collision", history=history, dispatch=InMemoryDispatch())
        token = Token("X", {"event": 7})
        engine.accept_delivery(SRC, token, identity="event-7")
        accepted_records = history.records

        with pytest.raises(ValueError) as conflict:
            engine.accept_delivery(other_source, token, identity="event-7")

        assert str(conflict.value) == (
            "delivery identity conflict for 'event-7': recorded source NetPath('src'), scope None; "
            "attempted source NetPath('other_source'), scope None; canonical token content matches"
        )
        assert history.records == accepted_records

    def test_identity_scope_collision_names_both_generations_before_mutation(self):
        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "scope-collision",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        scope = engine.open_scope("draft")
        token = Token("X", {"event": 7})
        engine.accept_delivery(SRC, token, identity="event-7", scope=scope)
        accepted_records = history.records
        other_scope = LifecycleScope("draft", 2)

        with pytest.raises(ValueError) as conflict:
            engine.accept_delivery(SRC, token, identity="event-7", scope=other_scope)

        assert str(conflict.value) == (
            "delivery identity conflict for 'event-7': recorded source NetPath('src'), "
            "scope LifecycleScope(name='draft', generation=1); attempted source NetPath('src'), "
            "scope LifecycleScope(name='draft', generation=2); canonical token content matches"
        )
        assert history.records == accepted_records

    @pytest.mark.parametrize(("accepted_data", "collision_data"), [(True, 1), (1, 1.0)])
    def test_identity_content_comparison_preserves_json_scalar_types(self, accepted_data, collision_data):
        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "typed-delivery-content",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        engine.accept_delivery(SRC, Token("X", accepted_data), identity="event-7")
        accepted_records = history.records

        with pytest.raises(ValueError, match=r"delivery identity conflict for 'event-7'.*token content differs"):
            engine.accept_delivery(SRC, Token("X", collision_data), identity="event-7")

        assert history.records == accepted_records

    def test_acceptance_snapshots_caller_owned_token_data_before_mutation(self):
        history = InMemoryHistoryStore()
        caller_data = {"items": [1]}
        engine = Engine.create(
            _ingress_net(),
            "snapshotted-delivery-content",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        accepted = engine.accept_delivery(SRC, Token("X", caller_data), identity="event-7")

        caller_data["items"].append(2)
        completed = engine.complete_delivery(accepted)

        recorded = next(record for record in history.records if isinstance(record, ExternalEventDelivered))
        assert recorded.tokens == (Token("X", {"items": [1]}),)
        assert completed.records[-2:] == (
            TokensProduced(A, (Token("X", {"items": [1]}),), occurrence=1),
            FiringCompleted(SRC, occurrence=1),
        )
        assert engine.marking == Marking({A: (Token("X", {"items": [1]}),)})

    def test_source_projection_cannot_mutate_the_accepted_delivery_fact(self, tmp_path):
        path = tmp_path / "handler-isolated-delivery.jsonl"

        def mutate(binding, outputs):
            del outputs
            binding.tokens[0].data["event"] = 8
            return {A: binding.tokens}

        net = Net(
            places=[Place(A), Place(B)],
            transitions=[Transition(SRC, handler="mutate"), Transition(T)],
            arcs=[Arc(SRC, A), Arc(A, T), Arc(T, B)],
        )
        token = Token("X", {"event": 7})
        engine = Engine.create(
            net,
            "handler-isolated-delivery",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            handlers={"mutate": mutate},
        )
        accepted = engine.accept_delivery(SRC, token, identity="event-7")

        completed = engine.complete_delivery(accepted)

        recorded = next(record for record in engine.records if isinstance(record, ExternalEventDelivered))
        assert recorded.tokens == (token,)
        assert completed.produced == ((A, Token("X", {"event": 8})),)
        assert engine.accept_delivery(SRC, token, identity="event-7") == PriorAcknowledgement("event-7", 1)
        engine.close()

        loaded = Engine.load(
            net,
            "handler-isolated-delivery",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            handlers={"mutate": mutate},
        )
        durable = next(record for record in loaded.records if isinstance(record, ExternalEventDelivered))
        assert durable.tokens == (token,)
        assert loaded.accept_delivery(SRC, token, identity="event-7") == PriorAcknowledgement("event-7", 1)

    def test_resumed_source_projection_cannot_mutate_the_accepted_delivery_fact(self, tmp_path):
        path = tmp_path / "resumed-handler-isolated-delivery.jsonl"

        def mutate(binding, outputs):
            del outputs
            binding.tokens[0].data["event"] = 8
            return {A: binding.tokens}

        net = Net(
            places=[Place(A), Place(B)],
            transitions=[Transition(SRC, handler="mutate"), Transition(T)],
            arcs=[Arc(SRC, A), Arc(A, T), Arc(T, B)],
        )
        token = Token("X", {"event": 7})
        created = Engine.create(
            net,
            "resumed-handler-isolated-delivery",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            handlers={"mutate": mutate},
        )
        accepted = created.accept_delivery(SRC, token, identity="event-7")
        created.close()
        loaded = Engine.load(
            net,
            "resumed-handler-isolated-delivery",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
            handlers={"mutate": mutate},
        )

        completed = loaded.complete_delivery(accepted)

        recorded = next(record for record in loaded.records if isinstance(record, ExternalEventDelivered))
        durable = next(
            record for record in JsonlHistoryStore(path).records if isinstance(record, ExternalEventDelivered)
        )
        assert recorded.tokens == durable.tokens == (token,)
        assert completed.produced == ((A, Token("X", {"event": 8})),)
        assert loaded.accept_delivery(SRC, token, identity="event-7") == PriorAcknowledgement("event-7", 1)

    def test_public_observations_and_completion_outcome_do_not_alias_accepted_content(self):
        history = InMemoryHistoryStore()
        token = Token("X", {"event": 7})
        engine = Engine.create(
            _ingress_net(),
            "detached-delivery-content",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        accepted = engine.accept_delivery(SRC, token, identity="event-7")

        recorded = next(record for record in engine.records if isinstance(record, ExternalEventDelivered))
        recorded.tokens[0].data["event"] = 8
        engine.in_flight[0].binding.delivered[0].data["event"] = 9

        completed = engine.complete_delivery(accepted)

        assert completed.produced == ((A, Token("X", {"event": 7})),)
        completed.produced[0][1].data["event"] = 10
        engine.marking.place(A)[0].data["event"] = 11
        completed_records = engine.records

        assert engine.accept_delivery(SRC, token, identity="event-7") == PriorAcknowledgement("event-7", 1)
        assert engine.records == completed_records
        assert engine.marking == Marking({A: (Token("X", {"event": 7}),)})

    def test_completion_detaches_its_outcome_before_the_terminal_batch_commits(self):
        history = InMemoryHistoryStore()

        class CommitAwareList(list):
            def __deepcopy__(self, memo):
                if any(isinstance(record, FiringCompleted) for record in history.records):
                    raise AssertionError("outcome detachment ran after its terminal commit")
                copied = list(self)
                memo[id(self)] = copied
                return copied

        projected = CommitAwareList([1])

        def project(binding, outputs):
            del binding, outputs
            return {A: (Token("X", projected),)}

        net = Net(
            places=[Place(A)],
            transitions=[Transition(SRC, handler="project")],
            arcs=[Arc(SRC, A)],
        )
        engine = Engine.create(
            net,
            "detach-before-completion-commit",
            history=history,
            dispatch=InMemoryDispatch(),
            handlers={"project": project},
        )
        accepted = engine.accept_delivery(SRC, Token("X"), identity="event-7")

        completed = engine.complete_delivery(accepted)
        projected.append(2)

        assert completed.produced == ((A, Token("X", [1])),)
        produced = next(record for record in history.records if isinstance(record, TokensProduced))
        assert produced.tokens == (Token("X", [1]),)
        assert isinstance(history.records[-1], FiringCompleted)

    def test_acceptance_refuses_mutable_token_color_before_history_mutation(self):
        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "invalid-delivery-color",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        before = history.records

        with pytest.raises(ValueError, match="token 1 color must be a string or None"):
            engine.accept_delivery(SRC, Token(["X"], {"event": 7}), identity="event-7")

        assert history.records == before

    def test_completion_validates_handler_output_before_copy_protocols_can_normalize_it(self):
        class NormalizingColor(str):
            def __deepcopy__(self, memo):
                del memo
                return str(self)

        def project(binding, outputs):
            del binding, outputs
            return {A: (Token(NormalizingColor("X"), {"projected": True}),)}

        net = Net(
            places=[Place(A)],
            transitions=[Transition(SRC, handler="project")],
            arcs=[Arc(SRC, A)],
        )
        history = InMemoryHistoryStore()
        engine = Engine.create(
            net,
            "hostile-projected-token-color",
            history=history,
            dispatch=InMemoryDispatch(),
            handlers={"project": project},
        )
        accepted = engine.accept_delivery(SRC, Token("Input"), identity="event-7")

        with pytest.raises(ValueError, match=r"TokensProduced tokens.*color.*exact string"):
            engine.complete_delivery(accepted)

        assert isinstance(history.records[-1], FiringFailed)
        assert not any(isinstance(record, (TokensProduced, FiringCompleted)) for record in history.records)

    def test_engine_creation_refuses_an_empty_identity_before_history_mutation(self):
        history = InMemoryHistoryStore()

        with pytest.raises(ValueError, match="Instance identity must be a non-empty string"):
            Engine.create(
                _ingress_net(),
                "",
                history=history,
                dispatch=InMemoryDispatch(),
            )

        assert history.records == ()

    def test_engine_load_refuses_an_empty_recorded_identity_without_history_mutation(self, tmp_path):
        path = tmp_path / "empty-recorded-identity.jsonl"
        created = Engine.create(
            _ingress_net(),
            "recorded-identity",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        created.close()
        records = [json.loads(line) for line in path.read_text().splitlines()]
        assert records[0]["record"] == "InstanceCreated"
        records[0]["instance"] = ""
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
        malformed_history = path.read_bytes()

        with pytest.raises(ValueError, match="Instance identity must be a non-empty string"):
            Engine.load(
                _ingress_net(),
                "",
                history=JsonlHistoryStore(path),
                dispatch=InMemoryDispatch(),
            )

        assert path.read_bytes() == malformed_history

    def test_json_lossy_delivery_content_reconstructs_after_durable_reload(self, tmp_path):
        path = tmp_path / "canonical-delivery.jsonl"
        created = Engine.create(
            _ingress_net(),
            "canonical-delivery-content",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        accepted = created.accept_delivery(SRC, Token("X", (1, 2)), identity="event-7")
        created.close()

        loaded = Engine.load(
            _ingress_net(),
            "canonical-delivery-content",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        reconstructed = loaded.accept_delivery(SRC, Token("X", (1, 2)), identity="event-7")
        loaded.complete_delivery(reconstructed)

        assert reconstructed == accepted
        assert loaded.marking == Marking({A: (Token("X", [1, 2]),)})

    def test_completion_refuses_an_ended_delivery_before_mutation(self):
        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "ended-delivery",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        accepted = engine.accept_delivery(SRC, Token("X", 7), identity="event-7")
        engine.complete_delivery(accepted)
        completed_records = history.records

        with pytest.raises(ValueError, match=r"accepted delivery 'event-7'.*occurrence 1 already ended"):
            engine.complete_delivery(accepted)

        assert history.records == completed_records

    def test_completion_refuses_a_non_acceptance_carrier_before_mutation(self):
        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "invalid-delivery-carrier",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        records = history.records

        with pytest.raises(TypeError, match=r"delivery completion requires an exact AcceptedDelivery"):
            engine.complete_delivery(object())

        assert history.records == records

    @pytest.mark.parametrize("route", ["direct", "composed", "sensed"])
    @pytest.mark.parametrize(
        ("arguments", "recorded"),
        [
            ((), "ProjectionError()"),
            (("x" * 5000,), f"ProjectionError({'x' * 5000!r})"[:4096]),
        ],
        ids=["no-arguments", "long-argument"],
    )
    def test_projection_exception_text_is_nonempty_bounded_and_the_original_propagates(
        self, route, arguments, recorded
    ):
        class ProjectionError(RuntimeError):
            def __repr__(self):
                raise AssertionError("durable failure rendering must not call exception repr")

        error = ProjectionError(*arguments)

        def explode(binding, outputs):
            raise error

        history = InMemoryHistoryStore()
        token = Token("X", {"event": 7})
        net = Net(
            places=[Place(A)],
            transitions=[Transition(SRC, handler="project")],
            arcs=[Arc(SRC, A)],
        )
        sensor = _scripted([Delivery(SRC, token, identity="event-7")]) if route == "sensed" else None
        engine = Engine.create(
            net,
            f"{route}-bounded-projection-failure",
            history=history,
            dispatch=InMemoryDispatch(),
            handlers={"project": explode},
            sensor=sensor,
        )

        with pytest.raises(ProjectionError) as propagated:
            if route == "direct":
                accepted = engine.accept_delivery(SRC, token, identity="event-7")
                engine.complete_delivery(accepted)
            elif route == "composed":
                engine.deliver(SRC, token, identity="event-7")
            else:
                engine.advance()

        assert propagated.value is error
        assert history.records[-1] == FiringFailed(SRC, recorded, occurrence=1)
        resumed = Engine.load(
            net,
            f"{route}-bounded-projection-failure",
            history=history,
            dispatch=InMemoryDispatch(),
            handlers={"project": lambda binding, outputs: {A: binding.tokens}},
        )
        assert resumed.accept_delivery(SRC, token, identity="event-7") == PriorAcknowledgement("event-7", 1)

    def test_projection_failure_replaces_object_identity_with_a_stable_type_marker(self):
        recorded = []
        for position, argument in enumerate((object(), object()), start=1):
            error = RuntimeError(argument)

            def explode(binding, outputs):
                del binding, outputs
                raise error

            history = InMemoryHistoryStore()
            token = Token("X", {"event": position})
            net = Net(
                places=[Place(A)],
                transitions=[Transition(SRC, handler="project")],
                arcs=[Arc(SRC, A)],
            )
            engine = Engine.create(
                net,
                f"deterministic-projection-failure-{position}",
                history=history,
                dispatch=InMemoryDispatch(),
                handlers={"project": explode},
            )
            accepted = engine.accept_delivery(SRC, token, identity=f"event-{position}")

            with pytest.raises(RuntimeError) as propagated:
                engine.complete_delivery(accepted)

            assert propagated.value is error
            recorded.append(history.records[-1].error)

        assert recorded == ["RuntimeError(<builtins.object>)", "RuntimeError(<builtins.object>)"]

    def test_projection_refuses_a_registration_key_subclass_without_corrupting_durable_authority(self):
        class DefaultImpersonatingKey(str):
            def __eq__(self, other):
                return other == "default"

            def __ne__(self, other):
                return other != "default"

            def __hash__(self):
                return hash("default")

        def close_default(binding, outputs):
            del outputs
            return HandlerResult(
                {A: binding.tokens},
                closes=(DeliveryRegistration(SRC, DefaultImpersonatingKey("evil")),),
            )

        net = Net(
            places=[Place(A)],
            transitions=[Transition(SRC, handler="close")],
            arcs=[Arc(SRC, A)],
        )
        history = InMemoryHistoryStore()
        token = Token("X")
        engine = Engine.create(
            net,
            "strict-registration-key",
            history=history,
            dispatch=InMemoryDispatch(),
            handlers={"close": close_default},
        )
        accepted = engine.accept_delivery(SRC, token, identity="event-7")

        with pytest.raises(ValueError, match="DeliveryRegistration requires a non-empty string key of the exact"):
            engine.complete_delivery(accepted)

        assert not [record for record in history.records if isinstance(record, DeliveryRegistrationClosed)]
        assert isinstance(history.records[-1], FiringFailed)
        resumed = Engine.load(
            net,
            "strict-registration-key",
            history=history,
            dispatch=InMemoryDispatch(),
            handlers={"close": lambda binding, outputs: {A: binding.tokens}},
        )
        assert resumed.accept_delivery(SRC, token, identity="event-7") == PriorAcknowledgement("event-7", 1)
        resumed.deliver(SRC, token, identity="event-8")

    def test_projection_refuses_a_registration_subclass_before_reading_its_fields(self):
        class RedirectingRegistration(DeliveryRegistration):
            redirect = False

            def __getattribute__(self, name):
                if name in {"source", "key"} and object.__getattribute__(self, "redirect"):
                    raise AssertionError("registration subclass field was read")
                return super().__getattribute__(name)

        effect = RedirectingRegistration(SRC, "default")
        object.__setattr__(effect, "redirect", True)

        def close_default(binding, outputs):
            del outputs
            return HandlerResult({A: binding.tokens}, closes=(effect,))

        net = Net(
            places=[Place(A)],
            transitions=[Transition(SRC, handler="close")],
            arcs=[Arc(SRC, A)],
        )
        history = InMemoryHistoryStore()
        engine = Engine.create(
            net,
            "exact-registration-effect",
            history=history,
            dispatch=InMemoryDispatch(),
            handlers={"close": close_default},
        )
        accepted = engine.accept_delivery(SRC, Token("X"), identity="event-7")

        with pytest.raises(
            ValueError, match="every delivery-registration effect must be an exact DeliveryRegistration"
        ):
            engine.complete_delivery(accepted)

        assert not [record for record in history.records if isinstance(record, DeliveryRegistrationClosed)]
        assert isinstance(history.records[-1], FiringFailed)

    def test_completion_refuses_a_foreign_acceptance_before_mutation(self):
        token = Token("X", 7)
        left_history = InMemoryHistoryStore()
        left = Engine.create(
            _ingress_net(),
            "left-delivery",
            history=left_history,
            dispatch=InMemoryDispatch(),
        )
        accepted = left.accept_delivery(SRC, token, identity="event-7")
        right_history = InMemoryHistoryStore()
        right = Engine.create(
            _ingress_net(),
            "right-delivery",
            history=right_history,
            dispatch=InMemoryDispatch(),
        )
        right_records = right_history.records

        with pytest.raises(ValueError, match=r"delivery for Instance 'left-delivery'.*Instance 'right-delivery'"):
            right.complete_delivery(accepted)

        assert right_history.records == right_records

    def test_completion_refuses_a_mismatched_acceptance_before_mutation(self):
        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "mismatched-delivery",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        accepted = engine.accept_delivery(SRC, Token("X", 7), identity="event-7")
        accepted_records = history.records
        mismatched = AcceptedDelivery(
            instance=accepted.instance,
            source=accepted.source,
            identity="other-event",
            occurrence=accepted.occurrence,
        )
        with pytest.raises(ValueError, match=r"acceptance does not match firing occurrence 1"):
            engine.complete_delivery(mismatched)

        assert history.records == accepted_records

    def test_completion_refuses_the_wrong_source_occurrence_before_mutation(self):
        other_source = NetPath("other_source")
        other_output = NetPath("other_output")
        net = Net(
            places=[Place(A), Place(other_output)],
            transitions=[Transition(SRC), Transition(other_source)],
            arcs=[Arc(SRC, A), Arc(other_source, other_output)],
        )
        history = InMemoryHistoryStore()
        engine = Engine.create(
            net,
            "wrong-source-occurrence",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        accepted = engine.accept_delivery(SRC, Token("X", 7), identity="event-7")
        other = engine.accept_delivery(other_source, Token("Y", 8), identity="event-8")
        accepted_records = history.records
        wrong = AcceptedDelivery(
            instance=accepted.instance,
            source=accepted.source,
            identity=accepted.identity,
            occurrence=other.occurrence,
        )

        with pytest.raises(ValueError, match=r"acceptance does not match firing occurrence 2"):
            engine.complete_delivery(wrong)

        assert history.records == accepted_records

    def test_completion_refuses_a_mutated_occurrence_alias_before_it_can_redirect(self):
        class FirstOccurrenceAlias(int):
            def __eq__(self, other):
                return other == 1 or other == 2

            def __hash__(self):
                return hash(2)

        history = InMemoryHistoryStore()
        engine = Engine.create(
            Net(places=[Place(A)], transitions=[Transition(SRC)], arcs=[Arc(SRC, A)]),
            "mutated-acceptance-carrier",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        first = engine.accept_delivery(SRC, Token("X", True), identity="event-1")
        second = engine.accept_delivery(SRC, Token("X", 1), identity="event-2")
        object.__setattr__(first, "occurrence", FirstOccurrenceAlias(second.occurrence))
        accepted_records = history.records

        with pytest.raises(ValueError, match="firing occurrence must be a positive integer"):
            engine.complete_delivery(first)

        assert history.records == accepted_records
        resumed = Engine.load(
            Net(places=[Place(A)], transitions=[Transition(SRC)], arcs=[Arc(SRC, A)]),
            "mutated-acceptance-carrier",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        assert [occurrence.id for occurrence in resumed.in_flight] == [1, 2]

    def test_completion_refuses_an_acceptance_subclass_before_it_can_redirect_the_occurrence(self):
        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "exact-acceptance-carrier",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        token = Token("X", 7)
        first = engine.accept_delivery(SRC, token, identity="event-1")
        second = engine.accept_delivery(SRC, token, identity="event-2")
        occurrence_reads = iter((first.occurrence, second.occurrence))

        class RedirectingAcceptance(AcceptedDelivery):
            def __getattribute__(self, name):
                if name == "occurrence":
                    return next(occurrence_reads)
                return super().__getattribute__(name)

        redirecting = RedirectingAcceptance(
            instance=second.instance,
            source=second.source,
            identity=second.identity,
            occurrence=second.occurrence,
        )
        accepted_records = history.records

        with pytest.raises(TypeError, match="delivery completion requires an exact AcceptedDelivery"):
            engine.complete_delivery(redirecting)

        assert history.records == accepted_records

    def test_acceptance_carrier_refuses_a_boolean_occurrence_before_completion(self):
        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "malformed-occurrence",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        accepted = engine.accept_delivery(SRC, Token("X", 7), identity="event-7")
        accepted_records = history.records

        with pytest.raises(ValueError, match="occurrence must be a positive integer"):
            malformed = AcceptedDelivery(
                instance=accepted.instance,
                source=accepted.source,
                identity=accepted.identity,
                occurrence=True,
            )
            engine.complete_delivery(malformed)

        assert history.records == accepted_records

    def test_acceptance_carrier_refuses_a_non_string_identity_before_completion(self):
        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "malformed-identity",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        accepted = engine.accept_delivery(SRC, Token("X", 7), identity="event-7")
        accepted_records = history.records

        with pytest.raises(ValueError, match="identity must be a non-empty string"):
            malformed = AcceptedDelivery(
                instance=accepted.instance,
                source=accepted.source,
                identity=[],
                occurrence=accepted.occurrence,
            )
            engine.complete_delivery(malformed)

        assert history.records == accepted_records

    def test_acceptance_carrier_refuses_an_instance_identity_subclass_at_construction(self):
        class TruthyEmptyInstanceIdentity(str):
            def __bool__(self):
                return True

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "strict-instance-carrier",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        accepted = engine.accept_delivery(SRC, Token("X", 7), identity="event-7")
        accepted_records = history.records

        with pytest.raises(ValueError, match="Instance identity must be a non-empty string"):
            AcceptedDelivery(
                instance=TruthyEmptyInstanceIdentity(""),
                source=accepted.source,
                identity=accepted.identity,
                occurrence=accepted.occurrence,
            )

        assert history.records == accepted_records

    def test_acceptance_carrier_refuses_an_occurrence_subclass_at_construction(self):
        class NonnegativeNegativeOccurrence(int):
            def __lt__(self, other):
                del other
                return False

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "strict-occurrence-carrier",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        accepted = engine.accept_delivery(SRC, Token("X", 7), identity="event-7")
        accepted_records = history.records

        with pytest.raises(ValueError, match="firing occurrence must be a positive integer"):
            AcceptedDelivery(
                instance=accepted.instance,
                source=accepted.source,
                identity=accepted.identity,
                occurrence=NonnegativeNegativeOccurrence(-1),
            )

        assert history.records == accepted_records

    def test_completion_refuses_an_impure_non_source_occurrence_before_mutation(self):
        class Work:
            def prepare(self, binding):
                return ActivityInvocation("work", input={"value": binding.tokens[0].data})

            def project(self, binding, result):
                return {B: (Token("Worked", result),)}

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _line_net(handler="work"),
            "wrong-occurrence",
            history=history,
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("Work", 3),)}),
            handlers={"work": Work()},
        )
        engine.advance()
        begun_records = history.records
        wrong = AcceptedDelivery(
            instance="wrong-occurrence",
            source=T,
            identity="event-7",
            occurrence=1,
        )

        with pytest.raises(ValueError, match=r"occurrence 1 belongs to an impure non-source transition t"):
            engine.complete_delivery(wrong)

        assert history.records == begun_records

    def test_fresh_engine_reconstructs_and_completes_the_exact_accepted_occurrence(self, tmp_path):
        path = tmp_path / "reconstructed.jsonl"
        token = Token("X", {"event": 7})
        created = Engine.create(
            _ingress_net(),
            "reconstructed-delivery",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        accepted = created.accept_delivery(SRC, token, identity="event-7")
        created.close()

        loaded = Engine.load(
            _ingress_net(),
            "reconstructed-delivery",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        reconstructed = loaded.accept_delivery(SRC, token, identity="event-7")
        completed = loaded.complete_delivery(reconstructed)

        assert reconstructed == accepted
        assert (completed.transition, completed.occurrence) == (SRC, 1)
        assert loaded.marking == Marking({A: (token,)})
        assert [record.occurrence for record in loaded.records if isinstance(record, FiringCompleted)] == [1]

    def test_fresh_engine_completes_a_persisted_acceptance_without_redelivery(self, tmp_path):
        path = tmp_path / "persisted-acceptance.jsonl"
        token = Token("X", {"event": 7})
        created = Engine.create(
            _ingress_net(),
            "persisted-acceptance",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        accepted = created.accept_delivery(SRC, token, identity="event-7")
        created.close()

        loaded = Engine.load(
            _ingress_net(),
            "persisted-acceptance",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        accepted_records = loaded.records

        completed = loaded.complete_delivery(accepted)

        assert (completed.transition, completed.occurrence) == (SRC, 1)
        assert loaded.records[len(accepted_records) :] == (
            TokensProduced(A, (token,), occurrence=1),
            FiringCompleted(SRC, occurrence=1),
        )
        assert len([record for record in loaded.records if isinstance(record, ExternalEventDelivered)]) == 1
        assert loaded.in_flight == ()

    def test_process_interruption_after_acceptance_resumes_only_that_occurrence(self, tmp_path):
        path = tmp_path / "interrupted.jsonl"
        program = """
import os
import sys

from petrus.engine import Engine
from petrus.motus.dispatch import InMemoryDispatch
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.petrinet import Arc, Net, NetPath, Place, Token, Transition

source = NetPath("src")
output = NetPath("a")
net = Net(places=[Place(output)], transitions=[Transition(source)], arcs=[Arc(source, output)])
engine = Engine.create(net, "interrupted-delivery", history=JsonlHistoryStore(sys.argv[1]), dispatch=InMemoryDispatch())
engine.accept_delivery(source, Token("X", {"event": 7}), identity="event-7")
os._exit(23)
"""

        interrupted = subprocess.run([sys.executable, "-c", program, str(path)], check=False)

        assert interrupted.returncode == 23
        token = Token("X", {"event": 7})
        source_only = Net(
            places=[Place(A)],
            transitions=[Transition(SRC)],
            arcs=[Arc(SRC, A)],
        )
        loaded = Engine.load(
            source_only,
            "interrupted-delivery",
            history=JsonlHistoryStore(path),
            dispatch=InMemoryDispatch(),
        )
        reconstructed = loaded.accept_delivery(SRC, token, identity="event-7")

        completed = loaded.complete_delivery(reconstructed)

        assert (completed.transition, completed.occurrence) == (SRC, 1)
        assert loaded.marking == Marking({A: (token,)})
        assert len([record for record in loaded.records if isinstance(record, ExternalEventDelivered)]) == 1
        assert len([record for record in loaded.records if isinstance(record, FiringCompleted)]) == 1

    def test_exact_redelivery_has_finite_record_and_in_flight_cost(self):
        engine = Engine.create(
            _ingress_net(),
            "bounded-redelivery",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
        )
        token = Token("X", {"event": 7})
        baseline = len(engine.records)
        accepted = engine.accept_delivery(SRC, token, identity="event-7")

        for _ in range(64):
            assert engine.accept_delivery(SRC, token, identity="event-7") == accepted

        assert len(engine.records) == baseline + 2
        assert len(engine.in_flight) == 1

        engine.complete_delivery(accepted)

        assert len(engine.records) == baseline + 4
        assert engine.in_flight == ()


class TestEngineObservesTimers:
    def test_simulated_time_matures_and_fires(self):
        token = Token("X")
        engine = Engine.create(
            _expiry_net(Delay(10)),
            "timer",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (token,)}),
        )

        outcome = _advance_until_rest(engine)

        assert [firing.transition for firing in outcome.firings] == [T]
        assert TimerMatured(maturation_instant=10, instant=10) in engine.records
        assert engine.marking == Marking({B: (token,)})

    def test_repeated_delays_anchor_on_each_production(self):
        token = Token("X")
        second = NetPath("second")
        net = Net(
            places=[Place(A), Place(B), Place(C)],
            transitions=[Transition(T, timers=(Delay(5),)), Transition(second, timers=(Delay(5),))],
            arcs=[Arc(A, T), Arc(T, B), Arc(B, second), Arc(second, C)],
        )
        engine = Engine.create(
            net,
            "repeated-timers",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (token,)}),
        )

        _advance_until_rest(engine)

        assert [record for record in engine.records if isinstance(record, TimerMatured)] == [
            TimerMatured(maturation_instant=5, instant=5),
            TimerMatured(maturation_instant=10, instant=10),
        ]

    def test_until_matures_at_its_declared_instant(self):
        engine = Engine.create(
            _expiry_net(Until(100)),
            "until",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("X"),)}),
        )

        _advance_until_rest(engine)

        assert TimerMatured(maturation_instant=100, instant=100) in engine.records

    def test_a_late_observation_is_harmless_and_an_early_one_fails_loud(self):
        class Clock:
            def __init__(self, adjustment):
                self.at = 0
                self.adjustment = adjustment

            def now(self):
                return self.at

            def observe(self, instant):
                self.at = instant + self.adjustment
                return self.at

        late = Engine.create(
            _expiry_net(Delay(10)),
            "late",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("X"),)}),
            clock=Clock(3),
        )
        _advance_until_rest(late)
        assert TimerMatured(maturation_instant=10, instant=13) in late.records

        early_history = InMemoryHistoryStore()
        early = Engine.create(
            _expiry_net(Delay(10)),
            "early",
            history=early_history,
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("X"),)}),
            clock=Clock(-1),
        )
        with pytest.raises(ValueError, match=r"observed 9, before the requested maturation 10"):
            early.advance()


class TestTerminalFailure:
    def test_a_raising_pure_handler_records_failure_and_poisons_the_engine(self):
        def explode(binding, outputs):
            raise RuntimeError("quote service down")

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _line_net(handler="price"),
            "failure",
            history=history,
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("X"), Token("X"))}),
            handlers={"price": explode},
        )

        with pytest.raises(RuntimeError, match="quote service down"):
            engine.advance()

        assert isinstance(history.records[-1], FiringFailed)
        assert "quote service down" in history.records[-1].error
        with pytest.raises(RuntimeError, match="poisoned"):
            engine.advance()


class TestDelivery:
    def test_normalizes_source_tokens_and_identity(self):
        token = Token("X")
        delivery = Delivery("src", token, identity="evt-9")

        assert delivery.source == SRC
        assert delivery.tokens == (token,)
        assert delivery.identity == "evt-9"

    def test_requires_a_stable_identity_at_parcel_construction(self):
        with pytest.raises(TypeError, match="identity"):
            Delivery(SRC, Token("X"))

        with pytest.raises(ValueError, match="identity must be a non-empty string"):
            Delivery(SRC, Token("X"), identity=None)

    def test_requires_an_exact_scope_type_at_parcel_construction(self):
        class ScopeName(str):
            pass

        class DerivedLifecycleScope(LifecycleScope):
            pass

        with pytest.raises(TypeError, match="delivery scope must be an exact LifecycleScope"):
            Delivery(SRC, Token("X"), identity="event-1", scope=ScopeName("draft"))

        with pytest.raises(TypeError, match="delivery scope must be an exact LifecycleScope"):
            Delivery(SRC, Token("X"), identity="event-1", scope=DerivedLifecycleScope("draft", 1))

    @pytest.mark.parametrize("scope", ["", "invalid\x00scope"])
    def test_requires_a_valid_scope_name_at_parcel_construction(self, scope):
        with pytest.raises(ValueError, match="delivery scope name must be non-empty and contain no NUL"):
            Delivery(SRC, Token("X"), identity="event-1", scope=scope)

    def test_rejects_a_string_payload_and_snapshots_a_sequence(self):
        with pytest.raises(ValueError, match=r"tokens must be a Token or a sequence of Tokens"):
            Delivery(SRC, "clean", identity="clean-event")

        delivery = Delivery(SRC, [Token("X"), Token("Y")], identity="token-event")
        assert delivery.tokens == (Token("X"), Token("Y"))


class TestEngineSenses:
    def test_sensor_refuses_a_delivery_subclass_before_reading_its_fields(self):
        class RedirectingDelivery(Delivery):
            redirect = False

            def __getattribute__(self, name):
                if name == "source" and object.__getattribute__(self, "redirect"):
                    raise AssertionError("sensor must reject a Delivery subclass before reading fields")
                return super().__getattribute__(name)

        parcel = RedirectingDelivery(SRC, Token("X"), identity="event-1")
        object.__setattr__(parcel, "redirect", True)
        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "exact-sensed-delivery",
            history=history,
            dispatch=InMemoryDispatch(),
            sensor=lambda: [parcel],
        )
        before = history.records

        with pytest.raises(TypeError, match="sensor must return exact Delivery values"):
            engine.advance()

        assert history.records == before

    def test_sensed_source_subclass_cannot_rewrite_its_address_before_acceptance(self):
        class RewritingSource(str):
            def split(self, separator=None, maximum=-1):
                del separator, maximum
                return ["src"]

        token = Token("X")

        def sensor():
            return [Delivery(RewritingSource("unauthorized"), token, identity="event-1")]

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "strict-sensed-source",
            history=history,
            dispatch=InMemoryDispatch(),
            sensor=sensor,
        )
        before = history.records

        with pytest.raises(ValueError, match="delivery source must be an exact NetPath or built-in string"):
            engine.advance()

        assert history.records == before

    def test_sensed_delivery_interleaves_with_internal_work(self):
        token = Token("X")
        engine = Engine.create(
            _ingress_net(),
            "sensed",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            sensor=_scripted([Delivery(SRC, token, identity="sensed-event")], [], []),
        )

        outcome = _advance_until_rest(engine)

        assert [firing.transition for firing in outcome.firings] == [SRC, T]
        assert engine.marking == Marking({B: (token,)})

    def test_sensed_redelivery_is_acknowledged_once(self):
        token = Token("X")
        redelivered = Delivery(SRC, token, identity="evt-9")
        engine = Engine.create(
            _ingress_net(),
            "redelivery",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            sensor=_scripted([redelivered], [redelivered], []),
        )

        _advance_until_rest(engine)

        events = [record for record in engine.records if isinstance(record, ExternalEventDelivered)]
        assert [event.identity for event in events] == ["evt-9"]

    def test_selecting_a_later_equal_delivery_does_not_drop_an_earlier_content_conflict(self):
        def select_second_delivery(snapshot):
            deliveries = tuple(action for action in snapshot.actions if isinstance(action, AcceptDelivery))
            if deliveries:
                return deliveries[min(1, len(deliveries) - 1)]
            return snapshot.actions[-1]

        history = InMemoryHistoryStore()
        engine = Engine.create(
            Net(places=[Place(A)], transitions=[Transition(SRC)], arcs=[Arc(SRC, A)]),
            "equal-sensor-collision",
            history=history,
            dispatch=InMemoryDispatch(),
            policy=select_second_delivery,
            sensor=_scripted(
                [
                    Delivery(SRC, Token("X", True), identity="event-7"),
                    Delivery(SRC, Token("X", 1), identity="event-7"),
                ]
            ),
        )

        engine.advance()
        accepted_records = history.records

        with pytest.raises(ValueError, match="delivery identity conflict for 'event-7'.*content differs"):
            engine.advance()

        [accepted] = [record for record in history.records if isinstance(record, ExternalEventDelivered)]
        assert type(accepted.tokens[0].data) is int
        assert history.records == accepted_records

    def test_sensor_can_redeliver_the_identity_returned_by_a_prior_acceptance(self):
        token = Token("X")
        history = InMemoryHistoryStore()
        first = Engine.create(
            _ingress_net(),
            "returned-sensor-identity",
            history=history,
            dispatch=InMemoryDispatch(),
        )
        accepted = first.accept_delivery(SRC, token, identity="event-7")
        first.close()
        parcel = Delivery(SRC, token, identity=accepted.identity)
        resumed = Engine.load(
            _ingress_net(),
            "returned-sensor-identity",
            history=history,
            dispatch=InMemoryDispatch(),
            sensor=_scripted([parcel], [], []),
        )

        outcome = _advance_until_rest(resumed)

        assert [firing.occurrence for firing in outcome.firings] == [accepted.occurrence, 2]
        events = [record for record in history.records if isinstance(record, ExternalEventDelivered)]
        assert [event.identity for event in events] == ["event-7"]

    def test_sensor_decline_returns_control_and_a_sealed_engine_never_consults(self):
        awaiting = Engine.create(
            _ingress_net(),
            "awaiting",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            sensor=_scripted([]),
        )
        assert _advance_until_rest(awaiting).firings == ()
        assert awaiting.status is Status.AWAITING

        def never():
            raise AssertionError("consulted with nothing armed")

        sealed = Engine.create(
            _ingress_net(),
            "sealed",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            sensor=never,
        )
        sealed.seal(SRC)
        assert _advance_until_rest(sealed).firings == ()
        assert sealed.status is Status.TERMINATED

    def test_completed_status_does_not_disable_an_armed_sensor(self):
        token = Token("X")
        net = Net(
            places=[Place(A)],
            transitions=[Transition(SRC)],
            arcs=[Arc(SRC, A)],
            completion=Cel("size(a) != 0"),
        )
        statuses = []
        engine = None

        def sensor():
            statuses.append(engine.status)
            return [Delivery(SRC, token, identity="completed-event")] if len(statuses) == 1 else []

        engine = Engine.create(
            net,
            "completed-sensor",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            sensor=sensor,
        )
        _advance_until_rest(engine)

        assert statuses == [Status.AWAITING, Status.COMPLETED]
        assert engine.status is Status.COMPLETED

    def test_available_ingress_interrupts_a_pending_timer_once(self):
        clock = SimulatedClock()
        net = Net(
            places=[Place(A), Place(B)],
            transitions=[Transition(SRC), Transition(T, timers=(Delay(10),))],
            arcs=[Arc(SRC, A), Arc(A, T), Arc(T, B)],
        )
        engine = Engine.create(
            net,
            "timer-ingress",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("X"),)}),
            clock=clock,
            sensor=_scripted([Delivery(SRC, Token("X"), identity="evt-1")], []),
        )

        first = engine.advance()
        assert clock.now() == 0
        second = engine.advance()

        assert [firing.transition for firing in first.firings] == [SRC]
        assert second.ready is True
        assert clock.now() == 10

    def test_sensed_delivery_is_stamped_from_the_clock_and_matches_direct_delivery(self):
        token = Token("X")
        sensed_history = InMemoryHistoryStore()
        sensed = Engine.create(
            _ingress_net(),
            "parity-sensed",
            history=sensed_history,
            dispatch=InMemoryDispatch(),
            clock=SimulatedClock(at=5),
            sensor=_scripted([Delivery(SRC, token, identity="parity-event")], [], []),
            at=5,
        )
        _advance_until_rest(sensed)

        manual_history = InMemoryHistoryStore()
        manual = Engine.create(
            _ingress_net(),
            "parity-sensed",
            history=manual_history,
            dispatch=InMemoryDispatch(),
            clock=SimulatedClock(at=5),
            at=5,
        )
        manual.deliver(SRC, token, identity="parity-event")
        _advance_until_rest(manual)

        assert sensed_history.records == manual_history.records
        [event] = [record for record in sensed.records if isinstance(record, ExternalEventDelivered)]
        assert event.instant == 5

    def test_source_projection_runs_inline_and_a_failure_poisons(self):
        def explode(binding, outputs):
            raise RuntimeError("bad event")

        history = InMemoryHistoryStore()
        engine = Engine.create(
            Net(places=[Place(A)], transitions=[Transition(SRC, handler="ingest")], arcs=[Arc(SRC, A)]),
            "bad-source",
            history=history,
            dispatch=InMemoryDispatch(),
            handlers={"ingest": explode},
            sensor=_scripted([Delivery(SRC, Token("X"), identity="failing-event")]),
        )

        with pytest.raises(RuntimeError, match="bad event"):
            engine.advance()

        assert isinstance(history.records[-1], FiringFailed)


class TestEngineRefusesABrokenSensor:
    def test_none_is_not_an_empty_answer(self):
        engine = Engine.create(
            _ingress_net(),
            "none-sensor",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            sensor=lambda: None,
        )

        with pytest.raises(ValueError, match=r"sensor returned None: a sensor answers with a sequence"):
            engine.advance()

    def test_a_generator_answer_is_snapshotted(self):
        token = Token("X")
        rounds = []

        def sensor():
            rounds.append(len(rounds))
            return iter([Delivery(SRC, token, identity="generator-event")]) if len(rounds) == 1 else iter(())

        engine = Engine.create(
            _ingress_net(),
            "generator-sensor",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            sensor=sensor,
        )

        outcome = _advance_until_rest(engine)

        assert [firing.transition for firing in outcome.firings] == [SRC, T]
        assert rounds == [0, 1, 2]

    def test_a_raising_sensor_appends_nothing_and_poisons(self):
        def broken():
            raise RuntimeError("sensor exploded")

        history = InMemoryHistoryStore()
        engine = Engine.create(
            _ingress_net(),
            "raising-sensor",
            history=history,
            dispatch=InMemoryDispatch(),
            sensor=broken,
        )
        before = history.records

        with pytest.raises(RuntimeError, match="sensor exploded"):
            engine.advance()

        assert history.records == before
        with pytest.raises(RuntimeError, match="poisoned"):
            engine.advance()
