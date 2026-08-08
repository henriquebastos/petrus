from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path

import pytest

from petrus.agenticus.hands.contract import RejectionCategory
from petrus.agenticus.program.agent_net import (
    AGENT_AS_NET,
    AGENT_AS_NET_CONTINUATION_CAPABILITIES,
    AGENT_AS_NET_CONTINUATION_DESCRIPTOR,
    AGENT_AS_NET_PROGRAM,
    AGENT_AS_NET_PROGRAM_CAPABILITIES,
    DONE,
    HANDS_ACTIVITY,
    MAX_JSON_BYTES,
    MAX_PHASES,
    MAX_PROPOSALS,
    MAX_TOOLS,
    MODEL_PHASE_ACTIVITY,
    LoopState,
    ModelResult,
    ModelSettlement,
    Proposal,
    StopReason,
    agent_net_guards,
    agent_net_handlers,
    initial_marking,
)
from petrus.agenticus.program.descriptor import ProgramOwnership
from petrus.engine import Engine
from petrus.impetus.history import ActivityCompleted, ActivityRequested
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath
from petrus.impetus.instance import Status
from petrus.motus.dispatch import InlineDispatch

DIGEST = "a" * 64
ERROR_CATEGORIES = (
    "capability",
    "path",
    "argv",
    "write",
    "unknown",
    "deadline",
    "aborted",
    "stale_epoch",
    "post_fence",
    "provider",
    "schema",
    "authority",
    "budget",
)


def state(
    *,
    phase: int = 1,
    phases: int = 3,
    tool_count: int = 0,
    tools: int = 4,
    output_ref: str | None = None,
    continuation_ref: str | None = None,
    capabilities: tuple[str, ...] = ("workspace_read",),
    results: tuple[ModelResult, ...] = (),
) -> LoopState:
    return LoopState(
        "episode-1",
        "turn-1",
        phase,
        phases,
        tool_count,
        tools,
        output_ref,
        continuation_ref,
        7,
        capabilities,
        results,
    )


def proposal(identity: str, method: str = "workspace_read") -> Proposal:
    return Proposal(identity, method, {"path": f"{identity}.txt"})


def run(script, hands=(), *, initial: LoopState | None = None):
    model_script = iter(script)
    hands_script = iter(hands)
    calls: list[tuple[object, ...]] = []

    def model(invocation, *, context):
        del context
        current = LoopState.from_data(invocation.input)
        stop, proposals = next(model_script)
        calls.append(
            (
                "model",
                current.phase,
                [item.id for item in proposals],
                [item.to_model_data() for item in current.results],
            )
        )
        return ModelSettlement(
            current, stop, DIGEST, f"output-{current.phase}", f"continuation-{current.phase}", proposals
        ).to_data()

    def tool(invocation, *, context):
        del context
        item = invocation.input["proposal"]
        calls.append(("hands", item["id"], item["method"]))
        category, ok = next(hands_script)
        result = ModelResult(
            item["id"],
            ok,
            {"value": item["id"]} if ok else None,
            None if ok else {"category": category, "detail": "safe failure"},
        )
        return {"version": 1, "result": result.to_data()}

    history = InMemoryHistoryStore()
    engine = Engine.create(
        AGENT_AS_NET,
        "scripted-agent",
        history=history,
        dispatch=InlineDispatch({MODEL_PHASE_ACTIVITY: model, HANDS_ACTIVITY: tool}),
        marking=initial_marking(initial or state()),
        handlers=agent_net_handlers(),
        guards=agent_net_guards(),
    )
    quiescent = []
    while True:
        outcome = engine.advance()
        if not engine.in_flight and (not quiescent or len(engine.records) != len(quiescent[-1][0])):
            quiescent.append((engine.records, engine.marking, engine.status))
        if not outcome.ready:
            break
    return engine, history, calls, quiescent


def terminal(engine) -> dict[str, object]:
    (token,) = engine.marking.place(DONE)
    return token.data


def test_exact_descriptors_capabilities_and_serializable_envelopes():
    assert AGENT_AS_NET_PROGRAM.ownership is ProgramOwnership.NET
    assert AGENT_AS_NET_PROGRAM.accepts_fresh_start is True
    assert AGENT_AS_NET_PROGRAM.owns_steering is False
    assert AGENT_AS_NET_PROGRAM.owns_evaluation is False
    assert AGENT_AS_NET_PROGRAM.accepted_continuations == (AGENT_AS_NET_PROGRAM.accepted_continuations[0],)
    assert AGENT_AS_NET_PROGRAM.accepted_continuations[0].identity == AGENT_AS_NET_CONTINUATION_DESCRIPTOR.identity
    assert AGENT_AS_NET_PROGRAM.produced_continuation == AGENT_AS_NET_CONTINUATION_DESCRIPTOR.identity
    assert AGENT_AS_NET_PROGRAM_CAPABILITIES.offers == frozenset({"program.net-owned"})
    assert AGENT_AS_NET_CONTINUATION_CAPABILITIES.offers == frozenset({"continuation.net-owned"})
    value = state()
    assert value.output_ref is None
    assert value.continuation_ref is None
    assert LoopState.from_data(json.loads(json.dumps(value.to_data()))) == value
    item = proposal("call-1")
    assert Proposal.from_data(json.loads(json.dumps(item.to_data()))) == item


def test_fresh_and_resumed_state_reference_contracts():
    assert state().output_ref is None
    resumed = state(output_ref="output-prior", continuation_ref="continuation-prior")
    assert LoopState.from_data(resumed.to_data()) == resumed
    with pytest.raises(ValueError, match="both be absent or both be present"):
        state(output_ref="output-only")
    with pytest.raises(ValueError, match="both be absent or both be present"):
        state(continuation_ref="continuation-only")


def test_exact_topology_activity_separation_and_done_token_completion():
    assert set(AGENT_AS_NET.places) == {
        NetPath(name) for name in ("model_pending", "model_settled", "tool_pending", "tool_settled", "done")
    }
    assert set(AGENT_AS_NET.transitions) == {
        NetPath(name) for name in ("model_phase", "classify_model", "execute_tool", "reject_tool", "record_result")
    }
    engine, _, calls, _ = run([(StopReason.STOP, ())])
    assert engine.marking == Marking({DONE: engine.marking.place(DONE)})
    assert engine.status is Status.COMPLETED
    assert calls == [("model", 1, [], [])]
    assert [record.activity for record in engine.records if isinstance(record, ActivityRequested)] == [
        MODEL_PHASE_ACTIVITY
    ]
    assert terminal(engine) == {
        "version": 1,
        "episode_id": "episode-1",
        "turn_id": "turn-1",
        "code": "completed",
        "phases": 1,
        "tools": 0,
        "output_ref": "output-1",
        "continuation_ref": "continuation-1",
    }


def test_multi_tool_batch_is_sequential_and_one_activity_per_actual_call():
    engine, _, calls, _ = run(
        [(StopReason.TOOL_USE, (proposal("one"), proposal("two"))), (StopReason.STOP, ())],
        [("ok", True), ("ok", True)],
    )
    assert calls == [
        ("model", 1, ["one", "two"], []),
        ("hands", "one", "workspace_read"),
        ("hands", "two", "workspace_read"),
        (
            "model",
            2,
            [],
            [
                {"version": 1, "ok": True, "data": {"value": "one"}, "error": None},
                {"version": 1, "ok": True, "data": {"value": "two"}, "error": None},
            ],
        ),
    ]
    activities = [record.activity for record in engine.records if isinstance(record, ActivityRequested)]
    assert activities == [MODEL_PHASE_ACTIVITY, HANDS_ACTIVITY, HANDS_ACTIVITY, MODEL_PHASE_ACTIVITY]
    assert terminal(engine)["code"] == "completed"


def test_unsupported_and_not_granted_are_pure_ordered_rejections():
    engine, _, calls, _ = run(
        [
            (StopReason.TOOL_USE, (proposal("unknown", "not_a_tool"), proposal("blocked", "workspace_write"))),
            (StopReason.STOP, ()),
        ],
    )
    assert calls == [
        ("model", 1, ["unknown", "blocked"], []),
        (
            "model",
            2,
            [],
            [
                {
                    "version": 1,
                    "ok": False,
                    "data": None,
                    "error": {"category": "capability", "detail": "tool is unsupported or not granted"},
                },
                {
                    "version": 1,
                    "ok": False,
                    "data": None,
                    "error": {"category": "capability", "detail": "tool is unsupported or not granted"},
                },
            ],
        ),
    ]
    assert Counter(record.activity for record in engine.records if isinstance(record, ActivityRequested)) == Counter(
        {MODEL_PHASE_ACTIVITY: 2}
    )


def test_length_rejects_whole_batch_without_hands_and_returns_ordered_results():
    engine, _, calls, _ = run(
        [(StopReason.LENGTH, (proposal("one"), proposal("two"))), (StopReason.STOP, ())],
    )
    assert calls == [
        ("model", 1, ["one", "two"], []),
        (
            "model",
            2,
            [],
            [
                {
                    "version": 1,
                    "ok": False,
                    "data": None,
                    "error": {"category": "provider", "detail": "proposal rejected after length stop"},
                },
                {
                    "version": 1,
                    "ok": False,
                    "data": None,
                    "error": {"category": "provider", "detail": "proposal rejected after length stop"},
                },
            ],
        ),
    ]
    assert not [
        record
        for record in engine.records
        if isinstance(record, ActivityRequested) and record.activity == HANDS_ACTIVITY
    ]
    assert terminal(engine)["code"] == "completed"


def test_length_without_proposals_is_a_completed_provider_phase():
    engine, _, calls, _ = run([(StopReason.LENGTH, ())])
    assert calls == [("model", 1, [], [])]
    assert terminal(engine)["code"] == "completed"


def test_proposals_are_discovered_from_content_not_the_stop_reason():
    engine, _, calls, _ = run(
        [(StopReason.STOP, (proposal("one"),)), (StopReason.STOP, ())],
        [("ok", True)],
    )
    assert [call[0] for call in calls] == ["model", "hands", "model"]
    assert terminal(engine)["code"] == "completed"


@pytest.mark.parametrize("stop,code", [(StopReason.ERROR, "failed"), (StopReason.ABORTED, "cancelled")])
def test_provider_terminal_routes(stop, code):
    engine, _, calls, _ = run([(stop, (proposal("ignored"),))])
    assert calls == [("model", 1, ["ignored"], [])]
    assert terminal(engine)["code"] == code


def test_hands_abort_cancels_after_current_call():
    engine, _, calls, _ = run(
        [(StopReason.TOOL_USE, (proposal("one"), proposal("two")))],
        [("aborted", False)],
    )
    assert calls == [("model", 1, ["one", "two"], []), ("hands", "one", "workspace_read")]
    assert terminal(engine)["code"] == "cancelled"
    assert terminal(engine)["tools"] == 1


def test_phase_and_tool_budget_terminals():
    phase, _, _, _ = run([(StopReason.LENGTH, (proposal("one"),))], initial=state(phases=1))
    tool, _, calls, _ = run([(StopReason.TOOL_USE, (proposal("one"),))], initial=state(tools=0))
    assert terminal(phase)["code"] == "phase-budget-exhausted"
    assert terminal(tool)["code"] == "tool-budget-exhausted"
    assert calls == [("model", 1, ["one"], [])]


def test_mid_batch_tool_budget_stops_before_a_second_hands_dispatch():
    engine, _, calls, _ = run(
        [(StopReason.TOOL_USE, (proposal("one"), proposal("two")))],
        [("ok", True)],
        initial=state(tools=1),
    )
    assert calls == [
        ("model", 1, ["one", "two"], []),
        ("hands", "one", "workspace_read"),
    ]
    assert terminal(engine)["code"] == "tool-budget-exhausted"
    assert terminal(engine)["tools"] == 1


def test_blocked_then_allowed_batch_preserves_result_order():
    _, _, calls, _ = run(
        [
            (StopReason.TOOL_USE, (proposal("blocked", "workspace_write"), proposal("allowed"))),
            (StopReason.STOP, ()),
        ],
        [("ok", True)],
    )
    assert calls[1] == ("hands", "allowed", "workspace_read")
    assert [result["ok"] for result in calls[2][3]] == [False, True]
    assert [result["error"]["category"] if result["error"] else None for result in calls[2][3]] == [
        "capability",
        None,
    ]


def test_failed_hands_result_is_model_data_and_not_an_escaped_failure():
    engine, _, calls, _ = run(
        [(StopReason.TOOL_USE, (proposal("one"),)), (StopReason.STOP, ())],
        [("path", False)],
    )
    assert calls == [
        ("model", 1, ["one"], []),
        ("hands", "one", "workspace_read"),
        (
            "model",
            2,
            [],
            [
                {
                    "version": 1,
                    "ok": False,
                    "data": None,
                    "error": {"category": "path", "detail": "safe failure"},
                }
            ],
        ),
    ]
    assert terminal(engine)["code"] == "completed"


def test_results_are_supplied_to_exactly_one_following_model_phase():
    _, _, calls, _ = run(
        [
            (StopReason.TOOL_USE, (proposal("one"),)),
            (StopReason.TOOL_USE, (proposal("two"),)),
            (StopReason.STOP, ()),
        ],
        [("ok", True), ("ok", True)],
    )
    model_calls = [call for call in calls if call[0] == "model"]
    assert [[result["data"]["value"] for result in call[3]] for call in model_calls] == [[], ["one"], ["two"]]


@pytest.mark.parametrize("category", ERROR_CATEGORIES)
def test_model_result_projection_has_exact_shape_and_known_error_categories(category):
    result = ModelResult("call", False, None, {"category": category, "detail": "bounded"})
    assert result.to_model_data() == {
        "version": 1,
        "ok": False,
        "data": None,
        "error": {"category": category, "detail": "bounded"},
    }
    assert ModelResult.from_data(result.to_data()) == result


def test_model_result_error_vocabulary_is_the_hands_contract():
    assert set(ERROR_CATEGORIES) == {category.value for category in RejectionCategory}
    with pytest.raises(ValueError, match="category is unsupported"):
        ModelResult("call", False, None, {"category": "new-unruled-error", "detail": "bounded"})


def test_payloads_and_all_loop_dimensions_are_bounded():
    with pytest.raises(ValueError, match="4096-byte bound"):
        Proposal("large", "workspace_write", {"content": "x" * MAX_JSON_BYTES})
    with pytest.raises(ValueError, match="128-byte bound"):
        ModelResult("failed", False, None, {"category": "unknown", "detail": "x" * 129})
    with pytest.raises(ValueError, match="bounded batch"):
        ModelSettlement(
            state(),
            StopReason.TOOL_USE,
            DIGEST,
            "output",
            "continuation",
            tuple(proposal(f"call-{index}") for index in range(MAX_PROPOSALS + 1)),
        )
    with pytest.raises(ValueError, match="unique"):
        ModelSettlement(
            state(),
            StopReason.TOOL_USE,
            DIGEST,
            "output",
            "continuation",
            (proposal("duplicate"), proposal("duplicate")),
        )
    with pytest.raises(ValueError, match="phase ordinal"):
        state(phases=MAX_PHASES + 1)
    with pytest.raises(ValueError, match="tool count"):
        state(tools=MAX_TOOLS + 1)
    with pytest.raises(ValueError, match="phase ordinal"):
        state(phase=True)  # type: ignore[arg-type]


def test_history_has_model_and_hands_facts_without_custody_data():
    engine, _, _, _ = run(
        [(StopReason.TOOL_USE, (proposal("one"),)), (StopReason.STOP, ())],
        [("ok", True)],
    )
    requested = [record.activity for record in engine.records if isinstance(record, ActivityRequested)]
    completed = [record for record in engine.records if isinstance(record, ActivityCompleted)]
    encoded = json.dumps([repr(record) for record in engine.records]).lower()
    assert requested == [MODEL_PHASE_ACTIVITY, HANDS_ACTIVITY, MODEL_PHASE_ACTIVITY]
    assert len(completed) == 3
    assert all(
        value not in encoded
        for value in (
            "transcript-bytes",
            "credential",
            "api_key",
            "attachment_id",
            "attachment_epoch",
            "territory_id",
            "raw_provider",
            "diagnostics",
        )
    )


def test_reconstruction_matches_every_committed_quiescent_prefix():
    engine, history, _, quiescent = run(
        [(StopReason.TOOL_USE, (proposal("one"),)), (StopReason.STOP, ())],
        [("ok", True)],
    )
    assert history.records == engine.records
    assert len(quiescent) > 2
    for prefix, expected_marking, expected_status in quiescent:
        prefix_history = InMemoryHistoryStore()
        prefix_history.extend(list(prefix))
        resumed = Engine.load(
            AGENT_AS_NET,
            "scripted-agent",
            history=prefix_history,
            dispatch=InlineDispatch({}),
            handlers=agent_net_handlers(),
            guards=agent_net_guards(),
        )
        assert resumed.in_flight == ()
        assert resumed.marking == expected_marking
        assert resumed.status == expected_status
        resumed.close()


def test_static_net_module_has_no_provider_or_runtime_dependency():
    source = Path("src/petrus/agenticus/program/agent_net.py").read_text()
    imported = {
        alias.name for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Import) for alias in node.names
    }
    imported.update(
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    assert not {
        name
        for name in imported
        if name.startswith(("anthropic", "openai", "@earendil-works", "petrus.agenticus.runtime"))
    }
