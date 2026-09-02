# Intent: Stop handlers re-typing claim details into the letters system
Author: J. Ortiz (claims operations). Status: draft.
Source: conversation (non-interactive session, 2026-09-02)
Record: none

## Problem
When a handler sends a customer an update they open a template in DocGen, the letters system, and type the claim's details into it from the claims screen on their other monitor. DocGen holds nothing about the customer, so every letter is filled in fresh. It is slow, and they make mistakes: QA sends letters back for a wrong detail, and the ones QA misses reach the customer.

Evidence from the originator:
- About 400 update letters a day across the team.
- Three to four minutes of re-keying per letter, so roughly 20 to 27 handler-hours a day.
- About one letter in twenty-five is sent back by QA for a wrong detail.

## Proposed outcome
A handler opens a template in DocGen for a claim and the claim's details are already filled in; nothing is typed a second time. The details a letter needs are the claim number, customer name, policy number, current status, date of loss, the next step, and the handler's name. Never amounts.

For the Correspondence team that means DocGen, when a template is opened, calls an HTTP endpoint with a fixed API key and gets those details back. Whether that endpoint is this claims service or claims-core directly is a spec decision (see open questions).

## Affected users and systems
- Claims handlers, who write the update letters.
- Customers and solicitors, who receive them.
- QA, who currently catch the wrong-detail letters.
- DocGen, the vendor letters system, owned by Priya on the Correspondence team. It can call an HTTP endpoint with a fixed API key when a template is opened.
- claims-core, the system of record, where all of these details live today.
- This claims service, which only mirrors the status from claims-core. It holds none of the other fields.

## Constraints
- Standard library only at runtime: no new dependencies.
- Recipient rule: some letters go to solicitors, not customers, and those must not include the customer's address. Whatever serves the details must make it impossible for a solicitor letter to carry the address.
- Never amounts. No monetary value is returned for a letter, whatever the template.
- Authentication: DocGen presents a fixed API key. This service currently does no authentication of its own and trusts the portal or gateway as its only caller. Accepting an API key, or terminating it at the gateway, is a spec decision; it is not "existing auth".
- PII: customer name, policy number and address are new PII for this service to carry and return. Its current rule of never echoing a claim id in an error message stands and extends to these fields.
- Deadline: wanted before the November 2026 renewals rush. No hard date.
- Out of scope: writing or choosing letter text, changing how DocGen composes or sends letters, and changing anything on the claim.

## Success
- Re-keying per letter under a minute, from three to four minutes today.
- Detail errors close to zero, from about one in twenty-five sent back by QA today.

## Open questions
- Which system serves DocGen: this service (which would need to mirror six more fields from claims-core) or claims-core itself? The originator believes this service only mirrors status. If claims-core can serve DocGen directly, the change is not in this repository.
- Address is not in the originator's list of seven fields, but the solicitor rule implies customer letters do carry it. Is the address needed for the letter itself, or only for the envelope, and does it come from this endpoint at all?
- Who decides the recipient type: DocGen's template, or the caller telling the endpoint "this is a solicitor letter"? Drives whether the endpoint returns the address at all.
- "Next step" and "handler's name": are these fields on the claim in claims-core, or does the handler still type them?
- How is a fixed API key issued, rotated and stored on the DocGen side, and where should it be checked?
- What happens when the claim is not found, or claims-core is unavailable at the moment a template is opened: blank fields the handler fills in, or an error that stops the letter?
