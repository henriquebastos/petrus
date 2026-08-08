"""Provider-free static Net which owns the bounded Pi-style agent loop."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorIdentity, DescriptorKind
from petrus.agenticus.hands.contract import RejectionCategory
from petrus.agenticus.program.descriptor import AgentProgramDescriptor, ContinuationRequirement, ProgramOwnership
from petrus.agenticus.thread.continuation import ContinuationDescriptor
from petrus.impetus.binding import ActivityHandler
from petrus.impetus.dsl import NetSpec, arc, petri_guard, petri_handler
from petrus.impetus.petrinet import Arc, Binding, Cel, Marking, Net, NetPath, Token
from petrus.motus.activity import ActivityInvocation

VERSION = 1
MAX_PROPOSALS = 16
MAX_PHASES = 16
MAX_TOOLS = 64
MAX_JSON_BYTES = 4096
_DIGEST = re.compile(r"[0-9a-f]{64}")
_TEXT_LIMIT = 256
_ERROR_DETAIL_LIMIT = 128
_ERROR_CATEGORIES = frozenset(category.value for category in RejectionCategory)

MODEL_PENDING = NetPath("model_pending")
MODEL_SETTLED = NetPath("model_settled")
TOOL_PENDING = NetPath("tool_pending")
TOOL_SETTLED = NetPath("tool_settled")
DONE = NetPath("done")
MODEL_PHASE = NetPath("model_phase")
CLASSIFY_MODEL = NetPath("classify_model")
EXECUTE_TOOL = NetPath("execute_tool")
REJECT_TOOL = NetPath("reject_tool")
RECORD_RESULT = NetPath("record_result")

MODEL_PHASE_ACTIVITY = "agenticus.net.model-phase"
HANDS_ACTIVITY = "agenticus.net.hands"

_PROGRAM_ID = DescriptorIdentity(DescriptorKind.PROGRAM, "agenticus.net-owned", VERSION)
_CONTINUATION_ID = DescriptorIdentity(DescriptorKind.CONTINUATION, "agenticus.net-owned", VERSION)
AGENT_AS_NET_CONTINUATION_DESCRIPTOR = ContinuationDescriptor(_CONTINUATION_ID, _PROGRAM_ID)
AGENT_AS_NET_PROGRAM = AgentProgramDescriptor(
    identity=_PROGRAM_ID,
    ownership=ProgramOwnership.NET,
    accepted_continuations=(ContinuationRequirement(_CONTINUATION_ID, _PROGRAM_ID),),
    produced_continuation=_CONTINUATION_ID,
)
AGENT_AS_NET_PROGRAM_CAPABILITIES = CapabilityDescriptor(_PROGRAM_ID, frozenset({"program.net-owned"}))
AGENT_AS_NET_CONTINUATION_CAPABILITIES = CapabilityDescriptor(_CONTINUATION_ID, frozenset({"continuation.net-owned"}))


class StopReason(StrEnum):
    STOP = "stop"
    TOOL_USE = "toolUse"
    LENGTH = "length"
    ERROR = "error"
    ABORTED = "aborted"


class TerminalCode(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PHASE_BUDGET = "phase-budget-exhausted"
    TOOL_BUDGET = "tool-budget-exhausted"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value.encode()) > _TEXT_LIMIT:
        raise ValueError(f"{name} must be bounded non-empty text")
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"{name} must not contain control characters")
    return value


def _json(value: object, name: str) -> object:
    try:
        encoded = json.dumps(value, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be JSON-faithful: {error}") from None
    if len(encoded.encode()) > MAX_JSON_BYTES:
        raise ValueError(f"{name} exceeds the {MAX_JSON_BYTES}-byte bound")
    return json.loads(encoded)


def _exact(data: object, fields: set[str], name: str) -> Any:
    if not isinstance(data, dict) or set(data) != fields or any(type(key) is not str for key in data):
        raise ValueError(f"{name} requires exact fields {sorted(fields)}")
    if data.get("version") != VERSION or type(data.get("version")) is not int:
        raise ValueError(f"{name} version must be integer {VERSION}")
    return data


@dataclass(frozen=True)
class Proposal:
    id: str
    method: str
    params: dict[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "proposal id"))
        object.__setattr__(self, "method", _text(self.method, "proposal method"))
        params = _json(self.params, "proposal params")
        if not isinstance(params, dict):
            raise ValueError("proposal params must be an object")
        object.__setattr__(self, "params", params)

    def to_data(self) -> dict[str, object]:
        return {"version": VERSION, "id": self.id, "method": self.method, "params": self.params}

    @classmethod
    def from_data(cls, data: object) -> Proposal:
        value = _exact(data, {"version", "id", "method", "params"}, "proposal")
        return cls(value["id"], value["method"], value["params"])  # type: ignore[arg-type]


@dataclass(frozen=True)
class ModelResult:
    id: str
    ok: bool
    data: object
    error: dict[str, object] | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "result id"))
        if type(self.ok) is not bool or self.ok != (self.error is None):
            raise ValueError("model result carries exactly an error when not ok")
        data = _json(self.data, "model result data")
        error = _json(self.error, "model result error")
        if self.ok:
            if not isinstance(data, dict) or error is not None:
                raise ValueError("successful model result requires object data and null error")
        elif data is not None or not isinstance(error, dict) or set(error) != {"category", "detail"}:
            raise ValueError("failed model result requires null data and an exact category/detail error")
        elif error.get("category") not in _ERROR_CATEGORIES:
            raise ValueError("model result error category is unsupported")
        else:
            detail = _text(error.get("detail"), "model result error detail")
            if len(detail.encode()) > _ERROR_DETAIL_LIMIT:
                raise ValueError(f"model result error detail exceeds the {_ERROR_DETAIL_LIMIT}-byte bound")
        object.__setattr__(self, "data", data)
        object.__setattr__(self, "error", error)

    def to_data(self) -> dict[str, object]:
        return {"version": VERSION, "id": self.id, "result": self.to_model_data()}

    def to_model_data(self) -> dict[str, object]:
        """Return the exact model-visible Agenticus result projection."""

        return {"version": VERSION, "ok": self.ok, "data": self.data, "error": self.error}

    @classmethod
    def from_data(cls, data: object) -> ModelResult:
        value = _exact(data, {"version", "id", "result"}, "model result")
        return cls.from_model_data(value["id"], value["result"])

    @classmethod
    def from_model_data(cls, identity: object, data: object) -> ModelResult:
        value = _exact(data, {"version", "ok", "data", "error"}, "model result projection")
        return cls(_text(identity, "result id"), value["ok"], value["data"], value["error"])


@dataclass(frozen=True)
class LoopState:
    episode_id: str
    turn_id: str
    phase: int
    phase_limit: int
    tool_count: int
    tool_limit: int
    output_ref: str | None
    continuation_ref: str | None
    grant_epoch: int
    capabilities: tuple[str, ...]
    results: tuple[ModelResult, ...] = ()

    def __post_init__(self) -> None:
        for field in ("episode_id", "turn_id"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        for field in ("output_ref", "continuation_ref"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _text(value, field))
        if (self.output_ref is None) != (self.continuation_ref is None):
            raise ValueError("output_ref and continuation_ref must both be absent or both be present")
        if (
            type(self.phase) is not int
            or type(self.phase_limit) is not int
            or not (1 <= self.phase <= self.phase_limit <= MAX_PHASES)
        ):
            raise ValueError("phase ordinal and bound are invalid")
        if (
            type(self.tool_count) is not int
            or type(self.tool_limit) is not int
            or not (0 <= self.tool_count <= self.tool_limit <= MAX_TOOLS)
        ):
            raise ValueError("tool count and bound are invalid")
        if type(self.grant_epoch) is not int or self.grant_epoch <= 0:
            raise ValueError("grant_epoch must be positive")
        capabilities = tuple(sorted({_text(item, "capability") for item in self.capabilities}))
        object.__setattr__(self, "capabilities", capabilities)
        if any(not isinstance(item, ModelResult) for item in self.results):
            raise TypeError("results must contain ModelResult values")
        if len(self.results) > MAX_PROPOSALS or len({item.id for item in self.results}) != len(self.results):
            raise ValueError("results must be one bounded unique-identity model batch")

    def to_data(self) -> dict[str, object]:
        data = asdict(self)
        data["version"] = VERSION
        data["capabilities"] = list(self.capabilities)
        data["results"] = [item.to_data() for item in self.results]
        return data

    @classmethod
    def from_data(cls, data: object) -> LoopState:
        fields = {
            "version",
            "episode_id",
            "turn_id",
            "phase",
            "phase_limit",
            "tool_count",
            "tool_limit",
            "output_ref",
            "continuation_ref",
            "grant_epoch",
            "capabilities",
            "results",
        }
        value = _exact(data, fields, "loop state")
        if not isinstance(value["capabilities"], list) or not isinstance(value["results"], list):
            raise ValueError("loop state capabilities and results must be arrays")
        return cls(
            episode_id=value["episode_id"],
            turn_id=value["turn_id"],
            phase=value["phase"],
            phase_limit=value["phase_limit"],
            tool_count=value["tool_count"],
            tool_limit=value["tool_limit"],
            output_ref=value["output_ref"],
            continuation_ref=value["continuation_ref"],
            grant_epoch=value["grant_epoch"],
            capabilities=tuple(value["capabilities"]),
            results=tuple(ModelResult.from_data(item) for item in value["results"]),
        )  # type: ignore[arg-type]


@dataclass(frozen=True)
class ModelSettlement:
    state: LoopState
    stop: StopReason
    assistant_digest: str
    output_ref: str
    continuation_ref: str
    proposals: tuple[Proposal, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.state, LoopState) or not isinstance(self.stop, StopReason):
            raise TypeError("model settlement requires LoopState and StopReason")
        if not isinstance(self.assistant_digest, str) or _DIGEST.fullmatch(self.assistant_digest) is None:
            raise ValueError("assistant_digest must be a lowercase sha256 digest")
        object.__setattr__(self, "output_ref", _text(self.output_ref, "output_ref"))
        object.__setattr__(self, "continuation_ref", _text(self.continuation_ref, "continuation_ref"))
        if len(self.proposals) > MAX_PROPOSALS or any(not isinstance(item, Proposal) for item in self.proposals):
            raise ValueError("proposals exceed the bounded batch")
        if len({item.id for item in self.proposals}) != len(self.proposals):
            raise ValueError("proposal identities must be unique within one model phase")

    def to_data(self) -> dict[str, object]:
        return {
            "version": VERSION,
            "state": self.state.to_data(),
            "stop": self.stop.value,
            "assistant_digest": self.assistant_digest,
            "output_ref": self.output_ref,
            "continuation_ref": self.continuation_ref,
            "proposals": [item.to_data() for item in self.proposals],
        }

    @classmethod
    def from_data(cls, data: object) -> ModelSettlement:
        value = _exact(
            data,
            {"version", "state", "stop", "assistant_digest", "output_ref", "continuation_ref", "proposals"},
            "model settlement",
        )
        if not isinstance(value["proposals"], list):
            raise ValueError("model settlement proposals must be an array")
        return cls(
            LoopState.from_data(value["state"]),
            StopReason(value["stop"]),
            value["assistant_digest"],
            value["output_ref"],
            value["continuation_ref"],
            tuple(Proposal.from_data(item) for item in value["proposals"]),
        )  # type: ignore[arg-type]


@dataclass(frozen=True)
class ToolWork:
    state: LoopState
    assistant_digest: str
    proposals: tuple[Proposal, ...]
    index: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.state, LoopState)
            or not self.proposals
            or any(not isinstance(item, Proposal) for item in self.proposals)
            or not (0 <= self.index < len(self.proposals))
        ):
            raise ValueError("tool work requires a valid non-empty batch position")
        if len(self.proposals) > MAX_PROPOSALS or len({item.id for item in self.proposals}) != len(self.proposals):
            raise ValueError("tool work requires one bounded unique-identity proposal batch")
        if _DIGEST.fullmatch(self.assistant_digest) is None:
            raise ValueError("assistant_digest must be a lowercase sha256 digest")
        if tuple(item.id for item in self.state.results) != tuple(item.id for item in self.proposals[: self.index]):
            raise ValueError("tool work state must contain exactly the preceding ordered results")

    @property
    def proposal(self) -> Proposal:
        return self.proposals[self.index]

    def to_data(self) -> dict[str, object]:
        return {
            "version": VERSION,
            "state": self.state.to_data(),
            "assistant_digest": self.assistant_digest,
            "proposals": [item.to_data() for item in self.proposals],
            "index": self.index,
        }

    @classmethod
    def from_data(cls, data: object) -> ToolWork:
        value = _exact(data, {"version", "state", "assistant_digest", "proposals", "index"}, "tool work")
        if not isinstance(value["proposals"], list):
            raise ValueError("tool work proposals must be an array")
        return cls(
            LoopState.from_data(value["state"]),
            value["assistant_digest"],
            tuple(Proposal.from_data(item) for item in value["proposals"]),
            value["index"],
        )  # type: ignore[arg-type]


@dataclass(frozen=True)
class HandsSettlement:
    work: ToolWork
    result: ModelResult

    def __post_init__(self) -> None:
        if not isinstance(self.work, ToolWork) or not isinstance(self.result, ModelResult):
            raise TypeError("Hands settlement requires ToolWork and ModelResult")
        if self.result.id != self.work.proposal.id:
            raise ValueError("Hands result id must match the proposal")

    def to_data(self) -> dict[str, object]:
        return {
            "version": VERSION,
            "work": self.work.to_data(),
            "result": self.result.to_data(),
        }

    @classmethod
    def from_data(cls, data: object) -> HandsSettlement:
        value = _exact(data, {"version", "work", "result"}, "Hands settlement")
        return cls(ToolWork.from_data(value["work"]), ModelResult.from_data(value["result"]))


@dataclass(frozen=True)
class Terminal:
    episode_id: str
    turn_id: str
    code: TerminalCode
    phases: int
    tools: int
    output_ref: str
    continuation_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "episode_id", _text(self.episode_id, "terminal episode_id"))
        object.__setattr__(self, "turn_id", _text(self.turn_id, "terminal turn_id"))
        if not isinstance(self.code, TerminalCode):
            raise TypeError("terminal code must be TerminalCode")
        if type(self.phases) is not int or not 1 <= self.phases <= MAX_PHASES:
            raise ValueError("terminal phases must be a bounded positive integer")
        if type(self.tools) is not int or not 0 <= self.tools <= MAX_TOOLS:
            raise ValueError("terminal tools must be a bounded nonnegative integer")
        object.__setattr__(self, "output_ref", _text(self.output_ref, "terminal output_ref"))
        object.__setattr__(self, "continuation_ref", _text(self.continuation_ref, "terminal continuation_ref"))

    def to_data(self) -> dict[str, object]:
        return {
            "version": VERSION,
            "episode_id": self.episode_id,
            "turn_id": self.turn_id,
            "code": self.code.value,
            "phases": self.phases,
            "tools": self.tools,
            "output_ref": self.output_ref,
            "continuation_ref": self.continuation_ref,
        }

    @classmethod
    def from_data(cls, data: object) -> Terminal:
        value = _exact(
            data,
            {
                "version",
                "episode_id",
                "turn_id",
                "code",
                "phases",
                "tools",
                "output_ref",
                "continuation_ref",
            },
            "terminal",
        )
        return cls(
            value["episode_id"],
            value["turn_id"],
            TerminalCode(value["code"]),
            value["phases"],
            value["tools"],
            value["output_ref"],
            value["continuation_ref"],
        )  # type: ignore[arg-type]


def initial_marking(state: LoopState) -> Marking:
    return Marking({MODEL_PENDING: (Token("LoopState", state.to_data()),)})


def _terminal(state: LoopState, code: TerminalCode) -> Token:
    if state.output_ref is None or state.continuation_ref is None:
        raise ValueError("terminal state requires settled output and Continuation references")
    return Token(
        "Terminal",
        Terminal(
            state.episode_id,
            state.turn_id,
            code,
            state.phase,
            state.tool_count,
            state.output_ref,
            state.continuation_ref,
        ).to_data(),
    )


class _ModelActivity(ActivityHandler):
    def prepare(self, binding: Binding) -> ActivityInvocation:
        (token,) = binding.tokens
        LoopState.from_data(token.data)
        return ActivityInvocation(MODEL_PHASE_ACTIVITY, input=token.data)

    def project(self, binding: Binding, result: object) -> Mapping[NetPath | str, Sequence[Token]]:
        (token,) = binding.tokens
        expected = LoopState.from_data(token.data)
        settled = ModelSettlement.from_data(result)
        if settled.state != expected:
            raise ValueError("model activity result does not match its recorded loop state")
        return {MODEL_SETTLED: (Token("ModelSettlement", settled.to_data()),)}


class _HandsActivity(ActivityHandler):
    def prepare(self, binding: Binding) -> ActivityInvocation:
        (token,) = binding.tokens
        work = ToolWork.from_data(token.data)
        proposal = work.proposal
        return ActivityInvocation(
            HANDS_ACTIVITY,
            input={"version": VERSION, "proposal": proposal.to_data(), "grant_epoch": work.state.grant_epoch},
        )

    def project(self, binding: Binding, result: object) -> Mapping[NetPath | str, Sequence[Token]]:
        (token,) = binding.tokens
        work = ToolWork.from_data(token.data)
        value = _exact(result, {"version", "result"}, "Hands activity result")
        settled = HandsSettlement(work, ModelResult.from_data(value["result"]))
        return {TOOL_SETTLED: (Token("HandsSettlement", settled.to_data()),)}


def _allowed(work: ToolWork) -> bool:
    return work.proposal.method in work.state.capabilities and work.state.tool_count < work.state.tool_limit


def _execute(binding: Binding) -> bool:
    return _allowed(ToolWork.from_data(binding.tokens[0].data))


def _reject(binding: Binding) -> bool:
    return not _allowed(ToolWork.from_data(binding.tokens[0].data))


def _next(state: LoopState, result: ModelResult, *, increment_tool: bool) -> LoopState:
    return LoopState(
        state.episode_id,
        state.turn_id,
        state.phase,
        state.phase_limit,
        state.tool_count + int(increment_tool),
        state.tool_limit,
        state.output_ref,
        state.continuation_ref,
        state.grant_epoch,
        state.capabilities,
        state.results + (result,),
    )


def _continue(outputs: dict[NetPath, tuple[Token, ...]], work: ToolWork, state: LoopState) -> None:
    if work.index + 1 < len(work.proposals):
        following = ToolWork(state, work.assistant_digest, work.proposals, work.index + 1)
        outputs[TOOL_PENDING] = (Token("ToolWork", following.to_data()),)
    elif state.phase >= state.phase_limit:
        outputs[DONE] = (_terminal(state, TerminalCode.PHASE_BUDGET),)
    else:
        next_state = LoopState(
            state.episode_id,
            state.turn_id,
            state.phase + 1,
            state.phase_limit,
            state.tool_count,
            state.tool_limit,
            state.output_ref,
            state.continuation_ref,
            state.grant_epoch,
            state.capabilities,
            state.results,
        )
        outputs[MODEL_PENDING] = (Token("LoopState", next_state.to_data()),)


def _classify(binding: Binding, arcs: tuple[Arc, ...]):
    del arcs
    settled = ModelSettlement.from_data(binding.tokens[0].data)
    state = LoopState(
        settled.state.episode_id,
        settled.state.turn_id,
        settled.state.phase,
        settled.state.phase_limit,
        settled.state.tool_count,
        settled.state.tool_limit,
        settled.output_ref,
        settled.continuation_ref,
        settled.state.grant_epoch,
        settled.state.capabilities,
        (),
    )
    if settled.stop is StopReason.ERROR:
        return {DONE: (_terminal(state, TerminalCode.FAILED),)}
    if settled.stop is StopReason.ABORTED:
        return {DONE: (_terminal(state, TerminalCode.CANCELLED),)}
    if not settled.proposals:
        return {DONE: (_terminal(state, TerminalCode.COMPLETED),)}
    if settled.stop is StopReason.LENGTH:
        results = tuple(
            ModelResult(
                item.id,
                False,
                None,
                {"category": "provider", "detail": "proposal rejected after length stop"},
            )
            for item in settled.proposals
        )
        state = LoopState(
            state.episode_id,
            state.turn_id,
            state.phase,
            state.phase_limit,
            state.tool_count,
            state.tool_limit,
            state.output_ref,
            state.continuation_ref,
            state.grant_epoch,
            state.capabilities,
            state.results + results,
        )
        if state.phase >= state.phase_limit:
            return {DONE: (_terminal(state, TerminalCode.PHASE_BUDGET),)}
        state = LoopState(
            state.episode_id,
            state.turn_id,
            state.phase + 1,
            state.phase_limit,
            state.tool_count,
            state.tool_limit,
            state.output_ref,
            state.continuation_ref,
            state.grant_epoch,
            state.capabilities,
            state.results,
        )
        return {MODEL_PENDING: (Token("LoopState", state.to_data()),)}
    if state.tool_count >= state.tool_limit:
        return {DONE: (_terminal(state, TerminalCode.TOOL_BUDGET),)}
    work = ToolWork(state, settled.assistant_digest, settled.proposals, 0)
    return {TOOL_PENDING: (Token("ToolWork", work.to_data()),)}


def _reject_tool(binding: Binding, arcs: tuple[Arc, ...]):
    del arcs
    work = ToolWork.from_data(binding.tokens[0].data)
    category = "budget" if work.state.tool_count >= work.state.tool_limit else "capability"
    detail = "tool budget exhausted" if category == "budget" else "tool is unsupported or not granted"
    state = _next(
        work.state,
        ModelResult(work.proposal.id, False, None, {"category": category, "detail": detail}),
        increment_tool=False,
    )
    if category == "budget":
        return {DONE: (_terminal(state, TerminalCode.TOOL_BUDGET),)}
    output: dict[NetPath, tuple[Token, ...]] = {}
    _continue(output, work, state)
    return output


def _record(binding: Binding, arcs: tuple[Arc, ...]):
    del arcs
    settled = HandsSettlement.from_data(binding.tokens[0].data)
    state = _next(settled.work.state, settled.result, increment_tool=True)
    if settled.result.error is not None and settled.result.error["category"] == "aborted":
        return {DONE: (_terminal(state, TerminalCode.CANCELLED),)}
    output: dict[NetPath, tuple[Token, ...]] = {}
    _continue(output, settled.work, state)
    return output


def _build_agent_net() -> tuple[Net, Any, Any]:
    """Build the immutable five-place Net and its provider-free implementations."""
    spec = NetSpec("agent-as-net", completion=Cel("size(done) != 0"))
    model_pending = spec.p.model_pending("LoopState")
    model_settled = spec.p.model_settled("ModelSettlement")
    tool_pending = spec.p.tool_pending("ToolWork")
    tool_settled = spec.p.tool_settled("HandsSettlement")
    done = spec.p.done("Terminal")
    model = spec.t.model_phase(handler="model_phase")
    classify = spec.t.classify_model(handler=petri_handler(_classify))
    execute = spec.t.execute_tool(handler="hands", guards=petri_guard(_execute))
    reject = spec.t.reject_tool(handler=petri_handler(_reject_tool), guards=petri_guard(_reject))
    record = spec.t.record_result(handler=petri_handler(_record))
    model_pending >> arc(color="LoopState") >> model >> arc(color="ModelSettlement") >> model_settled
    model_settled >> arc(color="ModelSettlement") >> classify
    classify >> arc(color="LoopState") >> model_pending
    classify >> arc(color="ToolWork") >> tool_pending
    classify >> arc(color="Terminal") >> done
    tool_pending >> arc(color="ToolWork") >> (execute, reject)
    execute >> arc(color="HandsSettlement") >> tool_settled >> arc(color="HandsSettlement") >> record
    reject >> arc(color="ToolWork") >> tool_pending
    reject >> arc(color="LoopState") >> model_pending
    reject >> arc(color="Terminal") >> done
    record >> arc(color="ToolWork") >> tool_pending
    record >> arc(color="LoopState") >> model_pending
    record >> arc(color="Terminal") >> done
    built = spec.build()
    net = built.net
    handlers = {
        **built.handlers,
        net.handler_uri(MODEL_PHASE): _ModelActivity(),
        net.handler_uri(EXECUTE_TOOL): _HandsActivity(),
    }
    return net, MappingProxyType(handlers), built.guards


AGENT_AS_NET, _AGENT_HANDLERS, _AGENT_GUARDS = _build_agent_net()


def agent_net() -> Net:
    """Return the static immutable Agent-as-Net topology."""
    return AGENT_AS_NET


def agent_net_handlers() -> Any:
    return _AGENT_HANDLERS


def agent_net_guards() -> Any:
    return _AGENT_GUARDS
