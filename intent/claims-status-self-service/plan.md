# Plan: Expose claim status over HTTP for the customer portal (from spec.md accepted 2026-09-02, commit 87b1280)
Status: accepted (engineer, 2026-09-02).

Inputs read: `intent.md` (accepted 1d2f3c3), `spec.md` (accepted 87b1280), `CLAUDE.md`, `REVIEW.md`, `Makefile`, `.github/workflows/ci.yml`, `.claude/protected-paths`, `app/claims.py`, `tests/test_claims.py`, and the `secure-api-review` policy skill the spec applied. The interrogation the skill asks for (what could break, riskiest step, options not taken, parallelisable) is answered in the sections below because nobody was available to interview.

Spec decisions this plan takes as settled: standard-library server behind the gateway (Areas of concern C, tech lead consulted per the spec header); malformed ids are `404`; `/health` is in scope; no authentication in this service. Anything still open in the spec (A, B, E, F, G, H) is a human decision and is not changed by this plan.

## Files that change

- `app/server.py` (new): the whole HTTP layer. One `http.server.BaseHTTPRequestHandler` subclass, a `create_server(host, port)` factory returning a `ThreadingHTTPServer`, and a `main()` entry point for `python -m app.server`. Imports only `http.server`, `json`, `logging`, `os`, `re`, `time`, `traceback` and `app.claims.get_status`.
- `tests/test_server.py` (new): one test module for the new app module, per convention. Starts a real server on `127.0.0.1:0` in a background thread and talks to it with `http.client`, so every acceptance criterion is exercised over a socket, including raw request lines the base class rejects itself.
- `Makefile` (modified): add a `run` target, `.venv/bin/python -m app.server`. `build`, `test` and `lint` unchanged.
- `CLAUDE.md` (modified): "There is no run target" and "no database, config, or HTTP layer" are no longer true. Update Commands (add `make run` and its healthy output), Architecture (add `app/server.py`, the two env vars), and the run-target sentence. Keep it under a page.

Not changed, deliberately:
- `app/claims.py` and `tests/test_claims.py`: the library contract is unchanged (spec R13, AC5). If either shows in the diff, the plan was departed from.
- `requirements-dev.txt`: no new dev dependency. The tests use `http.client`, `threading`, `socket` and pytest's `caplog` and `monkeypatch`.
- `.github/workflows/ci.yml`: protected path. See Risks for the Python version mismatch it carries.
- `intent/claims-status-self-service/spec.md`: nothing here overturns a spec decision.

## Order of work

Each step is small enough to run `make build`, `make test`, `make lint` afterwards. Steps 1 through 5 are one PR.

1. **Environment.** `.venv/` does not exist in this checkout. Create it exactly as `CLAUDE.md` says (`python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`, Python 3.14.7 locally). Run the three make targets and confirm the baseline: `Build succeeded`, `2 passed`, lint prints nothing after the command line.

2. **Server skeleton with the safe defaults first** (`app/server.py`). Before any route exists, neutralise the base-class behaviours that would violate the spec on their own:
   - `log_message` and `log_request` overridden to no-ops. The base class writes every raw request line (which contains the id) to stderr; this is the leak spec R11 forbids.
   - `log_error` overridden to log a fixed string (`request rejected`) at WARNING with no arguments. The base class passes it the raw request line on a malformed request.
   - `send_error` overridden to emit the JSON body and the R8 headers instead of the HTML page the base class generates for its own `400`, `414` and `501` responses. Mapping: `404` to `{"error": "not_found"}`, any other 4xx to `{"error": "bad_request"}`, 5xx to `{"error": "internal_error"}`. Sets `close_connection = True` like the original.
   - `version_string` overridden to return `claims-portal` so the `Server` header no longer advertises the Python and module versions.
   - `protocol_version` left at the default `HTTP/1.0` (see Options not taken).
   - A single `_send_json(code, payload, extra_headers=None)` helper that sets `Content-Type: application/json; charset=utf-8`, `Cache-Control: no-store`, `Content-Length`, and writes the UTF-8 body. Every response, including errors, goes through it.

3. **Routing and the two routes.** In `do_GET`: strip anything from `?` onward (query ignored, R-Interfaces), then match the path against exactly two patterns, `^/health$` and `^/claims/([^/]*)/status$`. No URL-decoding, no trailing-slash tolerance. For the claims route, the captured segment must match `^C-[0-9]+$` and be at most 32 characters; otherwise `404` without calling `get_status` (R5). On a match, call `get_status`; `KeyError` becomes `404` (R13); success is `200` with `{"claim_id": id, "status": status}`. Anything else is `404 {"error": "not_found"}` (R6). `do_POST`, `do_PUT`, `do_PATCH`, `do_DELETE`, `do_HEAD`, `do_OPTIONS` all call one `_method_not_allowed` that returns `405` with `Allow: GET` when the path is a known route and `404` otherwise (R7 applies to known paths only). Wrap the whole `do_*` body in a `try`/`except Exception` that answers `500 {"error": "internal_error"}` (Design, Behaviour).

4. **Access log and error log without ids.** A module logger `app.server`. Every request handled by a `do_*` method emits one INFO line: method, templated path, status code, duration in ms from `time.perf_counter`. The templated path is one of `/claims/{id}/status`, `/health` or `/other`; the raw path is never formatted into a log record, including for unknown paths (an unknown path such as `/claims/C-1001/status/` still carries an id). The `500` branch logs the exception class name and `traceback.format_tb` frames at ERROR, not `str(exc)`, because an exception message could carry the id.

5. **Factory and entry point.** `create_server(host="127.0.0.1", port=8000)` returns a `ThreadingHTTPServer` with `daemon_threads = True` and `allow_reuse_address = True`. `main()` reads `CLAIMS_HOST` and `CLAIMS_PORT`, calls `logging.basicConfig(level=INFO)`, serves forever, and closes cleanly on `KeyboardInterrupt`. The loopback default is deliberate: the spec's trust boundary is "reachable only from the portal or gateway", so exposing the service on all interfaces is an operator's explicit choice, never the default. `python -m app.server` runs `main()`.

6. **Tests** (`tests/test_server.py`). A module-scoped fixture builds `create_server("127.0.0.1", 0)`, starts `serve_forever` on a daemon thread, yields the bound port, and calls `shutdown()` then `server_close()` on teardown. A small `request(method, path, body=None)` helper opens a fresh `http.client.HTTPConnection` per call and returns status, headers and decoded body. Tests, each named for what it proves:
   - `test_known_claim_returns_status`: AC1, exact body and both R8 headers.
   - `test_unknown_claim_is_404`: `C-9999`, exact body.
   - `test_malformed_ids_are_404` (parametrised): `nonsense`, empty (`/claims//status`), trailing slash (`/claims/C-1001/status/`), lowercase `c-1001`, `C-` followed by 40 digits (length 42), `C-1001%0A`. Each asserts the exact `404` body and that the input does not appear in the body (R4). Uses `monkeypatch` on `app.server.get_status` to a function that raises `AssertionError` so any lookup on a malformed id fails the test (R5).
   - `test_unknown_paths_are_404`: `/`, `/claims`, `/claims/C-1001`, `/health/`.
   - `test_non_get_on_known_path_is_405_with_allow_get` (parametrised over POST, PUT, PATCH, DELETE, HEAD, OPTIONS, and both known paths): AC3.
   - `test_non_get_on_unknown_path_is_404`.
   - `test_health`: AC4, headers included.
   - `test_query_string_is_ignored`: `/claims/C-1001/status?x=1` is `200`.
   - `test_internal_error_is_500_without_details`: `monkeypatch` `get_status` to raise `RuntimeError("C-1001 secret")`; assert the body is exactly `{"error": "internal_error"}` and `caplog.text` contains neither `C-1001` nor `secret`.
   - `test_bad_request_line_is_json_and_unlogged`: open a raw socket and send `GET /claims/C-1001/status HTTP/1.1 extra\r\n\r\n` (four words, so the base class rejects it with its own `400`). Assert the response has the JSON content type and neither the response nor `caplog.text` contains `C-1001`. This is the test for step 2.
   - `test_access_log_contains_no_claim_id`: with `caplog` at INFO for `app.server`, hit the known, unknown, malformed and unknown-path routes; assert no record contains `C-1001`, `C-9999` or `nonsense`, and that at least one record contains `/claims/{id}/status` and one contains `/other`. AC6.
   - `test_server_header_does_not_advertise_python`: `Server` header is `claims-portal`.
   - `test_create_server_binds_requested_address`: port 0 yields a non-zero bound port on `127.0.0.1`.
   The `500` and bad-request tests must be written before their production code is considered done; they are the proof that step 2 and the `try`/`except` in step 3 are actually wired.

7. **Makefile and CLAUDE.md.** Add the `run` target. Update the three sentences in `CLAUDE.md` listed under Files that change. Also add the healthy output of `make run` (a single log line saying which host and port it is listening on, then nothing until a request arrives; stop it with Ctrl-C).

8. **Verify and hand over.** Run the three make targets, paste the output into the PR body per `.github/pull_request_template.md`, run the manual checks under Proof, and list any departure from this plan in the same PR with `plan.md` updated in the same commit.

## Risks

**What could break.**
- Nothing existing. `get_status` has one caller today, `tests/test_claims.py`, and neither file changes. There is no HTTP consumer yet; the portal team builds against this once merged.
- `make build` byte-compiles `app/`, so a syntax error in `app/server.py` breaks the build target, which is the intended signal.
- `make lint` now covers two more files. Unused imports in the tests are the likely nit; run lint before pushing.

**Riskiest step: step 2, the base-class overrides.** `http.server` leaks by default in exactly the ways the spec forbids: it prints every raw request line (with the id) to stderr, and it answers malformed requests with HTML bodies that echo the request line. Nothing in the happy path exposes this. A server that skips step 2 passes every `200`, `404`, `405` and `/health` test and still violates R4, R8 and R11 the first time a client sends a malformed line. Mitigation: step 2 is done first, before any route, and two tests (`test_bad_request_line_is_json_and_unlogged`, `test_access_log_contains_no_claim_id`) fail without it. The review pass should treat any removal of those overrides as an Important security finding.

**Second: the trust boundary is not enforceable here.** The service accepts every request that reaches it (spec R12, Areas of concern A and B). The only technical mitigation in this change is the loopback bind default in step 5; exposing the service is an explicit `CLAIMS_HOST` setting. Acceptance criterion 9 (portal team confirms in writing) is a human gate and cannot be satisfied by this plan. The PR must not be merged as "done" with AC9 unmet; it can merge as "implemented, pending AC9" if the code owner records that on the PR.

**Python version mismatch between CI and the project.** `ci.yml` installs Python 3.12; `CLAUDE.md` says 3.14 and the local interpreter is 3.14.7. Everything this plan uses (`ThreadingHTTPServer`, `re`, `json`, `logging`) exists in 3.12, and the implementation must not use 3.14-only syntax. `ci.yml` is under a protected path, so aligning it is a separate change for the tech lead; this plan notes it and does not touch it.

**Unread request bodies on non-GET.** A `POST` with a body gets `405` without the body being read. With `HTTP/1.0` (the default, kept) the connection closes after each response, so an unread body cannot corrupt a following request. If someone later switches to `HTTP/1.1` for keep-alive, they must also drain or `Connection: close` on the `405` path. Noted so the next change does not reintroduce it.

**Threaded tests and log capture.** The server runs on another thread; pytest's `caplog` attaches to the root logger so records propagate regardless of thread, provided `app.server` does not set `propagate = False`. Do not add a handler to the module logger; `main()` configures logging, the module does not.

**Fixture port reuse.** Binding port 0 avoids collisions with anything else on the machine, including a `make run` left open. Teardown must call `shutdown()` before `server_close()` or the daemon thread can hold the socket into the next module.

**Exotic method tokens.** `do_*` methods are defined for the seven standard non-GET methods. A request with an unknown method token (for example `BREW`) gets the base class's `501`, now with a JSON body through the `send_error` override. This is a narrow reading of R7 ("any method other than GET"); it is recorded here so a reviewer does not read it as an omission.

## Proof

Run before reporting done. Every automated line has a pass condition that needs no judgement.

- `make build` ends with `Build succeeded`.
- `make test` ends with `15 passed` (2 existing plus 13 new) and no `failed` or `error`. If the count differs, the test list above changed and this section is updated in the same commit.
- `make lint` prints nothing after the echoed `pyflakes` command line.
- Existing contract: `tests/test_claims.py` is unchanged in `git diff --stat` and both its tests pass (AC5).
- No runtime dependency: `git diff --name-only` does not include `requirements-dev.txt`, and `grep -h "^import\|^from" app/server.py` lists only standard-library modules and `app.claims` (AC7).
- Manual, once, with `make run` in a second terminal, each response checked against the spec:
  - `curl -si http://127.0.0.1:8000/claims/C-1001/status` returns `200`, body `{"claim_id": "C-1001", "status": "received"}`, `Content-Type: application/json; charset=utf-8`, `Cache-Control: no-store`, `Server: claims-portal` (AC1).
  - `curl -si http://127.0.0.1:8000/claims/C-9999/status`, `.../claims/nonsense/status`, `.../claims//status`, `.../claims/C-1001/status/` each return `404` with body `{"error": "not_found"}` (AC2).
  - `curl -si -X POST http://127.0.0.1:8000/claims/C-1001/status` returns `405` with `Allow: GET` (AC3).
  - `curl -si http://127.0.0.1:8000/health` returns `200` with `{"status": "ok"}` (AC4).
  - The `make run` terminal output for the above contains the strings `/claims/{id}/status` and `/other` and does not contain `C-1001`, `C-9999` or `nonsense` (AC6).
- Latency, informational only: 200 sequential `GET /claims/C-1001/status` calls via `http.client` from a Python one-liner report a maximum under 50 ms. Not a gating test because timing assertions are flaky in CI.
- Human, tracked on the PR and not automatable: AC9 (portal team confirms the trust boundary in writing) and AC10 (call-volume baseline recorded before go-live).

## Options not taken

- **Verify the gateway JWT in the service.** Rejected by the spec (R12, R14): it needs either a crypto dependency or a hand-rolled verifier, and the intent forbids the service adding auth. Stays with the gateway.
- **A third-party server (uvicorn, gunicorn, waitress) or framework.** A runtime dependency is a `spec.md` decision and the spec chose the standard library with the tech lead consulted (Areas of concern C). Behind a gateway for a four-row dictionary, `ThreadingHTTPServer` meets the concurrency requirement.
- **`http.server.HTTPServer` (single-threaded).** Fails the non-functional requirement that one slow client must not block others. `ThreadingHTTPServer` is the same import.
- **`HTTP/1.1` with keep-alive.** Would need every path to read or close on unread bodies and always send `Content-Length`. The gateway holds client keep-alives; between gateway and service the extra connection per request is cheap. Kept `HTTP/1.0`.
- **`400` for malformed ids.** Overturned by the spec in favour of a uniform `404`; one line and one test if the product owner reverses it.
- **URL-decoding the id before validation.** Decoding widens the accepted input (`C%2D1001` would become valid) for no caller benefit; the portal sends plain ids. Raw segment is validated as-is.
- **A `__getattr__` trick so any method token gets `405`.** Handles `BREW` correctly but is clever enough to surprise a reviewer. Explicit `do_*` methods for the standard set, with `501` JSON for the rest, is easier to read and is recorded in Risks.
- **Logging via `logger.exception` on the `500` path.** Includes `str(exc)`, which could carry the id. Logs class name and traceback frames instead.
- **Testing the handler in isolation with a fake socket.** Faster but would not exercise the base class's own request-line parsing and `send_error`, which is where the leak risk lives. Real socket, port 0.
- **Adding `scripts/check-endpoints.sh` now.** The policy skill asks for it; spec Areas of concern H leaves it to the tech lead. Out of this change.
- **Aligning `ci.yml` to Python 3.14.** Protected path; separate change.
- **A `Dockerfile` or deploy target.** No deploy target exists and the production gate hook blocks `deploy` plus `production` commands until `RELEASE_APPROVAL` is set. Not in scope.

## Parallelisable

Effectively none worth a second session. Step 7 (`Makefile`, `CLAUDE.md`) touches disjoint files and could run in a separate worktree, but it is a few lines and depends on knowing the entry point name from step 5. Steps 2 through 6 should be one session: the tests pin the module's public names (`create_server`, `app.server.get_status` for monkeypatching, the logger name `app.server`) and splitting them across sessions invites a mismatch that the plan cannot arbitrate.
