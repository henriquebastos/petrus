"""Petri- and history-agnostic activity execution values and contract."""

from __future__ import annotations

import json
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import KW_ONLY, asdict, dataclass, fields, is_dataclass
from inspect import Parameter, iscoroutinefunction, signature
from types import MappingProxyType
from typing import Protocol, get_type_hints


HEARTBEAT_DETAILS_LIMIT = 65_536
_OMITTED = object()


def snapshot_heartbeat_details(value: object) -> object:
    """Return the exact, detached JSON value accepted at the heartbeat door."""

    def normalize(item: object) -> object:
        if item is None or isinstance(item, (str, bool)):
            return item
        if isinstance(item, int) and not isinstance(item, bool):
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("heartbeat details require finite JSON numbers")
            return item
        if isinstance(item, list):
            return [normalize(child) for child in item]
        if isinstance(item, Mapping):
            if any(not isinstance(key, str) for key in item):
                raise ValueError("heartbeat details require string mapping keys")
            return {key: normalize(child) for key, child in item.items()}
        raise ValueError(f"heartbeat details are not JSON-faithful: {type(item).__name__}")

    normalized = normalize(value)
    encoded = json.dumps(normalized, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > HEARTBEAT_DETAILS_LIMIT:
        raise ValueError(f"heartbeat details encode to {len(encoded)} UTF-8 bytes; limit is {HEARTBEAT_DETAILS_LIMIT}")
    return json.loads(encoded)


@dataclass(frozen=True)
class ActivityDeclaration:
    """Engine-side Activity metadata, separate from Worker implementation code."""

    name: str
    heartbeat_timeout: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("ActivityDeclaration requires a non-empty string name")
        if self.heartbeat_timeout is not None and (
            isinstance(self.heartbeat_timeout, bool)
            or not isinstance(self.heartbeat_timeout, int)
            or self.heartbeat_timeout <= 0
        ):
            raise ValueError("ActivityDeclaration heartbeat_timeout must be a positive integer or None")


class PayloadConverter(Protocol):
    """Convert Activity payloads between canonical values and typed Python values."""

    def decode(self, value: object, annotation: object) -> object: ...

    def encode(self, value: object, annotation: object) -> object: ...


def _parameter_mapping(value: object, rejection: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{rejection} must be a mapping, got {type(value).__name__}")
    if any(not isinstance(name, str) for name in value):
        raise ValueError(f"{rejection} requires string parameter names")
    return {name: item for name, item in value.items() if isinstance(name, str)}


@dataclass(frozen=True)
class JsonPayloadConverter:
    """Preserve a detached JSON-faithful Activity value."""

    def decode(self, value: object, annotation: object) -> object:
        del annotation
        return self._canonical(value)

    def encode(self, value: object, annotation: object) -> object:
        del annotation
        return self._canonical(value)

    @staticmethod
    def _canonical(value: object) -> object:
        try:
            return json.loads(json.dumps(value, allow_nan=False))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Activity payload is not JSON-faithful: {error}") from None


@dataclass(frozen=True)
class DataclassPayloadConverter:
    """Convert top-level dataclass values, falling back to canonical JSON values."""

    fallback: PayloadConverter = JsonPayloadConverter()

    def decode(self, value: object, annotation: object) -> object:
        if isinstance(annotation, type) and is_dataclass(annotation):
            payload = _parameter_mapping(value, f"Activity payload for dataclass {annotation.__name__}")
            accepted = {field.name for field in fields(annotation)}
            return annotation(**{name: item for name, item in payload.items() if name in accepted})
        return self.fallback.decode(value, annotation)

    def encode(self, value: object, annotation: object) -> object:
        if isinstance(annotation, type) and is_dataclass(annotation):
            if not isinstance(value, annotation):
                raise ValueError(
                    f"Activity result for dataclass {annotation.__name__} must be {annotation.__name__}, "
                    f"got {type(value).__name__}"
                )
            return self.fallback.encode(asdict(value), annotation)
        return self.fallback.encode(value, annotation)


@dataclass(frozen=True)
class ActivityDefinition:
    """A typed function adapted to the Petri-agnostic Activity protocol."""

    function: Callable[..., object]
    declaration: ActivityDeclaration
    converter: PayloadConverter
    parameters: Mapping[str, object]
    result: object

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))

    def __call__(self, invocation: ActivityInvocation, *, context: ActivityExecutionContext) -> object:
        del context
        if invocation.activity != self.declaration.name:
            raise ValueError(
                f"Activity {self.declaration.name!r} cannot execute invocation for {invocation.activity!r}"
            )
        supplied_input = _parameter_mapping(invocation.input, f"Activity {self.declaration.name!r} parameter payload")
        expected = set(self.parameters)
        supplied = set(supplied_input)
        if supplied != expected:
            raise ValueError(
                f"Activity {self.declaration.name!r} requires parameters {sorted(expected)}, got {sorted(supplied)}"
            )
        arguments = {
            name: self.converter.decode(supplied_input[name], annotation)
            for name, annotation in self.parameters.items()
        }
        return self.converter.encode(self.function(**arguments), self.result)


def _typed_signature(implementation: Callable[..., object], *, kind: str) -> tuple[str, dict[str, object], object]:
    implementation_name = getattr(implementation, "__name__", type(implementation).__name__)
    call = signature(implementation)
    try:
        hints = get_type_hints(implementation)
    except NameError as error:
        raise TypeError(f"{kind} {implementation_name!r} cannot resolve its typed signature: {error}") from None
    parameters: dict[str, object] = {}
    for parameter in call.parameters.values():
        if parameter.kind not in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY):
            raise TypeError(f"{kind} {implementation_name!r} parameter {parameter.name!r} must be a named parameter")
        if parameter.name not in hints:
            raise TypeError(f"{kind} {implementation_name!r} parameter {parameter.name!r} requires a type annotation")
        parameters[parameter.name] = hints[parameter.name]
    if "return" not in hints:
        raise TypeError(f"{kind} {implementation_name!r} requires a return type annotation")
    return implementation_name, parameters, hints["return"]


def activity(
    function: Callable[..., object] | None = None,
    *,
    name: str | None = None,
    heartbeat_timeout: int | None = None,
    converter: PayloadConverter = JsonPayloadConverter(),
):
    """Declare a typed function as an Activity implementation and declaration."""

    def declare(implementation: Callable[..., object]) -> ActivityDefinition:
        implementation_name = getattr(implementation, "__name__", type(implementation).__name__)
        if iscoroutinefunction(implementation) or iscoroutinefunction(getattr(implementation, "__call__", None)):
            raise TypeError(f"Activity {implementation_name!r} requires a synchronous function; use async_activity")
        implementation_name, parameters, result = _typed_signature(implementation, kind="Activity")
        declaration = ActivityDeclaration(
            implementation_name if name is None else name, heartbeat_timeout=heartbeat_timeout
        )
        return ActivityDefinition(implementation, declaration, converter, parameters, result)

    return declare(function) if function is not None else declare


@dataclass(frozen=True)
class AsyncActivityDefinition:
    """A typed coroutine function adapted to the asynchronous Activity protocol."""

    function: Callable[..., Awaitable[object]]
    declaration: ActivityDeclaration
    converter: PayloadConverter
    parameters: Mapping[str, object]
    result: object

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))

    async def __call__(self, invocation: ActivityInvocation, *, context: AsyncActivityExecutionContext) -> object:
        del context
        if invocation.activity != self.declaration.name:
            raise ValueError(
                f"Activity {self.declaration.name!r} cannot execute invocation for {invocation.activity!r}"
            )
        supplied_input = _parameter_mapping(invocation.input, f"Activity {self.declaration.name!r} parameter payload")
        expected = set(self.parameters)
        supplied = set(supplied_input)
        if supplied != expected:
            raise ValueError(
                f"Activity {self.declaration.name!r} requires parameters {sorted(expected)}, got {sorted(supplied)}"
            )
        arguments = {
            name: self.converter.decode(supplied_input[name], annotation)
            for name, annotation in self.parameters.items()
        }
        value = await self.function(**arguments)
        return self.converter.encode(value, self.result)


def async_activity(
    function: Callable[..., Awaitable[object]] | None = None,
    *,
    name: str | None = None,
    heartbeat_timeout: int | None = None,
    converter: PayloadConverter = JsonPayloadConverter(),
):
    """Declare a typed coroutine function as an asynchronous Activity."""

    def declare(implementation: Callable[..., Awaitable[object]]) -> AsyncActivityDefinition:
        implementation_name = getattr(implementation, "__name__", type(implementation).__name__)
        if not iscoroutinefunction(implementation):
            raise TypeError(f"AsyncActivity {implementation_name!r} requires an async coroutine function")
        implementation_name, parameters, result = _typed_signature(implementation, kind="AsyncActivity")
        declaration = ActivityDeclaration(
            implementation_name if name is None else name, heartbeat_timeout=heartbeat_timeout
        )
        return AsyncActivityDefinition(implementation, declaration, converter, parameters, result)

    return declare(function) if function is not None else declare


@dataclass(frozen=True)
class ExecutionPolicy:
    """The resolved number of operational attempts for one invocation."""

    attempts: int = 1
    heartbeat_timeout: int = 30

    def __post_init__(self) -> None:
        if isinstance(self.attempts, bool) or not isinstance(self.attempts, int) or self.attempts < 1:
            raise ValueError(
                f"ExecutionPolicy requires attempts >= 1, got {self.attempts!r}: "
                f"an invocation that may never execute is a wedge, not a policy"
            )
        if (
            isinstance(self.heartbeat_timeout, bool)
            or not isinstance(self.heartbeat_timeout, int)
            or self.heartbeat_timeout <= 0
        ):
            raise ValueError("ExecutionPolicy heartbeat_timeout must be a positive integer")


@dataclass(frozen=True)
class ActivityInvocation:
    """The stable, Petri-agnostic instruction offered to Dispatch."""

    activity: str
    _: KW_ONLY
    input: object = None
    policy: ExecutionPolicy = ExecutionPolicy()
    correlation: str | None = None
    idempotency: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.activity, str) or not self.activity:
            raise ValueError(f"ActivityInvocation requires a non-empty string activity name, got {self.activity!r}")
        for name, value in (("correlation", self.correlation), ("idempotency", self.idempotency)):
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(
                    f"ActivityInvocation {name} must be a non-empty string, or None for the writer to "
                    f"derive at begin, got {value!r}"
                )


@dataclass(frozen=True)
class ActivityFailure:
    """A Dispatch terminal failure value."""

    error: str


class ActivityExecutionContext(Protocol):
    attempt_id: str
    epoch: str
    claimant: str
    latest_details: object

    def heartbeat(self, *, details: object = _OMITTED) -> object:
        """Renew this Attempt, optionally replacing its latest details."""
        ...


class Activity(Protocol):
    def __call__(self, invocation: ActivityInvocation, *, context: ActivityExecutionContext) -> object:
        """Execute one invocation under its injected Attempt context."""
        ...


class AsyncActivityExecutionContext(Protocol):
    attempt_id: str
    epoch: str
    claimant: str
    latest_details: object

    async def heartbeat(self, *, details: object = _OMITTED) -> object:
        """Renew this Attempt on its provider lane, optionally replacing details."""
        ...


class AsyncActivity(Protocol):
    async def __call__(self, invocation: ActivityInvocation, *, context: AsyncActivityExecutionContext) -> object:
        """Execute one invocation on the AsyncWorker event loop."""
        ...


__all__ = [
    "Activity",
    "ActivityDeclaration",
    "ActivityDefinition",
    "ActivityExecutionContext",
    "ActivityFailure",
    "ActivityInvocation",
    "AsyncActivity",
    "AsyncActivityDefinition",
    "AsyncActivityExecutionContext",
    "DataclassPayloadConverter",
    "ExecutionPolicy",
    "HEARTBEAT_DETAILS_LIMIT",
    "JsonPayloadConverter",
    "PayloadConverter",
    "activity",
    "async_activity",
    "snapshot_heartbeat_details",
]
