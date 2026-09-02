# Spec: Serve claim details to DocGen so handlers stop re-typing them (from intent.md, accepted 2026-09-02, commit 76cc93f)
Status: draft. Policies applied: `ai-native-sdlc:secure-api-review` (plugin example policy, v0.1.0; placeholder owner). No brand, compliance, UX or data-classification policy skill was available in this session; see Areas of concern.
Record: none

Written in a non-interactive session (2026-09-02). Where the intent left a decision open, this spec decides and says so. Anything only a human can answer is carried forward under Open questions.

## Summary
The claims service gains a second read-only endpoint, `GET /claims/{id}/letter-details`, that returns the seven details an update letter needs: claim number, customer name, policy number, current status, date of loss, next step and the assigned handler's name. DocGen, the vendor letters system, calls it when a handler opens a template for a claim and fills the template in, so the handler types nothing a second time. The endpoint is the service's first authenticated route: DocGen presents a fixed API key in a request header and the service checks it itself, because the response carries customer PII that the existing unauthenticated status route must never expose. The endpoint never returns an amount and never returns an address, which is how the solicitor rule is made impossible to break rather than merely enforced. The existing status route, the library contract and the trust arrangement with the portal are unchanged. The largest open decision, whether claims-core should serve DocGen directly instead, is decided provisionally in favour of this service and is the first concern the product owner must close.

## Requirements
1. `GET /claims/{id}/letter-details` returns HTTP `200` with a JSON object containing exactly these seven keys, in this order, when the caller is authenticated and `{id}` is a known claim: `claim_id`, `customer_name`, `policy_number`, `status`, `date_of_loss`, `next_step`, `handler_name`.
2. The response object never contains any key other than the seven in R1. In particular it never contains an amount, a monetary value, an address, or any part of an address, whatever the claim and whatever the template. This holds structurally: the response is built from a fixed allow-list of fields, not by copying a record.
3. `status` uses the existing lowercase snake_case values (`received`, `in_review`, `approved`, `paid`) and is the same value the status route returns for the same claim.
4. `date_of_loss` is an ISO 8601 calendar date string (`YYYY-MM-DD`). DocGen owns letter-facing date formatting.
5. Any of `customer_name`, `policy_number`, `date_of_loss`, `next_step` and `handler_name` may be `null` when the service holds no value for that claim. `claim_id` and `status` are never `null`. DocGen leaves a `null` field blank for the handler to type.
6. The endpoint requires a valid API key in the `X-API-Key` request header. A request with no key, an empty key or a key that does not match returns `401` with body `{"error": "unauthorized"}` before the claim id is inspected or any lookup is made.
7. Valid keys come from the service's configuration at startup (`CLAIMS_LETTERS_API_KEYS`: one or more keys, comma-separated, each at least 32 characters). Comparison is constant-time. The service refuses to start if a configured key is shorter than 32 characters.
8. If no key is configured, the endpoint is not served: it answers `404` `{"error": "not_found"}` like any unknown path, and the service logs one line at startup saying the letters endpoint is disabled. The endpoint fails closed; it never runs open because a key was forgotten.
9. An authenticated request for an id that fails the existing shape check (`^C-[0-9]+$`, at most 32 characters) or is not a known claim returns `404` with body `{"error": "not_found"}`, identical for both cases.
10. An authenticated request for a known claim whose details cannot be obtained because the source of details is unavailable returns `503` with body `{"error": "unavailable"}` and a `Retry-After: 5` header. No partial object is returned on a `503`.
11. No response body, log line or error message ever contains the claim id, the customer name, the policy number, the date of loss, the handler's name, the next step, or the presented API key. The existing rule for claim ids extends to every field this endpoint returns and to the key.
12. Access logs for the new route record method, the templated path `/claims/{id}/letter-details`, response code and duration only. A `401` is logged as a warning with the templated path and no header values.
13. Any method other than `GET` on `/claims/{id}/letter-details` returns `405` with `Allow: GET`, whether or not a key is presented.
14. All responses carry `Content-Type: application/json; charset=utf-8` and `Cache-Control: no-store`, as the existing routes do.
15. `GET /claims/{id}/status` and `GET /health` behave exactly as before. The status route does not require a key and does not gain any field.
16. The library contract is preserved: the lookup for letter details raises `KeyError` for an unknown id, as `get_status` does, and the HTTP layer maps that `KeyError` to `404`. `get_status` is unchanged.
17. Runtime dependencies remain standard library only. Key comparison, header parsing and JSON use the standard library.
18. Every behaviour above is covered by a test in the same PR (project convention), including a test that the set of keys in a `200` body equals exactly the seven in R1.

## Design
### Behaviour
- A handler opens a template for claim `C-1002` in DocGen. DocGen calls `GET /claims/C-1002/letter-details` with `X-API-Key: <key>`.
- Known claim, valid key: `200` with the seven fields. DocGen fills the template's merge fields; the handler reviews and sends.
- Any field `null`: DocGen leaves that merge field blank and the handler types it, as today for that one field.
- Missing or wrong key: `401`. DocGen tells the handler the letters link is not working and opens the template blank. This is a configuration fault, not a handler fault, and should page whoever owns the DocGen integration.
- Unknown or malformed id: `404`. DocGen tells the handler the claim was not found and opens the template blank.
- Details source unavailable: `503`. DocGen opens the template blank so the handler can still send the letter by typing, as today. DocGen may retry once after `Retry-After`; it must not retry in a loop.
- Wrong method: `405`, `Allow: GET`.
- Unhandled exception: `500`, `{"error": "internal_error"}`, nothing else in the body.

**Decision: this service serves DocGen, not claims-core.** The intent asks the spec to decide. Deciding for this service means the service must hold six more fields per claim than it does today, fed from claims-core by a mechanism that does not yet exist (see Data, and Areas of concern A and D). Deciding for claims-core would mean this change is not in this repository and this spec is void. This spec decides for this service because the intent was accepted into this repository, the service already sits behind the gateway that DocGen would need to traverse, and the originator's evidence is that claims-core has no HTTP surface for DocGen today. The product owner and the claims-core owner can overturn this at acceptance; if they do, this spec closes with that reason and no plan is written.

**Decision: the endpoint never returns an address, and has no notion of recipient.** The intent's recipient rule says it must be impossible for a solicitor letter to carry the customer's address. The address is not in the originator's seven fields. The strongest way to make the rule unbreakable is to never serve the address from this endpoint at all, so there is nothing for a mis-chosen template to leak. It follows that the endpoint does not need to know whether a letter is for a customer or a solicitor, so there is no recipient parameter. If the address is later wanted for customer letters, that is a new intent, and it will need a recipient-type input and its own version of this rule. This decision means handlers still type the address on customer letters, which bears on the success measure (Areas of concern E).

**Decision: `next_step` and `handler_name` are served if held, `null` if not.** The intent does not know whether claims-core holds these. The response shape includes both so DocGen's template mapping does not change when they become available; until then the field is `null` and the handler types it. `handler_name` is the handler assigned to the claim in the system of record, not the DocGen user opening the template. The service does not derive `next_step` from `status`; that would be inventing letter content, which the intent puts out of scope.

**Decision: the API key is checked in this service, not only at the gateway.** The prior spec (`claims-status-self-service`) placed all authentication at the gateway and had this service trust every request that reached it. That was acceptable for a status-only response. This endpoint returns a customer's name and policy number, and the portal must not be able to obtain those by reaching the same network. Two callers with different entitlements on one service means the service must be able to tell them apart, so it checks the key itself. The gateway should still restrict the letters path to DocGen's source addresses as defence in depth (Areas of concern F). This decision conflicts with the API security standard's rule 1 and is Areas of concern B.

**Decision: `X-API-Key`, not `Authorization: Bearer`.** The gateway is assumed to verify a JWT in `Authorization` for the portal's traffic. Putting an opaque key in that header invites the gateway to reject it as a malformed JWT. A dedicated header avoids the collision. Whether DocGen can set a custom header is carried forward to Priya.

**Decision: malformed and unknown ids are both `404`; `401` comes first.** The `404` decision matches the status route. Authentication is checked before the id is inspected so an unauthenticated caller learns nothing about which ids are well-formed or present.

### Interfaces
| Route | Method | Auth | Request | Responses | Data classification |
|---|---|---|---|---|---|
| `/claims/{id}/letter-details` | GET | `X-API-Key` header, checked by this service against configured keys (R6, R7). Gateway additionally restricts source to DocGen (recommended, Areas of concern F). | Path param `id`, `^C-[0-9]+$`, max 32 chars. No body. Query string ignored. | `200` seven-field object (R1); `401 {"error":"unauthorized"}`; `404 {"error":"not_found"}`; `405 Allow: GET`; `503 {"error":"unavailable"}` with `Retry-After: 5`; `500 {"error":"internal_error"}` | `claim_id`: customer data, PII for logging. `customer_name`, `policy_number`, `date_of_loss`: customer PII. `handler_name`: employee personal data. `next_step`: customer data. `status`: customer data. The presented key: secret. |
| `/claims/{id}/status` | GET | Unchanged (none at this service) | Unchanged | Unchanged | Unchanged |
| `/health` | GET | None (anonymous, per policy rule 1) | None | `200 {"status":"ok"}` | None |

Example `200` body:

```json
{
  "claim_id": "C-1002",
  "customer_name": "A. Example",
  "policy_number": "P-88213",
  "status": "in_review",
  "date_of_loss": "2026-08-14",
  "next_step": "Awaiting engineer's report",
  "handler_name": "J. Ortiz"
}
```

- Content negotiation: none. JSON only.
- Versioning: none in the path. The response shape is fixed at seven keys; adding a key is a new intent because of R2, and removing or renaming one is a breaking change for DocGen's template mapping.
- The endpoint is caller-agnostic beyond the key. It does not know which handler opened the template (Areas of concern G).

### Data
- **Read:** a per-claim details record holding the six fields beyond status, alongside the existing status table. Today the service holds a four-row status fixture and nothing else; the details record starts as a fixture of the same shape for the same four ids. Feeding both from claims-core is outside this change and is the subject of Areas of concern D.
- **Never held:** amounts, addresses, or any field not in R1. The details record's shape has no place for them, so there is nothing to filter out.
- **Stored:** nothing new at request time. Read-only and stateless.
- **Configuration:** `CLAIMS_LETTERS_API_KEYS` in the environment, read once at startup, held in memory only. Rotation is a restart with the new key added, then a second restart with the old key removed; the comma-separated list exists so the two keys overlap during the change. How the key reaches the environment (secrets manager, deployment config) is an operations decision outside this spec (Areas of concern C).
- **Logged:** one access line per request with method, templated path, code and duration. A `401` adds one warning line with no header values. Startup logs whether the letters endpoint is enabled. Nothing in R11 is ever logged.
- **Returned:** the seven fields only. Five of them are PII or personal data (see Interfaces); the intent accepts this as the purpose of the endpoint.
- **Audit:** the API security standard requires audit events for state-changing endpoints. This endpoint changes no state, so it emits none. Whether disclosure of name and policy number to a system on a handler's behalf needs an audit trail is for the compliance owner (Areas of concern G).
- **Retention:** nothing retained beyond logs, which contain no personal data.

### Non-functional
- **Volume:** about 400 template opens a day, one call each, peaking with the working day. Trivial for the service; no capacity work.
- **Performance:** target under 50 ms p99 at the service while the source is in-memory. If the source becomes a live call to claims-core, the target becomes 2 s p99 and the `503` path must trigger within 5 s so DocGen is never left waiting with a blank template.
- **Availability:** the letters endpoint failing must degrade to today's behaviour (handler types), never to a handler unable to send a letter. The `503` contract and DocGen's blank-template fallback are what deliver that.
- **Rate limiting:** at the gateway. The service does not rate-limit, but the gateway should cap the letters path well above 400 a day and far below the rate at which a leaked key could walk the id space (Areas of concern F).
- **Concurrency:** as before; one slow client must not block others.
- **Accessibility and copy:** not applicable at this service. DocGen renders the fields and its own error messages; wording for the `401`, `404` and `503` cases as seen by handlers is the Correspondence team's, and there is no UX or brand policy skill to constrain it (Areas of concern H).
- **Observability:** access log per request; `/health` for liveness; startup line for endpoint enabled or disabled. A rising `401` or `503` count on the letters path is the signal that the integration is broken.

## Acceptance criteria
1. `GET /claims/C-1002/letter-details` with a valid `X-API-Key` returns `200` and an object whose keys are exactly the seven in R1, in that order, with `status` equal to what `GET /claims/C-1002/status` returns.
2. The same request with no `X-API-Key`, an empty one, or a wrong one returns `401` `{"error": "unauthorized"}`, and the log for that request contains no header value.
3. The same request for `C-9999`, `nonsense`, and an empty id returns `404` `{"error": "not_found"}` with no echo of the input, and `401` takes precedence over `404` when the key is also wrong.
4. With `CLAIMS_LETTERS_API_KEYS` unset, `GET /claims/C-1002/letter-details` with any header returns `404`, and startup logs that the letters endpoint is disabled.
5. With a key shorter than 32 characters configured, the service refuses to start with a clear message.
6. With two keys configured, either key is accepted.
7. When the details source is unavailable, the response is `503` `{"error": "unavailable"}` with `Retry-After: 5` and no fields.
8. `POST`, `PUT`, `DELETE`, `HEAD` on the letters path return `405` with `Allow: GET`.
9. A search of the full `200`, `401`, `404`, `503` and `500` bodies and of the logs from a run covering all the above finds no claim id, customer name, policy number, date, handler name or key.
10. The response for every fixture claim contains no key named like an amount or address, and the test asserting exactly seven keys passes.
11. `GET /claims/{id}/status` and `GET /health` tests pass unchanged.
12. `requirements-dev.txt` is still the only dependency file and the app imports only the standard library.
13. Priya (Correspondence) confirms in writing on the PR or this spec that DocGen can send `X-API-Key`, maps the seven fields, and opens the template blank on `401`, `404` and `503` (Areas of concern C and E). A human must satisfy this criterion.
14. The security policy owner accepts, in writing, an API key checked at this service as the authentication for a system caller that cannot present a JWT (Areas of concern B). A human must satisfy this criterion.
15. Before go-live, a baseline is recorded for re-keying time per letter and for the QA return rate for wrong details, so the intent's success measures can be judged (Areas of concern E).

## Areas of concern
Listed in the order the product owner should work them.

- **A. Which system serves DocGen is decided provisionally, and the decision may be wrong.** This spec chooses this service. That obliges this service to mirror six more fields from claims-core, a feed that does not exist (D). If claims-core can expose the same seven fields to DocGen directly, that is one integration instead of two and no new PII enters this service. **Resolve with:** the product owner and the claims-core owner, before this spec is accepted. If claims-core serves DocGen, close this spec with that reason.
- **B. Authentication: policy and the caller's capability conflict.** `secure-api-review` rule 1 requires the gateway JWT on every endpoint. DocGen can only present a fixed API key. The prior spec's resolution (the service does no auth, the gateway does it all) cannot hold here because this endpoint returns PII the portal must not receive. This spec has the service check the key itself and asks the gateway to restrict the path to DocGen. **Resolve with:** the security policy owner (unnamed in the example skill) and the gateway team. The alternatives are the gateway exchanging DocGen's key for a JWT and injecting a caller identity this service checks, or Priya's team finding a way for DocGen to obtain a JWT. Either changes R6 to R8.
- **C. Key lifecycle is undesigned.** This spec defines how the service reads and checks keys, and how two keys overlap for rotation. It does not define who issues the key, how it is stored on the DocGen side, how often it rotates, or how it reaches this service's environment. A fixed shared secret with no rotation plan is a standing risk for as long as it lives. **Resolve with:** Priya (DocGen side), the security policy owner (rotation period, issuance), and whoever operates this service (secrets delivery).
- **D. The service holds a fixture, and a stale mirror produces the exact error this intent exists to remove.** The status table is four hard-coded rows. Six more fields per claim have no source yet. When a feed from claims-core exists, any lag between claims-core and this service means a letter with a stale status or next step, which is a wrong-detail letter reaching a customer. The intent's "detail errors close to zero" cannot be met by a mirror whose freshness is undefined. **Resolve with:** the tech lead and the claims-core owner. This is also the strongest argument for A going the other way. If the mirror stays, the feed's freshness guarantee is a new intent and this endpoint should not go live to DocGen before it exists.
- **E. The address is excluded, and the success measure may depend on it.** Handlers will still type the address on customer letters. If the address is most of the remaining typing, "under a minute" may not be reached by this change alone. The originator's seven fields did not include it, and the solicitor rule makes it the most dangerous field to serve. **Resolve with:** J. Ortiz and Priya: is the address typed today, where would it come from, and is a follow-on intent with a recipient-type input worth it.
- **F. One shared key can walk the whole customer base.** Claim ids are sequential. Anyone holding the key can enumerate names and policy numbers for every claim. The service cannot distinguish DocGen from a thief with DocGen's key. Mitigations are outside this service: gateway source restriction to DocGen, a rate cap on the letters path, and rotation (C). **Resolve with:** the security policy owner and the gateway team, before go-live.
- **G. PII disclosure is not audited, and the service cannot say which handler asked.** Rule 3 exempts read-only endpoints from audit. This endpoint discloses name and policy number on a handler's behalf, and the service knows only that DocGen asked. If the compliance owner wants a per-handler trail, DocGen would have to pass a handler identity, which is more personal data through this service, or keep the trail itself. **Resolve with:** the compliance owner and Priya.
- **H. Only one policy skill was available, and it is a placeholder.** `secure-api-review` is the plugin's example with no named owner. No brand, compliance, UX or data-classification policy exists. The classifications in Interfaces (customer PII, employee personal data, secret) are this spec's own. The handler-facing wording for the three error cases is unconstrained. **Resolve with:** the tech lead, who owns policy skills for this repository. Treat "policies applied" as advisory until real ones exist.
- **I. The standard-library server now carries PII.** The prior spec accepted Python's built-in server behind the gateway for a four-row status lookup. It now serves customer names and policy numbers. The risk has not changed in kind, but the consequence of a bug has. **Resolve with:** the tech lead, who accepted the earlier decision, to re-confirm it or make a production server the first runtime dependency here.
- **J. No endpoint checker.** The API security standard asks for `scripts/check-endpoints.sh` output. It does not exist. The new endpoint was checked by hand against the four rules (see the summary accompanying this spec). **Resolve with:** the tech lead, as before.

## Open questions
Carried from intent.md. Each is marked answered or still open.

1. **Which system serves DocGen: this service or claims-core?** Decided provisionally: this service (Design, Behaviour). Still open for confirmation. Owner: the product owner and the claims-core owner (Areas of concern A). If claims-core, this spec closes.
2. **Is the address needed for the letter or only the envelope, and does it come from this endpoint?** Answered for this change: it does not come from this endpoint (R2, Design). Whether it is needed at all, and from where, is still open. Owner: J. Ortiz and Priya (Areas of concern E).
3. **Who decides the recipient type: DocGen's template or the caller?** Answered: neither, because the endpoint returns nothing recipient-specific. DocGen's template continues to decide recipient and the endpoint does not need to know. Revisit only if the address is ever served.
4. **Are "next step" and "handler's name" fields on the claim in claims-core?** Answered for the contract: both are in the response and are `null` when not held (R5). Whether claims-core holds them is still open. Owner: the claims-core owner. Until answered, the fixture carries values for both so DocGen can test its mapping.
5. **How is the fixed API key issued, rotated and stored on the DocGen side, and where is it checked?** Answered for the check: at this service, `X-API-Key`, constant-time, one or more configured keys (R6, R7). Issuance, rotation period and storage are still open. Owner: Priya and the security policy owner (Areas of concern B and C).
6. **What happens when the claim is not found or claims-core is unavailable?** Answered: `404` and `503` respectively, and DocGen opens the template blank so the handler can still type; a letter is never blocked by this service (Design, Behaviour; R9, R10). DocGen's side of that behaviour is acceptance criterion 13. Owner for confirmation: Priya.

## Out of scope
- Writing, choosing or deriving letter text, including deriving `next_step` from `status`.
- Any change to how DocGen composes, addresses or sends letters, or to its handler-facing messages.
- Any change to a claim; the endpoint is read-only.
- Returning an amount, an address, or any field beyond the seven in R1; each is a new intent.
- A recipient-type input; not needed while no recipient-specific field is served.
- Feeding the status table or the details record from claims-core, and the freshness guarantee of that feed (Areas of concern D).
- Key issuance, rotation schedule, secrets storage and delivery (Areas of concern C).
- Gateway configuration: source restriction, rate limiting, TLS termination (Areas of concern F).
- Per-handler audit of disclosures (Areas of concern G).
- Any change to `GET /claims/{id}/status`, `GET /health`, or the portal's trust arrangement.
- Callers other than DocGen.
