"""Tests for app.server over a real socket, so the base class's own request
parsing and error responses are exercised, not just the routes."""

import http.client
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time

import pytest

import app.server
from app.letters import LettersUnavailable
from app.server import _key_matches, create_server, parse_api_keys

NOT_FOUND = '{"error": "not_found"}'
UNAUTHORIZED = '{"error": "unauthorized"}'
UNAVAILABLE = '{"error": "unavailable"}'
CONTENT_TYPE = "application/json; charset=utf-8"
METHODS = ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"]
KNOWN_PATHS = ["/claims/C-1001/status", "/health"]

# Two 40-character keys for the letters fixture. Obviously fake, never logged.
KEY_A = "test-key-a-" + "a" * 29
KEY_B = "test-key-b-" + "b" * 29
LETTERS = "/claims/C-1002/letter-details"
LETTERS_BODY = (
    '{"claim_id": "C-1002", "customer_name": "A. Example", "policy_number": "P-88213", '
    '"status": "in_review", "date_of_loss": "2026-08-14", '
    '"next_step": "Awaiting engineer\'s report", "handler_name": "H. Handler"}'
)


def serve(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def port():
    """Keyless server: the letters route is disabled here."""
    yield from serve(create_server("127.0.0.1", 0))


@pytest.fixture(scope="module")
def letters_port():
    """Server with two keys configured, so the letters route is enabled."""
    yield from serve(create_server("127.0.0.1", 0, api_keys=[KEY_A, KEY_B]))


def with_key(key):
    return {"X-API-Key": key}


def request(port, method, path, body=None, headers=None):
    """One request on a fresh connection; returns (status, headers, body text)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        return response.status, response.headers, response.read().decode("utf-8")
    finally:
        conn.close()


def raw_request(port, data):
    """Send ``data`` verbatim on a fresh socket and return everything the
    server writes back, for request lines ``http.client`` will not produce."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(data)
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    return b"".join(chunks)


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


@pytest.mark.parametrize(
    "method, path, expected",
    [
        ("GET", "/claims/C-1001/status", 200),
        ("GET", "/health", 200),
        ("GET", "/claims/C-9999/status", 404),
        ("GET", "/claims/nonsense/status", 404),
        ("GET", "/nope", 404),
        ("POST", "/claims/C-1001/status", 405),
        ("GET", "/claims/C-1001/status", 500),
    ],
)
def test_every_response_is_no_store(port, monkeypatch, method, path, expected):
    """Spec R8: no cache between the gateway and the customer may hold a status,
    so the header is asserted on every status code the routes can produce."""
    if expected == 500:
        monkeypatch.setattr(app.server, "get_status", lambda claim_id: 1 / 0)
    status, headers, _ = request(port, method, path)
    assert status == expected
    assert headers["Cache-Control"] == "no-store"


def test_bad_request_line_is_json_and_unlogged(port, caplog, capfd):
    caplog.set_level(logging.INFO, logger="app.server")
    raw = raw_request(port, b"GET /claims/C-1001/status HTTP/1.1 extra\r\n\r\n")
    assert raw.startswith(b"HTTP/1.0 400 ")
    assert b"Content-Type: " + CONTENT_TYPE.encode() in raw
    assert b"Cache-Control: no-store" in raw
    assert raw.endswith(b'\r\n\r\n{"error": "bad_request"}')
    assert b"C-1001" not in raw
    assert "request rejected" in caplog.text
    assert "C-1001" not in caplog.text
    assert "C-1001" not in capfd.readouterr().err


def test_http_0_9_request_gets_status_line_and_headers(port):
    """A simple request has no version, and the base class would answer it
    with a bare body: no status line, no Cache-Control. R8 says every response."""
    raw = raw_request(port, b"GET /health\r\n\r\n")
    assert raw.startswith(b"HTTP/1.0 200 ")
    assert b"Cache-Control: no-store" in raw
    assert raw.endswith(b'\r\n\r\n{"status": "ok"}')


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


# -- Letters route: key parsing and matching (plan step 3).


@pytest.mark.parametrize(
    "raw, expected, warning",
    [
        (None, (), None),
        ("", (), None),
        ("   ", (), None),
        (KEY_A, (KEY_A,), None),
        (KEY_A + "," + KEY_B, (KEY_A, KEY_B), None),
        (" " + KEY_A + " , " + KEY_B + " ", (KEY_A, KEY_B), None),
        (KEY_A + ",", (KEY_A,), "item 2"),
        ("," + KEY_A, (KEY_A,), "item 1"),
        (KEY_A + "," + KEY_A, (KEY_A,), "item 2"),
    ],
)
def test_parse_api_keys(caplog, raw, expected, warning):
    caplog.set_level(logging.WARNING, logger="app.server")
    assert parse_api_keys(raw) == expected
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    if warning is None:
        assert warnings == []
    else:
        assert len(warnings) == 1
        assert warning in warnings[0].getMessage()
    assert KEY_A not in caplog.text
    assert KEY_B not in caplog.text


@pytest.mark.parametrize(
    "raw, position",
    [("k" * 31, "item 1"), (KEY_A + "," + "k" * 31, "item 2")],
)
def test_parse_api_keys_refuses_short_key(raw, position):
    with pytest.raises(ValueError) as excinfo:
        parse_api_keys(raw)
    message = str(excinfo.value)
    assert "item" in message
    assert position in message
    assert "k" * 31 not in message
    assert KEY_A not in message


@pytest.mark.parametrize(
    "raw, position",
    [("ké" * 20, "item 1"), (KEY_A + "," + "é" * 32, "item 2")],
)
def test_parse_api_keys_refuses_non_ascii_key(raw, position):
    """The base class decodes headers as Latin-1, so a non-ASCII key sent as
    UTF-8 could never match; refuse it at startup instead of answering 401s."""
    with pytest.raises(ValueError) as excinfo:
        parse_api_keys(raw)
    message = str(excinfo.value)
    assert "non-ASCII" in message
    assert position in message
    assert "é" not in message
    assert KEY_A not in message


DIGESTS = (app.server._digest(KEY_A),)


@pytest.mark.parametrize(
    "presented, digests, expected",
    [
        (KEY_A, DIGESTS, True),
        ("x" * len(KEY_A), DIGESTS, False),
        (None, DIGESTS, False),
        ("", DIGESTS, False),
        ("ké" * 20, DIGESTS, False),
        (KEY_A, (), False),
    ],
)
def test_key_matches(presented, digests, expected):
    assert _key_matches(presented, digests) is expected


def test_create_server_default_has_no_keys():
    server = create_server("127.0.0.1", 0)
    try:
        assert server.letters_key_digests == ()
    finally:
        server.server_close()


def test_create_server_stores_digests():
    server = create_server("127.0.0.1", 0, api_keys=[KEY_A, KEY_B])
    try:
        digests = server.letters_key_digests
        assert len(digests) == 2
        assert all(isinstance(d, bytes) and len(d) == 32 for d in digests)
        state = repr(vars(server))
        assert KEY_A not in state
        assert KEY_B not in state
    finally:
        server.server_close()


# -- Entry point (plan step 5). ``main()`` runs as a real subprocess so the exit
# code and the startup lines are tested as an operator sees them.

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def start_main(keys):
    """Start ``python -m app.server`` on a free port with only the env we choose."""
    env = {name: value for name, value in os.environ.items() if not name.startswith("CLAIMS_")}
    env["CLAIMS_PORT"] = "0"
    if keys is not None:
        env["CLAIMS_LETTERS_API_KEYS"] = keys
    return subprocess.Popen(
        [sys.executable, "-m", "app.server"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_main_refuses_short_key():
    """Spec AC5: a short key stops startup with exit code 2 and never names the key."""
    proc = start_main("k" * 20)
    _, stderr = proc.communicate(timeout=10)
    assert proc.returncode == 2
    assert "ERROR" in stderr
    assert "CLAIMS_LETTERS_API_KEYS" in stderr
    assert "item 1" in stderr
    assert "k" * 20 not in stderr
    assert "listening on" not in stderr


@pytest.mark.parametrize(
    "keys, expected, warning",
    [
        (None, "letters endpoint disabled: CLAIMS_LETTERS_API_KEYS is not set", None),
        (KEY_A + "," + KEY_B + ",", "letters endpoint enabled (2 keys)", "item 3"),
    ],
    ids=["disabled", "enabled"],
)
def test_main_logs_letters_state_before_listening(keys, expected, warning):
    proc = start_main(keys)
    lines = []
    watchdog = threading.Timer(10, proc.kill)
    watchdog.start()
    try:
        for line in iter(proc.stderr.readline, ""):
            lines.append(line)
            if "listening on" in line:
                break
    finally:
        watchdog.cancel()
        proc.terminate()
        proc.communicate(timeout=10)
    text = "".join(lines)
    assert expected in text
    assert "listening on 127.0.0.1:" in text
    assert text.index(expected) < text.index("listening on")
    if warning is not None:
        assert "WARNING" in text
        assert warning in text
    else:
        assert "WARNING" not in text
    assert KEY_A not in text
    assert KEY_B not in text


# -- Letters route: the HTTP surface (plan step 4).


def raise_unavailable(claim_id):
    raise LettersUnavailable()


def test_letter_details_with_valid_key(letters_port):
    status, headers, body = request(letters_port, "GET", LETTERS, headers=with_key(KEY_A))
    assert status == 200
    assert body == LETTERS_BODY
    assert_json_headers(headers)
    _, _, status_body = request(letters_port, "GET", "/claims/C-1002/status")
    assert json.loads(body)["status"] == json.loads(status_body)["status"]


@pytest.mark.parametrize("key", [KEY_A, KEY_B])
def test_letter_details_either_key_accepted(letters_port, key):
    status, _, body = request(letters_port, "GET", LETTERS, headers=with_key(key))
    assert status == 200
    assert body == LETTERS_BODY


@pytest.mark.parametrize(
    "headers",
    [
        None,
        {"X-API-Key": ""},
        {"X-API-Key": "x" * len(KEY_A)},
        {"X-API-Key": "wrong"},
        {"X-API-Key": KEY_A + "a"},
    ],
    ids=["absent", "empty", "wrong-same-length", "wrong-short", "valid-plus-one"],
)
def test_letter_details_without_valid_key_is_401(letters_port, headers):
    status, response_headers, body = request(letters_port, "GET", LETTERS, headers=headers)
    assert status == 401
    assert body == UNAUTHORIZED
    assert_json_headers(response_headers)


@pytest.mark.parametrize("claim_id", ["C-9999", "nonsense", ""])
def test_letter_details_401_precedes_404(letters_port, monkeypatch, claim_id):
    def no_lookup(claim_id):
        raise AssertionError("get_letter_details must not be called before the key check")

    monkeypatch.setattr(app.server, "get_letter_details", no_lookup)
    path = "/claims/" + claim_id + "/letter-details"
    status, _, body = request(letters_port, "GET", path, headers=with_key("x" * len(KEY_A)))
    assert status == 401
    assert body == UNAUTHORIZED


def test_letter_details_unknown_claim_is_404(letters_port):
    status, headers, body = request(
        letters_port, "GET", "/claims/C-9999/letter-details", headers=with_key(KEY_A)
    )
    assert status == 404
    assert body == NOT_FOUND
    assert_json_headers(headers)


@pytest.mark.parametrize(
    "path, given",
    [
        ("/claims/nonsense/letter-details", "nonsense"),
        ("/claims//letter-details", ""),
        ("/claims/C-1001/letter-details/", "C-1001"),
        ("/claims/c-1001/letter-details", "c-1001"),
        ("/claims/C-" + "1" * 40 + "/letter-details", "C-" + "1" * 40),
        ("/claims/C-1001%0A/letter-details", "C-1001%0A"),
    ],
)
def test_letter_details_malformed_ids_are_404(letters_port, monkeypatch, path, given):
    def no_lookup(claim_id):
        raise AssertionError("get_letter_details must not be called for a malformed id")

    monkeypatch.setattr(app.server, "get_letter_details", no_lookup)
    status, headers, body = request(letters_port, "GET", path, headers=with_key(KEY_A))
    assert status == 404
    assert body == NOT_FOUND
    assert not given or given not in body
    assert_json_headers(headers)


@pytest.mark.parametrize("method", ["GET"] + METHODS)
def test_letter_details_disabled_is_404_on_every_method(port, method):
    """Spec R8: with no key configured the route does not exist, even to a
    caller holding a key that would be valid elsewhere."""
    status, headers, body = request(port, method, LETTERS, headers=with_key(KEY_A))
    assert status == 404
    assert "Allow" not in headers
    assert_json_headers(headers)
    if method != "HEAD":
        assert body == NOT_FOUND


def test_letter_details_unavailable_is_503(letters_port, monkeypatch):
    monkeypatch.setattr(app.server, "get_letter_details", raise_unavailable)
    status, headers, body = request(letters_port, "GET", LETTERS, headers=with_key(KEY_A))
    assert status == 503
    assert body == UNAVAILABLE
    assert headers["Retry-After"] == "5"
    assert_json_headers(headers)


@pytest.mark.parametrize("headers", [None, {"X-API-Key": KEY_A}], ids=["no-key", "key"])
@pytest.mark.parametrize("method", METHODS)
def test_letter_details_non_get_is_405(letters_port, method, headers):
    status, response_headers, body = request(letters_port, method, LETTERS, headers=headers)
    assert status == 405
    assert response_headers["Allow"] == "GET"
    assert_json_headers(response_headers)
    if method != "HEAD":
        assert body == '{"error": "method_not_allowed"}'


def test_letter_details_internal_error_is_500_without_pii(letters_port, monkeypatch, caplog):
    def boom(claim_id):
        raise RuntimeError("A. Example P-88213 " + KEY_A)

    monkeypatch.setattr(app.server, "get_letter_details", boom)
    caplog.set_level(logging.INFO, logger="app.server")
    status, headers, body = request(letters_port, "GET", LETTERS, headers=with_key(KEY_A))
    assert status == 500
    assert body == '{"error": "internal_error"}'
    assert_json_headers(headers)
    records = wait_for_records(caplog, 2)
    assert any(r.levelno == logging.ERROR and "RuntimeError" in r.getMessage() for r in records)
    for secret in ["A. Example", "P-88213", KEY_A, "C-1002"]:
        assert secret not in caplog.text, secret


def test_letter_details_logs_contain_no_pii_or_key(letters_port, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.server")
    request(letters_port, "GET", LETTERS, headers=with_key(KEY_A))  # 200
    request(letters_port, "GET", LETTERS)  # 401, plus one warning
    request(letters_port, "GET", "/claims/C-9999/letter-details", headers=with_key(KEY_A))  # 404
    request(letters_port, "GET", "/claims/nonsense/letter-details", headers=with_key(KEY_A))  # 404
    monkeypatch.setattr(app.server, "get_letter_details", raise_unavailable)
    request(letters_port, "GET", LETTERS, headers=with_key(KEY_A))  # 503
    records = wait_for_records(caplog, 6)
    messages = [r.getMessage() for r in records]
    assert len(messages) == 6
    for code in ["200", "401", "404", "503"]:
        assert any("GET /claims/{id}/letter-details " + code in m for m in messages), code
    assert any(r.levelno == logging.WARNING for r in records)
    for secret in [
        "A. Example", "P-88213", "2026-08-14", "H. Handler", "Awaiting engineer",
        "in_review", "C-1002", "C-9999", "nonsense", KEY_A, KEY_B,
    ]:
        assert secret not in caplog.text, secret


def test_letter_details_query_string_is_ignored(letters_port):
    status, _, body = request(letters_port, "GET", LETTERS + "?x=1", headers=with_key(KEY_A))
    assert status == 200
    assert body == LETTERS_BODY


@pytest.mark.parametrize(
    "method, path, headers, expected",
    [
        ("GET", LETTERS, {"X-API-Key": KEY_A}, 200),
        ("GET", LETTERS, None, 401),
        ("GET", "/claims/C-9999/letter-details", {"X-API-Key": KEY_A}, 404),
        ("POST", LETTERS, {"X-API-Key": KEY_A}, 405),
        ("GET", LETTERS, {"X-API-Key": KEY_A}, 503),
        ("GET", LETTERS, {"X-API-Key": KEY_A}, 500),
    ],
    ids=["200", "401", "404", "405", "503", "500"],
)
def test_letter_details_every_response_is_no_store(letters_port, monkeypatch, method, path, headers, expected):
    """Spec R14: no-store on every code the letters route can produce."""
    if expected == 503:
        monkeypatch.setattr(app.server, "get_letter_details", raise_unavailable)
    if expected == 500:
        monkeypatch.setattr(app.server, "get_letter_details", lambda claim_id: 1 / 0)
    status, response_headers, _ = request(letters_port, method, path, headers=headers)
    assert status == expected
    assert response_headers["Cache-Control"] == "no-store"
