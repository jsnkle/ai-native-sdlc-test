"""Tests for app.server over a real socket, so the base class's own request
parsing and error responses are exercised, not just the routes."""

import http.client
import logging
import socket
import threading
import time

import pytest

import app.server
from app.server import create_server

NOT_FOUND = '{"error": "not_found"}'
CONTENT_TYPE = "application/json; charset=utf-8"
METHODS = ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"]
KNOWN_PATHS = ["/claims/C-1001/status", "/health"]


@pytest.fixture(scope="module")
def port():
    server = create_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def request(port, method, path, body=None):
    """One request on a fresh connection; returns (status, headers, body text)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(method, path, body=body)
        response = conn.getresponse()
        return response.status, response.headers, response.read().decode("utf-8")
    finally:
        conn.close()


def wait_for_records(caplog, count, timeout=2.0):
    """The access line is logged after the response is written, so give the
    server thread a moment to catch up before inspecting caplog."""
    deadline = time.monotonic() + timeout
    while len(caplog.records) < count and time.monotonic() < deadline:
        time.sleep(0.01)
    return caplog.records


def assert_json_headers(headers):
    assert headers["Content-Type"] == CONTENT_TYPE
    assert headers["Cache-Control"] == "no-store"


def test_known_claim_returns_status(port):
    status, headers, body = request(port, "GET", "/claims/C-1001/status")
    assert status == 200
    assert body == '{"claim_id": "C-1001", "status": "received"}'
    assert_json_headers(headers)


def test_unknown_claim_is_404(port):
    status, headers, body = request(port, "GET", "/claims/C-9999/status")
    assert status == 404
    assert body == NOT_FOUND
    assert_json_headers(headers)


@pytest.mark.parametrize(
    "path, given",
    [
        ("/claims/nonsense/status", "nonsense"),
        ("/claims//status", ""),
        ("/claims/C-1001/status/", "C-1001"),
        ("/claims/c-1001/status", "c-1001"),
        ("/claims/C-" + "1" * 40 + "/status", "C-" + "1" * 40),
        ("/claims/C-1001%0A/status", "C-1001%0A"),
    ],
)
def test_malformed_ids_are_404(port, monkeypatch, path, given):
    def no_lookup(claim_id):
        raise AssertionError("get_status must not be called for a malformed id")

    monkeypatch.setattr(app.server, "get_status", no_lookup)
    status, headers, body = request(port, "GET", path)
    assert status == 404
    assert body == NOT_FOUND
    assert not given or given not in body
    assert_json_headers(headers)


def test_unknown_paths_are_404(port):
    for path in ["/", "/claims", "/claims/C-1001", "/health/"]:
        status, headers, body = request(port, "GET", path)
        assert (path, status) == (path, 404)
        assert body == NOT_FOUND
        assert_json_headers(headers)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("path", KNOWN_PATHS)
def test_non_get_on_known_path_is_405_with_allow_get(port, method, path):
    status, headers, body = request(port, method, path)
    assert status == 405
    assert headers["Allow"] == "GET"
    assert_json_headers(headers)
    if method != "HEAD":
        assert body == '{"error": "method_not_allowed"}'


def test_non_get_on_unknown_path_is_404(port):
    status, headers, body = request(port, "POST", "/claims/C-1001")
    assert status == 404
    assert body == NOT_FOUND
    assert "Allow" not in headers


def test_health(port):
    status, headers, body = request(port, "GET", "/health")
    assert status == 200
    assert body == '{"status": "ok"}'
    assert_json_headers(headers)


def test_query_string_is_ignored(port):
    status, _, body = request(port, "GET", "/claims/C-1001/status?x=1")
    assert status == 200
    assert body == '{"claim_id": "C-1001", "status": "received"}'


def test_internal_error_is_500_without_details(port, monkeypatch, caplog):
    def boom(claim_id):
        raise RuntimeError("C-1001 secret")

    monkeypatch.setattr(app.server, "get_status", boom)
    caplog.set_level(logging.INFO, logger="app.server")
    status, headers, body = request(port, "GET", "/claims/C-1001/status")
    assert status == 500
    assert body == '{"error": "internal_error"}'
    assert_json_headers(headers)
    records = wait_for_records(caplog, 2)
    assert any(r.levelno == logging.ERROR and "RuntimeError" in r.getMessage() for r in records)
    assert "C-1001" not in caplog.text
    assert "secret" not in caplog.text


def test_bad_request_line_is_json_and_unlogged(port, caplog, capfd):
    caplog.set_level(logging.INFO, logger="app.server")
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(b"GET /claims/C-1001/status HTTP/1.1 extra\r\n\r\n")
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    raw = b"".join(chunks)
    assert raw.startswith(b"HTTP/1.0 400 ")
    assert b"Content-Type: " + CONTENT_TYPE.encode() in raw
    assert raw.endswith(b'\r\n\r\n{"error": "bad_request"}')
    assert b"C-1001" not in raw
    assert "request rejected" in caplog.text
    assert "C-1001" not in caplog.text
    assert "C-1001" not in capfd.readouterr().err


def test_access_log_contains_no_claim_id(port, caplog):
    caplog.set_level(logging.INFO, logger="app.server")
    paths = [
        "/claims/C-1001/status",
        "/claims/C-9999/status",
        "/claims/nonsense/status",
        "/claims/C-1001/status/",
    ]
    for path in paths:
        request(port, "GET", path)
    records = wait_for_records(caplog, len(paths))
    messages = [r.getMessage() for r in records]
    assert len(messages) == len(paths)
    for message in messages:
        assert "C-1001" not in message
        assert "C-9999" not in message
        assert "nonsense" not in message
    assert any("GET /claims/{id}/status 200" in m for m in messages)
    assert any("GET /claims/{id}/status 404" in m for m in messages)
    assert any("GET /other 404" in m for m in messages)


def test_server_header_does_not_advertise_python(port):
    _, headers, _ = request(port, "GET", "/health")
    assert headers["Server"] == "claims-portal"


def test_create_server_binds_requested_address():
    server = create_server("127.0.0.1", 0)
    try:
        host, bound_port = server.server_address[:2]
        assert host == "127.0.0.1"
        assert bound_port != 0
    finally:
        server.server_close()
