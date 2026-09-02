# Plan: Serve claim details to DocGen over an API-key route (from spec.md accepted 2026-09-02, commit 3dc45a8)
Status: accepted (engineer, 2026-09-02).

Inputs read: `intent.md` (accepted 76cc93f), `spec.md` (accepted 3dc45a8), `CLAUDE.md`, `REVIEW.md`, `Makefile`, `.github/workflows/ci.yml`, `.claude/protected-paths`, `app/claims.py`, `app/server.py`, `tests/test_claims.py`, `tests/test_server.py`, and the previous plan `intent/claims-status-self-service/plan.md`. The engineer was interviewed on 2026-09-02; their decisions are marked "(engineer)" below.

Spec decisions this plan takes as settled: this service serves DocGen; the key is checked here in `X-API-Key`; no address, no amount, no recipient input; `null` for fields not held; 401 before 404; fail closed when no key is configured. Areas of concern A to J and acceptance criteria 13 to 15 are human decisions and are not changed by this plan.

## Files that change

- `app/letters.py` (new): the letter-details library. A `DETAILS` fixture keyed by the same four ids as `STATUSES`, each holding exactly five fields (`customer_name`, `policy_number`, `date_of_loss`, `next_step`, `handler_name`); a `LettersUnavailable(Exception)` class for the source-unavailable case; and `get_letter_details(claim_id)` returning the seven-key dict in spec order, with `status` taken from `app.claims.get_status` so the two routes can never disagree. `KeyError` for an unknown id. Imports only `app.claims`.
- `tests/test_letters.py` (new): one test module for the new app module, per convention. Pure function tests, no socket.
- `app/server.py` (modified): letters route pattern and log template; `parse_api_keys` and `_key_matches`; `create_server(host, port, *, api_keys=None)` storing SHA-256 digests on the server object; the authenticated `_letter_details` handler; disabled-state 404 in the 405 branch; `main()` reads `CLAIMS_LETTERS_API_KEYS`, logs enabled or disabled, refuses to start on a short key. New imports: `hashlib`, `hmac`, `app.letters`. Module docstring updated (no longer "two routes" or "no authentication").
- `tests/test_server.py` (modified): `request` helper gains an optional `headers` argument; a second module-scoped fixture `letters_port` starts a server with two keys; the existing keyless `port` fixture is reused for the disabled state. All 43 existing tests unchanged.
- `CLAUDE.md` (modified): Commands gains `CLAIMS_LETTERS_API_KEYS` and its startup lines; Architecture gains `app/letters.py`, the letters route, "authenticates only the letters route, by API key", and "three env vars". Stays under a page.

Not changed, deliberately:
- `app/claims.py` and `tests/test_claims.py`: spec R16, `get_status` unchanged. If either shows in the diff, the plan was departed from. (engineer)
- `requirements-dev.txt`: `hashlib`, `hmac`, `json`, `re` are standard library (R17).
- `ops/`, `.github/**`, `.claude/**`: untouched; the last two are protected paths.
- `intent/letters-claim-details-prefill/spec.md`: nothing here overturns a spec decision.

## Interfaces fixed by this plan

So the library and the HTTP work can proceed independently (see Parallelisable):

- `app.letters.get_letter_details(claim_id: str) -> dict` returns, in this order, `claim_id`, `customer_name`, `policy_number`, `status`, `date_of_loss`, `next_step`, `handler_name`. Raises `KeyError` (unknown id) or `app.letters.LettersUnavailable` (source unreachable; the fixture never raises it).
- `app.server.parse_api_keys(raw: str | None) -> tuple[str, ...]`. `None`, empty or whitespace-only gives `()`. Items are split on commas and stripped. An empty item is dropped with one WARNING naming its 1-based position (engineer: a trailing comma must not stop the service). An item shorter than 32 characters raises `ValueError` whose message names the position and never the value.
- `app.server.create_server(host="127.0.0.1", port=8000, *, api_keys=None)`. Stores `tuple(sha256(k) for k in api_keys or ())` as `server.letters_key_digests`. Existing positional callers are unaffected. (engineer)
- `app.server._key_matches(presented: str | None, digests) -> bool`. `False` for `None`, empty or no digests. Otherwise SHA-256 of the UTF-8 presented value is compared with `hmac.compare_digest` against every digest, results OR-ed with no early exit.

## Order of work

Each step ends with `make build`, `make test`, `make lint` green. Steps 2 to 6 are one PR.

1. **Baseline.** `.venv/` exists (Python 3.14.7 locally, 3.12 in CI). Confirm `Build succeeded`, `57 passed`, lint prints nothing.

2. **Library** (`app/letters.py`, `tests/test_letters.py`). Fixture values are obviously fake (engineer): `C-1001` B. Example, `P-10001`, `2026-08-02`, "Awaiting documents from customer", H. Handler; `C-1002` A. Example, `P-88213`, `2026-08-14`, "Awaiting engineer's report", H. Handler (matches the spec's example body except the handler name); `C-1003` C. Example, `P-10003`, `2026-07-21`, "Payment being arranged", K. Handler; `C-1004` D. Example, `P-10004`, `2026-06-30`, `next_step` and `handler_name` both `None` (engineer: the null case). `get_letter_details` does `record = DETAILS[claim_id]` then builds the dict field by field from the five named keys plus `claim_id` and `get_status(claim_id)`, never `**record` (R2, allow-list not copy). Tests:
   - `test_known_claim_returns_exactly_seven_keys_in_order`: `list(result)` equals the seven names.
   - `test_status_matches_get_status` (parametrised over the four ids).
   - `test_unknown_claim_raises_keyerror`.
   - `test_paid_claim_has_null_next_step_and_handler`: `C-1004`.
   - `test_no_field_named_like_amount_or_address`: for every fixture id, no key contains `amount`, `address`, `postcode`, `street`.
   - `test_claim_id_and_status_never_null`: every fixture id.
   - `test_fixture_covers_every_status_id`: `set(DETAILS) == set(STATUSES)`.
   - `test_date_of_loss_is_iso_date`: `date.fromisoformat` succeeds for every id.

3. **Key parsing and matching** (`app/server.py`, tests in `tests/test_server.py`). `parse_api_keys` and `_key_matches` as fixed above; `create_server` keyword. Tests:
   - `test_parse_api_keys` (parametrised): `None`, `""`, `"   "` give `()`; one key; two keys; `" A , B "` stripped; `"A,"` gives `(A,)` and a WARNING containing `item 2`; `",A"` gives `(A,)` with `item 1`. Keys in these cases are 32-plus characters.
   - `test_parse_api_keys_refuses_short_key` (parametrised): a lone 31-character key, and a good key followed by a short one, raise `ValueError` whose message contains `item` and neither key's text.
   - `test_key_matches` (parametrised): correct key `True`; wrong key same length `False`; `None`, `""`, non-ASCII, and correct key against no digests, all `False`.
   - `test_create_server_default_has_no_keys` and `test_create_server_stores_digests` (two keys give two 32-byte digests; the plaintext is not an attribute of the server).

4. **Route** (`app/server.py`, `tests/test_server.py`). `LETTERS_PATH = re.compile(r"/claims/([^/]*)/letter-details")`. `_template` returns `/claims/{id}/letter-details` for it, enabled or not (engineer). `_get` dispatches to `_letter_details(claim_id)`, whose order is fixed and is the point of the step:
   1. no digests configured: `404 NOT_FOUND` (R8);
   2. `_key_matches(self.headers.get("X-API-Key"), digests)` false: `logger.warning("unauthorized /claims/{id}/letter-details")`, then `401 {"error": "unauthorized"}` (R6, R12);
   3. shape check, same rule as the status route: `404`;
   4. `get_letter_details`: `KeyError` gives `404`; `LettersUnavailable` gives `503 {"error": "unavailable"}` with `Retry-After: 5` (R9, R10);
   5. `200` with the dict as returned.
   `_method_not_allowed`: letters path gives `405 Allow: GET` only when digests are configured, else `404` with no `Allow` (engineer: R8 governs R13 when disabled). The `500` path is the existing `_handle` wrapper and needs no change. Tests, on `letters_port` unless stated, with `KEY_A` and `KEY_B` 40-character module constants and `request(..., headers={"X-API-Key": ...})`:
   - `test_letter_details_with_valid_key`: `C-1002`, exact body string in spec order, `status` equal to the status route's for the same id, both JSON headers (AC1).
   - `test_letter_details_either_key_accepted` (parametrised over the two keys) (AC6).
   - `test_letter_details_without_valid_key_is_401` (parametrised: header absent, empty, wrong key same length, wrong key different length, `KEY_A` plus one character): exact body, headers (AC2).
   - `test_letter_details_401_precedes_404` (parametrised: `C-9999`, `nonsense`, empty id) with a wrong key and `app.server.get_letter_details` monkeypatched to raise `AssertionError` if called (AC3).
   - `test_letter_details_unknown_claim_is_404`: valid key, `C-9999`.
   - `test_letter_details_malformed_ids_are_404` (parametrised: the same six inputs as the status route's malformed test) with valid key and lookup monkeypatched to fail on call; input absent from body (R9, R11).
   - `test_letter_details_disabled_is_404_on_every_method` (parametrised: GET plus the eight non-GET methods) on the keyless `port` fixture with a valid key sent: `404`, exact body, no `Allow` header (AC4).
   - `test_letter_details_unavailable_is_503`: lookup monkeypatched to raise `LettersUnavailable`; exact body, `Retry-After` is `5`, both JSON headers (AC7).
   - `test_letter_details_non_get_is_405` (parametrised: eight methods, key present and absent): `Allow: GET`, body except for HEAD (AC8, R13).
   - `test_letter_details_internal_error_is_500_without_pii`: lookup raises `RuntimeError("A. Example P-88213 " + KEY_A)`; exact body; `caplog.text` contains none of `A. Example`, `P-88213`, `KEY_A`, `C-1002`.
   - `test_letter_details_logs_contain_no_pii_or_key`: one request each for `200`, `401`, unknown-id `404`, malformed `404`, `503`; wait for six records (five access lines plus one warning); assert `GET /claims/{id}/letter-details 200`, `401`, `404`, `503` appear, a WARNING record exists, and `caplog.text` contains no fixture name, policy number, date, handler name, claim id or key (AC9, R11, R12).
   - `test_letter_details_query_string_is_ignored`.
   - `test_letter_details_every_response_is_no_store` (parametrised: `200`, `401`, `404`, `405`, `503`, `500`) (R14).
   Write the 401-precedence and disabled tests before wiring the lookup; they are the proof that the gate is in front of everything.

5. **Entry point** (`app/server.py`). `main()` calls `parse_api_keys(os.environ.get("CLAIMS_LETTERS_API_KEYS"))`. On `ValueError`: `logger.error` with the exception's message (safe by step 3's test) and `raise SystemExit(2)`, before `create_server`. With keys: `logger.info("letters endpoint enabled (%d keys)")`. Without: `logger.info("letters endpoint disabled: CLAIMS_LETTERS_API_KEYS is not set")`. No tests on `main` (engineer); covered by the manual checks in Proof.

6. **Docs.** `CLAUDE.md` sentences listed under Files that change; `app/server.py` module docstring.

7. **Verify and hand over.** Three make targets, output pasted into the PR body per the template; manual checks under Proof; any departure recorded in `plan.md` in the same commit.

## Risks

**What could break.**
- The 43 existing server tests, through the extended `_template`, the longer known-path check in `_method_not_allowed` and the `create_server` change. The keyword-only default keeps every existing call valid; the tests must pass unchanged, and `git diff` on the existing test functions must be empty apart from the `request` helper's new optional argument.
- `tests/test_claims.py` and `app/claims.py`: must not appear in the diff.
- `make lint` covers two more files; unused imports in tests are the likely nit.
- CI runs Python 3.12. `hashlib.sha256`, `hmac.compare_digest`, keyword-only arguments and `dict` insertion order all exist there. No 3.14-only syntax.

**Riskiest step: step 4, the gate order.** A key check placed after the lookup, or a disabled server that still serves `405`/`200`, exposes customer names and policy numbers to anything on the portal network, and every happy-path test still passes. Mitigation: the order is written as a numbered list above; the 401-precedence test monkeypatches the lookup to fail on call so a gate behind the lookup cannot pass; the disabled test sends a valid key so an enabled-by-default server cannot pass. A reviewer should treat any reordering of `_letter_details` as an Important security finding.

**Timing on the key compare.** `hmac.compare_digest` leaks length differences, not values. Hashing both sides to 32 bytes first removes the length signal; OR-ing over all digests removes the match-position signal. Keeping digests rather than plaintext on the server object is a side benefit, not a security claim: the process environment still holds the plaintext.

**PII in the 500 path.** The existing `_frames` logger writes file, line and function, never source text or `str(exc)`, so fixture values on source lines in `app/letters.py` cannot reach the log. The 500 test raises with a name, a policy number and a key in the message to prove it. `main()` does log `str(exc)` for the config `ValueError`; that is safe only because `parse_api_keys` never puts key text in its message, which step 3 tests.

**Header handling.** `self.headers` is case-insensitive, so `x-api-key` works. If a client sends the header twice, `get` returns the first; the second is ignored, not merged. Non-ASCII header values are decoded as Latin-1 by the base class, re-encoded as UTF-8 here, and simply fail to match.

**Two servers in one test module.** `port` and `letters_port` both bind port 0 on loopback and both shut down in fixture teardown. Log assertions count records, and a 401 adds a warning record to the access line, so waits must count both.

**Rotation with a trailing comma.** Handled by ignoring the item with a warning (engineer). The residual risk is a key list that is entirely commas: it parses to `()` and the endpoint is disabled with a startup line saying so, which is the fail-closed behaviour R8 asks for.

**Fixture names look like people.** All values are placeholders (`A. Example`, `H. Handler`). The spec's example body used the intent author's name; this plan does not.

**Enumeration with a leaked key** (spec Areas of concern F) is not mitigated here and cannot be; the gateway work is out of scope and remains a go-live gate.

## Proof

Run before reporting done. Every automated line has a pass condition that needs no judgement.

- `make build` ends with `Build succeeded`.
- `make test` ends with `148 passed` and no `failed` or `error`: 60 existing, 11 in `tests/test_letters.py` (1 + 4 + 1 + 1 + 1 + 1 + 1 + 1), 77 new in `tests/test_server.py` (step 3: 9 + 2 + 2 + 6 + 2 = 21; step 4: 1 + 2 + 5 + 3 + 1 + 6 + 9 + 1 + 16 + 1 + 1 + 1 + 6 = 53; step 5: 1 + 2 = 3; see Departures after review). If the count differs, the test list above changed and this section is updated in the same commit.
- `make lint` prints nothing after the echoed `pyflakes` command line.
- `git diff --stat main` lists exactly `app/letters.py`, `app/server.py`, `tests/test_letters.py`, `tests/test_server.py`, `CLAUDE.md`, and this `plan.md` when updated, plus `intent.md` and `spec.md` for this change, which ride on the same branch and are part of the same PR. Not `app/claims.py`, not `tests/test_claims.py`, not `requirements-dev.txt` (R16, R17, AC11, AC12).
- `grep -h "^import\|^from" app/letters.py app/server.py` lists only standard-library modules, `app.claims` and `app.letters` (AC12).
- Manual, once, via a throwaway Python driver that starts `python -m app.server` as a subprocess with a chosen environment and makes requests with `http.client` (the sandbox does not expand shell variables, so the driver sets `env=` itself):
  - No `CLAIMS_LETTERS_API_KEYS`: stdout contains `letters endpoint disabled`; `GET /claims/C-1002/letter-details` with any header is `404` (AC4).
  - `CLAIMS_LETTERS_API_KEYS` set to a 20-character key: exit code `2`, stderr contains `CLAIMS_LETTERS_API_KEYS` and `item 1`, and does not contain the key (AC5).
  - Two 40-character keys with a trailing comma: stdout contains `letters endpoint enabled (2 keys)` and a warning containing `item 3`; a request with either key is `200` with the seven keys (AC6); `C-9999` is `404`; no key is `401`; `POST` is `405` with `Allow: GET`.
  - The captured stdout for the run contains `/claims/{id}/letter-details` and none of `C-1002`, `A. Example`, `P-88213`, `2026-08-14`, `H. Handler` or either key (AC9).
- Latency, informational only: 200 sequential authenticated `GET /claims/C-1002/letter-details` calls report a maximum under 50 ms. Not a gating test.
- Human, tracked on the PR and not automatable: AC13 (Priya confirms DocGen sends `X-API-Key`, maps seven fields, opens blank on `401`, `404`, `503`), AC14 (security policy owner accepts service-side key check), AC15 (baseline for re-keying time and QA return rate recorded before go-live).

## Departures during implementation (2026-09-02)

Recorded in the same commit as the code, per step 7.

- **Proof count corrected from 138 to 142.** Two causes. `main` gained three `tests/test_detect.py` tests (PR #6) after this plan was accepted; `origin/main` was merged into the branch before step 1, so the baseline is `60 passed`, not 57. And the step 4 sum was mis-added: the listed cases total 53, not 52, so the new server tests number 71, not 70. No test was added to or removed from the lists above.
- **Step 1 baseline** therefore reads `60 passed`; nothing else in step 1 changed.
- **`tests/test_server.py` fixtures.** The `port` fixture body moved into a shared `serve` helper so `letters_port` does not duplicate the start-and-shutdown sequence. The fixture's behaviour and every existing test function are unchanged; the diff on existing code is the `request` helper's `headers` argument and this fixture refactor.
- **Shape check shared.** `app/server.py` gained a one-line `_well_formed(claim_id)` helper used by both claim routes, instead of repeating the length-and-pattern test in `_letter_details`. Same rule, one place.
- **Disabled-state test and `HEAD`.** `test_letter_details_disabled_is_404_on_every_method` asserts the exact `404` body for every method except `HEAD`, which carries no body by protocol. The status code and the absence of `Allow` are asserted for all nine.
- **Startup line order.** `main()` logs the letters enabled or disabled line before the `listening on` line, so `make run` now prints two lines before the first access line. `CLAUDE.md` says so.

## Departures after review (2026-09-02, PR #8)

Each answers a review thread on the PR; recorded in the same commit as the change.

- **Tests on `main()` after all.** The review found the three `main()` behaviours (exit 2 on a short key, the enabled line, the disabled line) untested, against the CLAUDE.md convention; step 5's "no tests on `main`" is withdrawn and the matching entry under Options not taken no longer applies. `tests/test_server.py` gains `test_main_refuses_short_key` (a `python -m app.server` subprocess with a 20-character key: exit code 2, `ERROR`, `CLAIMS_LETTERS_API_KEYS` and `item 1` in stderr, the key and `listening on` absent) and `test_main_logs_letters_state_before_listening` (parametrised: no keys gives the disabled line; two keys and a trailing comma give `enabled (2 keys)` and a warning naming `item 3`; both precede `listening on`; neither key appears). The Proof's manual AC4 and AC5 checks on startup output are therefore automated; the request-level manual checks stand.
- **Non-ASCII keys refused at startup.** `parse_api_keys` raises the same positional `ValueError` for an item that is not pure ASCII, with a message naming the position and never the value. Reason: `http.server` decodes header values as Latin-1, so a non-ASCII key sent as UTF-8 by the client could never match and the operator would see the endpoint reported enabled but every request answered `401`. Test: `test_parse_api_keys_refuses_non_ascii_key` (parametrised, 2). `CLAUDE.md` and the Interfaces line for `parse_api_keys` now read "ASCII"; the spec's "at least 32 characters" (R7) is tightened, not overturned.
- **Duplicate keys dropped with a warning.** A repeat of an earlier item is ignored with a `WARNING` naming its position, like an empty item, so `letters endpoint enabled (N keys)` counts distinct keys and an operator mid-rotation is not told two keys overlap when one is live. One new case in `test_parse_api_keys`.
- **`METHOD_NOT_ALLOWED` constant.** The `405` body literal appeared twice in `_method_not_allowed` while every other error body was a module constant; it is now one constant beside them. No behaviour change.
- **Proof diff line.** The `git diff --stat main` line now says `intent.md` and `spec.md` are in the diff too, since the intent, spec and plan commits ride on this branch.

## Options not taken

- **Gateway-only authentication, or `Authorization: Bearer`.** Both rejected by the spec (Design decisions, Areas of concern B).
- **Bare `hmac.compare_digest` on the raw strings.** Leaks the configured key's length via loop count, and rejects non-ASCII input with a `TypeError` on `str`. Hash both sides first.
- **Extend `app/claims.py` with the details table.** Would put PII-shaped fixture data next to the status table and make R16 a matter of reading the diff instead of seeing no diff. Separate module. (engineer)
- **A separate `app/auth.py`.** Two functions do not justify a fourth module and a fourth test file.
- **Refuse to start on an empty item in the key list.** Rejected by the engineer: a trailing comma on the first rotation would take the service down. Ignore with a warning.
- **Read the environment per request** so keys rotate without a restart. The spec reads at startup and the comma list already gives overlap.
- **Hashed keys in configuration.** Operations complexity the spec did not ask for. The service hashes in memory instead.
- **`WWW-Authenticate` on `401`.** No registered scheme for an API-key header, and DocGen does not negotiate. Omitted. (engineer)
- **`403` for a wrong key.** Spec says `401` for all three failure cases.
- **Serve `405` on the letters path while disabled.** Would reveal the route exists without a key. `404` on every method. (engineer)
- **Tests on `main()`.** Engineer chose to cover parsing and refusal through `parse_api_keys` and the manual run.
- **Derive a `503` from a timeout or a live client.** There is no source yet (Areas of concern D). A named exception is the contract the future feed implements.
- **Derive `next_step` from `status`.** Out of scope in the spec.
- **Aligning `ci.yml` to 3.14, `scripts/check-endpoints.sh`, a deploy target.** Protected paths or tech-lead decisions, as before.

## Parallelisable

Step 2 (`app/letters.py`, `tests/test_letters.py`) and steps 3 to 5 (`app/server.py`, `tests/test_server.py`) touch disjoint files and can run as two sessions or worktrees, because the function name, return order, exception name and fixture values are fixed in this plan. The server session monkeypatches `app.server.get_letter_details` and imports `LettersUnavailable` by name, so it needs the library merged before its own tests run for real. Step 6 is a few lines and not worth a session.
