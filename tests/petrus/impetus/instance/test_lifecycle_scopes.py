"""Production lifecycle-scope semantics on the real Instance and History."""

from __future__ import annotations

from dataclasses import replace

import pytest

from petrus.impetus.history import (
    FiringFailed,
    ActivityRequested,
    ActivityTerminalQuarantined,
    ScopeClosed,
    ScopeReset,
    ScopedDeliveryDropped,
    ScopedDeliveryQuarantined,
    TokensConsumed,
    TokensProduced,
    replay_queues,
)
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.instance import (
    DeliveryDisposition,
    Instance,
    ScopedDeliveryAcknowledgement,
    TerminalDisposition,
)
from petrus.impetus.petrinet import Arc, Marking, Net, NetPath, Place, Token, Transition
from petrus.impetus.scope import LifecycleScope
from petrus.motus.activity import ActivityInvocation

SOURCE, QUEUE, WORK, OUT = map(NetPath, ("source", "queue", "work", "out"))


class Work:
    def prepare(self, binding) -> ActivityInvocation:
        return ActivityInvocation("work", input={"value": binding.tokens[0].data})

    def project(self, binding, result):
        return {OUT: (Token("Value", result),)}


def scoped_net(*, activity: bool = False) -> Net:
    return Net(
        places=[Place(QUEUE), Place(OUT)],
        transitions=[Transition(SOURCE), Transition(WORK, handler="work" if activity else None)],
        arcs=[Arc(SOURCE, QUEUE), Arc(QUEUE, WORK), Arc(WORK, OUT)],
    )


def instance(*, activity: bool = False, history=None) -> Instance:
    handlers = {"work": Work()} if activity else None
    return Instance(scoped_net(activity=activity), handlers=handlers, history=history)


def test_close_discards_duplicate_valued_entries_by_identity_and_replay_preserves_the_other_scope():
    history = InMemoryHistoryStore()
    runtime = instance(history=history)
    first = runtime.open_scope("first", at=1)
    second = runtime.open_scope("second", at=1)
    token = Token("Value", {"same": True})
    runtime.deliver(SOURCE, token, identity="first-1", scope=first, at=2)
    runtime.deliver(SOURCE, token, identity="second-1", scope=second, at=2)
    runtime.deliver(SOURCE, token, identity="first-2", scope=first, at=2)

    before = replay_queues(history)
    first_ids = tuple(
        identity for identity, scope in zip(before[QUEUE].identities, before[QUEUE].scopes) if scope == first
    )
    second_ids = tuple(
        identity for identity, scope in zip(before[QUEUE].identities, before[QUEUE].scopes) if scope == second
    )

    closure = runtime.close_scope(first, at=3)

    assert closure.discarded == first_ids
    assert runtime.marking == Marking({QUEUE: (token,)})
    assert replay_queues(history)[QUEUE].identities == second_ids
    assert replay_queues(history)[QUEUE].scopes == (second,)
    assert next(record for record in history if isinstance(record, ScopeClosed)).discarded == first_ids


def test_queue_identity_never_reuses_a_spent_occurrence_after_restart():
    history = InMemoryHistoryStore()
    runtime = instance(activity=True, history=history)
    first = runtime.open_scope("draft")
    runtime.deliver(SOURCE, Token("Value", 7), identity="draft-7", scope=first)
    occurrence = runtime.begin(runtime.candidates()[0])
    first_entry = next(
        record.entries[0] for record in history if isinstance(record, TokensProduced) and record.scope == first
    )
    runtime.close_scope(first)

    resumed = Instance.resume(scoped_net(activity=True), history, handlers={"work": Work()})
    second = resumed.open_scope("draft")
    resumed.deliver(SOURCE, Token("Value", 8), identity="draft-8", scope=second)
    second_entry = next(
        record.entries[0]
        for record in reversed(history.records)
        if isinstance(record, TokensProduced) and record.scope == second
    )

    assert occurrence.id in {held.id for held in resumed.cancelled}
    assert second_entry > first_entry


def test_scoped_identity_allocation_matches_live_and_replay_after_unscoped_movements():
    live_history = InMemoryHistoryStore()
    live = instance(history=live_history)
    live.deliver(SOURCE, Token("Value", 1), identity="unscoped")
    live.step()
    scope = live.open_scope("draft")
    resumed_history = InMemoryHistoryStore()
    resumed_history.extend(list(live_history.records))
    resumed = Instance.resume(scoped_net(), resumed_history)

    live.deliver(SOURCE, Token("Value", 2), identity="live-scoped", scope=scope)
    resumed.deliver(SOURCE, Token("Value", 2), identity="resumed-scoped", scope=scope)

    live_entry = next(
        record.entries
        for record in reversed(live_history.records)
        if isinstance(record, TokensProduced) and record.scope == scope
    )
    resumed_entry = next(
        record.entries
        for record in reversed(resumed_history.records)
        if isinstance(record, TokensProduced) and record.scope == scope
    )
    assert live_entry == resumed_entry


def test_begin_records_exact_consumed_identity_and_scope_on_the_activity_outbox():
    runtime = instance(activity=True)
    scope = runtime.open_scope("draft")
    runtime.deliver(SOURCE, Token("Value", 7), identity="draft-7", scope=scope)

    occurrence = runtime.begin(runtime.candidates()[0])

    consumed = next(record for record in occurrence.records if isinstance(record, TokensConsumed))
    requested = next(record for record in occurrence.records if isinstance(record, ActivityRequested))
    assert len(consumed.entries) == 1
    assert consumed.scope == scope
    assert requested.scope == scope
    assert occurrence.scope == scope


def test_close_cancels_an_activity_without_restoring_its_consumed_input():
    runtime = instance(activity=True)
    scope = runtime.open_scope("draft")
    token = Token("Value", 7)
    runtime.deliver(SOURCE, token, identity="draft-7", scope=scope)
    occurrence = runtime.begin(runtime.candidates()[0])

    closure = runtime.close_scope(scope)

    assert closure.cancelled == (occurrence.id,)
    assert runtime.in_flight == ()
    assert not runtime.marking
    assert runtime.cancelled == (occurrence,)


def test_completion_before_close_at_the_same_instant_is_accepted_then_its_output_is_cleaned():
    runtime = instance(activity=True)
    scope = runtime.open_scope("draft", at=1)
    runtime.deliver(SOURCE, Token("Value", 7), identity="draft-7", scope=scope, at=2)
    occurrence = runtime.begin(runtime.candidates()[0], at=3)
    assert runtime.record_activity_completion(occurrence, {"answer": 8}, at=20) is TerminalDisposition.ACCEPTED
    runtime.complete(occurrence, at=20)

    runtime.close_scope(scope, at=20)

    assert not runtime.marking
    assert not [record for record in runtime.history if isinstance(record, ActivityTerminalQuarantined)]
    produced = next(record for record in runtime.history if isinstance(record, TokensProduced) and record.place == OUT)
    assert produced.scope == scope


def test_close_before_completion_at_the_same_instant_quarantines_exact_redelivery_and_refuses_conflict():
    runtime = instance(activity=True)
    scope = runtime.open_scope("draft", at=1)
    runtime.deliver(SOURCE, Token("Value", 7), identity="draft-7", scope=scope, at=2)
    occurrence = runtime.begin(runtime.candidates()[0], at=3)
    runtime.close_scope(scope, at=20)

    assert runtime.record_activity_completion(occurrence, {"answer": 8}, at=20) is TerminalDisposition.QUARANTINED
    before = len(runtime.history)
    assert runtime.record_activity_completion(occurrence, {"answer": 8}, at=20) is TerminalDisposition.ACKNOWLEDGED
    assert len(runtime.history) == before
    with pytest.raises(ValueError, match="conflicting terminal activity report"):
        runtime.record_activity_completion(occurrence, {"answer": 9}, at=20)
    assert not runtime.marking


def test_reset_is_one_record_that_closes_cleanup_and_opens_the_next_generation():
    runtime = instance(activity=True)
    first = runtime.open_scope("draft", at=1)
    runtime.deliver(SOURCE, Token("Value", 7), identity="draft-7", scope=first, at=2)
    occurrence = runtime.begin(runtime.candidates()[0], at=3)
    before = len(runtime.history)

    second = runtime.reset_scope(first, at=4)

    assert second == LifecycleScope("draft", 2)
    assert len(runtime.history) == before + 1
    [record] = runtime.history.records[before:]
    assert isinstance(record, ScopeReset)
    assert record.closed == first and record.opened == second
    assert record.cancelled == (occurrence.id,)
    assert runtime.active_scopes == {"draft": second}


def test_scope_append_failure_leaves_live_state_unchanged():
    class RefusingHistory(InMemoryHistoryStore):
        refuse = False

        def append(self, record) -> None:
            if self.refuse and isinstance(record, ScopeClosed):
                raise OSError("refused close")
            super().append(record)

    history = RefusingHistory()
    runtime = instance(activity=True, history=history)
    scope = runtime.open_scope("draft")
    runtime.deliver(SOURCE, Token("Value", 7), identity="draft-7", scope=scope)
    occurrence = runtime.begin(runtime.candidates()[0])
    history.refuse = True

    with pytest.raises(OSError, match="refused close"):
        runtime.close_scope(scope)

    assert runtime.active_scopes == {"draft": scope}
    assert runtime.in_flight == (occurrence,)


def test_closed_and_uncertain_scoped_delivery_are_canonical_idempotent_dispositions():
    runtime = instance()
    scope = runtime.open_scope("draft")
    runtime.close_scope(scope)
    runtime.seal(SOURCE)
    token = Token("Value", 7)

    dropped = runtime.deliver(SOURCE, token, identity="closed", scope=scope)
    quarantined = runtime.deliver(SOURCE, token, identity="uncertain", scope="draft")

    assert dropped == ScopedDeliveryAcknowledgement("closed", DeliveryDisposition.DROPPED, scope)
    assert quarantined == ScopedDeliveryAcknowledgement("uncertain", DeliveryDisposition.QUARANTINED, "draft")
    before = len(runtime.history)
    assert runtime.deliver(SOURCE, token, identity="closed", scope=scope) == dropped
    assert runtime.deliver(SOURCE, token, identity="uncertain", scope="draft") == quarantined
    assert len(runtime.history) == before
    with pytest.raises(ValueError, match="delivery identity conflict"):
        runtime.deliver(SOURCE, Token("Value", 8), identity="uncertain", scope="draft")
    assert len([record for record in runtime.history if isinstance(record, ScopedDeliveryDropped)]) == 1
    assert len([record for record in runtime.history if isinstance(record, ScopedDeliveryQuarantined)]) == 1


def test_exact_future_generation_is_quarantined_without_losing_its_target_identity():
    runtime = instance()
    current = runtime.open_scope("draft")
    future = LifecycleScope("draft", current.generation + 1)

    acknowledgement = runtime.deliver(
        SOURCE,
        Token("Value", 7),
        identity="future",
        scope=future,
    )

    assert acknowledgement == ScopedDeliveryAcknowledgement("future", DeliveryDisposition.QUARANTINED, future)
    record = next(record for record in runtime.history if isinstance(record, ScopedDeliveryQuarantined))
    assert record.scope == future


def test_scope_projection_and_quarantine_rebuild_deterministically_on_resume():
    history = InMemoryHistoryStore()
    runtime = instance(activity=True, history=history)
    first = runtime.open_scope("draft")
    runtime.deliver(SOURCE, Token("Value", 7), identity="draft-7", scope=first)
    occurrence = runtime.begin(runtime.candidates()[0])
    second = runtime.reset_scope(first)
    runtime.record_activity_completion(occurrence, {"answer": 8})

    resumed = Instance.resume(scoped_net(activity=True), history, handlers={"work": Work()})

    assert resumed.active_scopes == {"draft": second}
    assert resumed.cancelled[0].id == occurrence.id
    assert resumed.record_activity_completion(occurrence, {"answer": 8}) is TerminalDisposition.ACKNOWLEDGED
    with pytest.raises(ValueError, match="conflicting terminal activity report"):
        resumed.record_activity_completion(occurrence, {"answer": 9})


def test_replay_refuses_a_scope_close_that_omits_queued_cleanup():
    history = InMemoryHistoryStore()
    runtime = instance(history=history)
    scope = runtime.open_scope("draft")
    runtime.deliver(SOURCE, Token("Value", 7), identity="draft-7", scope=scope)
    malformed = InMemoryHistoryStore()
    malformed.extend(list(history.records))
    malformed.append(ScopeClosed(scope))

    with pytest.raises(ValueError, match="lifecycle close left queue entries"):
        replay_queues(malformed)


def test_replay_refuses_a_scope_close_that_omits_an_in_flight_occurrence():
    history = InMemoryHistoryStore()
    runtime = instance(activity=True, history=history)
    scope = runtime.open_scope("draft")
    runtime.deliver(SOURCE, Token("Value", 7), identity="draft-7", scope=scope)
    runtime.begin(runtime.candidates()[0])
    malformed = InMemoryHistoryStore()
    malformed.extend(list(history.records))
    malformed.append(ScopeClosed(scope))

    with pytest.raises(ValueError, match="exact open occurrence set"):
        Instance.resume(scoped_net(activity=True), malformed, handlers={"work": Work()})


def test_replay_refuses_a_scope_close_that_reclassifies_an_already_ended_occurrence():
    history = InMemoryHistoryStore()
    runtime = instance(activity=True, history=history)
    scope = runtime.open_scope("draft")
    runtime.deliver(SOURCE, Token("Value", 7), identity="draft-7", scope=scope)
    occurrence = runtime.begin(runtime.candidates()[0])
    runtime.record_activity_completion(occurrence, {"answer": 8})
    runtime.complete(occurrence)
    queues = replay_queues(history)
    discarded = tuple(
        identity
        for queue in queues.values()
        for identity, provenance in zip(queue.identities, queue.scopes, strict=True)
        if provenance == scope and identity is not None
    )
    malformed = InMemoryHistoryStore()
    malformed.extend(list(history.records))
    malformed.append(ScopeClosed(scope, discarded=discarded, cancelled=(occurrence.id,)))

    with pytest.raises(ValueError, match=r"cancels \(2,\).*exact open occurrence set.*\(\)"):
        Instance.resume(scoped_net(activity=True), malformed, handlers={"work": Work()})


def test_replay_refuses_a_scope_close_that_reclassifies_an_accepted_terminal_awaiting_projection():
    history = InMemoryHistoryStore()
    runtime = instance(activity=True, history=history)
    scope = runtime.open_scope("draft")
    runtime.deliver(SOURCE, Token("Value", 7), identity="draft-7", scope=scope)
    occurrence = runtime.begin(runtime.candidates()[0])
    runtime.record_activity_completion(occurrence, {"answer": 8})
    malformed = InMemoryHistoryStore()
    malformed.extend(list(history.records))
    malformed.append(ScopeClosed(scope, cancelled=(occurrence.id,)))

    with pytest.raises(ValueError, match="accepted Activity terminal.*awaiting deterministic projection"):
        Instance.resume(scoped_net(activity=True), malformed, handlers={"work": Work()})


def test_replay_refuses_a_normal_terminal_boundary_after_lifecycle_cancellation():
    history = InMemoryHistoryStore()
    runtime = instance(activity=True, history=history)
    scope = runtime.open_scope("draft")
    runtime.deliver(SOURCE, Token("Value", 7), identity="draft-7", scope=scope)
    occurrence = runtime.begin(runtime.candidates()[0])
    runtime.close_scope(scope)
    malformed = InMemoryHistoryStore()
    malformed.extend(list(history.records))
    malformed.append(FiringFailed(WORK, "late", occurrence=occurrence.id))

    with pytest.raises(ValueError, match="FiringFailed after lifecycle cancellation"):
        Instance.resume(scoped_net(activity=True), malformed, handlers={"work": Work()})


def test_replay_refuses_inconsistent_same_occurrence_scope_provenance():
    history = InMemoryHistoryStore()
    runtime = instance(activity=True, history=history)
    first = runtime.open_scope("first")
    second = runtime.open_scope("second")
    runtime.deliver(SOURCE, Token("Value", 7), identity="first-7", scope=first)
    runtime.begin(runtime.candidates()[0])
    malformed = InMemoryHistoryStore()
    malformed.extend(
        [replace(record, scope=second) if isinstance(record, ActivityRequested) else record for record in history]
    )

    with pytest.raises(ValueError, match="scope provenance inconsistent"):
        Instance.resume(scoped_net(activity=True), malformed, handlers={"work": Work()})
