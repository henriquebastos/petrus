"""Call payloads and Envelope-v1 construction helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

from petrus.fabric import Envelope, ReplyRoute
from petrus.fabric.model import _exact_object, _freeze_json, _json_copy, _json_object, _text, _thaw_json


@dataclass(frozen=True)
class CallRequest:
    call_id: str
    operation: str
    input: Mapping[str, object]

    kind = "process.call.request"

    def __post_init__(self) -> None:
        object.__setattr__(self, "call_id", _text(self.call_id, "call_id"))
        object.__setattr__(self, "operation", _text(self.operation, "operation"))
        if not isinstance(self.input, dict):
            raise TypeError("input must be a JSON object")
        object.__setattr__(self, "input", _freeze_json(_json_copy(self.input, "input")))

    def to_data(self) -> dict[str, object]:
        return {
            "version": 1,
            "kind": self.kind,
            "call_id": self.call_id,
            "operation": self.operation,
            "input": _thaw_json(self.input),
        }

    @classmethod
    def from_data(cls, data: object) -> CallRequest:
        data = _exact(_thaw_json(data), cls.kind, {"version", "kind", "call_id", "operation", "input"})
        input_ = _json_object(data["input"], "input")
        return cls(_text(data["call_id"], "call_id"), _text(data["operation"], "operation"), input_)


@dataclass(frozen=True)
class CallResult:
    call_id: str
    result: object
    kind = "process.call.result"

    def __post_init__(self) -> None:
        object.__setattr__(self, "call_id", _text(self.call_id, "call_id"))
        object.__setattr__(self, "result", _freeze_json(_json_copy(self.result, "result")))

    def to_data(self) -> dict[str, object]:
        return {"version": 1, "kind": self.kind, "call_id": self.call_id, "result": _thaw_json(self.result)}

    @classmethod
    def from_data(cls, data: object) -> CallResult:
        data = _exact(_thaw_json(data), cls.kind, {"version", "kind", "call_id", "result"})
        return cls(_text(data["call_id"], "call_id"), data["result"])


@dataclass(frozen=True)
class CallError:
    call_id: str
    code: str
    message: str
    details: object = None
    kind = "process.call.error"

    def __post_init__(self) -> None:
        for name in ("call_id", "code", "message"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "details", _freeze_json(_json_copy(self.details, "details")))

    def to_data(self) -> dict[str, object]:
        return {
            "version": 1,
            "kind": self.kind,
            "call_id": self.call_id,
            "code": self.code,
            "message": self.message,
            "details": _thaw_json(self.details),
        }

    @classmethod
    def from_data(cls, data: object) -> CallError:
        data = _exact(_thaw_json(data), cls.kind, {"version", "kind", "call_id", "code", "message", "details"})
        return cls(
            _text(data["call_id"], "call_id"),
            _text(data["code"], "code"),
            _text(data["message"], "message"),
            data["details"],
        )


def _exact(data: object, kind: str, fields: set[str]) -> dict[str, object]:
    message = f"payload requires exact version-1 {kind} fields"
    data = _exact_object(data, fields, message)
    if type(data.get("version")) is not int or data["version"] != 1 or data.get("kind") != kind:
        raise ValueError(message)
    return data


def _required_reply_route(request: Envelope) -> ReplyRoute:
    route = request.reply_route
    if route is None:
        raise ValueError("call request must carry a reply route")
    return route


def _delivery_id(call_id: str, leg: str) -> str:
    digest = hashlib.sha256(call_id.encode()).hexdigest()
    return f"process-call-v1-{leg}-{digest}"


def _reply_delivery_id(caller: str, call_id: str) -> str:
    caller_bytes = caller.encode()
    digest = hashlib.sha256(len(caller_bytes).to_bytes(4, "big") + caller_bytes + call_id.encode()).hexdigest()
    return f"process-call-v1-reply-{digest}"


def request_from_envelope(envelope: Envelope) -> CallRequest:
    if not isinstance(envelope, Envelope):
        raise TypeError("call request must be an Envelope")
    request = CallRequest.from_data(envelope.payload)
    if request.call_id != envelope.correlation:
        raise ValueError("call request payload must match the envelope correlation")
    if _required_reply_route(envelope).instance_id != envelope.sender:
        raise ValueError("call request must reply to its sender process")
    return request


def reply_from_envelope(envelope: Envelope, *, request: Envelope) -> CallResult | CallError:
    """Decode a reply and bind it to the callee, route, and correlation of a request."""
    if not isinstance(envelope, Envelope):
        raise TypeError("call reply must be an Envelope")
    call = request_from_envelope(request)
    route = _required_reply_route(request)
    kind = envelope.payload.get("kind")
    if kind == CallResult.kind:
        reply: CallResult | CallError = CallResult.from_data(envelope.payload)
    elif kind == CallError.kind:
        reply = CallError.from_data(envelope.payload)
    else:
        raise ValueError("call reply payload must be a process.call.result or process.call.error")
    if reply.call_id != call.call_id or envelope.correlation != call.call_id:
        raise ValueError("call reply payload and envelope must match the request correlation")
    if envelope.sender != request.recipient or envelope.recipient != request.sender or envelope.source != route.source:
        raise ValueError("call reply must come from the request callee through the requested reply route")
    if envelope.reply_route is not None:
        raise ValueError("call reply must not carry another reply route")
    return reply


def request_envelope(
    *,
    request: CallRequest,
    sender: str,
    recipient: str,
    source: str,
    reply_route: ReplyRoute,
    delivery_id: str | None = None,
) -> Envelope:
    if not isinstance(request, CallRequest):
        raise TypeError("request must be CallRequest")
    if not isinstance(reply_route, ReplyRoute) or reply_route.instance_id != sender:
        raise ValueError("call reply_route must belong to the sender process")
    return Envelope(
        delivery_id or _delivery_id(request.call_id, "request"),
        sender,
        recipient,
        source,
        request.call_id,
        request.to_data(),
        reply_route,
    )


def result_envelope(*, result: CallResult, request: Envelope, sender: str, delivery_id: str | None = None) -> Envelope:
    if not isinstance(result, CallResult):
        raise TypeError("result must be CallResult")
    call = request_from_envelope(request)
    route = _required_reply_route(request)
    if result.call_id != call.call_id or sender != request.recipient:
        raise ValueError("call result must correlate to a request with a reply route")
    return Envelope(
        delivery_id or _reply_delivery_id(request.sender, result.call_id),
        sender,
        route.instance_id,
        route.source,
        result.call_id,
        result.to_data(),
    )


def error_envelope(*, error: CallError, request: Envelope, sender: str, delivery_id: str | None = None) -> Envelope:
    if not isinstance(error, CallError):
        raise TypeError("error must be CallError")
    call = request_from_envelope(request)
    route = _required_reply_route(request)
    if error.call_id != call.call_id or sender != request.recipient:
        raise ValueError("call error must correlate to a request with a reply route")
    return Envelope(
        delivery_id or _reply_delivery_id(request.sender, error.call_id),
        sender,
        route.instance_id,
        route.source,
        error.call_id,
        error.to_data(),
    )
