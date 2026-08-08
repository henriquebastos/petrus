"""Strict host-owned HTTP transport for one fixed bounded simulation build."""

from __future__ import annotations

import json
import ipaddress
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
import threading
from typing import cast
from urllib.parse import urlsplit

from petrus.impetus.dsl import BuiltNet
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.simulation import (
    CONNECTION_TIMEOUT_SECONDS,
    MAX_ACTIONS,
    MAX_REQUEST_BODY_BYTES,
    SimulationProfileError,
    simulate,
    simulation_profile,
)

_PROFILE_PATH = "/v1/simulation-profile"
_SIMULATIONS_PATH = "/v1/simulations"


class _RequestError(Exception):
    def __init__(self, status: HTTPStatus, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()


def _strict_loads(payload: bytes) -> object:
    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate object member")
            result[key] = value
        return result

    def constant(_: str) -> object:
        raise ValueError("non-finite number")

    try:
        text = payload.decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=object_pairs, parse_constant=constant)
        # ``loads`` accepts overflowed floats and lone surrogates. A strict,
        # UTF-8 round trip validates every nested value before it reaches a decoder.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8", errors="strict")
        return value
    except (
        UnicodeDecodeError,
        UnicodeEncodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
        MemoryError,
        OverflowError,
    ):
        raise _RequestError(HTTPStatus.BAD_REQUEST, "invalid_request", "request body must be strict JSON") from None


def _exact_json_equal(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        left_object = cast(dict[object, object], left)
        right_object = cast(dict[object, object], right)
        return left_object.keys() == right_object.keys() and all(
            _exact_json_equal(left_object[key], right_object[key]) for key in left_object
        )
    if isinstance(left, list):
        right_array = cast(list[object], right)
        return len(left) == len(right_array) and all(_exact_json_equal(a, b) for a, b in zip(left, right_array))
    return left == right


def _exact_object(value: object, fields: set[str], subject: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise _RequestError(
            HTTPStatus.BAD_REQUEST, "invalid_request", f"{subject} must contain exactly {sorted(fields)}"
        )
    return cast(dict[str, object], value)


def _decode_marking(value: object) -> Marking:  # noqa: C901 - strict field-complete wire admission
    if type(value) is not list:
        raise _RequestError(HTTPStatus.BAD_REQUEST, "invalid_request", "initial_marking must be an array")
    queues: dict[NetPath, tuple[Token, ...]] = {}
    previous: str | None = None
    for entry in value:
        item = _exact_object(entry, {"place", "tokens"}, "marking entry")
        place_name, token_values = item["place"], item["tokens"]
        if type(place_name) is not str or not place_name:
            raise _RequestError(HTTPStatus.BAD_REQUEST, "invalid_request", "marking place must be a nonempty string")
        if previous is not None and place_name <= previous:
            raise _RequestError(
                HTTPStatus.BAD_REQUEST, "invalid_request", "initial_marking places must be unique and sorted"
            )
        previous = place_name
        if type(token_values) is not list or not token_values:
            raise _RequestError(
                HTTPStatus.BAD_REQUEST, "invalid_request", "marking token queues must be nonempty arrays"
            )
        try:
            path = NetPath(place_name)
        except ValueError:
            raise _RequestError(HTTPStatus.BAD_REQUEST, "invalid_request", "marking place is invalid") from None
        tokens = []
        for token_value in token_values:
            token_object = _exact_object(token_value, {"color", "data"}, "token")
            color = token_object["color"]
            if color is not None and (type(color) is not str or not color):
                raise _RequestError(
                    HTTPStatus.BAD_REQUEST, "invalid_request", "token color must be null or nonempty string"
                )
            tokens.append(Token(color, token_object["data"]))
        queues[path] = tuple(tokens)
    return Marking(queues)


class SimulationHTTPServer(ThreadingHTTPServer):
    """An inert server over one immutable admitted build; its application owns lifecycle."""

    daemon_threads = False
    block_on_close = True

    def __init__(self, address: tuple[str, int], built: BuiltNet, allowed_origin: str, profile: dict[str, object]):
        self._built = built
        self._allowed_origin = allowed_origin
        self._profile_bytes = _encoded(profile)
        self._definition = _strict_loads(_encoded(profile["definition"]))
        self._slot = threading.BoundedSemaphore(1)
        self._admission_lock = threading.Lock()
        self._shutting_down = False
        super().__init__(address, _SimulationHandler)

    @property
    def profile(self) -> dict[str, object]:
        return cast(dict[str, object], _strict_loads(self._profile_bytes))

    def acquire_simulation(self) -> str:
        """Linearize draining and one-slot admission without holding the lock during work."""
        with self._admission_lock:
            if self._shutting_down:
                return "shutting_down"
            return "acquired" if self._slot.acquire(blocking=False) else "busy"

    def shutdown(self) -> None:
        with self._admission_lock:
            self._shutting_down = True
        super().shutdown()


class _SimulationHandler(BaseHTTPRequestHandler):
    server: SimulationHTTPServer
    protocol_version = "HTTP/1.0"
    _raw_target = ""

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(CONNECTION_TIMEOUT_SECONDS)

    def parse_request(self) -> bool:
        """Retain the request-line target before the stdlib normalizes leading `//`."""
        parts = self.raw_requestline.decode("iso-8859-1").rstrip("\r\n").split()
        self._raw_target = parts[1] if len(parts) >= 2 else ""
        return super().parse_request()

    def __getattr__(self, name: str):
        if name.startswith("do_"):
            return lambda: self._dispatch(name[3:])
        raise AttributeError(name)

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._dispatch("OPTIONS")

    def do_HEAD(self) -> None:  # noqa: N802
        self._dispatch("HEAD")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def _dispatch(self, method: str) -> None:  # noqa: C901
        self.close_connection = True
        try:
            origins = self.headers.get_all("Origin", failobj=[])
            if len(origins) != 1 or origins[0] != self.server._allowed_origin:
                raise _RequestError(HTTPStatus.FORBIDDEN, "origin_not_allowed", "origin is not allowed")
            if (
                not self._raw_target.startswith("/")
                or self._raw_target.startswith("//")
                or "?" in self._raw_target
                or "#" in self._raw_target
            ):
                raise _RequestError(
                    HTTPStatus.BAD_REQUEST, "invalid_request", "an origin-form path without query is required"
                )
            allow = self._allow(self._raw_target)
            if allow is None:
                raise _RequestError(HTTPStatus.NOT_FOUND, "not_found", "route not found")
            if method not in allow.split(", "):
                self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed", "method not allowed", allow=allow)
                return
            if method == "OPTIONS":
                self._respond(HTTPStatus.NO_CONTENT, b"", allow=allow)
            elif self._raw_target == _PROFILE_PATH:
                self._respond(HTTPStatus.OK, self.server._profile_bytes, content_type=True)
            else:
                self._simulation()
        except _RequestError as error:
            self._error(error.status, error.code, error.message)
        except ConnectionError, TimeoutError:
            pass
        except Exception:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "internal server error")

    @staticmethod
    def _allow(path: str) -> str | None:
        if path == _PROFILE_PATH:
            return "GET, OPTIONS"
        if path == _SIMULATIONS_PATH:
            return "POST, OPTIONS"
        return None

    def _body(self) -> bytes:
        if self.headers.get("Expect") is not None:
            raise _RequestError(HTTPStatus.BAD_REQUEST, "invalid_request", "Expect is not supported")
        if self.headers.get("Transfer-Encoding") is not None or self.headers.get("Content-Encoding") is not None:
            raise _RequestError(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "unsupported_media_type", "encoded bodies are not supported"
            )
        media_values = self.headers.get_all("Content-Type", failobj=[])
        if len(media_values) != 1:
            raise _RequestError(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "unsupported_media_type", "application/json is required"
            )
        media = media_values[0]
        parts = [part.strip().lower() for part in media.split(";")]
        if parts[0] != "application/json" or any(part != "charset=utf-8" for part in parts[1:]) or len(parts) > 2:
            raise _RequestError(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "unsupported_media_type", "application/json utf-8 is required"
            )
        lengths = self.headers.get_all("Content-Length", failobj=[])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            raise _RequestError(
                HTTPStatus.LENGTH_REQUIRED, "length_required", "exactly one valid Content-Length is required"
            )
        lexical = lengths[0].lstrip("0") or "0"
        maximum = str(MAX_REQUEST_BODY_BYTES)
        if len(lexical) > len(maximum) or (len(lexical) == len(maximum) and lexical > maximum):
            raise _RequestError(HTTPStatus.CONTENT_TOO_LARGE, "payload_too_large", "request body exceeds 1048576 bytes")
        length = int(lexical)
        try:
            body = self.rfile.read(length)
        except TimeoutError:
            self.close_connection = True
            raise _RequestError(
                HTTPStatus.BAD_REQUEST, "invalid_request", "request body is shorter than Content-Length"
            ) from None
        if len(body) != length:
            self.close_connection = True
            raise _RequestError(
                HTTPStatus.BAD_REQUEST, "invalid_request", "request body is shorter than Content-Length"
            )
        return body

    def _simulation(self) -> None:
        request = _exact_object(
            _strict_loads(self._body()), {"expected_definition", "initial_marking", "max_actions"}, "request"
        )
        expected_definition = request["expected_definition"]
        if type(expected_definition) is not dict:
            raise _RequestError(HTTPStatus.BAD_REQUEST, "invalid_request", "expected_definition must be an object")
        marking = _decode_marking(request["initial_marking"])
        maximum = request["max_actions"]
        if isinstance(maximum, bool) or type(maximum) is not int or not 1 <= maximum <= MAX_ACTIONS:
            raise _RequestError(
                HTTPStatus.BAD_REQUEST, "invalid_request", "max_actions must be an integer from 1 through 256"
            )
        if not _exact_json_equal(expected_definition, self.server._definition):
            raise _RequestError(
                HTTPStatus.CONFLICT, "definition_mismatch", "expected definition does not match fixed definition"
            )
        admission = self.server.acquire_simulation()
        if admission == "shutting_down":
            raise _RequestError(HTTPStatus.SERVICE_UNAVAILABLE, "server_shutting_down", "server is shutting down")
        if admission == "busy":
            raise _RequestError(HTTPStatus.TOO_MANY_REQUESTS, "simulation_busy", "another simulation is running")
        try:
            try:
                result = simulate(self.server._built, marking, max_actions=maximum)
            except SimulationProfileError:
                raise _RequestError(
                    HTTPStatus.UNPROCESSABLE_ENTITY, "simulation_rejected", "simulation was rejected"
                ) from None
        finally:
            self.server._slot.release()
        self._respond(HTTPStatus.OK, result, content_type=True)

    def _error(self, status: HTTPStatus, code: str, message: str, *, allow: str | None = None) -> None:
        try:
            self._respond(
                status, _encoded({"error": {"code": code, "message": message}}), content_type=True, allow=allow
            )
        except ConnectionError, TimeoutError:
            pass

    def _respond(
        self, status: HTTPStatus, body: bytes, *, content_type: bool = False, allow: str | None = None
    ) -> None:
        self.send_response(status)
        if content_type:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", self.server._allowed_origin)
        self.send_header("Vary", "Origin")
        if allow is not None:
            self.send_header("Allow", allow)
            self.send_header("Access-Control-Allow-Methods", allow)
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        if body and self.command != "HEAD":
            try:
                self.wfile.write(body)
            except ConnectionError, TimeoutError:
                pass

    def log_message(self, format: str, *args: object) -> None:
        """Leave access logging to the application."""


def _validate_origin(origin: str) -> str:
    if (
        type(origin) is not str
        or origin in {"*", "null"}
        or any(character.isspace() or ord(character) < 32 for character in origin)
    ):
        raise ValueError("allowed_origin must be one exact absolute HTTP(S) origin")
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("allowed_origin must be one exact absolute HTTP(S) origin without path, query, or fragment")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("allowed_origin must not contain user information")
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("allowed_origin port must be in range") from None
    if parsed.hostname is None or (port is not None and not 1 <= port <= 65535) or parsed.netloc.endswith(":"):
        raise ValueError("allowed_origin must contain a hostname and valid port")
    _validate_hostname(parsed.netloc, parsed.hostname, port)
    if origin != f"{parsed.scheme}://{parsed.netloc}":
        raise ValueError("allowed_origin must be an exactly serialized web origin")
    return origin


def _validate_hostname(netloc: str, hostname: str, port: int | None) -> None:
    """Accept a conservative canonical DNS, IPv4, or bracketed IPv6 authority."""
    if netloc.startswith("["):
        closing = netloc.find("]")
        authority = netloc[: closing + 1] if closing >= 0 else netloc
    else:
        authority = netloc.rsplit(":", 1)[0] if port is not None else netloc
    if any(character in netloc for character in ("%", "\\", ",")) or not hostname.isascii():
        raise ValueError("allowed_origin contains an invalid host")
    if authority.startswith("["):
        if not authority.endswith("]"):
            raise ValueError("allowed_origin contains an invalid host")
        try:
            ipaddress.IPv6Address(hostname)
        except ValueError:
            raise ValueError("allowed_origin contains an invalid host") from None
    else:
        try:
            ipaddress.IPv4Address(hostname)
        except ValueError:
            labels = hostname.split(".")
            if len(hostname) > 253 or any(
                not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels
            ):
                raise ValueError("allowed_origin contains an invalid host") from None


def create_simulation_server(built: BuiltNet, host: str, port: int, *, allowed_origin: str) -> SimulationHTTPServer:
    """Admit and capture the fixed build, then bind an inert application-owned server."""
    origin = _validate_origin(allowed_origin)
    profile = simulation_profile(built)
    return SimulationHTTPServer((host, port), built, origin, profile)


__all__ = ["CONNECTION_TIMEOUT_SECONDS", "MAX_REQUEST_BODY_BYTES", "SimulationHTTPServer", "create_simulation_server"]
