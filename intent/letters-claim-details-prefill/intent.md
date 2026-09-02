# Intent: Stop handlers re-typing claim details into the letters system
Author: not given (claims operations, on behalf of handlers). Status: draft.
Source: conversation (non-interactive session, 2026-09-02)
Record: none

## Problem
When a handler sends a customer an update, they read the claim's details off the claims system and type them again into the letters system. It is slow, and they make mistakes: a letter can go out with the wrong details on it. The cost is handler time on every update letter, plus whatever a wrong letter costs afterwards (a correction letter, a complaint, or a letter with someone else's details on it). No volume or error rate was given.

## Proposed outcome
A handler sending an update enters the claim id once and the letters system already has the claim's details; nothing is typed a second time. Fewer letters go out with wrong details. For the letters team that most likely means this claims service answers a request for a claim's details, the same way it already answers for status; the exact shape is a spec decision.

## Affected users and systems
- Claims handlers, who write the update letters.
- Customers, who receive them (accuracy of what they are told).
- The letters system and whoever owns it; it has to take the details from somewhere rather than from the handler's keyboard.
- This claims service, which today holds only a claim id and its status. The details a letter needs are not in it yet; where they live is an open question.

## Constraints
- Standard library only at runtime: no new dependencies.
- Existing auth only. The letters system is an internal caller like the portal; this service adds no login of its own.
- PII. The service currently returns nothing about the customer and never echoes a claim id in an error. An update letter may need customer details (name, address), which would be new PII for this service to carry. That is a decision for spec, not something to slip in.
- Out of scope: writing the letter text, changing how the letters system composes or sends letters, and changing anything on the claim.

## Open questions
- Which details does the letters system need? Assumed: claim id and status at least; possibly customer name, address, and claim-specific facts (dates, amounts). To be confirmed with a handler and the letters team.
- Where does the handler start: in the letters system (which then fetches the claim), or in the claims tooling (which then opens a letter)? Assumed the former.
- Where do the claim details live today? This service has only the status table. If they live in another system, the fix may not be in this service at all.
- Can the letters system call an HTTP endpoint, and who owns it? If it cannot, an export or a different integration is needed.
- Does the letters system already hold customer name and address (so this service need only supply claim facts), or must it come from here? Drives the PII decision above.
- Evidence: how many update letters a day, how long the re-typing takes, how often a letter goes out wrong. None given; needed for a baseline.
- Success measure: assumed "handlers no longer type claim details into a letter" and "fewer wrong-detail letters", with no target or date agreed.
- Deadline or budget: none stated.
