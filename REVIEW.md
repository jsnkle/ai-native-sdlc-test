# Review instructions

Applied to every PR by the Claude review pass. Findings inform the code owner; they do not approve or block on their own. Branch protection still requires a human approval.

## Passes

Run three passes and tag each finding with its pass:

- **Bugs:** logic errors, broken edge cases, subtle regressions. In this codebase that mostly means the claim-id contract: an unknown id must still raise `KeyError`, and status strings must stay lowercase snake_case.
- **Security:** injection risks, authentication gaps, PII in logs. Claim ids and statuses are customer data; flag anything that logs or exposes them beyond the lookup.
- **Compliance:** the change matches `intent/<slug>/spec.md`, `intent/<slug>/plan.md` and our design principles. If the diff departs from `plan.md` and `plan.md` was not updated in the same PR, that is an Important finding. A behaviour change without a test in `tests/` in the same PR is also Important.

## What Important means here

Reserve Important for findings that would break behavior, leak data or breach a policy. Style and naming are nits.

## Cap the nits

Report at most five nits per review; summarize the rest as a count.

## Do not report

- Anything `make lint` (pyflakes) already catches: unused imports, undefined names, unused variables. Tell the author to run it instead.
- Byte-compile failures; `make build` catches those.
- There are no generated paths yet. Add them here when `.claude/protected-paths` gains entries.
- What CI already enforces: `make build`, `make test` and `make lint` run on every PR (`.github/workflows/ci.yml`), the build is byte-compiled, and the detector tests cover `ops/`. Do not report what those would catch.

## Feedback into CLAUDE.md

When a finding flags a mistake for the second time, the correction goes into `CLAUDE.md` as part of the same PR. Also flag when a change has made `CLAUDE.md` outdated.

## Tuning

Once a month the tech lead rates findings, adjusts the nit cap, and prunes anything CI has since taken over.
