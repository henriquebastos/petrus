"""
Behavioral tests for persistence: the durable spelling of the event history.

The durable artifact is not a new concept — it is the one event history,
persisted by a backend [DR 2026-07-10 durable-history-is-a-history-backend].
``petrus.impetus.history.codec`` owns the ratified public record serialization schema;
``petrus.impetus.history_store`` owns the first backend,
``JsonlHistoryStore``: a write-through ``InMemoryHistoryStore`` whose every append is
durable before it is in memory. Injecting one at ``Instance`` construction
makes the whole history durable from the first record — construction records
and ``deliver()``'s inline firings included, with no sync step for a lag to
hide behind.
"""

from __future__ import annotations

# Python imports
import json
from typing import get_args

# Pip imports
import pytest

# Internal imports
from petrus.motus.activity import ExecutionPolicy
from petrus.impetus.history import (
    InstanceCreated,
    ActivityCompleted,
    ActivityFailed,
    ActivityRequested,
    ActivityTerminalQuarantined,
    CandidateSelected,
    ExternalEventDelivered,
    FiringBegun,
    FiringCompleted,
    FiringFailed,
    Record,
    ScopeClosed,
    ScopeOpened,
    ScopeReset,
    ScopedDeliveryDropped,
    ScopedDeliveryQuarantined,
    DeliveryRegistrationClosed,
    DeliveryRegistrationOpened,
    TimerMatured,
    TokensConsumed,
    TokensInitialized,
    TokensProduced,
    TokensRead,
)
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.history.codec import (
    LIFECYCLE_SCHEMA_VERSION,
    READABLE_SCHEMA_VERSIONS,
    SCHEMA_VERSION,
    decode_record,
    encode_record,
)
from petrus.impetus.history_store import DurableAppend, JsonlHistoryStore
from petrus.impetus.instance import Instance
from petrus.impetus.petrinet import Arc, ArcMode, Net, NetPath, Place, Transition
from petrus.impetus.scope import LifecycleScope

PLACE, TRANSITION = NetPath("p"), NetPath("t")
TOKEN = Token("issue", {"id": "goose", "passed": True})


def every_record_category() -> list[Record]:
    """One constructed instance of every category in the kernel's Record union."""
    first = LifecycleScope("draft", 1)
    second = LifecycleScope("draft", 2)
    return [
        InstanceCreated("instance-7f", name="order-fulfillment", instant=0),
        TokensInitialized(PLACE, (TOKEN, Token.black()), instant=0),
        ScopeOpened(first, instant=0),
        ScopeClosed(first, discarded=(), cancelled=(), instant=1),
        ScopeReset(first, second, discarded=(), cancelled=(), instant=1),
        DeliveryRegistrationOpened(TRANSITION, "default", occurrence=None, instant=0),
        ExternalEventDelivered(TRANSITION, (TOKEN,), identity="occurrence-1", occurrence=1, instant=1),
        ScopedDeliveryDropped(TRANSITION, (TOKEN,), identity="closed-1", scope=first, instant=1),
        ScopedDeliveryQuarantined(TRANSITION, (TOKEN,), identity="uncertain-1", scope="draft", instant=1),
        CandidateSelected(TRANSITION, occurrence=2, instant=2),
        FiringBegun(TRANSITION, occurrence=2, instant=2),
        TokensConsumed(PLACE, (TOKEN,), occurrence=2, instant=2),
        TokensRead(PLACE, (Token.black(),), occurrence=2, instant=2),
        TimerMatured(maturation_instant=2, instant=3),
        ActivityRequested(
            TRANSITION,
            activity="charge_card",
            input={"amount": 100},
            policy=ExecutionPolicy(attempts=2, heartbeat_timeout=45),
            correlation="order-77",
            idempotency="occurrence-2",
            occurrence=2,
            instant=3,
        ),
        ActivityCompleted(TRANSITION, {"status": "captured"}, occurrence=2, instant=4),
        ActivityTerminalQuarantined(
            TRANSITION,
            {"kind": "completed", "value": {"status": "late"}},
            first,
            occurrence=3,
            instant=4,
        ),
        TokensProduced(PLACE, (TOKEN,), occurrence=2, instant=4),
        DeliveryRegistrationClosed(TRANSITION, "default", occurrence=2, instant=4),
        FiringCompleted(TRANSITION, occurrence=2, instant=4),
        ActivityFailed(TRANSITION, "TimeoutError('gone')", occurrence=1, instant=5),
        FiringFailed(TRANSITION, "boom", occurrence=1, instant=5),
    ]


class TestRecordCodec:
    """The ratified public record serialization schema."""

    def test_every_record_category_round_trips_value_equal(self):
        # The codec's whole-union claim, with a completeness assertion that
        # reads the union itself — a new kernel category fails here until the
        # codec proves it. The round trip crosses real JSON text, so every
        # value survives the wire, not just the dict shapes.
        records = every_record_category()
        assert {type(record) for record in records} == set(get_args(Record))
        for record in records:
            assert decode_record(json.loads(json.dumps(encode_record(record)))) == record

    def test_the_ratified_wire_shape(self):
        # The public schema, pinned field by field on representatives of each
        # encoding rule: the "record" class-name discriminator; the "schema"
        # envelope version 4; a node spelled by its
        # role (place / transition / source) as a dotted string; Token as
        # {color, data}; DeliveryRegistration as {source, key};
        # ExecutionPolicy as {attempts, heartbeat_timeout}; the
        # activity family's input/result as raw JSON values; tuples as
        # lists; occurrence None as null; the delivery's stable identity.
        assert encode_record(
            ExternalEventDelivered(NetPath("net.in"), (TOKEN,), identity="evt_123", occurrence=1, instant=3)
        ) == {
            "record": "ExternalEventDelivered",
            "schema": 4,
            "source": "net.in",
            "tokens": [{"color": "issue", "data": {"id": "goose", "passed": True}}],
            "identity": "evt_123",
            "occurrence": 1,
            "instant": 3,
        }
        assert encode_record(TokensConsumed(PLACE, (Token.black(),), occurrence=2, instant=2)) == {
            "record": "TokensConsumed",
            "schema": 4,
            "place": "p",
            "tokens": [{"color": None, "data": None}],
            "occurrence": 2,
            "instant": 2,
        }
        assert encode_record(TokensRead(PLACE, (Token.black(),), occurrence=2, instant=2)) == {
            "record": "TokensRead",
            "schema": 4,
            "place": "p",
            "tokens": [{"color": None, "data": None}],
            "occurrence": 2,
            "instant": 2,
        }
        assert encode_record(CandidateSelected(TRANSITION, occurrence=2, instant=2)) == {
            "record": "CandidateSelected",
            "schema": 4,
            "transition": "t",
            "occurrence": 2,
            "instant": 2,
        }
        assert encode_record(DeliveryRegistrationOpened(TRANSITION, "default", occurrence=None, instant=0)) == {
            "record": "DeliveryRegistrationOpened",
            "schema": 4,
            "source": "t",
            "key": "default",
            "occurrence": None,
            "instant": 0,
        }
        assert encode_record(
            ActivityRequested(
                TRANSITION,
                activity="charge_card",
                input={"amount": 100},
                policy=ExecutionPolicy(attempts=2, heartbeat_timeout=45),
                correlation="order-77",
                idempotency="key-9",
                occurrence=2,
                instant=3,
            )
        ) == {
            "record": "ActivityRequested",
            "schema": 4,
            "transition": "t",
            "activity": "charge_card",
            "input": {"amount": 100},
            "policy": {"attempts": 2, "heartbeat_timeout": 45},
            "correlation": "order-77",
            "idempotency": "key-9",
            "occurrence": 2,
            "instant": 3,
        }
        assert encode_record(ActivityCompleted(TRANSITION, {"status": "declined"}, occurrence=2, instant=4)) == {
            "record": "ActivityCompleted",
            "schema": 4,
            "transition": "t",
            "result": {"status": "declined"},
            "occurrence": 2,
            "instant": 4,
        }

    def test_schema_5_is_used_only_for_lifecycle_scope_records_and_provenance(self):
        scope = LifecycleScope("draft", 3)
        scoped = TokensProduced(
            PLACE,
            (TOKEN,),
            occurrence=2,
            entries=(17,),
            scope=scope,
            instant=4,
        )

        assert encode_record(scoped) == {
            "record": "TokensProduced",
            "schema": 5,
            "place": "p",
            "tokens": [{"color": "issue", "data": {"id": "goose", "passed": True}}],
            "occurrence": 2,
            "entries": [17],
            "scope": {"name": "draft", "generation": 3},
            "instant": 4,
        }
        assert decode_record(encode_record(scoped)) == scoped
        with pytest.raises(ValueError, match="provenance require schema 5"):
            decode_record(encode_record(scoped) | {"schema": 4})
        assert SCHEMA_VERSION == 4
        assert LIFECYCLE_SCHEMA_VERSION == 5
        assert READABLE_SCHEMA_VERSIONS == {4, 5}
        with pytest.raises(ValueError, match="not its canonical record spelling.*expected schema 4"):
            decode_record(encode_record(FiringCompleted(TRANSITION, occurrence=2)) | {"schema": 5})
        with pytest.raises(ValueError, match="not its canonical record spelling.*expected schema 4"):
            decode_record(
                {
                    "record": "TokensProduced",
                    "schema": 5,
                    "place": "p",
                    "tokens": [],
                    "occurrence": 2,
                    "entries": [],
                    "scope": None,
                    "instant": 0,
                }
            )

    def test_schema_5_refuses_partial_or_invalid_scope_provenance(self):
        payload = encode_record(
            TokensProduced(
                PLACE,
                (TOKEN,),
                occurrence=2,
                entries=(17,),
                scope=LifecycleScope("draft", 3),
                instant=4,
            )
        )

        without_entries = {key: value for key, value in payload.items() if key != "entries"}
        with pytest.raises(ValueError, match="scoped movements require one queue-entry identity per token"):
            decode_record(without_entries)
        without_scope = {key: value for key, value in payload.items() if key != "scope"}
        with pytest.raises(ValueError, match="queue-entry identities require lifecycle scope provenance"):
            decode_record(without_scope)
        for generation in (0, -1, True, "3"):
            malformed = payload | {"scope": {"name": "draft", "generation": generation}}
            with pytest.raises(ValueError, match="generation must be a positive integer"):
                decode_record(malformed)
        for name in ("", "bad\x00name", 3):
            malformed = payload | {"scope": {"name": name, "generation": 3}}
            with pytest.raises(ValueError, match="name must be a non-empty string without NUL"):
                decode_record(malformed)

    def test_token_data_must_be_json_faithful_to_round_trip(self):
        # The codec's defended looseness, pinned: a tuple in token data is
        # legal JSON (an array) but reads back a list — value equality across
        # the wire, and with it rebuilt-occurrence equality, holds only for
        # JSON-faithful data.
        record = TokensInitialized(PLACE, (Token("x", (1, 2)),), instant=0)
        decoded = decode_record(json.loads(json.dumps(encode_record(record))))
        assert decoded == TokensInitialized(PLACE, (Token("x", [1, 2]),), instant=0)
        assert decoded != record

    def test_an_unknown_record_name_fails_loud(self):
        with pytest.raises(ValueError, match="unknown 'record' discriminator 'Bogus'"):
            decode_record({"record": "Bogus", "schema": 4, "instant": 0})

    def test_a_payload_without_a_discriminator_fails_loud(self):
        # A distinct misuse class with its own honest message: this payload
        # carried NO discriminator, not an unknown one spelled None.
        with pytest.raises(ValueError, match="has no 'record' discriminator"):
            decode_record({"transition": "t", "instant": 0})

    def test_field_drift_fails_as_the_record_types_own_rejection(self):
        # A known category whose field shape drifted is the constructor's
        # rejection, not a silent partial decode.
        with pytest.raises(TypeError):
            decode_record(
                {"record": "FiringBegun", "schema": 4, "transition": "t", "occurrence": 1, "instant": 0, "stray": 1}
            )

    @pytest.mark.parametrize(
        "policy",
        [
            {"attempts": 2},
            {"attempts": 2, "heartbeat_timeout": 30, "extra": True},
            {"attempts": True, "heartbeat_timeout": 30},
            {"attempts": 2, "heartbeat_timeout": "30"},
        ],
    )
    def test_schema_4_activity_request_refuses_noncanonical_policy_shapes(self, policy):
        payload = {
            "record": "ActivityRequested",
            "schema": 4,
            "transition": "t",
            "activity": "work",
            "input": None,
            "policy": policy,
            "correlation": "c",
            "idempotency": "i",
            "occurrence": 1,
            "instant": 0,
        }
        with pytest.raises(ValueError, match="policy must be exactly"):
            decode_record(payload)

    def test_a_delivery_identity_must_be_a_non_empty_string_to_decode(self):
        # The record's own precondition (the DeliveryRegistration.key
        # precedent): a payload whose identity is empty or not a string fails
        # as the constructor's rejection — decode and direct construction
        # refuse identically.
        for bad in ("", 7):
            payload = {
                "record": "ExternalEventDelivered",
                "schema": 4,
                "source": "t",
                "tokens": [],
                "identity": bad,
                "occurrence": 1,
                "instant": 0,
            }
            with pytest.raises(ValueError, match="non-empty string identity"):
                decode_record(payload)

    def test_a_payload_without_a_schema_version_fails_naming_the_migration(self):
        # A v1 line (or a hand-built payload) carries no "schema": the refusal
        # names the CV3 schema-2 migration and the no-converter posture — no
        # production histories predate it, so nothing silently converts.
        with pytest.raises(ValueError, match=r"no 'schema' version.*schemas \[4, 5\].*no converter"):
            decode_record({"record": "FiringBegun", "transition": "t", "occurrence": 1, "instant": 0})

    def test_a_wrong_schema_version_fails_naming_the_migration(self):
        with pytest.raises(ValueError, match=r"'schema' is 1.*reads schemas \[4, 5\] only.*no migration"):
            decode_record({"record": "FiringBegun", "schema": 1, "transition": "t", "occurrence": 1, "instant": 0})
        for malformed in (True, 4.0, "4"):
            with pytest.raises(ValueError, match=r"reads schemas \[4, 5\] only"):
                decode_record(
                    {
                        "record": "FiringBegun",
                        "schema": malformed,
                        "transition": "t",
                        "occurrence": 1,
                        "instant": 0,
                    }
                )

    def test_schema_2_is_refused_before_record_interpretation(self):
        with pytest.raises(ValueError, match=r"'schema' is 2.*reads schemas \[4, 5\] only.*no migration"):
            decode_record({"record": "FiringBegun", "schema": 2, "not": "the schema-4 fields"})

    def test_schema_3_is_refused_before_record_interpretation(self):
        with pytest.raises(ValueError, match=r"'schema' is 3.*reads schemas \[4, 5\] only.*no migration"):
            decode_record({"record": "FiringBegun", "schema": 3, "not": "the schema-4 fields"})

    def test_unversioned_old_discriminators_are_refused_before_interpretation(self):
        for old_name in ("RegistrationOpened", "RegistrationClosed", "ExternalEventRecorded"):
            with pytest.raises(ValueError, match=rf"{old_name}.*no 'schema' version.*schemas \[4, 5\]"):
                decode_record({"record": old_name, "source": "t", "key": "default", "attempt": None})


class TestDurableAppend:
    """The durability policy, split from the format: batches of already-encoded lines, one open-append-close per call, no format knowledge."""

    def test_appends_accumulate_across_calls(self, tmp_path):
        path = tmp_path / "lines.jsonl"
        durable = DurableAppend(path)

        durable.append(["one", "two"])
        durable.append(["three"])

        assert path.read_text(encoding="utf-8") == "one\ntwo\nthree\n"

    def test_makes_the_parent_directory_once_needed(self, tmp_path):
        path = tmp_path / "nested" / "deeper" / "lines.jsonl"

        DurableAppend(path).append(["one"])

        assert path.read_text(encoding="utf-8") == "one\n"


class TestJsonlHistoryStore:
    """The first backend: one JSON object per line, durable at every append."""

    def test_the_durable_spelling_is_byte_stable(self, tmp_path):
        # The ratified wire format pinned at the byte level, both directions:
        # the exact JSONL written today is what every future revision keeps
        # writing AND reading — a refactor of the codec or the durability
        # seam that moves a key or a separator fails here, not at a
        # migration (this IS the schema-2 spelling the CV3 migration ruled).
        path = tmp_path / "history.jsonl"
        fixture = (
            '{"record": "TokensInitialized", "schema": 4, "place": "p", '
            '"tokens": [{"color": "issue", "data": {"id": "goose", "passed": true}}], "instant": 0}\n'
            '{"record": "CandidateSelected", "schema": 4, "transition": "t", "occurrence": 1, "instant": 2}\n'
        )
        records = [
            TokensInitialized(PLACE, (TOKEN,), instant=0),
            CandidateSelected(TRANSITION, occurrence=1, instant=2),
        ]

        JsonlHistoryStore(path).extend(records)

        assert path.read_text(encoding="utf-8") == fixture, "encode half: byte-identical durable spelling"
        assert JsonlHistoryStore(path).records == tuple(records), "decode half: the fixture reads back value-equal"

    def test_direct_firing_lifecycle_jsonl_bytes_are_stable(self, tmp_path):
        """The pre-extraction direct lifecycle baseline, including every movement boundary byte."""
        path = tmp_path / "firing.jsonl"
        consumed, observed, produced = NetPath("consume"), NetPath("read"), NetPath("produced")
        net = Net(
            places=[Place(consumed), Place(observed), Place(produced)],
            transitions=[Transition(TRANSITION)],
            arcs=[Arc(consumed, TRANSITION), Arc(observed, TRANSITION, mode=ArcMode.READ), Arc(TRANSITION, produced)],
        )
        fixture = (
            '{"record": "InstanceCreated", "schema": 4, "instance": "fixture-instance", "name": null, "instant": 1}\n'
            '{"record": "TokensInitialized", "schema": 4, "place": "consume", "tokens": [{"color": "issue", "data": {"id": "goose", "passed": true}}], "instant": 1}\n'
            '{"record": "TokensInitialized", "schema": 4, "place": "read", "tokens": [{"color": null, "data": null}], "instant": 1}\n'
            '{"record": "CandidateSelected", "schema": 4, "transition": "t", "occurrence": 1, "instant": 2}\n'
            '{"record": "FiringBegun", "schema": 4, "transition": "t", "occurrence": 1, "instant": 2}\n'
            '{"record": "TokensConsumed", "schema": 4, "place": "consume", "tokens": [{"color": "issue", "data": {"id": "goose", "passed": true}}], "occurrence": 1, "instant": 2}\n'
            '{"record": "TokensRead", "schema": 4, "place": "read", "tokens": [{"color": null, "data": null}], "occurrence": 1, "instant": 2}\n'
            '{"record": "TokensProduced", "schema": 4, "place": "produced", "tokens": [{"color": "result", "data": {"fixed": true}}], "occurrence": 1, "instant": 3}\n'
            '{"record": "FiringCompleted", "schema": 4, "transition": "t", "occurrence": 1, "instant": 3}\n'
        )

        history = JsonlHistoryStore(path)
        instance = Instance(
            net,
            Marking({consumed: (TOKEN,), observed: (Token.black(),)}),
            at=1,
            history=history,
            instance_id="fixture-instance",
        )
        occurrence = instance.begin(instance.candidates()[0], at=2)
        instance.complete(occurrence, {produced: (Token("result", {"fixed": True}),)}, at=3)

        assert path.read_bytes() == fixture.encode()
        assert JsonlHistoryStore(path).records == instance.history.records

    def test_every_append_is_durable_immediately(self, tmp_path):
        # Write-through IS the seam: no sync step, no driver-owed flush — the
        # record is on disk when append returns, and a fresh load reads back
        # value-equal records in order.
        path = tmp_path / "history.jsonl"
        history = JsonlHistoryStore(path)
        history.append(TokensInitialized(PLACE, (TOKEN,), instant=0))
        assert JsonlHistoryStore(path).records == history.records
        history.extend(
            [FiringBegun(TRANSITION, occurrence=1, instant=1), FiringCompleted(TRANSITION, occurrence=1, instant=1)]
        )
        assert JsonlHistoryStore(path).records == history.records
        assert len(history) == 3

    def test_loading_then_appending_continues_the_file(self, tmp_path):
        path = tmp_path / "history.jsonl"
        JsonlHistoryStore(path).extend(every_record_category())

        resumed = JsonlHistoryStore(path)
        resumed.append(FiringFailed(TRANSITION, "later", occurrence=3, instant=6))

        assert JsonlHistoryStore(path).records == tuple(every_record_category()) + (
            FiringFailed(TRANSITION, "later", occurrence=3, instant=6),
        )

    def test_a_missing_file_is_an_empty_history(self, tmp_path):
        history = JsonlHistoryStore(tmp_path / "nested" / "history.jsonl")
        assert history.records == ()
        history.append(TokensInitialized(PLACE, (TOKEN,), instant=0))
        assert (tmp_path / "nested" / "history.jsonl").exists()

    def test_a_v1_encoded_line_fails_loud_at_load_naming_the_migration(self, tmp_path):
        # The ruled no-converter posture at the file door: a schema-1 history
        # (old discriminator, no "schema" version) refuses to load, and the
        # failure names the line, the v2 successor, and the migration —
        # never a silent partial read.
        path = tmp_path / "history.jsonl"
        path.write_text(
            '{"record": "RegistrationOpened", "source": "t", "key": "default", "attempt": null, "instant": 0}\n',
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match=r"line 1.*no 'schema' version.*schemas \[4, 5\]"):
            JsonlHistoryStore(path)

    def test_a_schema_2_line_fails_through_the_actual_jsonl_load(self, tmp_path):
        path = tmp_path / "history.jsonl"
        path.write_text(
            '{"record": "ActivityRequested", "schema": 2, "transition": "t", '
            '"activity": "old", "capabilities": ["gpu"], "occurrence": 1, "instant": 0}\n',
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match=r"line 1.*'schema' is 2.*reads schemas \[4, 5\] only"):
            JsonlHistoryStore(path)

    def test_a_torn_tail_fails_loud_naming_the_line(self, tmp_path):
        # A crash mid-write leaves a torn final line; loading refuses it
        # rather than silently dropping the tail — recovery is the operator's
        # call, not the decoder's guess.
        path = tmp_path / "history.jsonl"
        JsonlHistoryStore(path).append(TokensInitialized(PLACE, (TOKEN,), instant=0))
        with path.open("a", encoding="utf-8") as file:
            file.write('{"record": "FiringComp')
        with pytest.raises(ValueError, match=r"history\.jsonl.*2"):
            JsonlHistoryStore(path)

    def test_unencodable_data_fails_loud_and_appends_nothing(self, tmp_path):
        # Durable instants and token data must be JSON-faithful; a record
        # that cannot be encoded enters neither the file nor memory — the
        # durable record never trails what the instance believes.
        path = tmp_path / "history.jsonl"
        history = JsonlHistoryStore(path)
        with pytest.raises(ValueError, match="TokensInitialized"):
            history.append(TokensInitialized(PLACE, (Token("x", object()),), instant=0))
        assert len(history) == 0
        assert not path.exists()

    def test_a_mid_batch_encoding_failure_writes_nothing(self, tmp_path):
        # extend encodes every record before writing any: a batch is durable
        # whole or not at all, never a valid prefix of a failed commit.
        path = tmp_path / "history.jsonl"
        history = JsonlHistoryStore(path)
        with pytest.raises(ValueError, match="TokensProduced"):
            history.extend(
                [
                    FiringBegun(TRANSITION, occurrence=1, instant=1),
                    TokensProduced(PLACE, (Token("x", object()),), occurrence=1, instant=1),
                ]
            )
        assert len(history) == 0
        assert not path.exists()


class TestInstanceDurableHistory:
    """The injection seam: a Instance built over a durable history."""

    SOURCE, DONE, FORWARD, OUT = NetPath("intake"), NetPath("done"), NetPath("forward"), NetPath("out")

    def net(self) -> Net:
        return Net(
            places=[Place(self.DONE), Place(self.OUT)],
            transitions=[Transition(self.SOURCE), Transition(self.FORWARD)],
            arcs=[Arc(self.SOURCE, self.DONE), Arc(self.DONE, self.FORWARD), Arc(self.FORWARD, self.OUT)],
        )

    def test_construction_records_are_durable_at_construction(self, tmp_path):
        path = tmp_path / "history.jsonl"
        instance = Instance(self.net(), history=JsonlHistoryStore(path))
        assert DeliveryRegistrationOpened(self.SOURCE, "default", occurrence=None) in JsonlHistoryStore(path).records
        assert JsonlHistoryStore(path).records == instance.history.records

    def test_every_appending_door_writes_through(self, tmp_path):
        # deliver's inline firing (the spike's ingress lag), the scheduled
        # firing, and seal — one durable record stream, no door outside it.
        path = tmp_path / "history.jsonl"
        instance = Instance(self.net(), history=JsonlHistoryStore(path))
        instance.deliver(self.SOURCE, Token.black())
        instance.run()
        instance.seal(self.SOURCE)
        durable = JsonlHistoryStore(path).records
        assert durable == instance.history.records
        assert any(isinstance(record, ExternalEventDelivered) for record in durable)
        assert any(isinstance(record, CandidateSelected) for record in durable)
        assert any(isinstance(record, DeliveryRegistrationClosed) for record in durable)
        assert instance.marking == Marking({self.OUT: (Token.black(),)})

    def test_a_refused_durable_append_leaves_the_instance_unchanged(self, tmp_path):
        # The seam's failure contract, pinned with a real backend: a delivery
        # whose token data cannot be encoded raises at the append, and the
        # instance moves NOTHING — watermark, occurrence counter, marking, and
        # in-flight all still speak only appended records (advance-after-
        # append). The next delivery proves it: same occurrence id the failed
        # one never burned.
        path = tmp_path / "history.jsonl"
        instance = Instance(self.net(), history=JsonlHistoryStore(path))
        constructed = instance.history.records

        with pytest.raises(ValueError, match="ExternalEventDelivered"):
            instance.deliver(self.SOURCE, Token("bad", object()), at=7)

        assert instance.history.records == constructed
        assert JsonlHistoryStore(path).records == constructed
        assert instance.watermark == 0
        assert instance.marking == Marking()
        assert instance.in_flight == ()
        assert instance.deliver(self.SOURCE, Token.black(), at=7).occurrence == 1
        assert instance.watermark == 7

    def test_a_recorded_history_is_rejected_at_construction(self, tmp_path):
        # The door partition: construction appends the instance's initial
        # records, so it takes a fresh history only — a recorded one is for
        # resuming, and constructing over it would append a second beginning.
        path = tmp_path / "history.jsonl"
        Instance(self.net(), history=JsonlHistoryStore(path))
        with pytest.raises(ValueError, match="recorded history"):
            Instance(self.net(), history=JsonlHistoryStore(path))

        recorded = InMemoryHistoryStore()
        recorded.append(TokensInitialized(PLACE, (TOKEN,), instant=0))
        with pytest.raises(ValueError, match="recorded history"):
            Instance(self.net(), history=recorded)


class RefusingHistory(InMemoryHistoryStore):
    """A backend whose commit fails on demand — the I/O-failure double for the doors' obligation that a raising append moves nothing else. (The encoding failure is pinned with the real backend above; DeliveryRegistrationClosed and end records always encode, so their doors need the refusal here.)"""

    def __init__(self):
        super().__init__()
        self.refuse = False

    def append(self, record):
        if self.refuse:
            raise OSError("disk full")
        super().append(record)

    def extend(self, records):
        if self.refuse:
            raise OSError("disk full")
        super().extend(records)


class TestARaisingAppendMovesNothingElse:
    """Every appending door commits its append before any other instance state."""

    SOURCE, DONE = NetPath("intake"), NetPath("done")
    START, WORK, OUT = NetPath("start"), NetPath("work"), NetPath("out")

    def test_a_refused_seal_keeps_the_registration_armed(self):
        net = Net(places=[Place(self.DONE)], transitions=[Transition(self.SOURCE)], arcs=[Arc(self.SOURCE, self.DONE)])
        history = RefusingHistory()
        instance = Instance(net, history=history)

        history.refuse = True
        with pytest.raises(OSError, match="disk full"):
            instance.seal(self.SOURCE, at=5)

        assert instance.watermark == 0
        history.refuse = False
        instance.deliver(self.SOURCE, Token.black())  # still armed: the failed seal closed nothing
        instance.seal(self.SOURCE)
        with pytest.raises(ValueError, match="no armed delivery registration"):
            instance.deliver(self.SOURCE, Token.black())

    def test_a_refused_complete_leaves_the_occurrence_in_flight(self):
        net = Net(
            places=[Place(self.START), Place(self.OUT)],
            transitions=[Transition(self.WORK)],
            arcs=[Arc(self.START, self.WORK), Arc(self.WORK, self.OUT)],
        )
        history = RefusingHistory()
        instance = Instance(net, Marking.from_counts({self.START: 1}), history=history)
        occurrence = instance.begin(instance.candidates()[0], at=3)

        history.refuse = True
        with pytest.raises(OSError, match="disk full"):
            instance.complete(occurrence, {self.OUT: occurrence.binding.tokens}, at=9)

        # The occurrence stays in flight for its driver — begin's commit stands
        # (tokens accounted, watermark at 3), the failed completion's does not.
        assert instance.in_flight == (occurrence,)
        assert instance.watermark == 3
        assert instance.marking == Marking()
        history.refuse = False
        firing = instance.complete(occurrence, {self.OUT: occurrence.binding.tokens}, at=9)
        assert firing.occurrence == occurrence.id
        assert instance.marking == Marking({self.OUT: (Token.black(),)})
        assert instance.watermark == 9
