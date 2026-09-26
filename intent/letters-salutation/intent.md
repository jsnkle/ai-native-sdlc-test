# Intent: Update letters open with the customer's name
Author: jsnkle (kit e2e test, 2026-09-26). Status: accepted.
Source: e2e test of the kit's spec workflow; not a real request.
Record: none

## Problem
Handlers copy the customer's name into the first line of every update letter by hand. It is slow, and twice last month the wrong name went out because a handler copied it from the previous claim.

## Proposed outcome
The letter details DocGen already fetches include a ready-made opening line such as "Dear B. Example,", built from the claim's own record. An unknown claim id fails the same way the other letter fields do.

## Affected users and systems
Claims handlers, the DocGen update-letter template, `app/letters.py`.

## Constraints
No new personal data leaves the service beyond the name DocGen already receives. Claim ids are never logged.

## Open questions
What should the line say when a claim has no customer name on record?
