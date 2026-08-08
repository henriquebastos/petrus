"""Durable Local host and Thread projection for the Net-owned agent loop."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Protocol, cast, runtime_checkable
from uuid import uuid4

from petrus.agenticus.attachment.episode import EpisodeAttachment
from petrus.agenticus.hands.contract import CAPABILITY_SCOPED_HANDS
from petrus.agenticus.hands.gateway import HandsAdapter, HandsGateway
from petrus.agenticus.program.agent_net import (
    AGENT_AS_NET_CONTINUATION_DESCRIPTOR,
    AGENT_AS_NET_PROGRAM,
    DONE,
    HANDS_ACTIVITY,
    MODEL_PHASE_ACTIVITY,
    LoopState,
    ModelResult,
    ModelSettlement,
    Proposal,
    Terminal,
    TerminalCode,
    agent_net,
    agent_net_guards,
    agent_net_handlers,
    initial_marking,
)
from petrus.agenticus.runtime.profiles import AGENT_AS_NET_A5_LOCAL, TerritoryProfile, territory_identity
from petrus.agenticus.thread.continuation import Continuation
from petrus.agenticus.thread.identity import ContinuationId, EpisodeId, TurnId
from petrus.agenticus.thread.lifecycle import EpisodeBudget, EpisodeOutcome, Thread, TurnOutcome
from petrus.engine import DriveOutcome, Engine
from petrus.impetus.history import ActivityCompleted, ActivityFailed, ActivityRequested
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.motus.activity import Activity, ActivityExecutionContext, ActivityInvocation
from petrus.motus.dispatch import InlineDispatch

_SCHEMA_VERSION = 1
_THREAD_FILE = "thread.json"
_HISTORY_FILE = "history.jsonl"


class AgentNetRunnerError(RuntimeError):
    """The Local Agent-as-a-Net host cannot progress without violating custody."""


class HaltCode(StrEnum):
    INDETERMINATE = "indeterminate"
    ACTIVITY_FAILED = "activity-failed"


def _exact(data: object, fields: set[str], label: str) -> dict[str, object]:
    if not isinstance(data, dict) or set(data) != fields or any(type(key) is not str for key in data):
        raise ValueError(f"{label} requires exact fields {sorted(fields)}")
    return cast(dict[str, object], data)


def _positive(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _activity(value: object) -> str:
    if value not in {MODEL_PHASE_ACTIVITY, HANDS_ACTIVITY}:
        raise ValueError("Agent-as-a-Net halt activity is unsupported")
    return str(value)


@dataclass(frozen=True)
class ProjectedAppend:
    """One committed model-phase append projected into Thread accounting."""

    occurrence: int
    output_reference: str
    continuation_reference: str

    def __post_init__(self) -> None:
        _positive(self.occurrence, "projected append occurrence")
        for name in ("output_reference", "continuation_reference"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value.encode()) > 512:
                raise ValueError(f"projected append {name} must be a bounded non-empty reference")

    def to_data(self) -> dict[str, object]:
        return {
            "occurrence": self.occurrence,
            "output_reference": self.output_reference,
            "continuation_reference": self.continuation_reference,
        }

    @classmethod
    def from_data(cls, data: object) -> ProjectedAppend:
        value = _exact(
            data,
            {"occurrence", "output_reference", "continuation_reference"},
            "projected append",
        )
        return cls(
            _positive(value["occurrence"], "projected append occurrence"),
            cast(str, value["output_reference"]),
            cast(str, value["continuation_reference"]),
        )


@dataclass(frozen=True)
class ProjectedHands:
    """One committed Hands result observed by the Thread projector."""

    occurrence: int
    call_id: str

    def __post_init__(self) -> None:
        _positive(self.occurrence, "projected Hands occurrence")
        if not isinstance(self.call_id, str) or not self.call_id or len(self.call_id.encode()) > 256:
            raise ValueError("projected Hands call_id must be bounded non-empty text")

    def to_data(self) -> dict[str, object]:
        return {"occurrence": self.occurrence, "call_id": self.call_id}

    @classmethod
    def from_data(cls, data: object) -> ProjectedHands:
        value = _exact(data, {"occurrence", "call_id"}, "projected Hands result")
        return cls(_positive(value["occurrence"], "projected Hands occurrence"), cast(str, value["call_id"]))


@dataclass(frozen=True)
class AgentNetAttachmentFence:
    """Exact host-only Attachment coordinates expected across reconstruction."""

    episode_id: str
    attachment_id: str
    attachment_epoch: int
    grant_epoch: int

    def __post_init__(self) -> None:
        for name in ("episode_id", "attachment_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value.encode()) > 256:
                raise ValueError(f"Agent-as-a-Net {name} must be bounded non-empty text")
        _positive(self.attachment_epoch, "Agent-as-a-Net attachment_epoch")
        _positive(self.grant_epoch, "Agent-as-a-Net grant_epoch")

    def to_data(self) -> dict[str, object]:
        return {
            "episode_id": self.episode_id,
            "attachment_id": self.attachment_id,
            "attachment_epoch": self.attachment_epoch,
            "grant_epoch": self.grant_epoch,
        }

    @classmethod
    def from_data(cls, data: object) -> AgentNetAttachmentFence:
        value = _exact(
            data,
            {"episode_id", "attachment_id", "attachment_epoch", "grant_epoch"},
            "Agent-as-a-Net Attachment fence",
        )
        return cls(
            cast(str, value["episode_id"]),
            cast(str, value["attachment_id"]),
            _positive(value["attachment_epoch"], "Agent-as-a-Net attachment_epoch"),
            _positive(value["grant_epoch"], "Agent-as-a-Net grant_epoch"),
        )


@dataclass(frozen=True)
class AgentNetHalt:
    code: HaltCode
    activity: str
    occurrence: int

    def __post_init__(self) -> None:
        if not isinstance(self.code, HaltCode):
            raise TypeError("Agent-as-a-Net halt requires HaltCode")
        object.__setattr__(self, "activity", _activity(self.activity))
        _positive(self.occurrence, "halt occurrence")

    def to_data(self) -> dict[str, object]:
        return {"code": self.code.value, "activity": self.activity, "occurrence": self.occurrence}

    @classmethod
    def from_data(cls, data: object) -> AgentNetHalt:
        value = _exact(data, {"code", "activity", "occurrence"}, "Agent-as-a-Net halt")
        return cls(
            HaltCode(value["code"]), _activity(value["activity"]), _positive(value["occurrence"], "halt occurrence")
        )


@dataclass(frozen=True)
class AgentNetThreadProjection:
    """Durable Thread authority plus its idempotent History projection cursor."""

    instance_id: str
    initial: LoopState
    thread: Thread
    attachment: AgentNetAttachmentFence
    appends: tuple[ProjectedAppend, ...] = ()
    hands: tuple[ProjectedHands, ...] = ()
    terminal: Terminal | None = None
    halt: AgentNetHalt | None = None

    # Complexity exception: one decoder-equivalent invariant boundary for the durable cross-store cursor.
    def __post_init__(self) -> None:  # noqa: C901
        if not isinstance(self.instance_id, str) or not self.instance_id or len(self.instance_id.encode()) > 256:
            raise ValueError("Agent-as-a-Net instance_id must be bounded non-empty text")
        if (
            not isinstance(self.initial, LoopState)
            or not isinstance(self.thread, Thread)
            or not isinstance(self.attachment, AgentNetAttachmentFence)
        ):
            raise TypeError("Agent-as-a-Net projection requires LoopState, Thread, and Attachment fence")
        if (
            self.attachment.episode_id != self.initial.episode_id
            or self.attachment.grant_epoch != self.initial.grant_epoch
        ):
            raise ValueError("Agent-as-a-Net Attachment fence does not match the initial loop state")
        appends, hands = tuple(self.appends), tuple(self.hands)
        if any(not isinstance(item, ProjectedAppend) for item in appends):
            raise TypeError("Agent-as-a-Net appends must contain ProjectedAppend values")
        if any(not isinstance(item, ProjectedHands) for item in hands):
            raise TypeError("Agent-as-a-Net Hands facts must contain ProjectedHands values")
        occurrences = [item.occurrence for item in (*appends, *hands)]
        if len(set(occurrences)) != len(occurrences):
            raise ValueError("one Activity occurrence may be projected only once")
        if tuple(item.occurrence for item in appends) != tuple(sorted(item.occurrence for item in appends)):
            raise ValueError("projected appends must retain History order")
        if tuple(item.occurrence for item in hands) != tuple(sorted(item.occurrence for item in hands)):
            raise ValueError("projected Hands facts must retain History order")
        if self.terminal is not None and not isinstance(self.terminal, Terminal):
            raise TypeError("Agent-as-a-Net terminal must be Terminal")
        if self.halt is not None and not isinstance(self.halt, AgentNetHalt):
            raise TypeError("Agent-as-a-Net halt must be AgentNetHalt")
        if self.terminal is not None and self.halt is not None:
            raise ValueError("Agent-as-a-Net projection cannot be terminal and halted")
        episodes = self.thread.episodes
        if not episodes or episodes[-1].id.value != self.initial.episode_id:
            raise ValueError("projected Thread final Episode does not match the initial loop state")
        episode = episodes[-1]
        if not episode.turns or episode.turns[-1].id.value != self.initial.turn_id:
            raise ValueError("projected Thread final Turn does not match the initial loop state")
        if episode.accepted_appends != len(appends):
            raise ValueError("projected append cursor must equal Thread accepted-append accounting")
        settled = episode.settlement is not None
        if settled != (self.terminal is not None or self.halt is not None):
            raise ValueError("projected Thread settles exactly with one terminal or halt fact")
        object.__setattr__(self, "appends", appends)
        object.__setattr__(self, "hands", hands)

    @property
    def settled(self) -> bool:
        return self.terminal is not None or self.halt is not None

    def to_data(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "instance_id": self.instance_id,
            "initial": self.initial.to_data(),
            "thread": self.thread.to_data(),
            "attachment": self.attachment.to_data(),
            "appends": [item.to_data() for item in self.appends],
            "hands": [item.to_data() for item in self.hands],
            "terminal": None if self.terminal is None else self.terminal.to_data(),
            "halt": None if self.halt is None else self.halt.to_data(),
        }

    @classmethod
    def from_data(cls, data: object) -> AgentNetThreadProjection:
        value = _exact(
            data,
            {
                "schema_version",
                "instance_id",
                "initial",
                "thread",
                "attachment",
                "appends",
                "hands",
                "terminal",
                "halt",
            },
            "Agent-as-a-Net Thread projection",
        )
        if value["schema_version"] != _SCHEMA_VERSION or type(value["schema_version"]) is not int:
            raise ValueError(f"Agent-as-a-Net Thread projection schema_version must be integer {_SCHEMA_VERSION}")
        if not isinstance(value["appends"], list) or not isinstance(value["hands"], list):
            raise TypeError("Agent-as-a-Net projection cursors must be arrays")
        terminal, halt = value["terminal"], value["halt"]
        return cls(
            cast(str, value["instance_id"]),
            LoopState.from_data(value["initial"]),
            Thread.from_data(value["thread"]),
            AgentNetAttachmentFence.from_data(value["attachment"]),
            tuple(ProjectedAppend.from_data(item) for item in value["appends"]),
            tuple(ProjectedHands.from_data(item) for item in value["hands"]),
            None if terminal is None else Terminal.from_data(terminal),
            None if halt is None else AgentNetHalt.from_data(halt),
        )


@runtime_checkable
class AgentNetThreadRepository(Protocol):
    """Compare-and-save Thread projection boundary, separate from payload custody."""

    def load(self) -> AgentNetThreadProjection | None: ...

    def save(
        self,
        expected: AgentNetThreadProjection | None,
        value: AgentNetThreadProjection,
    ) -> None: ...


class JsonAgentNetThreadRepository:
    """Single-writer atomic JSON persistence for one Local runner's Thread."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> AgentNetThreadProjection | None:
        if not self.path.exists():
            return None
        try:
            return AgentNetThreadProjection.from_data(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise AgentNetRunnerError("durable Thread projection is unreadable") from error

    def save(
        self,
        expected: AgentNetThreadProjection | None,
        value: AgentNetThreadProjection,
    ) -> None:
        if not isinstance(value, AgentNetThreadProjection):
            raise TypeError("Thread repository saves AgentNetThreadProjection values")
        if self.load() != expected:
            raise AgentNetRunnerError("durable Thread projection changed concurrently")
        encoded = json.dumps(value.to_data(), allow_nan=False, separators=(",", ":"), sort_keys=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.parent / f".{self.path.name}.{uuid4().hex}.tmp"
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise


class AgentNetHandsActivity:
    """Execute one current proposal through one current Episode Attachment."""

    def __init__(self, attachment: EpisodeAttachment, adapter: HandsAdapter) -> None:
        self._attachment = attachment
        self._adapter = adapter
        self._gateway: HandsGateway | None = None

    def __call__(self, invocation: ActivityInvocation, *, context: ActivityExecutionContext) -> object:
        if invocation.activity != HANDS_ACTIVITY:
            raise AgentNetRunnerError("Hands Activity identity mismatch")
        value = _exact(invocation.input, {"version", "proposal", "grant_epoch"}, "Hands Activity input")
        if value["version"] != _SCHEMA_VERSION or type(value["version"]) is not int:
            raise AgentNetRunnerError("Hands Activity input version mismatch")
        proposal = Proposal.from_data(value["proposal"])
        grant_epoch = _positive(value["grant_epoch"], "Hands Activity grant_epoch")
        coordinates = self._attachment.coordinates()
        grant = self._attachment.grants().current()
        if (
            grant is None
            or grant.grant_epoch != grant_epoch
            or grant.attachment_id != coordinates.attachment_id
            or grant.attachment_epoch != coordinates.attachment_epoch
        ):
            raise AgentNetRunnerError("Hands Activity grant is not current")
        try:
            context.heartbeat(details={"phase": "hands"})
        except Exception:
            raise AgentNetRunnerError("Hands Activity ownership is stale") from None
        if self._gateway is None:
            self._gateway = self._attachment.gateway(self._adapter)
        result = self._gateway.submit(
            {
                "version": _SCHEMA_VERSION,
                "call_id": proposal.id,
                "episode_id": coordinates.episode_id,
                "attachment_id": coordinates.attachment_id,
                "attachment_epoch": coordinates.attachment_epoch,
                "grant_epoch": grant_epoch,
                "method": proposal.method,
                "params": proposal.params,
            }
        )
        if (
            result.call_id != proposal.id
            or result.attachment_id != coordinates.attachment_id
            or result.epoch != coordinates.attachment_epoch
        ):
            raise AgentNetRunnerError("Hands Activity result fence mismatch")
        projected = ModelResult.from_model_data(proposal.id, result.to_model_data())
        return {"version": _SCHEMA_VERSION, "result": projected.to_data()}


class AgentNetRunner:
    """Single-writer Local host whose Engine History alone schedules the loop."""

    def __init__(
        self,
        *,
        engine: Engine,
        history: JsonlHistoryStore,
        repository: AgentNetThreadRepository,
        projection: AgentNetThreadProjection,
        attachment: EpisodeAttachment,
    ) -> None:
        self.engine = engine
        self.history = history
        self.repository = repository
        self.projection = projection
        self.attachment = attachment

    @classmethod
    def create(
        cls,
        root: str | Path,
        *,
        instance_id: str,
        thread: Thread,
        initial: LoopState,
        attachment: EpisodeAttachment,
        model_activity: Activity,
        hands_adapter: HandsAdapter,
    ) -> AgentNetRunner:
        root = Path(root)
        repository = JsonAgentNetThreadRepository(root / _THREAD_FILE)
        history_path = root / _HISTORY_FILE
        if repository.load() is not None or history_path.exists():
            raise AgentNetRunnerError("Agent-as-a-Net runner already exists; load it instead")
        cls._validate_initial(thread, initial, attachment)
        running = thread.start_episode(
            EpisodeId(initial.episode_id),
            AGENT_AS_NET_PROGRAM,
            AGENT_AS_NET_A5_LOCAL.identity,
            EpisodeBudget(max_turns=1, max_accepted_appends=initial.phase_limit),
        ).start_turn(TurnId(initial.turn_id))
        projection = AgentNetThreadProjection(
            instance_id,
            initial,
            running,
            cls._attachment_fence(initial, attachment),
        )
        repository.save(None, projection)
        return cls._open(root, repository, projection, attachment, model_activity, hands_adapter)

    @classmethod
    def load(
        cls,
        root: str | Path,
        *,
        attachment: EpisodeAttachment,
        model_activity: Activity,
        hands_adapter: HandsAdapter,
    ) -> AgentNetRunner:
        root = Path(root)
        repository = JsonAgentNetThreadRepository(root / _THREAD_FILE)
        projection = repository.load()
        if projection is None:
            raise AgentNetRunnerError("Agent-as-a-Net Thread projection does not exist")
        # A crash may land after verified Attachment settlement but before the
        # corresponding Thread save. Validate immutable profile coordinates
        # here; _open consumes terminal/ambiguity facts first and requires a
        # live grant only if the reconstructed run remains active.
        cls._validate_attachment(
            projection.initial,
            attachment,
            expected=projection.attachment,
            require_grant=False,
        )
        return cls._open(root, repository, projection, attachment, model_activity, hands_adapter)

    @classmethod
    def _open(
        cls,
        root: Path,
        repository: AgentNetThreadRepository,
        projection: AgentNetThreadProjection,
        attachment: EpisodeAttachment,
        model_activity: Activity,
        hands_adapter: HandsAdapter,
    ) -> AgentNetRunner:
        history = JsonlHistoryStore(root / _HISTORY_FILE)
        dispatch = InlineDispatch(
            {
                MODEL_PHASE_ACTIVITY: model_activity,
                HANDS_ACTIVITY: AgentNetHandsActivity(attachment, hands_adapter),
            }
        )
        engine = (
            Engine.load(
                agent_net(),
                projection.instance_id,
                history=history,
                dispatch=dispatch,
                handlers=agent_net_handlers(),
                guards=agent_net_guards(),
            )
            if len(history)
            else Engine.create(
                agent_net(),
                projection.instance_id,
                history=history,
                dispatch=dispatch,
                marking=initial_marking(projection.initial),
                handlers=agent_net_handlers(),
                guards=agent_net_guards(),
            )
        )
        runner = cls(
            engine=engine,
            history=history,
            repository=repository,
            projection=projection,
            attachment=attachment,
        )
        runner._project_committed()
        runner._settle_recorded_failure()
        runner._settle_terminal()
        runner._fence_reconstructed_activities()
        if not runner.projection.settled:
            runner._validate_attachment(
                runner.projection.initial,
                attachment,
                expected=runner.projection.attachment,
            )
        return runner

    @staticmethod
    def _validate_initial(thread: Thread, initial: LoopState, attachment: EpisodeAttachment) -> None:
        if not isinstance(thread, Thread) or not isinstance(initial, LoopState):
            raise TypeError("Agent-as-a-Net create requires exact Thread and LoopState values")
        if initial.phase != 1 or initial.tool_count != 0 or initial.results:
            raise AgentNetRunnerError("initial loop state must begin at the first empty phase")
        if thread.episodes and thread.episodes[-1].settlement is None:
            raise AgentNetRunnerError("initial Thread already has an active Episode")
        continuation = thread.continuation
        if continuation is None:
            if initial.output_ref is not None or initial.continuation_ref is not None:
                raise AgentNetRunnerError("fresh Thread cannot start from opaque prior references")
        elif initial.continuation_ref != continuation.state_reference or initial.output_ref is None:
            raise AgentNetRunnerError("initial references do not match the Thread Continuation lineage")
        AgentNetRunner._validate_attachment(initial, attachment)

    @staticmethod
    def _validate_attachment(
        initial: LoopState,
        attachment: EpisodeAttachment,
        *,
        expected: AgentNetAttachmentFence | None = None,
        require_grant: bool = True,
    ) -> None:
        if not isinstance(attachment, EpisodeAttachment):
            raise TypeError("Agent-as-a-Net runner requires EpisodeAttachment")
        runtime = attachment.snapshot.descriptor(AGENT_AS_NET_A5_LOCAL.identity.kind)
        hands = attachment.snapshot.descriptor(CAPABILITY_SCOPED_HANDS.identity.kind)
        territory = attachment.snapshot.descriptor(territory_identity(TerritoryProfile.LOCAL).kind)
        grant = attachment.grants().current()
        coordinates = attachment.coordinates()
        if (
            attachment.episode_id.value != initial.episode_id
            or runtime != AGENT_AS_NET_A5_LOCAL
            or hands != CAPABILITY_SCOPED_HANDS
            or territory is None
            or territory.identity != territory_identity(TerritoryProfile.LOCAL)
        ):
            raise AgentNetRunnerError("Episode Attachment or grant does not match the Local loop state")
        if expected is not None and (
            expected.episode_id != coordinates.episode_id
            or expected.attachment_id != coordinates.attachment_id
            or expected.attachment_epoch != coordinates.attachment_epoch
            or expected.grant_epoch != initial.grant_epoch
        ):
            raise AgentNetRunnerError("Episode Attachment or grant does not match the Local loop state")
        if require_grant and (
            grant is None
            or grant.grant_epoch != initial.grant_epoch
            or set(initial.capabilities) != {method.value for method in grant.capabilities}
            or initial.tool_limit > grant.max_calls
        ):
            raise AgentNetRunnerError("Episode Attachment or grant does not match the Local loop state")

    @staticmethod
    def _attachment_fence(initial: LoopState, attachment: EpisodeAttachment) -> AgentNetAttachmentFence:
        coordinates = attachment.coordinates()
        return AgentNetAttachmentFence(
            coordinates.episode_id,
            coordinates.attachment_id,
            coordinates.attachment_epoch,
            initial.grant_epoch,
        )

    @property
    def thread(self) -> Thread:
        return self.projection.thread

    @property
    def settled(self) -> bool:
        return self.projection.settled

    def advance(self) -> DriveOutcome:
        if self.projection.settled:
            raise AgentNetRunnerError("settled Agent-as-a-Net runner cannot advance")
        self._validate_attachment(
            self.projection.initial,
            self.attachment,
            expected=self.projection.attachment,
        )
        try:
            outcome = self.engine.advance()
        except RuntimeError:
            self._project_committed()
            self._settle_recorded_failure()
            raise
        self._project_committed()
        self._settle_recorded_failure()
        self._settle_terminal()
        return outcome

    def drain(self, *, max_actions: int = 256) -> AgentNetThreadProjection:
        _positive(max_actions, "Agent-as-a-Net max_actions")
        for _ in range(max_actions):
            if self.projection.settled:
                return self.projection
            outcome = self.advance()
            if not outcome.ready:
                if self.engine.in_flight:
                    raise AgentNetRunnerError("Agent-as-a-Net runner is waiting for external Activity custody")
                raise AgentNetRunnerError("Agent-as-a-Net runner stopped before a terminal fact")
        raise AgentNetRunnerError("Agent-as-a-Net action bound exhausted")

    def _save(self, projection: AgentNetThreadProjection) -> None:
        self.repository.save(self.projection, projection)
        self.projection = projection

    # Complexity exception: one ordered History-to-Thread projection boundary.
    def _project_committed(self) -> None:  # noqa: C901
        requests = {
            record.occurrence: record for record in self.history.records if isinstance(record, ActivityRequested)
        }
        append_by_occurrence = {item.occurrence: item for item in self.projection.appends}
        hands_by_occurrence = {item.occurrence: item for item in self.projection.hands}
        for record in self.history.records:
            if not isinstance(record, ActivityCompleted):
                continue
            requested = requests.get(record.occurrence)
            if requested is None:
                raise AgentNetRunnerError("Activity completion has no recorded request")
            if requested.activity == MODEL_PHASE_ACTIVITY:
                settled = ModelSettlement.from_data(record.result)
                if (settled.state.episode_id, settled.state.turn_id) != (
                    self.projection.initial.episode_id,
                    self.projection.initial.turn_id,
                ):
                    raise AgentNetRunnerError("committed model settlement names stale Thread coordinates")
                projected = ProjectedAppend(
                    record.occurrence,
                    settled.output_ref,
                    settled.continuation_ref,
                )
                prior = append_by_occurrence.get(record.occurrence)
                if prior is not None:
                    if prior != projected:
                        raise AgentNetRunnerError("committed model append conflicts with its Thread projection")
                    continue
                if self.projection.settled:
                    raise AgentNetRunnerError("new model append follows settled Thread projection")
                thread = self.projection.thread.accept_append(TurnId(self.projection.initial.turn_id))
                self._save(replace(self.projection, thread=thread, appends=(*self.projection.appends, projected)))
                append_by_occurrence[record.occurrence] = projected
                continue
            if requested.activity == HANDS_ACTIVITY:
                result = self._hands_result(requested, record.result)
                projected_hands = ProjectedHands(record.occurrence, result.id)
                prior_hands = hands_by_occurrence.get(record.occurrence)
                if prior_hands is not None:
                    if prior_hands != projected_hands:
                        raise AgentNetRunnerError("committed Hands result conflicts with its Thread projection")
                    continue
                if self.projection.settled:
                    raise AgentNetRunnerError("new Hands result follows settled Thread projection")
                self._save(replace(self.projection, hands=(*self.projection.hands, projected_hands)))
                hands_by_occurrence[record.occurrence] = projected_hands
                continue
            raise AgentNetRunnerError("Agent-as-a-Net History contains an unsupported Activity")

    @staticmethod
    def _hands_result(requested: ActivityRequested, result: object) -> ModelResult:
        request = _exact(requested.input, {"version", "proposal", "grant_epoch"}, "recorded Hands request")
        proposal = Proposal.from_data(request["proposal"])
        value = _exact(result, {"version", "result"}, "committed Hands result")
        if value["version"] != _SCHEMA_VERSION or type(value["version"]) is not int:
            raise AgentNetRunnerError("committed Hands result version mismatch")
        settled = ModelResult.from_data(value["result"])
        if settled.id != proposal.id:
            raise AgentNetRunnerError("committed Hands result names another proposal")
        return settled

    def _settle_recorded_failure(self) -> None:
        if self.projection.settled:
            return
        requests = {
            record.occurrence: record for record in self.history.records if isinstance(record, ActivityRequested)
        }
        failures = [record for record in self.history.records if isinstance(record, ActivityFailed)]
        if not failures:
            return
        failure = failures[-1]
        requested = requests.get(failure.occurrence)
        if requested is None:
            raise AgentNetRunnerError("Activity failure has no recorded request")
        activity = _activity(requested.activity)
        self._settle_attachment(cancel_reason="activity-failed")
        thread = self.projection.thread.settle_turn(
            TurnId(self.projection.initial.turn_id),
            TurnOutcome.FAILED,
        )
        thread = thread.settle_episode(EpisodeOutcome.FAILED).thread
        self._save(
            replace(
                self.projection,
                thread=thread,
                halt=AgentNetHalt(HaltCode.ACTIVITY_FAILED, activity, failure.occurrence),
            )
        )

    # Complexity exception: one terminal-code-to-lifecycle projection boundary.
    def _settle_terminal(self) -> None:  # noqa: C901
        tokens = self.engine.marking.place(DONE)
        if not tokens:
            return
        if len(tokens) != 1 or tokens[0].color != "Terminal":
            raise AgentNetRunnerError("Agent-as-a-Net terminal marking is invalid")
        terminal = Terminal.from_data(tokens[0].data)
        if (terminal.episode_id, terminal.turn_id) != (
            self.projection.initial.episode_id,
            self.projection.initial.turn_id,
        ):
            raise AgentNetRunnerError("terminal fact names stale Thread coordinates")
        if self.projection.terminal is not None:
            if self.projection.terminal != terminal:
                raise AgentNetRunnerError("terminal fact conflicts with its Thread projection")
            return
        if self.projection.halt is not None:
            raise AgentNetRunnerError("terminal fact follows a settled halt")
        if not self.projection.appends:
            raise AgentNetRunnerError("terminal fact has no committed model append")
        final = self.projection.appends[-1]
        if (terminal.output_ref, terminal.continuation_ref) != (
            final.output_reference,
            final.continuation_reference,
        ):
            raise AgentNetRunnerError("terminal references do not match the final committed append")
        if terminal.code is TerminalCode.CANCELLED:
            self._settle_attachment(cancel_reason="agent-cancelled")
            thread = self.projection.thread.request_cancellation().thread
            thread = thread.settle_turn(TurnId(terminal.turn_id), TurnOutcome.CANCELLED)
            episode_outcome, continuation = EpisodeOutcome.CANCELLED, self._continuation(terminal)
        else:
            self._settle_attachment()
            turn_outcome = TurnOutcome.FAILED if terminal.code is TerminalCode.FAILED else TurnOutcome.COMPLETED
            thread = self.projection.thread.settle_turn(TurnId(terminal.turn_id), turn_outcome)
            if terminal.code is TerminalCode.COMPLETED:
                episode_outcome = EpisodeOutcome.COMPLETED
            elif terminal.code in {TerminalCode.PHASE_BUDGET, TerminalCode.TOOL_BUDGET}:
                episode_outcome = EpisodeOutcome.BUDGET_EXHAUSTED
            else:
                episode_outcome = EpisodeOutcome.FAILED
            continuation = self._continuation(terminal)
        thread = thread.settle_episode(episode_outcome, continuation).thread
        self._save(replace(self.projection, thread=thread, terminal=terminal))

    def _continuation(self, terminal: Terminal) -> Continuation:
        digest = sha256(
            f"{self.projection.thread.id.value}\0{terminal.episode_id}\0{terminal.continuation_ref}".encode()
        ).hexdigest()
        return Continuation(
            ContinuationId(f"agent-net:{digest}"),
            self.projection.thread.id,
            AGENT_AS_NET_CONTINUATION_DESCRIPTOR,
            terminal.continuation_ref,
        )

    def _fence_reconstructed_activities(self) -> None:
        if self.projection.settled:
            return
        completed = {record.occurrence for record in self.engine.records if isinstance(record, ActivityCompleted)}
        ambiguous = [
            occurrence
            for occurrence in self.engine.in_flight
            if occurrence.invocation is not None and occurrence.id not in completed
        ]
        if not ambiguous:
            return
        if len(ambiguous) != 1:
            raise AgentNetRunnerError("sequential Agent-as-a-Net History reconstructed multiple Activities")
        occurrence = ambiguous[0]
        invocation = occurrence.invocation
        assert invocation is not None
        activity = _activity(invocation.activity)
        self._settle_attachment(cancel_reason="reconstruction-indeterminate")
        thread = self.projection.thread.settle_turn(
            TurnId(self.projection.initial.turn_id),
            TurnOutcome.INDETERMINATE,
        )
        thread = thread.settle_episode(EpisodeOutcome.INDETERMINATE).thread
        self._save(
            replace(
                self.projection,
                thread=thread,
                halt=AgentNetHalt(HaltCode.INDETERMINATE, activity, occurrence.id),
            )
        )

    def _settle_attachment(self, *, cancel_reason: str | None = None) -> None:
        if self.attachment.settled:
            settlement = self.attachment.last_settlement
        else:
            if self.attachment.custody_uncertain:
                raise AgentNetRunnerError("Episode Attachment cleanup custody is uncertain")
            if cancel_reason is not None:
                self.attachment.cancel(cancel_reason)
            settlement = self.attachment.settle()
        if settlement is None or not settlement.settlement.verified:
            raise AgentNetRunnerError("Episode Attachment settlement was not independently verified")

    def close(self) -> None:
        self.engine.close()


__all__ = [
    "AgentNetAttachmentFence",
    "AgentNetHandsActivity",
    "AgentNetHalt",
    "AgentNetRunner",
    "AgentNetRunnerError",
    "AgentNetThreadProjection",
    "AgentNetThreadRepository",
    "HaltCode",
    "JsonAgentNetThreadRepository",
    "ProjectedAppend",
    "ProjectedHands",
]
