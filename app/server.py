"""HTTP layer over ``app.claims`` and ``app.letters``.

Three routes: ``GET /claims/{id}/status`` and ``GET /health`` for the customer
portal, and ``GET /claims/{id}/letter-details`` for DocGen. Everything else is
``404``. The service authenticates only the letters route, by API key in
``X-API-Key`` checked against ``CLAIMS_LETTERS_API_KEYS``; the other two trust
the portal and the gateway in front of it (see
``intent/claims-status-self-service/spec.md`` and
``intent/letters-claim-details-prefill/spec.md``). With no key configured the
letters route is not served at all.

Claim ids, letter fields and presented keys are never logged or echoed in an
error body. The base class logs every raw request line and answers malformed
requests with HTML that echoes the request line, so those behaviours are
overridden before any route is defined.
"""

import hashlib
import hmac
import json
import logging
import os
import re
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.claims import get_status
from app.letters import LettersUnavailable, get_letter_details

# Named explicitly rather than via __name__ so ``python -m app.server`` and
# ``import app.server`` share one logger. Never given a handler here: ``main``
# configures logging, and tests capture through the root logger.
logger = logging.getLogger("app.server")

CLAIM_ID_PATTERN = re.compile(r"C-[0-9]+")
CLAIM_ID_MAX_LENGTH = 32

HEALTH_PATH = re.compile(r"/health")
CLAIMS_PATH = re.compile(r"/claims/([^/]*)/status")
LETTERS_PATH = re.compile(r"/claims/([^/]*)/letter-details")

API_KEY_HEADER = "X-API-Key"
API_KEY_MIN_LENGTH = 32

CONTENT_TYPE = "application/json; charset=utf-8"
NOT_FOUND = {"error": "not_found"}
BAD_REQUEST = {"error": "bad_request"}
UNAUTHORIZED = {"error": "unauthorized"}
UNAVAILABLE = {"error": "unavailable"}
INTERNAL_ERROR = {"error": "internal_error"}


def _template(path):
    """Return the log-safe shape of ``path``; the raw path is never logged."""
    if CLAIMS_PATH.fullmatch(path):
        return "/claims/{id}/status"
    if LETTERS_PATH.fullmatch(path):
        return "/claims/{id}/letter-details"
    if HEALTH_PATH.fullmatch(path):
        return "/health"
    return "/other"


def _well_formed(claim_id):
    """The shape check both claim routes apply before any lookup."""
    return len(claim_id) <= CLAIM_ID_MAX_LENGTH and CLAIM_ID_PATTERN.fullmatch(claim_id) is not None


def parse_api_keys(raw):
    """Turn ``CLAIMS_LETTERS_API_KEYS`` into a tuple of keys.

    ``None``, empty or whitespace-only gives ``()``: the letters endpoint is
    disabled. Items are comma-separated and stripped. An empty item (a trailing
    comma on rotation) is dropped with a warning rather than stopping the
    service. A short item raises ``ValueError``; the message names the item's
    position and never its value, because ``main`` logs it.
    """
    if raw is None or not raw.strip():
        return ()
    keys = []
    for position, item in enumerate(raw.split(","), start=1):
        key = item.strip()
        if not key:
            logger.warning("CLAIMS_LETTERS_API_KEYS: item %d is empty and was ignored", position)
            continue
        if len(key) < API_KEY_MIN_LENGTH:
            raise ValueError(
                "CLAIMS_LETTERS_API_KEYS: item %d is shorter than %d characters"
                % (position, API_KEY_MIN_LENGTH)
            )
        keys.append(key)
    return tuple(keys)


def _digest(key):
    return hashlib.sha256(key.encode("utf-8")).digest()


def _key_matches(presented, digests):
    """Constant-time check of a presented key against the configured digests.

    Both sides are hashed to 32 bytes first, so ``compare_digest`` never sees a
    length difference and a non-ASCII header value simply fails to match. Every
    digest is compared, with no early exit, so timing does not reveal which
    configured key matched.
    """
    if not presented or not digests:
        return False
    candidate = _digest(presented)
    matched = False
    for digest in digests:
        matched |= hmac.compare_digest(candidate, digest)
    return matched


def _frames(exc):
    """File, line and function for each traceback frame, without source text.

    Source lines and ``str(exc)`` are left out: either could carry a claim id.
    """
    return " <- ".join(
        "%s:%d %s" % (os.path.basename(frame.filename), frame.lineno, frame.name)
        for frame in traceback.extract_tb(exc.__traceback__)
    )


class ClaimsHandler(BaseHTTPRequestHandler):
    """Request handler. ``protocol_version`` stays ``HTTP/1.0``: one request per
    connection, so an unread body on a ``405`` cannot bleed into the next request."""

    # -- Safe defaults: neutralise base-class behaviours that leak the request line.

    def version_string(self):
        return "claims-portal"

    def log_request(self, code="-", size="-"):
        # The base class writes the raw request line, which contains the id.
        pass

    def log_message(self, format, *args):
        pass

    def log_error(self, format, *args):
        # The base class passes the raw request line here on a malformed request.
        logger.warning("request rejected")

    def send_error(self, code, message=None, explain=None):
        """JSON error for the base class's own rejections (400, 414, 501, ...)."""
        self.log_error("code %d", code)
        if code == 404:
            payload = NOT_FOUND
        elif code < 500:
            payload = BAD_REQUEST
        else:
            payload = INTERNAL_ERROR
        self._send_json(code, payload, {"Connection": "close"})
        self.close_connection = True

    def _send_json(self, code, payload, extra_headers=None):
        # The base class writes no status line and no headers when it believes the
        # request was HTTP/0.9: a genuine simple request, or (on Python 3.12) any
        # request line it could not parse. Every response must carry the R8
        # headers, so the service never answers in HTTP/0.9.
        if self.request_version == "HTTP/0.9":
            self.request_version = self.protocol_version
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", CONTENT_TYPE)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        return code

    # -- Routing.

    def do_GET(self):
        self._handle(self._get)

    def do_HEAD(self):
        self._handle(self._method_not_allowed)

    def do_POST(self):
        self._handle(self._method_not_allowed)

    def do_PUT(self):
        self._handle(self._method_not_allowed)

    def do_PATCH(self):
        self._handle(self._method_not_allowed)

    def do_DELETE(self):
        self._handle(self._method_not_allowed)

    def do_OPTIONS(self):
        self._handle(self._method_not_allowed)

    def do_TRACE(self):
        self._handle(self._method_not_allowed)

    def do_CONNECT(self):
        self._handle(self._method_not_allowed)

    def _handle(self, action):
        started = time.perf_counter()
        path = self.path.split("?", 1)[0]  # query string ignored
        template = _template(path)
        try:
            code = action(path)
        except Exception as exc:  # every failure must become a 500, never a dropped connection
            logger.error("unhandled %s at %s", type(exc).__name__, _frames(exc))
            code = self._send_json(500, INTERNAL_ERROR)
        duration_ms = (time.perf_counter() - started) * 1000
        logger.info("%s %s %d %.1fms", self.command, template, code, duration_ms)

    def _get(self, path):
        if HEALTH_PATH.fullmatch(path):
            return self._send_json(200, {"status": "ok"})
        match = LETTERS_PATH.fullmatch(path)
        if match is not None:
            return self._letter_details(match.group(1))
        match = CLAIMS_PATH.fullmatch(path)
        if match is None:
            return self._send_json(404, NOT_FOUND)
        claim_id = match.group(1)
        if not _well_formed(claim_id):
            return self._send_json(404, NOT_FOUND)  # shape check before any lookup
        try:
            status = get_status(claim_id)
        except KeyError:
            return self._send_json(404, NOT_FOUND)
        return self._send_json(200, {"claim_id": claim_id, "status": status})

    def _letter_details(self, claim_id):
        """The order here is the security contract (plan step 4): disabled,
        then key, then shape, then lookup. Nothing about the id is inspected
        before the key has matched."""
        digests = self.server.letters_key_digests
        if not digests:
            return self._send_json(404, NOT_FOUND)  # fails closed: no key, no route
        if not _key_matches(self.headers.get(API_KEY_HEADER), digests):
            logger.warning("unauthorized /claims/{id}/letter-details")
            return self._send_json(401, UNAUTHORIZED)
        if not _well_formed(claim_id):
            return self._send_json(404, NOT_FOUND)
        try:
            details = get_letter_details(claim_id)
        except KeyError:
            return self._send_json(404, NOT_FOUND)
        except LettersUnavailable:
            return self._send_json(503, UNAVAILABLE, {"Retry-After": "5"})
        return self._send_json(200, details)

    def _method_not_allowed(self, path):
        if HEALTH_PATH.fullmatch(path) or CLAIMS_PATH.fullmatch(path):
            return self._send_json(405, {"error": "method_not_allowed"}, {"Allow": "GET"})
        if LETTERS_PATH.fullmatch(path) and self.server.letters_key_digests:
            return self._send_json(405, {"error": "method_not_allowed"}, {"Allow": "GET"})
        return self._send_json(404, NOT_FOUND)  # disabled letters path: no Allow, no hint


def create_server(host="127.0.0.1", port=8000, *, api_keys=None):
    """Bind and return the server. ``ThreadingHTTPServer`` already sets
    ``daemon_threads`` and ``allow_reuse_address``; ``port=0`` picks a free port.

    ``api_keys`` enables the letters route. Only SHA-256 digests are kept on
    the server object; the plaintext stays in the caller's hands."""
    server = ThreadingHTTPServer((host, port), ClaimsHandler)
    server.letters_key_digests = tuple(_digest(key) for key in api_keys or ())
    return server


def main():
    """Entry point for ``python -m app.server``.

    Loopback by default: the service is meant to be reachable only from the
    portal or gateway, so listening more widely is an operator's explicit choice
    via ``CLAIMS_HOST``.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    host = os.environ.get("CLAIMS_HOST", "127.0.0.1")
    port = int(os.environ.get("CLAIMS_PORT", "8000"))
    try:
        api_keys = parse_api_keys(os.environ.get("CLAIMS_LETTERS_API_KEYS"))
    except ValueError as exc:
        logger.error("%s", exc)  # names the item's position, never the key
        raise SystemExit(2)
    server = create_server(host, port, api_keys=api_keys)
    if api_keys:
        logger.info("letters endpoint enabled (%d keys)", len(api_keys))
    else:
        logger.info("letters endpoint disabled: CLAIMS_LETTERS_API_KEYS is not set")
    bound_host, bound_port = server.server_address[:2]
    logger.info("listening on %s:%d", bound_host, bound_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
