"""Real-HTTP evidence for the host-owned protocol-1 observation adapter."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from petrus.engine import Engine
from petrus.engine.observation_http import MAX_HISTORY_PAGE_LIMIT, create_observation_server
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Arc, Marking, Net, NetPath, Place, Token, Transition
from petrus.motus.dispatch import InMemoryDispatch

A, B, MOVE = NetPath("a"), NetPath("b"), NetPath("move")


def make_engine() -> Engine:
    return Engine.create(
        Net([Place(A), Place(B)], [Transition(MOVE)], [Arc(A, MOVE), Arc(MOVE, B)], name="http-observation"),
        "http-instance",
        history=InMemoryHistoryStore(),
        dispatch=InMemoryDispatch(),
        marking=Marking({A: (Token("value", {"n": 1}),)}),
    )


@contextmanager
def serving(engine: Engine):
    server = create_observation_server(engine, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def request(url: str, *, method: str = "GET") -> tuple[int, dict[str, str], object]:
    try:
        response = urlopen(Request(url, method=method))
    except HTTPError as error:
        response = error
    with response:
        body = response.read()
        return response.status, dict(response.headers.items()), json.loads(body) if body else None


def test_factory_binds_without_starting_a_hidden_thread():
    engine = make_engine()
    before = set(threading.enumerate())
    server = create_observation_server(engine, "127.0.0.1", 0)
    try:
        assert set(threading.enumerate()) == before
    finally:
        server.server_close()
        engine.close()


def test_snapshot_history_and_required_http_headers_are_exact():
    engine = make_engine()
    expected_snapshot = engine.snapshot()
    expected_history = engine.history_page(0, 100)
    with serving(engine) as base:
        status, headers, snapshot = request(f"{base}/v1/snapshot")
        assert (status, snapshot) == (200, expected_snapshot)
        assert headers["Content-Type"] == "application/json; charset=utf-8"
        assert headers["Cache-Control"] == "no-store"
        assert headers["Access-Control-Allow-Origin"] == "*"
        assert headers["Access-Control-Allow-Methods"] == "GET, OPTIONS"
        assert headers["Access-Control-Allow-Headers"] == "Content-Type"
        encoded = json.dumps(snapshot, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()
        assert int(headers["Content-Length"]) == len(encoded)
        history_status, _, history = request(f"{base}/v1/history?after=0&limit=100")
        assert (history_status, history) == (200, expected_history)
    engine.close()


@pytest.mark.parametrize(
    "query",
    [
        "",
        "after=0",
        "limit=1",
        "after=0&after=1&limit=1",
        "after=0&limit=1&extra=1",
        "after=&limit=1",
        "after=+1&limit=1",
        "after=%201&limit=1",
        "after=-1&limit=1",
        "after=1.0&limit=1",
        f"after=0&limit={MAX_HISTORY_PAGE_LIMIT + 1}",
    ],
)
def test_history_query_grammar_is_exact(query):
    engine = make_engine()
    with serving(engine) as base:
        status, _, payload = request(f"{base}/v1/history?{query}")
        assert status == 400
        assert payload["error"]["code"] == "invalid_request"
    engine.close()


def test_future_cursor_is_a_protocol_400():
    engine = make_engine()
    with serving(engine) as base:
        status, _, payload = request(f"{base}/v1/history?after=999&limit=1")
        assert (status, payload["error"]["code"]) == (400, "invalid_request")
    engine.close()


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_mutation_methods_are_405_and_never_reach_engine(method):
    engine = make_engine()
    before = engine.history_page(0, 100)
    with serving(engine) as base:
        status, headers, payload = request(f"{base}/v1/snapshot", method=method)
        assert (status, headers["Allow"], payload["error"]["code"]) == (405, "GET, OPTIONS", "method_not_allowed")
        assert engine.history_page(0, 100) == before
    engine.close()


def test_unknown_route_options_and_closed_engine():
    engine = make_engine()
    with serving(engine) as base:
        assert request(f"{base}/unknown")[0] == 404
        status, headers, body = request(f"{base}/v1/snapshot", method="OPTIONS")
        assert (status, body, headers["Allow"]) == (204, None, "GET, OPTIONS")
        assert headers["Access-Control-Allow-Origin"] == "*"
        engine.close()
        status, _, payload = request(f"{base}/v1/snapshot")
        assert (status, payload) == (503, {"error": {"code": "engine_unavailable", "message": "Engine is unavailable"}})


def test_transport_shutdown_does_not_close_engine_and_engine_keeps_executing():
    engine = make_engine()
    with serving(engine) as base:
        assert request(f"{base}/v1/snapshot")[0] == 200
    assert engine.advance().ready
    assert engine.snapshot()["current"]["marking"][0]["place"] == "b"
    engine.close()
