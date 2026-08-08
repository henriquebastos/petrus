"""Version-1 bounded Hands tool request and result contracts.

This module owns the exact request/result/error envelopes for the five earned
workspace tools. The fixed set and its bounds come from the accepted ES-049
contract; version 1 is not a claim that all future tools share one schema.
Every rendered error stays within a fixed secret-safe vocabulary; raw provider
output and exception text never enter a result.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorIdentity, DescriptorKind

_SCHEMA_VERSION = 1

MAX_PATH_CHARS = 64
MAX_QUERY_CHARS = 64
MAX_ARGV_PART_CHARS = 64
MAX_ARGV_PARTS = 4
MAX_CONTENT_CHARS = 256
MAX_CWD_CHARS = 8
MAX_DATA_TEXT_BYTES = 4096
_MAX_IDENTITY_BYTES = 256
_MAX_DETAIL_BYTES = 128

_ENVELOPE_FIELDS = {
    "version",
    "call_id",
    "episode_id",
    "attachment_id",
    "attachment_epoch",
    "grant_epoch",
    "method",
    "params",
}


class ToolMethod(StrEnum):
    """The five earned version-1 workspace tools; the set is exact and closed."""

    WORKSPACE_READ = "workspace_read"
    WORKSPACE_SEARCH = "workspace_search"
    WORKSPACE_SHELL = "workspace_shell"
    WORKSPACE_WRITE = "workspace_write"
    WORKSPACE_TEST = "workspace_test"


CAPABILITY_SCOPED_HANDS = CapabilityDescriptor(
    identity=DescriptorIdentity(DescriptorKind.HANDS, "agenticus.capability-scoped", 1),
    offers=frozenset(
        {
            "hands.capability-scoped",
            "workspace.read",
            "workspace.search",
            "workspace.shell",
            "workspace.write",
            "workspace.test",
        }
    ),
)


_PARAM_FIELDS: dict[ToolMethod, set[str]] = {
    ToolMethod.WORKSPACE_READ: {"path"},
    ToolMethod.WORKSPACE_SEARCH: {"query", "path"},
    ToolMethod.WORKSPACE_SHELL: {"argv", "cwd"},
    ToolMethod.WORKSPACE_WRITE: {"path", "content"},
    ToolMethod.WORKSPACE_TEST: set(),
}


class RejectionCategory(StrEnum):
    """Complete secret-safe error vocabulary rendered by the Hands gateway.

    The first ten categories are the required ES-049-equivalent classes.
    ``schema`` names a malformed or non-exact envelope and ``authority`` names
    a stale, revoked, or removed Agent Connection admission fence.
    """

    CAPABILITY = "capability"
    PATH = "path"
    ARGV = "argv"
    WRITE = "write"
    UNKNOWN = "unknown"
    DEADLINE = "deadline"
    ABORTED = "aborted"
    STALE_EPOCH = "stale_epoch"
    POST_FENCE = "post_fence"
    PROVIDER = "provider"
    SCHEMA = "schema"
    AUTHORITY = "authority"
    BUDGET = "budget"


class ToolCallConflict(RuntimeError):
    """A call identity was reused for a materially different request."""

    def __init__(self) -> None:
        super().__init__("tool call identity conflicts with its immutable request")


class ToolRequestRejected(ValueError):
    """A request failed its exact schema or bound before any policy check."""

    def __init__(self, category: RejectionCategory, detail: str) -> None:
        self.category = category
        self.detail = _detail(detail)
        super().__init__(f"{category.value}: {self.detail}")


def _detail(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > _MAX_DETAIL_BYTES
        or any(ord(character) < 32 for character in value)
    ):
        raise AssertionError("rejection detail must stay within the fixed safe vocabulary bounds")
    return value


def _identity(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > _MAX_IDENTITY_BYTES
        or any(ord(character) < 32 for character in value)
    ):
        raise ToolRequestRejected(RejectionCategory.SCHEMA, f"{name} must be a bounded non-empty identity string")
    return value


def _positive_integer(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ToolRequestRejected(RejectionCategory.SCHEMA, f"{name} must be a positive integer")
    return value


def _bounded_text(value: object, name: str, limit: int, category: RejectionCategory) -> str:
    if not isinstance(value, str):
        raise ToolRequestRejected(RejectionCategory.SCHEMA, f"{name} must be a string")
    if any(ord(character) < 32 for character in value) or "\x7f" in value:
        raise ToolRequestRejected(category, f"{name} must not contain control characters")
    if not value or len(value) > limit:
        raise ToolRequestRejected(category, f"{name} must be 1..{limit} characters")
    return value


def _relative_path(value: object, name: str) -> str:
    path = _bounded_text(value, name, MAX_PATH_CHARS, RejectionCategory.PATH)
    parts = path.split("/")
    if path.startswith("/") or "\\" in path or any(part in ("", ".", "..") for part in parts):
        raise ToolRequestRejected(RejectionCategory.PATH, f"{name} must be a normalized relative path")
    return path


@dataclass(frozen=True)
class ReadParams:
    path: str


@dataclass(frozen=True)
class SearchParams:
    query: str
    path: str


@dataclass(frozen=True)
class ShellParams:
    argv: tuple[str, ...]
    cwd: str


@dataclass(frozen=True)
class WriteParams:
    path: str
    content: str


@dataclass(frozen=True)
class TestParams:
    """The exact empty workspace_test arguments."""


ToolParams = ReadParams | SearchParams | ShellParams | WriteParams | TestParams


@dataclass(frozen=True)
class ToolRequest:
    """One parsed, bound-checked version-1 tool call with full call identity."""

    call_id: str
    episode_id: str
    attachment_id: str
    attachment_epoch: int
    grant_epoch: int
    method: ToolMethod
    params: ToolParams

    def __post_init__(self) -> None:
        for name in ("call_id", "episode_id", "attachment_id"):
            object.__setattr__(self, name, _identity(getattr(self, name), name))
        _positive_integer(self.attachment_epoch, "attachment_epoch")
        _positive_integer(self.grant_epoch, "grant_epoch")
        if not isinstance(self.method, ToolMethod):
            raise TypeError("tool request method must be ToolMethod")
        expected = _PARAMS_BY_METHOD[self.method]
        if type(self.params) is not expected:
            raise TypeError(f"tool request params must be {expected.__name__}")


_PARAMS_BY_METHOD: dict[ToolMethod, type] = {
    ToolMethod.WORKSPACE_READ: ReadParams,
    ToolMethod.WORKSPACE_SEARCH: SearchParams,
    ToolMethod.WORKSPACE_SHELL: ShellParams,
    ToolMethod.WORKSPACE_WRITE: WriteParams,
    ToolMethod.WORKSPACE_TEST: TestParams,
}


def _parse_read(params: dict[str, object]) -> ReadParams:
    return ReadParams(path=_relative_path(params["path"], "path"))


def _parse_search(params: dict[str, object]) -> SearchParams:
    return SearchParams(
        query=_bounded_text(params["query"], "query", MAX_QUERY_CHARS, RejectionCategory.SCHEMA),
        path=_relative_path(params["path"], "path"),
    )


def _parse_shell(params: dict[str, object]) -> ShellParams:
    argv = params["argv"]
    if not isinstance(argv, list) or not argv or any(not isinstance(part, str) for part in argv):
        raise ToolRequestRejected(RejectionCategory.SCHEMA, "argv must be a non-empty JSON array of strings")
    if len(argv) > MAX_ARGV_PARTS:
        raise ToolRequestRejected(RejectionCategory.ARGV, f"argv must have at most {MAX_ARGV_PARTS} parts")
    parts = tuple(
        _bounded_text(part, f"argv[{index}]", MAX_ARGV_PART_CHARS, RejectionCategory.ARGV)
        for index, part in enumerate(argv)
    )
    if any("\\" in part or any(segment in (".", "..") for segment in part.split("/")) for part in parts):
        raise ToolRequestRejected(RejectionCategory.ARGV, "argv must not contain backslash or traversal segments")
    cwd = _bounded_text(params["cwd"], "cwd", MAX_CWD_CHARS, RejectionCategory.ARGV)
    cwd_parts = cwd.split("/")
    if cwd != "." and (cwd.startswith("/") or "\\" in cwd or any(part in ("", ".", "..") for part in cwd_parts)):
        raise ToolRequestRejected(RejectionCategory.ARGV, "cwd must be '.' or a bounded relative directory")
    return ShellParams(argv=parts, cwd=cwd)


def _parse_write(params: dict[str, object]) -> WriteParams:
    path = _relative_path(params["path"], "path")
    content = params["content"]
    if not isinstance(content, str) or "\x00" in content:
        raise ToolRequestRejected(RejectionCategory.SCHEMA, "content must be a string without NUL characters")
    if len(content) > MAX_CONTENT_CHARS:
        raise ToolRequestRejected(RejectionCategory.WRITE, f"content must be at most {MAX_CONTENT_CHARS} characters")
    return WriteParams(path=path, content=content)


def _string_keyed(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ToolRequestRejected(RejectionCategory.SCHEMA, f"{name} must be a JSON object")
    fields: dict[str, object] = {}
    for key, item in value.items():
        if type(key) is not str:
            raise ToolRequestRejected(RejectionCategory.SCHEMA, f"{name} keys must be strings")
        fields[key] = item
    return fields


def _method(value: object) -> ToolMethod:
    if not isinstance(value, str):
        raise ToolRequestRejected(RejectionCategory.SCHEMA, "method must be a string")
    try:
        return ToolMethod(value)
    except ValueError:
        raise ToolRequestRejected(RejectionCategory.UNKNOWN, "method is not a supported version-1 tool") from None


def parse_tool_request(data: object) -> ToolRequest:
    """Parse one exact version-1 envelope, rejecting extra fields and types.

    Raises :class:`ToolRequestRejected` with ``schema`` for malformed shape,
    ``unknown`` for an unsupported method, and the exact bound category for an
    oversize or malformed field. Nothing here touches an adapter or provider.
    """

    envelope = _string_keyed(data, "request envelope")
    if set(envelope) != _ENVELOPE_FIELDS:
        raise ToolRequestRejected(RejectionCategory.SCHEMA, "request requires its exact version-1 envelope fields")
    version = envelope["version"]
    if type(version) is not int or version != _SCHEMA_VERSION:
        raise ToolRequestRejected(RejectionCategory.SCHEMA, f"request version must be integer {_SCHEMA_VERSION}")
    method = _method(envelope["method"])
    raw_params = _string_keyed(envelope["params"], f"{method.value} params")
    if set(raw_params) != _PARAM_FIELDS[method]:
        raise ToolRequestRejected(
            RejectionCategory.SCHEMA,
            f"{method.value} params must have exact fields {sorted(_PARAM_FIELDS[method])}",
        )
    parsers = {
        ToolMethod.WORKSPACE_READ: _parse_read,
        ToolMethod.WORKSPACE_SEARCH: _parse_search,
        ToolMethod.WORKSPACE_SHELL: _parse_shell,
        ToolMethod.WORKSPACE_WRITE: _parse_write,
    }
    params: ToolParams = TestParams() if method is ToolMethod.WORKSPACE_TEST else parsers[method](raw_params)
    return ToolRequest(
        call_id=_identity(envelope["call_id"], "call_id"),
        episode_id=_identity(envelope["episode_id"], "episode_id"),
        attachment_id=_identity(envelope["attachment_id"], "attachment_id"),
        attachment_epoch=_positive_integer(envelope["attachment_epoch"], "attachment_epoch"),
        grant_epoch=_positive_integer(envelope["grant_epoch"], "grant_epoch"),
        method=method,
        params=params,
    )


def _strict_data(value: object, name: str) -> None:
    if value is None or type(value) in {str, bool, int}:
        if type(value) is str and len(value.encode()) > MAX_DATA_TEXT_BYTES:
            raise ValueError(f"{name} text exceeds the bounded result size")
        return
    if type(value) is list:
        for item in value:
            _strict_data(item, name)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError(f"{name} object keys must be strings")
            _strict_data(item, name)
        return
    raise TypeError(f"{name} must contain only bounded strict JSON values")


@dataclass(frozen=True)
class ToolError:
    """One rendered secret-safe error with a fixed category and bounded detail."""

    category: RejectionCategory
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.category, RejectionCategory):
            raise TypeError("tool error category must be RejectionCategory")
        object.__setattr__(self, "detail", _detail(self.detail))

    def to_data(self) -> dict[str, str]:
        return {"category": self.category.value, "detail": self.detail}


@dataclass(frozen=True)
class ToolResult:
    """The exact ``{version, ok, data, error, epoch}`` envelope plus correlation identity."""

    call_id: str
    attachment_id: str
    epoch: int
    ok: bool
    data: dict[str, object] | None
    error: ToolError | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "call_id", _identity(self.call_id, "call_id"))
        object.__setattr__(self, "attachment_id", _identity(self.attachment_id, "attachment_id"))
        _positive_integer(self.epoch, "epoch")
        if type(self.ok) is not bool:
            raise TypeError("tool result ok must be a boolean")
        if self.ok != (self.error is None) or self.ok != (self.data is not None):
            raise ValueError("a tool result carries exactly data when ok and exactly an error when not")
        if self.data is not None:
            _strict_data(self.data, "tool result data")
        if self.error is not None and not isinstance(self.error, ToolError):
            raise TypeError("tool result error must be ToolError")

    def to_data(self) -> dict[str, object]:
        return {
            "version": _SCHEMA_VERSION,
            "ok": self.ok,
            "data": self.data,
            "error": None if self.error is None else self.error.to_data(),
            "epoch": self.epoch,
            "call_id": self.call_id,
            "attachment_id": self.attachment_id,
        }

    def to_model_data(self) -> dict[str, object]:
        """Project semantic result data without host custody coordinates."""
        return {
            "version": _SCHEMA_VERSION,
            "ok": self.ok,
            "data": self.data,
            "error": None if self.error is None else self.error.to_data(),
        }


__all__ = [
    "CAPABILITY_SCOPED_HANDS",
    "MAX_ARGV_PARTS",
    "MAX_ARGV_PART_CHARS",
    "MAX_CONTENT_CHARS",
    "MAX_CWD_CHARS",
    "MAX_DATA_TEXT_BYTES",
    "MAX_PATH_CHARS",
    "MAX_QUERY_CHARS",
    "ReadParams",
    "RejectionCategory",
    "SearchParams",
    "ShellParams",
    "TestParams",
    "ToolError",
    "ToolCallConflict",
    "ToolMethod",
    "ToolParams",
    "ToolRequest",
    "ToolRequestRejected",
    "ToolResult",
    "WriteParams",
    "parse_tool_request",
]
