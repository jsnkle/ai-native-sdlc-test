# Spec: Update letters open with the customer's name (from intent.md, accepted 2026-09-26, commit fa9de38)
Status: draft. Policies applied: `ai-native-sdlc:secure-api-review` (plugin example policy, v0.2.3; placeholder owner). No brand, compliance, UX or data-classification policy skill was available in this session; see Areas of concern.
Record: none

Written in a non-interactive session (2026-09-26). Where the intent left a decision open, this spec decides and says so. Anything only a human can answer is carried forward under Open questions.

## Summary
The letter details DocGen already fetches from `GET /claims/{id}/letter-details` gain an eighth field, `salutation`, holding a ready-made opening line such as `"Dear B. Example,"`. The service builds it from the same claim record that supplies `customer_name`, in the same lookup, so the line cannot name a customer from a different claim. That removes the hand-copying step and with it the wrong-name letters handlers produced by copying from the previous claim. When the claim has no customer name on record, `salutation` is `null` and DocGen leaves the line blank for the handler, as it already does for any other `null` field. An unknown claim id fails exactly as it does today (`KeyError` in the library, `404` over HTTP). No new personal data leaves the service: the line is the name DocGen already receives, with fixed wording around it. This change reopens the "exactly seven keys" contract from `letters-claim-details-prefill`, which that spec said only a new intent could do; this is that intent.

## Requirements
1. For a known claim with a customer name on record, the letter details include a key `salutation` whose value is exactly `"Dear "` + the claim's `customer_name` + `","`. For `C-1001` that is `"Dear B. Example,"`.
2. `salutation` is derived from the same record, in the same lookup, as `customer_name` in the same response. The two can never refer to different claims, and whenever `salutation` is not `null` it contains the `customer_name` of that response verbatim.
3. When the claim's `customer_name` is `null`, empty, or whitespace only, `salutation` is `null`. The service never substitutes a generic greeting, a placeholder, or a name from anywhere else.
4. The customer name is inserted as held, without changing case, adding a title or honorific, or reformatting initials. Surrounding whitespace on the held name is trimmed before it is inserted.
5. The response object now contains exactly these eight keys, in this order: `claim_id`, `customer_name`, `policy_number`, `status`, `date_of_loss`, `next_step`, `handler_name`, `salutation`. The first seven keep their meaning, values, order and `null` rules unchanged. The allow-list rule from the prior spec (R2 there) holds, extended by this one key: no amount, no address, nothing else.
6. An unknown claim id raises `KeyError` from the library lookup before any salutation is built, and the HTTP layer returns `404 {"error": "not_found"}` exactly as today. A malformed id, a missing or wrong key, a disabled endpoint, an unavailable source and a wrong method all behave exactly as today (`404`, `401`, `404`, `503`, `405`). None of these responses carries a `salutation` or any partial object.
7. `salutation` is classified as customer PII, the same as `customer_name`. It never appears in a log line, an error body or an exception message, joining the list of never-logged fields in the prior spec (R11 there).
8. `GET /claims/{id}/status`, `GET /health` and `GET /version` are unchanged. The status route does not gain `salutation`.
9. Runtime dependencies remain standard library only.
10. Every behaviour above is covered by a test in the same PR (project convention). That includes the test asserting the exact key set, which moves from seven to eight keys, and a test that a claim with no name yields `null`.

## Design
### Behaviour
- A handler opens an update-letter template for `C-1001`. DocGen calls the letters route as today and receives the eight fields. The template's first line is filled from `salutation`: `Dear B. Example,`. The handler no longer types or copies it.
- Claim with no name on record: `salutation` is `null`. DocGen leaves the opening line blank and the handler types it, exactly as today for that one line. The handler can see the line is missing, so a letter does not silently go out with an impersonal greeting.
- Unknown or malformed claim id, bad key, source unavailable: unchanged. DocGen opens the template blank, as agreed in the prior spec.

**Decision: the new field is named `salutation` and appended last.** Appending keeps the position of the seven existing keys, so a DocGen mapping that depends on order (it should not, but the prior spec promised order) keeps working. `salutation` is the term correspondence teams use for the opening line.

**Decision: when there is no name, `salutation` is `null`, not a fallback greeting.** This answers the intent's open question provisionally. Reasons: it follows the existing rule that any field the service does not hold is `null` and DocGen leaves it blank (prior spec R5); it does not have this service invent customer-facing wording for a case nobody has specified; and a blank line is something the handler notices, while a quiet `"Dear Customer,"` is something they may not. The cost is that a no-name claim still needs typing. If the Correspondence team or a brand owner prefers a fixed fallback such as `"Dear Sir or Madam,"`, that changes R3 to return that exact string instead of `null` and nothing else. Carried forward under Open questions.

**Decision: fixed wording `Dear <name>,` with the name as held.** The intent gives `"Dear B. Example,"` as the example and this spec adopts it literally. The service holds no title, gender or preferred name, and adding any of them would be new personal data leaving the service, which the intent's constraint forbids. Initials-plus-surname is how the record holds names today; the salutation reads the same way.

**Decision: the line is built in this service, not left to DocGen's template.** DocGen already receives `customer_name` and could in principle template `Dear {customer_name},` itself, with no change here. The intent asks for the ready-made line from the letter details, and building it here puts the no-name rule and the wording in one tested place. Whether DocGen's template can do this without a service change is still worth asking before the plan is written (Areas of concern A).

### Interfaces
| Route | Method | Auth | Request | Responses | Data classification |
|---|---|---|---|---|---|
| `/claims/{id}/letter-details` | GET | Unchanged: `X-API-Key`, checked by this service | Unchanged | `200` now carries eight keys (R5). All other responses unchanged. | As prior spec, plus `salutation`: customer PII. |
| `/claims/{id}/status`, `/health`, `/version` | GET | Unchanged | Unchanged | Unchanged | Unchanged |

Example `200` body:

```json
{
  "claim_id": "C-1001",
  "customer_name": "B. Example",
  "policy_number": "P-10001",
  "status": "received",
  "date_of_loss": "2026-08-02",
  "next_step": "Awaiting documents from customer",
  "handler_name": "H. Handler",
  "salutation": "Dear B. Example,"
}
```

- The library contract follows the HTTP contract: `get_letter_details` returns the eight fields in R5 order, raises `KeyError` for an unknown id and `LettersUnavailable` when the source cannot be reached. `get_status` is unchanged.
- Adding a key is additive for a well-behaved JSON consumer, but the prior spec told DocGen the shape was fixed at seven. DocGen must tolerate the new key before this ships (acceptance criterion 8).

### Data
- **Read:** the existing per-claim details record. No new field is stored; `salutation` is computed from `customer_name` at request time.
- **Stored:** nothing new.
- **Returned:** one new field, which repeats `customer_name` inside fixed wording. No personal data beyond what DocGen already receives leaves the service, meeting the intent's constraint.
- **Logged:** unchanged. Access lines carry method, templated path, code and duration. Neither claim ids nor `salutation` is ever logged (R7), meeting the intent's constraint.
- **Audit:** unchanged; the route changes no state (`secure-api-review` rule 3 does not apply).

### Non-functional
- Performance: one string concatenation per request; no measurable change.
- Availability and failure modes: unchanged; the `503` and `404` paths still return no fields.
- Accessibility and copy: the service supplies a line of customer-facing copy for the first time. There is no brand or UX policy skill to constrain it (Areas of concern C).

### Policy check (`secure-api-review`, no endpoint checker exists in this repo)
- Rule 1, authentication: no change. The route keeps the `X-API-Key` arrangement the prior spec recorded as a conflict with this rule (its Areas of concern B); that remains open with the security policy owner and this change neither widens nor narrows it.
- Rule 2, input validation: no request body; the id shape check is unchanged.
- Rule 3, audit: read-only, no audit event required.
- Rule 4, data classification: `salutation` is classified PII and is excluded from logs and error messages (R7).

## Acceptance criteria
1. `GET /claims/C-1001/letter-details` with a valid key returns `200` with exactly the eight keys in R5, in that order, and `salutation` equal to `"Dear B. Example,"`.
2. For every fixture claim with a name, `salutation == "Dear " + customer_name.strip() + ","`, and `customer_name` in the same body is the name in the salutation.
3. For a claim whose `customer_name` is `null`, empty or whitespace only, `salutation` is `null` and every other field is as before. (No current fixture claim has a null name; the proof uses one supplied by the test.)
4. `get_letter_details("C-9999")` raises `KeyError`; the HTTP route returns `404 {"error": "not_found"}` for it with no `salutation`.
5. The `401`, `404`, `405` and `503` responses are byte-for-byte what they were before the change.
6. Logs from a run covering all the above contain no claim id, customer name or salutation.
7. The status, health and version route tests pass unchanged; `make build`, `make test` and `make lint` are clean.
8. The Correspondence team (Priya, per the prior spec) confirms in writing on the PR or this spec that DocGen tolerates the eighth key, maps `salutation` to the update-letter template's first line, and leaves the line blank when it is `null`. A human must satisfy this criterion.

## Areas of concern
Listed in the order the product owner should work them.

- **A. DocGen may be able to do this without a service change.** DocGen already receives `customer_name`. If its template language can write `Dear {customer_name},` and blank the line when the name is missing, the wrong-name problem is solved with no change to the contract, and the question of who owns the wording goes away. This spec proceeds with the service-side line because the intent asks for it. **Resolve with:** the product owner and the Correspondence team (Priya), before the plan is written. If DocGen can do it, close this spec with that reason.
- **B. Behaviour for a claim with no name is decided provisionally.** The spec returns `null` and lets the handler type the line (Design). A fixed fallback greeting is a one-line change to R3 if preferred, but choosing its wording is a customer-facing copy decision this service should not make alone. **Resolve with:** the Correspondence team, with a brand owner if one exists.
- **C. The service now produces customer-facing copy, and no brand or UX policy governs it.** Until now the service returned data only; the prior spec put writing letter text out of scope. `Dear <name>,` is letter text, however small. There is no brand, tone or localisation policy skill to say whether `Dear`, the comma, initials-plus-surname, or a single fixed language is right. **Resolve with:** the tech lead, who owns policy skills for this repository, and the Correspondence team for the wording itself. Any later change to the wording is a contract change for DocGen.
- **D. The fix removes copying errors, not record errors.** The wrong names last month came from handlers copying from the previous claim; this change removes that path. It cannot fix a claim whose record holds the wrong name, and the details record is still a fixture with no feed from claims-core (prior spec, Areas of concern D). While the source is a fixture or a stale mirror, the salutation is only as right as the record. **Resolve with:** the tech lead and the claims-core owner, as already open under the prior spec.
- **E. The "exactly seven keys" contract is reopened.** The prior spec, CLAUDE.md, the `app/letters.py` docstring and an existing test all state seven keys. This spec changes that to eight; the plan must update all of them in the same PR. DocGen was told the shape was fixed, so acceptance criterion 8 is a hard gate before release, not a formality. **Resolve with:** the engineer writing the plan (documents and test) and Priya (DocGen tolerance).
- **F. Only one policy skill was available, and it is a placeholder.** `secure-api-review` is the plugin's example with no named owner. The PII classification of `salutation` is this spec's own. The rule 1 conflict on the letters route is inherited, not new. **Resolve with:** the tech lead. Treat "policies applied" as advisory until real policies exist.

## Open questions
Carried from intent.md. Each is marked answered or still open.

1. **What should the line say when a claim has no customer name on record?** Answered provisionally: nothing; `salutation` is `null` and DocGen leaves the line blank for the handler (R3, Design). Still open for confirmation, including whether a fixed fallback greeting is preferred and what its wording would be. Owner: the Correspondence team (Priya), with a brand owner if one exists (Areas of concern B and C).

Raised by this spec:

2. **Can DocGen's template build the line itself from `customer_name`?** Open. Owner: Priya (Areas of concern A). If yes, this spec may close.
3. **Does DocGen tolerate an eighth key in the letter details?** Open. Owner: Priya (acceptance criterion 8, Areas of concern E).

## Out of scope
- Any other letter text: sign-off, body, subject line, or deriving `next_step` from `status`.
- Titles, honorifics, gender, preferred names or any new name data; each would be new personal data leaving the service.
- Localised or multilingual salutations.
- A salutation for recipients other than the customer (solicitors, third parties); the route still has no notion of recipient.
- Correcting names held in the record, and feeding the details record from claims-core.
- Any change to authentication, key handling, the status, health or version routes, or DocGen's handling of `401`, `404` and `503`.
