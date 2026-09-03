# Intent: Let operators see which build is running from the health endpoint
Author: J. Ortiz (claims operations). Status: accepted (product owner, 2026-09-03).
Source: conversation
Record: none

## Problem
When something looks wrong after a deploy, operators cannot tell which build of the claims service is serving traffic without logging on to the host. `GET /health` says only `{"status": "ok"}`.

## Proposed outcome
`GET /health` also reports a build identifier, so an operator or the portal team can confirm what is running from the response alone.

## Affected users and systems
Operators, the portal team, this claims service's health route.

## Constraints
Standard library only. No new PII. The identifier must not reveal secrets or internal hostnames. `/health` stays anonymous.

## Open questions
Where does the identifier come from: a `CLAIMS_BUILD` environment variable set at deploy time, or the git commit baked in at build? Prefer the environment variable if nothing bakes a version today.
