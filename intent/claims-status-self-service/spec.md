# Spec: Expose claim status over HTTP for the customer portal (from intent.md, accepted 2026-09-02, commit 1d2f3c3)
Status: accepted (product owner, 2026-09-02; tech lead consulted on the server choice). Policies applied: `ai-native-sdlc:secure-api-review` (plugin example policy, v0.1.0; placeholder owner). No brand, compliance, UX or data-classification policy skill was available in this session; see Areas of concern.
Record: none

Written in a non-interactive session (2026-09-02). Where the intent left a decision open, this spec decides and says so. Anything only a human can answer is carried forward under Open questions.

## Summary
The claims service gains its first HTTP surface: a single read-only endpoint, `GET /claims/{id}/status`, that returns a claim's current status as JSON, plus an anonymous `GET /health` so operators can tell the process is up. The portal backend calls the status endpoint on behalf of a customer it has already authenticated and shows the result, so customers stop phoning the contact centre for status-only queries. The existing library lookup (`get_status`, `KeyError` for unknown ids) is unchanged; the HTTP layer sits on top of it. The service does not authenticate callers itself: it trusts the portal and gateway in front of it, and that trust boundary is the first concern the product owner must close with the portal team and the security policy owner.

## Requirements
1. `GET /claims/{id}/status` returns HTTP `200` with body `{"claim_id": "<id>", "status": "<status>"}` when `{id}` is in the status table.
2. `status` is one of the existing lowercase snake_case values: `received`, `in_review`, `approved`, `paid`. The endpoint never invents, maps or translates statuses; the portal owns customer-facing wording.
3. `GET /claims/{id}/status` returns HTTP `404` with body `{"error": "not_found"}` for any id not in the status table, including ids that are not shaped like `C-1001`. There is no `400` for a malformed id (decision, see Design).
4. The `404` body and any error message never echo the requested id.
5. Before lookup, the id is checked against the shape `^C-[0-9]+$` and a maximum length of 32 characters. An id failing the check is answered `404` without touching the status table.
6. Any path other than `/claims/{id}/status` and `/health` returns `404` with the same `{"error": "not_found"}` body.
7. Any method other than `GET` on a known path returns `405` with an `Allow: GET` header.
8. All responses carry `Content-Type: application/json; charset=utf-8` and `Cache-Control: no-store`.
9. `GET /health` returns `200` with body `{"status": "ok"}` and requires no authentication. It is the only anonymous route.
10. The response carries no data about the customer: no name, policy number, amount, dates or handler. Only the claim id (which the caller supplied) and the status.
11. The service does not log claim ids. Access logs record method, path with the id replaced by a placeholder (`/claims/{id}/status`), response code and duration.
12. The service performs no authentication or authorisation of its own. It relies on being reachable only from the portal or gateway (see Design, Trust boundary, and Areas of concern A and B).
13. The existing library contract is unchanged: `get_status` still raises `KeyError` for an unknown id, and the HTTP layer maps that `KeyError` to `404`.
14. Runtime dependencies remain standard library only. Serving HTTP uses the standard library.
15. Every behaviour above is covered by a test in the same PR (project convention).

## Design
### Behaviour
- Portal backend, holding an authenticated customer session and a claim id the customer is entitled to see, calls `GET /claims/{id}/status`.
- Known id: `200`, JSON with `claim_id` and `status`. The portal renders the status in its own words.
- Unknown id, malformed id, or unknown path: `404`, `{"error": "not_found"}`. The portal treats these identically ("we could not find that claim").
- Wrong method: `405`, `Allow: GET`.
- `GET /health`: `200`, `{"status": "ok"}`. No lookup, no logging of anything beyond the access line.
- Any unhandled exception inside the service: `500`, `{"error": "internal_error"}`, no stack trace or id in the body.

**Decision: malformed ids are `404`, not `400`.** The intent assumed `404`. The caller already knows the id, so a distinct `400` gives it nothing it can act on, and a uniform `404` keeps the two error paths (bad shape, not in table) indistinguishable to a caller probing the id space. Rule 2 of the API security standard (input validation) is still met: the id is validated against a pattern and length before any lookup (R5). The product owner can overturn this at acceptance; it changes one status code and one test.

**Decision: `/health` is in scope.** The service gains its first listening process, and the API security standard names `/health` as the one permitted anonymous route. Adding it here avoids a second change to the same surface.

### Interfaces
| Route | Method | Auth | Request | Responses | Data classification |
|---|---|---|---|---|---|
| `/claims/{id}/status` | GET | None at this service; portal/gateway authenticates (see Trust boundary) | Path param `id`, `^C-[0-9]+$`, max 32 chars. No body, no query params (ignored if present). | `200 {"claim_id","status"}`; `404 {"error":"not_found"}`; `405`; `500 {"error":"internal_error"}` | `claim_id`: customer data (REVIEW.md), treated as PII under rule 4 until classification says otherwise. `status`: customer data, not identifying on its own. |
| `/health` | GET | None (anonymous, per policy rule 1) | None | `200 {"status":"ok"}` | None |

- The HTTP layer is a thin adapter over `app/claims.py`. It contains no business logic beyond routing, validation of the id shape, and mapping `KeyError` to `404`.
- Content negotiation: none. JSON only.
- Versioning: none in the path. The response shape is additive-only from here; new fields may be added, existing ones are not renamed or removed without a new intent.

**Trust boundary (decision, pending confirmation).** The intent says "existing auth only; the endpoint adds no login, token or session of its own". The API security standard says every endpoint requires the gateway JWT. This spec resolves the conflict by placing JWT verification at the gateway, not in this service: the service listens only on a private interface reachable from the portal or gateway, and accepts every request that reaches it. This is the interpretation of "existing auth" that keeps the service standard-library-only and matches the intent's constraint. It must be confirmed by the portal team and the security policy owner (Areas of concern A). If they require the service to verify the JWT itself, that is a new runtime dependency or a hand-rolled verifier, and comes back to this spec.

**Authorisation (not this service's job, and it cannot do it).** The service has no notion of customer; it holds claim ids and statuses only. It therefore cannot check that the signed-in customer owns claim `C-1002`. The portal must only ask for claim ids it has already established belong to the signed-in customer. Without that check on the portal side, any customer who can guess an id can read any claim's status (Areas of concern B).

### Data
- **Read:** the in-memory `STATUSES` table in `app/claims.py`. Nothing else.
- **Stored:** nothing. The endpoint is read-only and stateless.
- **Logged:** one access line per request with method, templated path, response code and duration. Claim ids are not logged (R11). Errors are logged without the request id or any body content.
- **Returned:** `claim_id` (echo of the caller's input) and `status`. No customer attributes (R10).
- **Audit:** the API security standard requires audit events for state-changing endpoints. This endpoint changes no state, so no audit event is emitted. If the compliance owner wants read access to claim status audited, that is a new requirement (Areas of concern E).
- **Data source:** the table is currently a four-row fixture. Serving it over HTTP does not make it real data. Feeding the table from the claims system of record is outside this change (Areas of concern G).

### Non-functional
- **Performance:** a dictionary lookup; target under 50 ms at the service for p99, excluding network. No caching layer; `Cache-Control: no-store` because status changes and is customer data.
- **Rate limiting:** at the gateway, not in this service. The service has no per-caller identity to rate-limit on.
- **Availability:** matches whatever hosts it; the service holds no state and can run as more than one instance.
- **Concurrency:** the server must handle concurrent requests without one slow client blocking others.
- **Accessibility and copy:** not applicable at this service; the portal renders the status. Whoever owns brand and UX policy must review the portal's wording for the four statuses and the not-found case (Areas of concern D).
- **Observability:** access log per request as above; `/health` for liveness.

## Acceptance criteria
1. `GET /claims/C-1001/status` returns `200` and `{"claim_id": "C-1001", "status": "received"}` with the headers in R8.
2. `GET /claims/C-9999/status`, `GET /claims/nonsense/status`, `GET /claims//status` and `GET /claims/C-1001/status/` all return `404` with `{"error": "not_found"}` and no echo of the input.
3. `POST /claims/C-1001/status` returns `405` with `Allow: GET`.
4. `GET /health` returns `200` and `{"status": "ok"}`.
5. Existing tests pass unchanged: `get_status("C-9999")` still raises `KeyError`.
6. Access logs from a run covering the above contain no claim id.
7. `requirements-dev.txt` is the only dependency file and the app still imports only the standard library.
8. Every route and status code above has a test in `tests/` in the same PR.
9. The portal team confirms, in writing on the PR or the spec, that the trust boundary in Design is how they will call the service (Areas of concern A). This is the acceptance criterion that a human must satisfy; the rest can be automated.
10. A call-volume baseline for status-only calls is recorded before the portal goes live, so the intent's outcome (fewer status-only calls) can be measured (Areas of concern F).

## Areas of concern
Listed in the order the product owner should work them.

- **A. Authentication: policy and intent conflict.** `secure-api-review` rule 1 requires the gateway JWT on every endpoint. The intent forbids the endpoint adding any token check of its own. This spec resolves it by trusting the gateway to verify the JWT and having the service listen only where the gateway can reach it. That is a network-level trust decision nobody has yet confirmed. **Resolve with:** the security policy owner (unnamed in the example skill) and the portal team. If they require in-service verification, the standard-library-only constraint or the "existing auth only" constraint has to give.
- **B. Authorisation cannot be done here.** The service has no customer data, so it cannot check that the requester owns the claim. If the portal passes through an id the customer typed, one customer can read another's claim status by guessing ids (they are sequential). **Resolve with:** the portal team, who must look up only claim ids already tied to the signed-in customer, and the security policy owner, who should decide whether that check needs to be verifiable from this side (for example, a gateway-injected header this service could log or check later).
- **C. Standard-library HTTP server in production.** R14 forces a standard-library server. Python documents its built-in server as not recommended for production because it implements only basic security checks. It is adequate behind a gateway for a four-row lookup, but this is the point at which "no runtime dependencies" becomes a production-architecture decision rather than a convenience. **Resolve with:** the tech lead, before plan mode. Options are accept it behind the gateway, or add a production server as the first runtime dependency (a `spec.md` decision per CLAUDE.md, so it belongs here, not in the plan).
- **D. Only one policy skill was available, and it is a placeholder.** `secure-api-review` is the plugin's example, with no named owner or source of truth. No brand, compliance, UX or data-classification policy skill exists in this repository. The spec applied the four example rules and general good practice, but no organisation standard has actually constrained it. **Resolve with:** whoever owns policy skills for this repository (the tech lead, per the adoption decisions). Until real policy skills exist, the product owner should treat "policies applied" on this spec as advisory.
- **E. Is a claim id PII, and should reads be audited?** REVIEW.md treats claim ids and statuses as customer data. The API security standard's rule 4 bars `pii`-tagged fields from logs and error messages, and there is no schema tagging anything. This spec treats the claim id as PII for logging purposes (never logged, never in error bodies) but still returns it in the `200` body, as the intent allowed. Rule 3 exempts read-only endpoints from audit, so status reads are not audited. **Resolve with:** the data or compliance owner, who should confirm the classification and whether customer status reads need an audit trail.
- **F. No success baseline.** The intent's evidence is "about a third of call time" with no baseline, target or date. Acceptance criterion 10 asks for a baseline before go-live, but nobody owns it yet. **Resolve with:** J. Ortiz (originator) and the product owner.
- **G. The data is a fixture.** `STATUSES` holds four hard-coded rows. The endpoint will faithfully serve them, which is correct for this change and useless for a customer. Connecting the table to real claim data is a separate intent, and the portal should not go live against this service until it exists. **Resolve with:** the product owner, who should sequence that intent before or alongside the portal work.
- **H. No endpoint checker.** The API security standard asks for `scripts/check-endpoints.sh` output. The script does not exist in this repository, so the two endpoints were checked by hand against the four rules (see the summary accompanying this spec). **Resolve with:** the tech lead, who decides whether to add the checker when the first endpoint lands.

## Open questions
Carried from intent.md. Each is marked answered or still open.

1. **Do third-party loss adjusters need access too?** Still open. Owner: J. Ortiz and the product owner. The design does not preclude it (the endpoint is caller-agnostic), but every additional caller widens the trust boundary in Areas of concern A and B and would need its own authorisation story. Out of scope for this change.
2. **Read-only, current status only; echoing the id is acceptable but nothing else.** Answered, confirmed: R1, R10, and Out of scope.
3. **Should a malformed id be `400` instead of `404`?** Answered: `404`, uniformly, with validation still performed first. Rationale under Design, Behaviour. The product owner may overturn at acceptance.
4. **Where does the "existing auth" trust boundary sit (network, gateway, header)?** Decided provisionally as network plus gateway-verified JWT, with this service performing no check. Still open for confirmation. Owner: the portal team and the security policy owner (Areas of concern A).
5. **Success measure: no target, baseline or date.** Still open. Owner: J. Ortiz and the product owner. Acceptance criterion 10 requires a baseline before go-live (Areas of concern F).
6. **Should the same endpoint serve contact centre tooling?** Still open. Owner: the product owner with claims operations. Technically nothing in this spec prevents it, but handler tooling would be a second caller with a different identity and audit expectation, so it needs its own intent and a revisit of Areas of concern A, B and E.

## Out of scope
- Writing or changing a status; any status history or timeline.
- Any field beyond `claim_id` and `status` in the response.
- Authentication, session or token handling inside this service.
- Authorisation (customer-owns-claim checks); the portal's responsibility.
- Access for loss adjusters, contact centre tooling or any caller other than the portal.
- Feeding `STATUSES` from a real data source.
- Customer-facing wording, translation or presentation of statuses; the portal's responsibility.
- Rate limiting, TLS termination and CORS; the gateway's responsibility.
- Changing the existing `get_status` contract.
