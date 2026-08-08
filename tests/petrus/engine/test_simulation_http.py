"""Focused real-HTTP evidence for the fixed bounded simulation transport."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from http import HTTPStatus
import json
from pathlib import Path
import socket
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from tests.simulation_support import build_scenario
from petrus.engine import Engine
from petrus.impetus.observation import marking as project_marking
from petrus.simulation import SimulationProfileError, simulate, simulation_profile
from petrus.simulation_http import create_simulation_server
import petrus.simulation_http as simulation_http

ORIGIN = "http://localhost:5173"
FIXTURE = Path("spec/observation/simulation-service-profile-v1.json")


@contextmanager
def serving():
    built, marking = build_scenario()
    server = create_simulation_server(built, "127.0.0.1", 0, allowed_origin=ORIGIN)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01))
    thread.start()
    try:
        yield server, built, marking, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def request(url: str, *, method: str = "GET", body: bytes | None = None, origin: str = ORIGIN):
    headers = {"Origin": origin}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        response = urlopen(Request(url, method=method, data=body, headers=headers))
    except HTTPError as error:
        response = error
    with response:
        return response.status, dict(response.headers.items()), response.read()


def raw(server, payload: bytes) -> bytes:
    with socket.create_connection(server.server_address, timeout=2) as client:
        client.sendall(payload)
        client.shutdown(socket.SHUT_WR)
        chunks = []
        while chunk := client.recv(65_536):
            chunks.append(chunk)
    return b"".join(chunks)


def raw_parts(server, payload: bytes) -> tuple[int, dict[str, str], bytes]:
    response = raw(server, payload)
    head, body = response.split(b"\r\n\r\n", 1)
    lines = head.decode("iso-8859-1").split("\r\n")
    return int(lines[0].split()[1]), dict(line.split(": ", 1) for line in lines[1:]), body


def post_body(server, marking: list[object] | None = None, *, definition: object | None = None) -> bytes:
    return json.dumps(
        {
            "expected_definition": server.profile["definition"] if definition is None else definition,
            "initial_marking": [] if marking is None else marking,
            "max_actions": 1,
        },
        separators=(",", ":"),
    ).encode()


def raw_post(server, body: bytes, *, extra: str = "") -> bytes:
    return (
        f"POST /v1/simulations HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\n"
        f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n{extra}\r\n"
    ).encode() + body


def test_profile_fixture_and_factory_admission_precede_bind_and_engine(monkeypatch) -> None:
    built, _ = build_scenario()
    expected = json.loads(FIXTURE.read_bytes())
    assert simulation_profile(built) == expected
    monkeypatch.setattr(Engine, "create", lambda *args, **kwargs: pytest.fail("Engine.create reached"))
    server = create_simulation_server(built, "127.0.0.1", 0, allowed_origin=ORIGIN)
    server.server_close()


def test_profile_routes_cors_options_and_origin_are_exact() -> None:
    with serving() as (server, _, _, base):
        status, headers, body = request(f"{base}/v1/simulation-profile")
        assert (status, json.loads(body)) == (200, server.profile)
        assert headers["Access-Control-Allow-Origin"] == ORIGIN
        assert headers["Vary"] == "Origin"
        status, headers, body = request(f"{base}/v1/simulation-profile", method="OPTIONS")
        assert (status, body, headers["Allow"]) == (204, b"", "GET, OPTIONS")
        assert headers["Access-Control-Allow-Methods"] == "GET, OPTIONS"
        assert request(f"{base}/v1/simulations", method="GET")[0] == 405
        assert request(f"{base}/unknown")[0] == 404
        assert request(f"{base}/v1/simulation-profile?x=1")[0] == 400
        assert request(f"{base}/v1/simulation-profile", origin="http://other.test")[0] == 403


def test_profile_property_is_detached_and_head_and_extension_methods_have_no_body() -> None:
    with serving() as (server, _, _, base):
        changed = server.profile
        changed["bounds"]["actions"] = 0
        assert request(f"{base}/v1/simulation-profile")[2] == server._profile_bytes
        for method in ("HEAD", "TRACE", "FROBNICATE"):
            response = raw(
                server,
                f"{method} /v1/simulation-profile HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\n\r\n".encode(),
            )
            headers, body = response.split(b"\r\n\r\n", 1)
            assert b" 405 " in headers
            assert (
                body == b""
                if method == "HEAD"
                else json.loads(body) == {"error": {"code": "method_not_allowed", "message": "method not allowed"}}
            )


def test_success_is_exact_direct_simulate_bytes() -> None:
    with serving() as (server, built, marking, base):
        direct = simulate(built, marking, max_actions=32)
        payload = json.dumps(
            {
                "expected_definition": server.profile["definition"],
                "initial_marking": project_marking(marking),
                "max_actions": 32,
            },
            separators=(",", ":"),
        ).encode()
        status, _, body = request(f"{base}/v1/simulations", method="POST", body=payload)
        assert (status, body) == (200, direct)


@pytest.mark.parametrize(
    ("body", "status"),
    [
        (b"{", 400),
        (b'{"expected_definition":{},"initial_marking":[],"max_actions":NaN}', 400),
        (b'{"expected_definition":{},"expected_definition":{},"initial_marking":[],"max_actions":1}', 400),
        (b'{"expected_definition":{},"initial_marking":[],"max_actions":true}', 400),
        (b'{"expected_definition":{},"initial_marking":[],"max_actions":1}', 409),
    ],
)
def test_strict_json_schema_types_and_definition_mismatch(body: bytes, status: int) -> None:
    with serving() as (_, _, _, base):
        actual, _, response = request(f"{base}/v1/simulations", method="POST", body=body)
        assert actual == status
        assert set(json.loads(response)) == {"error"}


@pytest.mark.parametrize(
    "bad_value",
    [b'{"nested":{"x":1,"x":2}}', b'{"nested":1e400}', b'{"nested":"\\ud800"}'],
)
def test_nested_non_strict_json_is_400_before_simulation(monkeypatch, bad_value: bytes) -> None:
    monkeypatch.setattr(simulation_http, "simulate", lambda *args, **kwargs: pytest.fail("simulate reached"))
    body = b'{"expected_definition":{},"initial_marking":[],"max_actions":1,"extra":' + bad_value + b"}"
    with serving() as (_, _, _, base):
        assert request(f"{base}/v1/simulations", method="POST", body=body)[0] == 400


@pytest.mark.parametrize("expected", [1, 1.0, True])
def test_expected_definition_must_be_exact_object(expected: object) -> None:
    body = json.dumps({"expected_definition": expected, "initial_marking": [], "max_actions": 1}).encode()
    with serving() as (_, _, _, base):
        assert request(f"{base}/v1/simulations", method="POST", body=body)[0] == 400


def test_foreign_place_is_structural_and_unexpected_producer_failure_does_not_leak(monkeypatch) -> None:
    with serving() as (server, _, _, base):
        body = json.dumps(
            {
                "expected_definition": server.profile["definition"],
                "initial_marking": [{"place": "foreign", "tokens": [{"color": None, "data": None}]}],
                "max_actions": 1,
            }
        ).encode()
        assert request(f"{base}/v1/simulations", method="POST", body=body)[0] == 422
        monkeypatch.setattr(
            simulation_http, "simulate", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("secret"))
        )
        body = json.dumps(
            {"expected_definition": server.profile["definition"], "initial_marking": [], "max_actions": 1}
        ).encode()
        status, _, response = request(f"{base}/v1/simulations", method="POST", body=body)
        assert status == 500
        assert response == b'{"error":{"code":"internal_error","message":"internal server error"}}'


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ("", b" 415 "),
        ("Content-Type: application/json\r\n", b" 411 "),
        ("Content-Type: application/json\r\nContent-Length: 1, 2\r\n", b" 411 "),
        ("Content-Type: application/json\r\nContent-Length: 999999999999999999999999\r\n", b" 413 "),
        ("Content-Type: application/json\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n", b" 415 "),
        ("Content-Type: application/json\r\nContent-Length: 0\r\nContent-Encoding: gzip\r\n", b" 415 "),
        ("Content-Type: application/json\r\nContent-Type: application/json\r\nContent-Length: 0\r\n", b" 415 "),
        ("Content-Type: application/json\r\nContent-Length: 0\r\nExpect: 100-continue\r\n", b" 400 "),
    ],
)
def test_raw_framing_refusals(headers: str, status: bytes) -> None:
    with serving() as (server, _, _, _):
        response = raw(
            server,
            f"POST /v1/simulations HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\n{headers}\r\n".encode(),
        )
        assert status in response.split(b"\r\n", 1)[0]


@pytest.mark.parametrize("origin", ["*", "null", "file://host", "https://example.test/path", "relative"])
def test_allowed_origin_is_one_exact_absolute_web_origin(origin: str) -> None:
    built, _ = build_scenario()
    with pytest.raises(ValueError, match="allowed_origin"):
        create_simulation_server(built, "127.0.0.1", 0, allowed_origin=origin)


def test_one_slot_refuses_overlap_then_releases_after_success_and_profile_error(monkeypatch) -> None:
    entered, release = threading.Event(), threading.Event()
    calls = 0

    def held(*args, **kwargs):
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(2)
        return b"{}"

    monkeypatch.setattr(simulation_http, "simulate", held)
    with serving() as (server, _, _, base):
        body = post_body(server)
        first_result: list[tuple[int, dict[str, str], bytes]] = []
        first = threading.Thread(
            target=lambda: first_result.append(request(f"{base}/v1/simulations", method="POST", body=body))
        )
        first.start()
        assert entered.wait(2)
        status, _, response = request(f"{base}/v1/simulations", method="POST", body=body)
        assert (status, response, calls) == (
            429,
            b'{"error":{"code":"simulation_busy","message":"another simulation is running"}}',
            1,
        )
        release.set()
        first.join(2)
        assert not first.is_alive()
        assert (first_result[0][0], first_result[0][2]) == (200, b"{}")
        assert request(f"{base}/v1/simulations", method="POST", body=body)[0] == 200
        assert calls == 2

        monkeypatch.setattr(
            simulation_http, "simulate", lambda *args, **kwargs: (_ for _ in ()).throw(SimulationProfileError("x"))
        )
        assert request(f"{base}/v1/simulations", method="POST", body=body)[0:3:2] == (
            422,
            b'{"error":{"code":"simulation_rejected","message":"simulation was rejected"}}',
        )
        monkeypatch.setattr(simulation_http, "simulate", lambda *args, **kwargs: b"{}")
        assert request(f"{base}/v1/simulations", method="POST", body=body)[0] == 200


def test_slot_is_released_before_response_write(monkeypatch) -> None:
    reached_response = threading.Event()
    original = simulation_http._SimulationHandler._respond

    def checked_respond(self, status, body, **kwargs):
        if status == HTTPStatus.OK and self.command == "POST":
            assert self.server._slot.acquire(blocking=False)
            self.server._slot.release()
            reached_response.set()
        return original(self, status, body, **kwargs)

    monkeypatch.setattr(simulation_http, "simulate", lambda *args, **kwargs: b"{}")
    monkeypatch.setattr(simulation_http._SimulationHandler, "_respond", checked_respond)
    with serving() as (server, _, _, _):
        client = socket.create_connection(server.server_address, timeout=2)
        client.sendall(raw_post(server, post_body(server)))
        client.close()
        assert reached_response.wait(2)
        assert raw_parts(server, raw_post(server, post_body(server)))[0] == 200


def test_shutdown_and_close_wait_for_active_simulation(monkeypatch) -> None:
    entered, release = threading.Event(), threading.Event()

    def held(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return b"{}"

    monkeypatch.setattr(simulation_http, "simulate", held)
    built, _ = build_scenario()
    server = create_simulation_server(built, "127.0.0.1", 0, allowed_origin=ORIGIN)
    serving_thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01))
    serving_thread.start()
    client_thread = threading.Thread(target=lambda: raw(server, raw_post(server, post_body(server))))
    client_thread.start()
    assert entered.wait(2)
    closed = threading.Event()

    def close() -> None:
        server.shutdown()
        server.server_close()
        closed.set()

    close_thread = threading.Thread(target=close)
    close_thread.start()
    assert not closed.wait(0.2)
    release.set()
    close_thread.join(3)
    client_thread.join(3)
    serving_thread.join(3)
    assert (
        closed.is_set()
        and not close_thread.is_alive()
        and not client_thread.is_alive()
        and not serving_thread.is_alive()
    )


def test_partial_body_times_out_without_simulation_or_close_deadlock(monkeypatch) -> None:
    monkeypatch.setattr(simulation_http, "simulate", lambda *args, **kwargs: pytest.fail("simulate reached"))
    built, _ = build_scenario()
    server = create_simulation_server(built, "127.0.0.1", 0, allowed_origin=ORIGIN)
    monkeypatch.setattr(simulation_http, "CONNECTION_TIMEOUT_SECONDS", 0.1)
    serving_thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01))
    serving_thread.start()
    client = socket.create_connection(server.server_address, timeout=2)
    client.sendall(
        f"POST /v1/simulations HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{{".encode()
    )
    client.settimeout(2)
    response = b""
    while chunk := client.recv(65_536):
        response += chunk
    assert b" 400 " in response.split(b"\r\n", 1)[0]
    client.close()
    server.shutdown()
    close_thread = threading.Thread(target=server.server_close)
    close_thread.start()
    close_thread.join(2)
    serving_thread.join(2)
    assert not close_thread.is_alive() and not serving_thread.is_alive()


@pytest.mark.parametrize(
    ("length", "status", "code"),
    [
        ("+1", 411, "length_required"),
        ("-1", 411, "length_required"),
        ("1 0", 411, "length_required"),
        ("1 ", 411, "length_required"),
        ("1, 1", 411, "length_required"),
        ("1048577", 413, "payload_too_large"),
        ("999999999999999999999999999", 413, "payload_too_large"),
    ],
)
def test_content_length_lexemes_have_exact_errors(length: str, status: int, code: str) -> None:
    with serving() as (server, _, _, _):
        payload = (
            f"POST /v1/simulations HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\n"
            f"Content-Type: application/json\r\nContent-Length:{length}\r\n\r\n"
        ).encode()
        actual, _, body = raw_parts(server, payload)
        assert (actual, json.loads(body)["error"]["code"]) == (status, code)


def test_duplicate_headers_targets_short_body_and_pipeline_are_closed_exactly() -> None:
    with serving() as (server, _, _, _):
        cases = [
            (
                f"GET /v1/simulation-profile HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\nOrigin: {ORIGIN}\r\n\r\n",
                403,
                "origin_not_allowed",
            ),
            (
                f"POST /v1/simulations HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\nContent-Type: application/json\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n",
                411,
                "length_required",
            ),
            (
                f"POST /v1/simulations HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\nContent-Type: application/json\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n",
                415,
                "unsupported_media_type",
            ),
            (
                f"POST /v1/simulations HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\nContent-Type: application/json\r\nContent-Type: application/json\r\nContent-Length: 0\r\n\r\n",
                415,
                "unsupported_media_type",
            ),
            (
                f"POST /v1/simulations HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\nContent-Type: application/json\r\nContent-Length: 1\r\nExpect: x\r\n\r\nx",
                400,
                "invalid_request",
            ),
            (
                f"GET http://test/v1/simulation-profile HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\n\r\n",
                400,
                "invalid_request",
            ),
            (
                f"GET http://[x]/v1/simulation-profile HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\n\r\n",
                400,
                "invalid_request",
            ),
            (
                f"GET //v1/simulation-profile HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\n\r\n",
                400,
                "invalid_request",
            ),
            (
                f"GET /v1/simulation-profile#x HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\n\r\n",
                400,
                "invalid_request",
            ),
        ]
        for payload, status, code in cases:
            actual, _, body = raw_parts(server, payload.encode())
            assert (actual, json.loads(body)["error"]["code"]) == (status, code)
        short = raw_parts(server, raw_post(server, b"{", extra="Content-Length: 2\r\n"))
        assert (short[0], json.loads(short[2])["error"]["code"]) == (411, "length_required")
        pipeline = raw(
            server,
            f"GET /v1/simulation-profile HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\n\r\nGET /v1/simulation-profile HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\n\r\n".encode(),
        )
        assert pipeline.count(b"HTTP/1.0 200 OK") == 1


def test_short_body_is_exact_400() -> None:
    with serving() as (server, _, _, _):
        payload = f"POST /v1/simulations HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{{".encode()
        status, _, body = raw_parts(server, payload)
        assert (status, json.loads(body)["error"]["code"]) == (400, "invalid_request")


@pytest.mark.parametrize("color", [1, ""])
def test_malformed_color_is_400_before_simulation(monkeypatch, color: object) -> None:
    monkeypatch.setattr(simulation_http, "simulate", lambda *args, **kwargs: pytest.fail("simulate reached"))
    marking = [{"place": "pending", "tokens": [{"color": color, "data": {"priority": 1}}]}]
    with serving() as (server, _, _, base):
        status, _, body = request(f"{base}/v1/simulations", method="POST", body=post_body(server, marking))
        assert (status, json.loads(body)["error"]["code"]) == (400, "invalid_request")


def test_typed_color_mismatch_and_runner_resource_rejection_are_422(monkeypatch) -> None:
    mismatch = [{"place": "pending", "tokens": [{"color": "Other", "data": {"priority": 1}}]}]
    with serving() as (server, _, _, base):
        assert request(f"{base}/v1/simulations", method="POST", body=post_body(server, mismatch))[0] == 422
        monkeypatch.setattr(
            simulation_http,
            "simulate",
            lambda *args, **kwargs: (_ for _ in ()).throw(SimulationProfileError("resource")),
        )
        status, _, body = request(f"{base}/v1/simulations", method="POST", body=post_body(server))
        assert (status, json.loads(body)["error"]["code"]) == (422, "simulation_rejected")


@pytest.mark.parametrize("replacement", [1.0, True])
def test_nested_definition_number_type_mismatch_is_409_before_engine_or_simulate(
    monkeypatch, replacement: object
) -> None:
    monkeypatch.setattr(simulation_http, "simulate", lambda *args, **kwargs: pytest.fail("simulate reached"))
    monkeypatch.setattr(Engine, "create", lambda *args, **kwargs: pytest.fail("Engine.create reached"))
    with serving() as (server, _, _, base):
        definition = deepcopy(server.profile["definition"])
        definition["arcs"][0]["weight"] = replacement
        status, _, body = request(
            f"{base}/v1/simulations", method="POST", body=post_body(server, definition=definition)
        )
        assert (status, json.loads(body)["error"]["code"]) == (409, "definition_mismatch")


@pytest.mark.parametrize(
    "body",
    [
        b"\xff",
        b'{"expected_definition":{},"initial_marking":[],"max_actions":1,"x":{"a":1,"a":2}}',
        b'{"expected_definition":{},"initial_marking":[],"max_actions":1e400}',
        b'{"expected_definition":{},"initial_marking":[],"max_actions":"\\ud800"}',
        (b"[" * 1200) + b"0" + (b"]" * 1200),
    ],
)
def test_strict_value_failures_are_exact_400_before_simulate(monkeypatch, body: bytes) -> None:
    monkeypatch.setattr(simulation_http, "simulate", lambda *args, **kwargs: pytest.fail("simulate reached"))
    with serving() as (_, _, _, base):
        status, _, response = request(f"{base}/v1/simulations", method="POST", body=body)
        assert (status, json.loads(response)["error"]["code"]) == (400, "invalid_request")


def test_head_and_all_extension_methods_have_exact_405_headers_cors_and_body_rules() -> None:
    with serving() as (server, _, _, _):
        expected = b'{"error":{"code":"method_not_allowed","message":"method not allowed"}}'
        for method in ("HEAD", "TRACE", "CONNECT", "FROBNICATE"):
            status, headers, body = raw_parts(
                server, f"{method} /v1/simulation-profile HTTP/1.1\r\nHost: test\r\nOrigin: {ORIGIN}\r\n\r\n".encode()
            )
            assert (status, headers["Allow"], headers["Access-Control-Allow-Origin"]) == (405, "GET, OPTIONS", ORIGIN)
            assert int(headers["Content-Length"]) == len(expected)
            assert "Access-Control-Allow-Credentials" not in headers
            assert body == (b"" if method == "HEAD" else expected)


@pytest.mark.parametrize(
    "origin",
    [
        "http://",
        "http:///",
        "http://:80",
        "http://host:",
        "http://host:0",
        "http://host:65536",
        "http://host:abc",
        "http://user@host",
        "http://user:pass@host",
        "http://host ",
        "http://host\x00",
        "http://host\\evil",
        "http://host,evil",
        "http://%65xample.test",
        "http://host/",
        "http://host?",
        "http://host#",
    ],
)
def test_allowed_origin_rejects_ambiguous_or_invalid_authorities(origin: str) -> None:
    built, _ = build_scenario()
    with pytest.raises(ValueError, match="allowed_origin"):
        create_simulation_server(built, "127.0.0.1", 0, allowed_origin=origin)


def test_profile_copies_cannot_mutate_get_or_post_definition_compare(monkeypatch) -> None:
    monkeypatch.setattr(simulation_http, "simulate", lambda *args, **kwargs: b"{}")
    with serving() as (server, _, _, base):
        original = server.profile
        changed = server.profile
        changed["definition"]["arcs"][0]["weight"] = 99
        assert json.loads(request(f"{base}/v1/simulation-profile")[2]) == original
        assert (
            request(f"{base}/v1/simulations", method="POST", body=post_body(server, definition=original["definition"]))[
                0
            ]
            == 200
        )
