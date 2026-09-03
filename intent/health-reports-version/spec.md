# Spec: Let operators see which build is running from the health endpoint (from intent.md, accepted 2026-09-03, commit a3d15b1)
Status: draft. Policies applied: `ai-native-sdlc:secure-api-review` (plugin example policy, v0.2.0; placeholder owner). No brand, compliance, UX or data-classification policy skill was available in this session; see Areas of concern G.
Record: none

Written in a non-interactive session (2026-09-03). Where the intent left a decision open, this spec decides and says so. Anything only a human can answer is carried forward under Open questions.

## Summary
`GET /health` gains a second field, `build`, alongside the existing `status`. Its value is whatever `CLAIMS_BUILD` held in the service's environment when the process started, so an operator investigating a bad deploy can `curl` the health route and see which build is answering without logging on to the host. The route stays anonymous, stays free of claim data, and gains no request parameters. When `CLAIMS_BUILD` is not set — which is the case in every environment today, because nothing in this repository sets it — the field reads `"unknown"` and the service starts normally. That is the largest gap in this change: the code half is small, and the outcome the intent asks for is not delivered until whoever deploys the service sets the variable (Areas of concern A).

## Requirements
1. `GET /health` returns HTTP `200` with a JSON object containing exactly two keys, in this order: `status`, `build`.
2. `status` keeps its current value `"ok"` and its current meaning: the process is listening and able to answer. It is not a rollup of dependencies and does not change with this spec.
3. `build` is always present and is always a non-empty ASCII string. It is opaque to the caller: a build identifier to be compared and quoted, not parsed.
4. The value of `build` comes from the `CLAIMS_BUILD` environment variable, read once at process start. Changing the variable takes effect on the next restart and never mid-process, so two requests to the same process always report the same build.
5. If `CLAIMS_BUILD` is unset, empty, or whitespace-only, `build` is the literal string `"unknown"` and the service starts normally. `/health` never fails, and never returns `500`, because no build identifier was supplied.
6. Leading and trailing whitespace is stripped from the value before it is used or validated.
7. An accepted value is 1 to 64 characters long and contains only ASCII letters, digits, and the characters `.`, `_`, `+` and `-`. A value that is too long or contains any other character (a space, `/`, `:`, `@`, a control character, any non-ASCII character) is rejected: `build` is `"unknown"`, and the service logs one `WARNING` at startup that names the reason and never the value.
8. The service logs exactly one line at startup stating the build identifier in effect, or stating that it is unknown. The rejected value from R7 is never logged; the accepted value is.
9. `/health` stays anonymous: no API key, no gateway JWT required at this service, no request parameters, query string still ignored (policy rule 1 names `/health` as the one permitted anonymous route).
10. `/health` responses keep the headers every route already sends: `Content-Type: application/json; charset=utf-8` and `Cache-Control: no-store`. No cache between the operator and the service may hold a build identifier from a previous deploy.
11. `build` appears only in the `200` body of `GET /health`. No error body carries it: a non-`GET` on `/health` still returns `405` with `Allow: GET` and body `{"error": "method_not_allowed"}`, and `404` and `500` bodies are unchanged.
12. No response body or log line gains a claim id, a letter field, an API key, a hostname, a bind address, a file path, or any environment value other than the accepted build identifier. The rule that this service never echoes a claim id is unchanged; `/health` still touches no claim data.
13. `GET /claims/{id}/status`, `GET /claims/{id}/letter-details`, the `404`/`405`/`500` behaviour of every path, and the access log format are unchanged.
14. Runtime dependencies remain standard library only. Reading the environment and serialising the field use the standard library.
15. Every behaviour above is covered by a test in the same PR (project convention), including a test that the set of keys in the `/health` body is exactly `status` and `build`.

## Design
### Behaviour
- An operator sees odd behaviour after a deploy and runs `curl -s http://<service>/health`. They get `{"status": "ok", "build": "a3d15b1"}` and can say which build answered.
- The portal team does the same from their own tooling to confirm which build they are talking to before raising a ticket.
- `CLAIMS_BUILD` not set (every environment today, and `make run` on a laptop): `{"status": "ok", "build": "unknown"}`, plus a startup line saying the build identifier is unknown. An operator seeing `"unknown"` in a deployed environment has learned something real: the deploy did not set it.
- `CLAIMS_BUILD` set to something the service will not serve (too long, or containing a space, a slash or a colon): `"unknown"`, plus one `WARNING` at startup. The claims routes are unaffected and the service serves traffic.
- Two instances behind one address: a single `curl` reports whichever instance answered, not the fleet (Areas of concern F).

**Decision: the identifier comes from `CLAIMS_BUILD`, not from a git commit baked at build time.** The intent asks for the environment variable if nothing bakes a version today, and nothing does: `make build` is `compileall` over `app/`, CI (`.github/workflows/ci.yml`) runs build, test and lint and produces no artifact, and there is no deploy target or deploy workflow in this repository — the `production-gate.sh` hook guards a deploy command that does not yet exist. There is no build step in which to bake a commit, and inventing one is a larger change than the intent asks for. If a packaging or deploy step is added later, baking the commit becomes the better source and removes two of the concerns below; that is a new intent (Areas of concern H).

**Decision: the field is named `build` and its value is an opaque string.** `build` matches the operator's question ("which build is this?") and does not promise semver ordering the way `version` would. It is a string and not an object so the portal team can log or display it without a shape to keep in step. What the string means — commit sha, release tag, pipeline number — is the deployer's choice, constrained only by R7's charset (Areas of concern C).

**Decision: a missing or malformed value degrades to `"unknown"`; it does not stop startup.** This differs from the precedent set by `CLAIMS_LETTERS_API_KEYS`, where a bad item exits with code 2. That variable guards PII, and starting with a key the operator did not intend risks serving customer data; here the only consequence of a bad value is that an operator cannot tell which build is running, which is exactly today's situation. Taking the whole claims service down over a cosmetic health field would trade a real outage for a diagnostic. `make run` on a laptop with no environment set must also keep working. The tech lead can overturn this (Areas of concern D).

**Decision: the value is validated by shape before it is served.** `/health` is anonymous, so whatever `CLAIMS_BUILD` holds is readable by anyone who can reach the service. The charset and length in R7 bound what can be disclosed: no spaces, no `/` (so no path and no `owner/branch`), no `:` or `@` (so no `host:port` and no `user@host`), no control or non-ASCII characters (so no header or log injection through the value), at most 64 characters. This makes the accidental paste — a full path, a connection string, a branch name carrying a ticket title — fail closed to `"unknown"` rather than be published. It cannot stop a well-formed value that is itself sensitive, such as an internal hostname written without dots; that is a policy question, not a validation one (Areas of concern C).

**Decision: read once at startup, not per request.** The build cannot change while a process runs, so re-reading the environment on every request would only add a way for two requests to disagree. It also keeps `/health` free of any work beyond serialising a constant, which is what a liveness probe needs.

**Decision: `/health` gains nothing else.** No uptime, no start time, no dependency status, no `/version` route. The intent asks one question and this answers it; anything more makes the anonymous route a richer description of the deployment (Out of scope).

### Interfaces
| Route | Method | Auth | Request | Responses | Data classification |
|---|---|---|---|---|---|
| `/health` | GET | None (anonymous, per policy rule 1) | None. Query string ignored. | `200 {"status":"ok","build":"<id>"}`; `405` with `Allow: GET` on any other method | `status`: none. `build`: operational metadata, disclosed unauthenticated. No PII, no customer data, no secret (R7 and Areas of concern C). |
| `/claims/{id}/status` | GET | Unchanged | Unchanged | Unchanged | Unchanged |
| `/claims/{id}/letter-details` | GET | Unchanged (`X-API-Key`) | Unchanged | Unchanged | Unchanged |

Example `200` body:

```json
{"status": "ok", "build": "a3d15b1"}
```

- Versioning: none in the path. This is an additive change to an existing response object. A consumer that reads `status` by key is unaffected; a consumer asserting the exact body string breaks (Areas of concern E).
- Configuration surface after this change: `CLAIMS_HOST`, `CLAIMS_PORT`, `CLAIMS_LETTERS_API_KEYS`, `CLAIMS_BUILD`.

### Data
- **Read:** `CLAIMS_BUILD` from the process environment, once, at startup. Nothing else new.
- **Stored:** the validated identifier in memory for the life of the process. Nothing at request time; the route stays read-only and stateless.
- **Logged:** one additional startup line naming the build in effect or saying it is unknown, and at most one `WARNING` when a supplied value is rejected, without the value. The per-request access line is unchanged: method, templated path, code, duration.
- **Returned:** the identifier, to any caller who can reach `/health`. Treat it as public to everyone inside the gateway's reach.
- **PII:** none. `/health` reads no claim, no letter field and no key, and this change does not give it access to any.
- **Audit:** policy rule 3 requires audit events for state-changing endpoints. `/health` changes no state and emits none.
- **Retention:** nothing retained beyond logs, which contain no personal data.

### Non-functional
- **Performance:** unchanged. `/health` still does no lookup and no I/O; the response grows by a few dozen bytes. It remains suitable as a liveness probe at probe frequency.
- **Availability:** the change must not add a way for the service to fail to start or for `/health` to fail (R5, R7). A liveness probe that starts failing because of a health-endpoint change would cause the very outage this is meant to help diagnose.
- **Security:** the endpoint stays anonymous and its new field is bounded in shape and length (R7). Fingerprinting exposure is discussed in Areas of concern B.
- **Observability:** the startup line and the `/health` field are two views of the same value, so an operator with log access and an operator with only network access can both answer the question.
- **Accessibility and copy:** not applicable; the response is machine-facing. No operator-facing UI is in scope.

## Acceptance criteria
1. With `CLAIMS_BUILD=a3d15b1`, `GET /health` returns `200` and exactly `{"status": "ok", "build": "a3d15b1"}`, with `Content-Type: application/json; charset=utf-8` and `Cache-Control: no-store`.
2. With `CLAIMS_BUILD` unset, `GET /health` returns `200` with `build` equal to `"unknown"`, and the service starts and serves the claims routes normally.
3. With `CLAIMS_BUILD` set to an empty string or to spaces, the result is identical to criterion 2.
4. With `CLAIMS_BUILD` set to `  v1.4.2  `, `build` is `v1.4.2` (whitespace stripped).
5. With `CLAIMS_BUILD` set to a 65-character value, to `ops/stage-automation`, to `deploy host:8000`, to a value containing a newline, or to a non-ASCII value, the service starts, `build` is `"unknown"`, and a `WARNING` is logged that does not contain the supplied value.
6. Startup logs exactly one line naming the build in effect, or saying it is unknown, in every case above.
7. `POST`, `PUT`, `DELETE` and `HEAD` on `/health` return `405` with `Allow: GET`, and no response other than the `GET` `200` contains a `build` key.
8. The test asserting that `/health`'s `200` body has exactly the keys `status` and `build` passes.
9. Every existing test for `GET /claims/{id}/status`, `GET /claims/{id}/letter-details`, `404`, `405`, `500`, the `no-store` header and the HTTP/0.9 guard passes unchanged, apart from the one assertion of the exact `/health` body, which is updated rather than removed.
10. A run covering all the above shows no claim id, letter field or API key in any `/health` body or in the logs.
11. `requirements-dev.txt` is still the only dependency file and `app/` imports only the standard library.
12. `make build`, `make test` and `make lint` are green, with output pasted in the PR.
13. The operator who deploys the service confirms in writing where `CLAIMS_BUILD` will be set and to what kind of value, or the PR records that it will read `"unknown"` in every environment until that exists (Areas of concern A and C). A human must satisfy this criterion.
14. Whoever probes `/health` today (portal, gateway, any monitor) confirms that an added key does not break their check (Areas of concern E). A human must satisfy this criterion.

## Areas of concern
Listed in the order the product owner should work them.

- **A. Nothing sets `CLAIMS_BUILD`, so merging this alone does not deliver the intent.** There is no deploy target, no deploy workflow and no packaging step in this repository. Shipping this change makes every environment report `"unknown"` until an operator wires the variable into however the service is actually started. The code is a prerequisite, not the outcome. **Resolve with:** whoever operates the service, and the tech lead. Decide before merge whether the deployment side lands in the same window; if it will not, say so on the PR so nobody reads `"unknown"` as a bug.
- **B. The build identifier is disclosed to any unauthenticated caller.** Policy rule 1 permits `/health` to be anonymous but says nothing about what it may contain. Naming the exact build lets anyone who can reach the route match it against known defects in that build. The service binds to loopback by default and is meant to sit behind the portal or gateway, so the exposure should be internal — but this spec cannot verify that the gateway does not proxy `/health` outward. **Resolve with:** the security policy owner (unnamed in the example skill) and the gateway team: confirm `/health` is not reachable from the public internet, or accept the disclosure explicitly.
- **C. Validation bounds the shape of the value, not its meaning.** R7 stops a path, a `host:port`, a branch name with slashes and anything non-ASCII, but `prod-db-01` or a 40-character token passes the charset. The service cannot tell a commit sha from a secret. **Resolve with:** the operator who sets the variable and the security policy owner: write down the permitted kinds of value (commit sha or release tag), and confirm that no secret and no internal hostname is ever placed there. The intent's constraint — no secrets, no internal hostnames — ultimately holds in the deploy configuration, not in this code.
- **D. Degrading to `"unknown"` breaks the precedent set by the API-keys variable.** `CLAIMS_LETTERS_API_KEYS` exits with code 2 on a bad item; this variable does not. The reasoning is in Design (failing open here costs a diagnostic, not customer data), but a repository with two different conventions for bad configuration is a thing a reader will trip over. **Resolve with:** the tech lead: accept the split with the reason recorded, or make both exit.
- **E. An added key can break an exact-match consumer.** `tests/test_server.py` asserts the `/health` body as an exact string today, which is a fair sign that someone else may too. A liveness probe that string-matches `{"status": "ok"}` would start failing on deploy and take the service out of rotation — a worse incident than the one this change helps diagnose. **Resolve with:** the portal team and whoever configures the probes, before merge.
- **F. One response describes one process, not the deployment.** If the service ever runs as more than one instance behind a single address, a `curl` reports whichever answered, and a half-finished rollout can look healthy. This change is still worth having, but an operator should not read it as "the fleet is on this build". **Resolve with:** J. Ortiz and the operators: say whether more than one instance is ever in play, and if so whether per-instance identification is a follow-on intent.
- **G. Only one policy skill was available, and it is a placeholder.** `secure-api-review` is the plugin's example with no named owner, and no brand, compliance, UX or data-classification policy exists in this repository. The classification of `build` as operational metadata is this spec's own. **Resolve with:** the tech lead, who owns policy skills here. Treat "policies applied" as advisory until real ones exist. Carried from the two prior specs, still unresolved.
- **H. No endpoint checker.** The API security standard asks for `scripts/check-endpoints.sh` output; it does not exist. `/health` was checked by hand against the four rules (see the summary accompanying this spec). **Resolve with:** the tech lead, as in the two prior specs.
- **I. The env-var choice is provisional on there being no build step.** If a packaging or deploy step is added, a commit sha baked at build time would be more trustworthy than a variable an operator can mistype, and would close A and most of C. **Resolve with:** the tech lead, when a deploy pipeline is designed. Not a blocker for this change.

## Open questions
Carried from intent.md. Each is marked answered or still open.

1. **Where does the identifier come from: a `CLAIMS_BUILD` environment variable, or the git commit baked in at build?** Answered: the `CLAIMS_BUILD` environment variable (R4, Design). The intent's own tie-breaker applies — nothing bakes a version today: `make build` byte-compiles `app/`, CI produces no artifact, and there is no deploy target or workflow. Revisit if a packaging step is ever added (Areas of concern I).
2. **Who sets `CLAIMS_BUILD`, where, and to what value?** Still open, and it is what stands between this change and the outcome the intent wants. Owner: whoever operates the service, with the security policy owner on the permitted kinds of value (Areas of concern A and C). Acceptance criterion 13.
3. **Is `/health` reachable from outside the gateway?** Raised by this spec, not the intent, because the intent's "must not reveal secrets or internal hostnames" constraint depends on the answer. Still open. Owner: the gateway team and the security policy owner (Areas of concern B).

## Out of scope
- Any other field on `/health`: uptime, start time, process id, dependency or downstream status, a claims-core check. `status` keeps its current meaning.
- A separate `/version` route, or a build identifier on any other route or in the per-request access log.
- Exposing git metadata of any kind: branch, tag, dirty flag, commit message, author.
- Creating a build, packaging or deploy pipeline, or a `make deploy` target, and anything that would bake a version at build time.
- Setting `CLAIMS_BUILD` in any environment; that is deployment configuration, not code (Areas of concern A).
- Gateway configuration: whether `/health` is proxied, and to whom (Areas of concern B).
- Authentication or rate limiting on `/health`; it stays anonymous per policy rule 1.
- Any change to `GET /claims/{id}/status`, `GET /claims/{id}/letter-details`, the letters API key handling, or the trust arrangement with the portal.
- Fleet-wide or per-instance build reporting (Areas of concern F).
