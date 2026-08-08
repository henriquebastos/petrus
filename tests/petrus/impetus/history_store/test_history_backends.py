"""
The backend-contract suite: one behavior, every ``InMemoryHistoryStore`` backend.

The event history has one contract and three durable spellings — JSONL and SQLite
(``petrus.impetus.history_store.JsonlHistoryStore`` / ``SqliteHistoryStore``) and PostgreSQL
(``petrus.impetus.history_store.postgres.PostgresHistoryStore``, CV3.DS3) — and the DS3 acceptance
pins them as behaviorally identical: same records back, same rejections, same
resume [CV3.DS3 acceptance]. Every test here runs verbatim against both
backends through one ``reopen`` fixture, whose each call loads a FRESH backend
over the same storage — the crash-and-reload move, so "kill the process" is a
reopen and "resumes from the durable record alone" is literal. Backend-only
properties (transactional batches, verify-on-conflict, caller-transaction
join) live in ``test_postgres_history.py``; this module is the part that must
never diverge.
"""

from __future__ import annotations

# Python imports
from uuid import uuid4

# Pip imports
import pytest

from petrus.motus.activity import ActivityInvocation
from petrus.impetus.history import ExternalEventDelivered, FiringBegun, TokensInitialized, TokensProduced
from petrus.impetus.history_store import InMemoryHistoryStore, JsonlHistoryStore, SqliteHistoryStore

# Internal imports
from petrus.impetus.instance import FiringOutcome, Instance, PriorAcknowledgement
from petrus.impetus.petrinet import Arc, Marking, Net, NetPath, Place, Token, Transition
from tests.petrus.impetus.history_store.test_persistence import every_record_category

INTAKE, QUEUE, WORK, OUT = NetPath("intake"), NetPath("queue"), NetPath("work"), NetPath("out")


@pytest.fixture(params=["jsonl", "sqlite", "postgres"])
def reopen(request, tmp_path):
    """A zero-arg factory: each call loads a fresh backend over the same storage — the kill-and-reload move."""
    if request.param == "jsonl":
        path = tmp_path / "history.jsonl"
        return lambda: JsonlHistoryStore(path)
    if request.param == "sqlite":
        path = tmp_path / "history.sqlite3"
        return lambda: SqliteHistoryStore(path, instance="backend-contract")
    # The container fixture is consulted only on the postgres parameter, so a
    # JSONL-only selection never provisions docker.
    connection = request.getfixturevalue("pg_connection")
    from petrus.impetus.history_store.postgres import PostgresHistoryStore

    instance_id = f"backend-contract-{uuid4()}"
    return lambda: PostgresHistoryStore(connection, instance=instance_id)


class Charge:
    """A counting ActivityHandler — re-runs of either half betray themselves."""

    def __init__(self):
        self.prepared = 0
        self.projected = 0

    def prepare(self, binding) -> ActivityInvocation:
        self.prepared += 1
        [issue] = binding.tokens
        return ActivityInvocation("charge_card", input={"amount": issue.data["amount"]})

    def project(self, binding, result):
        self.projected += 1
        return {OUT: (Token("Receipt", {"status": result["status"]}),)}


def activity_net() -> Net:
    """intake (source) -> queue -> work (ActivityHandler) -> out."""
    return Net(
        places=[Place(QUEUE), Place(OUT)],
        transitions=[Transition(INTAKE), Transition(WORK, handler="charge")],
        arcs=[Arc(INTAKE, QUEUE), Arc(QUEUE, WORK), Arc(WORK, OUT)],
    )


def payment(amount: int = 100) -> Token:
    return Token("Payment", {"amount": amount})


class TestRoundTrip:
    """Append/extend write through; a fresh load reads back value-equal, in order."""

    def test_a_store_contains_history_without_being_history(self, reopen):
        store = reopen()
        assert not isinstance(store, InMemoryHistoryStore)
        store.append(TokensInitialized(QUEUE, (Token.black(),), instant=0))
        assert store.records == (TokensInitialized(QUEUE, (Token.black(),), instant=0),)

    def test_every_record_category_round_trips_value_equal(self, reopen):
        # The codec's whole-union claim, carried by the backend: one instance
        # of every Record category survives the durable round trip value-equal
        # and in append order — the completeness assertion lives in
        # tests.test_persistence.every_record_category, which reads the union.
        reopen().extend(every_record_category())
        assert reopen().records == tuple(every_record_category())

    def test_append_and_extend_accumulate_and_a_reload_continues(self, reopen):
        history = reopen()
        history.append(TokensInitialized(QUEUE, (Token.black(),), instant=0))
        history.extend([FiringBegun(WORK, occurrence=1, instant=1)])
        assert len(history) == 2

        resumed = reopen()
        assert resumed.records == history.records
        resumed.append(TokensProduced(OUT, (Token.black(),), occurrence=1, instant=2))
        assert reopen().records == history.records + (TokensProduced(OUT, (Token.black(),), occurrence=1, instant=2),)

    def test_durable_before_in_memory(self, reopen):
        # Every append is durable when the call returns: a fresh load never
        # trails the in-memory records.
        history = reopen()
        history.append(TokensInitialized(QUEUE, (Token.black(),), instant=0))
        assert reopen().records == history.records

    def test_an_unencodable_record_fails_loud_and_enters_nothing(self, reopen):
        # Same rejection, both backends: a record that cannot be spelled
        # durably enters neither the storage nor memory.
        history = reopen()
        with pytest.raises(ValueError, match="TokensInitialized"):
            history.append(TokensInitialized(QUEUE, (Token("x", object()),), instant=0))
        assert len(history) == 0
        assert reopen().records == ()

    def test_nan_token_data_is_refused_loud_on_both_backends(self, reopen):
        # The codec-wide rule [DS3 review, ratifying the backend's posture]:
        # NaN/Infinity have no strict-JSON spelling and are not value-equal
        # to themselves back — both backends refuse them identically at
        # encode, before anything reaches the sink.
        history = reopen()
        with pytest.raises(ValueError, match="TokensInitialized"):
            history.append(TokensInitialized(QUEUE, (Token("x", float("nan")),), instant=0))
        assert len(history) == 0
        assert reopen().records == ()

    def test_a_mid_batch_encode_failure_writes_nothing(self, reopen):
        # The whole batch encodes before anything reaches the sink
        # [convention 63]: a batch is durable whole or not at all — never a
        # valid prefix of a failed commit.
        history = reopen()
        with pytest.raises(ValueError, match="TokensProduced"):
            history.extend(
                [
                    FiringBegun(WORK, occurrence=1, instant=1),
                    TokensProduced(OUT, (Token("x", object()),), occurrence=1, instant=1),
                ]
            )
        assert len(history) == 0
        assert reopen().records == ()


class TestInstanceParity:
    """A Instance over either backend: same drive, same kill-resume, same folds rebuilt."""

    def _driven(self, reopen):
        """Construct, deliver one identified payment, drive the activity occurrence to its end — the pre-kill truth."""
        instance = Instance(activity_net(), handlers={"charge": Charge()}, history=reopen())
        instance.deliver(INTAKE, payment(), identity="evt_123", at=1)
        occurrence = instance.begin(instance.candidates()[0], at=2)
        instance.record_activity_completion(occurrence, {"status": "captured"}, at=3)
        instance.complete(occurrence, at=4)
        return instance, occurrence

    def test_construction_over_a_recorded_history_is_rejected(self, reopen):
        Instance(activity_net(), handlers={"charge": Charge()}, history=reopen())
        with pytest.raises(ValueError, match="recorded history"):
            Instance(activity_net(), handlers={"charge": Charge()}, history=reopen())

    def test_a_full_drive_kills_and_resumes_identical(self, reopen):
        instance, _ = self._driven(reopen)
        records, marking, status = instance.history.records, instance.marking, instance.status
        del instance  # the kill: the durable record is the survivor

        resumed = Instance.resume(activity_net(), reopen(), handlers={"charge": Charge()})

        assert resumed.history.records == records
        assert resumed.marking == marking == Marking({OUT: (Token("Receipt", {"status": "captured"}),)})
        assert resumed.watermark == 4
        assert resumed.status is status

    def test_the_occurrence_counter_resumes_past_every_recorded_id(self, reopen):
        instance, occurrence = self._driven(reopen)
        del instance

        resumed = Instance.resume(activity_net(), reopen(), handlers={"charge": Charge()})
        outcome = resumed.deliver(INTAKE, payment(), identity="evt_456")

        assert isinstance(outcome, FiringOutcome)
        assert outcome.occurrence == occurrence.id + 1

    def test_the_accepted_identity_index_resumes_from_the_records(self, reopen):
        instance, _ = self._driven(reopen)
        accepted = next(r for r in instance.history if isinstance(r, ExternalEventDelivered))
        del instance

        resumed = Instance.resume(activity_net(), reopen(), handlers={"charge": Charge()})
        acknowledgement = resumed.deliver(INTAKE, payment(), identity="evt_123")

        # The redelivered identity is answered with the prior acknowledgement,
        # never a second semantic record — the index rebuilt from the durable
        # record alone.
        assert acknowledgement == PriorAcknowledgement("evt_123", accepted.occurrence)
        assert resumed.history.records == reopen().records

    def test_the_terminal_activity_index_resumes_from_the_records(self, reopen):
        instance, occurrence = self._driven(reopen)
        del instance

        resumed = Instance.resume(activity_net(), reopen(), handlers={"charge": Charge()})

        # An at-least-once adapter redelivers after the firing ENDED: the
        # terminal-result index — rebuilt from the records alone — answers the
        # identical result quietly, appending nothing; a different late result
        # is an operational conflict.
        before = len(resumed.history)
        resumed.record_activity_completion(occurrence, {"status": "captured"})
        assert len(resumed.history) == before
        with pytest.raises(ValueError, match="different result"):
            resumed.record_activity_completion(occurrence, {"status": "declined"})


class TestKillWindowParity:
    """The DS1b kill windows, pinned per backend: the durable record alone carries the occurrence across."""

    def _begun(self, reopen):
        instance = Instance(
            activity_net(), Marking({QUEUE: (payment(),)}), handlers={"charge": Charge()}, history=reopen()
        )
        occurrence = instance.begin(instance.candidates()[0], at=2)
        return instance, occurrence

    def test_killed_after_the_begin_batch_resumes_and_redispatches(self, reopen):
        # Kill window 1: history ends after the begin batch (ActivityRequested
        # frozen, no terminal activity fact). Resume rebuilds the invocation
        # from the record — prepare never re-runs — and the rebuilt invocation
        # drives to completion.
        instance, occurrence = self._begun(reopen)
        del instance  # the process dies before any dispatch acknowledged

        handler = Charge()
        resumed = Instance.resume(activity_net(), reopen(), handlers={"charge": handler})

        [rebuilt] = resumed.in_flight
        assert rebuilt == occurrence
        assert rebuilt.invocation == ActivityInvocation(
            "charge_card", input={"amount": 100}, correlation="occurrence-1", idempotency="occurrence-1"
        )
        resumed.record_activity_completion(rebuilt, {"status": "captured"}, at=9)
        resumed.complete(rebuilt, at=9)
        assert handler.prepared == 0  # the record supplied the invocation
        assert handler.projected == 1
        assert resumed.marking == Marking({OUT: (Token("Receipt", {"status": "captured"}),)})

    def test_killed_after_the_frozen_result_resumes_projection_pending(self, reopen):
        # Kill window 2: history ends after ActivityCompleted. The frozen
        # result survives in the durable record; projection is all that
        # remains — the activity is never re-invoked.
        instance, occurrence = self._begun(reopen)
        instance.record_activity_completion(occurrence, {"status": "captured"}, at=3)
        del instance  # the process dies before projection committed

        handler = Charge()
        resumed = Instance.resume(activity_net(), reopen(), handlers={"charge": handler})

        [rebuilt] = resumed.in_flight
        assert rebuilt.id in {pending.id for pending in resumed.projection_pending}
        firing = resumed.complete(rebuilt, at=9)  # projection only, from the frozen result
        assert handler.prepared == 0
        assert handler.projected == 1
        assert firing.occurrence == rebuilt.id
        assert resumed.marking == Marking({OUT: (Token("Receipt", {"status": "captured"}),)})
        assert reopen().records == resumed.history.records
