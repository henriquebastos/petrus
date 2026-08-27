"""Host-owned standard-library HTTP binding for observation protocol 1."""

from __future__ import annotations

import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlsplit

if TYPE_CHECKING:
    from petrus.engine import Engine

MAX_HISTORY_PAGE_LIMIT = 1000
_DECIMAL = re.compile(r"[0-9]+\Z")
_CORS_HEADERS = (
    ("Access-Control-Allow-Origin", "*"),
    ("Access-Control-Allow-Methods", "GET, OPTIONS"),
    ("Access-Control-Allow-Headers", "Content-Type"),
)


class ObservationHTTPServer(ThreadingHTTPServer):
    """An HTTP server bound to one Engine without owning its lifecycle."""

    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], engine: Engine):
        self.engine = engine
        super().__init__(server_address, _ObservationHandler)


class _ObservationHandler(BaseHTTPRequestHandler):
    server: ObservationHTTPServer

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        try:
            target = urlsplit(self.path)
            if target.path == "/v1/snapshot":
                if target.query:
                    raise ValueError("snapshot does not accept query parameters")
                self._json(HTTPStatus.OK, self.server.engine.snapshot())
                return
            if target.path == "/v1/document":
                if target.query:
                    raise ValueError("document does not accept query parameters")
                self._json(HTTPStatus.OK, self.server.engine.net_document())
                return
            if target.path == "/v1/history":
                after, limit = self._history_query(target.query)
                self._json(HTTPStatus.OK, self.server.engine.history_page(after, limit))
                return
            self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
        except ValueError as error:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(error))
        except RuntimeError:
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "engine_unavailable", "Engine is unavailable")
        except BrokenPipeError, ConnectionResetError:
            pass
        except Exception:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "internal server error")

    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._respond(HTTPStatus.NO_CONTENT, b"", content_type=None, allow="GET, OPTIONS")

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._method_not_allowed()

    def do_PUT(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._method_not_allowed()

    def do_PATCH(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._method_not_allowed()

    def do_DELETE(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._method_not_allowed()

    def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._method_not_allowed()

    def _method_not_allowed(self) -> None:
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed", "method not allowed", allow="GET, OPTIONS")

    @staticmethod
    def _history_query(query: str) -> tuple[int, int]:
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True)
        values: dict[str, str] = {}
        for name, value in pairs:
            if name not in {"after", "limit"}:
                raise ValueError(f"unknown history query parameter: {name or '<empty>'}")
            if name in values:
                raise ValueError(f"history query parameter {name} must appear exactly once")
            values[name] = value
        for name in ("after", "limit"):
            if name not in values:
                raise ValueError(f"history query parameter {name} is required exactly once")
            if not _DECIMAL.fullmatch(values[name]):
                raise ValueError(f"history query parameter {name} must be a non-empty unsigned decimal integer")
        after, limit = int(values["after"]), int(values["limit"])
        if limit > MAX_HISTORY_PAGE_LIMIT:
            raise ValueError(f"history limit must not exceed adapter maximum {MAX_HISTORY_PAGE_LIMIT}")
        return after, limit

    def _json(self, status: HTTPStatus, value: object, *, allow: str | None = None) -> None:
        encoded = json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()
        self._respond(status, encoded, content_type="application/json; charset=utf-8", allow=allow)

    def _error(self, status: HTTPStatus, code: str, message: str, *, allow: str | None = None) -> None:
        try:
            self._json(status, {"error": {"code": code, "message": message}}, allow=allow)
        except BrokenPipeError, ConnectionResetError:
            pass

    def _respond(
        self,
        status: HTTPStatus,
        body: bytes,
        *,
        content_type: str | None,
        allow: str | None = None,
    ) -> None:
        self.send_response(status)
        if content_type is not None:
            self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in _CORS_HEADERS:
            self.send_header(name, value)
        if allow is not None:
            self.send_header("Allow", allow)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Leave access logging to the application host."""


def create_observation_server(engine: Engine, host: str, port: int) -> ObservationHTTPServer:
    """Bind an inert server; the application owns serving, shutdown, and close."""
    return ObservationHTTPServer((host, port), engine)


__all__ = ["MAX_HISTORY_PAGE_LIMIT", "ObservationHTTPServer", "create_observation_server"]
