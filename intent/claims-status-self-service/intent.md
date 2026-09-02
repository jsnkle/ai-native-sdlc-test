# Intent: Let the customer portal show claim status so customers stop phoning for it
Author: J. Ortiz (claims operations). Status: accepted (product owner, 2026-09-02).
Source: conversation (non-interactive session, 2026-09-02)
Record: none

## Problem
Customers phone the contact centre to ask where their claim is. Handlers spend about a third of call time on status-only queries: calls that need no judgement, only a lookup. The customer portal cannot answer the question itself because this claims service has no way to expose a claim's status outside the process; it is a library module with no HTTP layer.

## Proposed outcome
A customer signed in to the portal can see their claim's current status on the portal, and does not need to call. For the portal team that means this service answers `GET /claims/{id}/status` with the status as JSON, and `404` for a claim id it does not know. The contact centre sees fewer status-only calls.

## Affected users and systems
- Claims handlers in the contact centre (fewer status-only calls).
- Customers using the portal (self-service status).
- The portal team, who build the portal side and call the new endpoint.
- This claims service, which gains its first HTTP surface over the existing in-memory lookup.

## Constraints
- Standard library only at runtime: no new dependencies.
- Existing auth only. The portal already authenticates the customer and this service sits behind it; the endpoint adds no login, token or session of its own.
- No new PII in the response. The response carries the status, and nothing about the customer.
- Out of scope: writing or changing a status, and any history of status changes. Read-only, current status only.

## Open questions
- Do third-party loss adjusters need access too? (Originator's question, unanswered.)
- Assumed: the endpoint is read-only and returns only the claim's current status; the claim id is already known to the caller, so echoing it is acceptable but nothing else is. To be confirmed at spec.
- Assumed: any id not in the status table gets `404`, including ids that are not shaped like `C-1001`. Whether a malformed id should instead be `400` is a spec decision.
- Assumed: "existing auth" means the service trusts the portal as its only caller and does not check identity itself. Where that trust boundary sits (network, gateway, header) needs confirming with the portal team.
- Success measure: the originator's evidence is "about a third of call time"; there is no agreed target or baseline for how much of that should move to the portal, or by when.
- Whether the same endpoint should also serve contact centre tooling, so handlers who still take the call use the same lookup.
