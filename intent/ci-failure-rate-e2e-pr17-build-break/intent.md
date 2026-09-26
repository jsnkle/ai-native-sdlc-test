# Intent: The ci_test_failure_rate breach is PR #17's deliberate build breaks, not a regression — close the e2e PR and quarantine e2e branches
Author: closing-the-loop (ops/detect.py). Status: draft.
Source: incident — ci_test_failure_rate 3-sigma breach, detection 2026-09-26T12:18:37Z (`ops/log/20260926T121835Z-detect.json`)
Record: none

## Problem
`ci_test_failure_rate` breached its control band on 2026-09-26 at 12:18 UTC: z 3.727 on the current window (3 failures in the last 5 runs against a baseline rate of 0.1), tier 3, rule "one window beyond 3 sigma". All three failures come from one branch and one PR:

- Run [36241201001](https://github.com/jsnkle/ai-native-sdlc-test/actions/runs/36241201001), 12:12 UTC, head `98116d1`.
- Run [36241388349](https://github.com/jsnkle/ai-native-sdlc-test/actions/runs/36241388349), 12:16 UTC, head `c4ccc1a`.
- Run [36241471035](https://github.com/jsnkle/ai-native-sdlc-test/actions/runs/36241471035), 12:17 UTC, head `4b293f3`.

Each is branch `e2e/0.2.3`, event `pull_request`, workflow `ci`, job `test`, conclusion `failure`. No test ran: every run failed at the `make build` step (`compileall` on `app/`), so `make test` and `make lint` were skipped. The errors are plain syntax errors:

- `app/letters.py`, line 81: `def broken(:` — `SyntaxError: invalid syntax` (all three runs).
- `app/claims.py`, line 10: `def also_broken(:` — `SyntaxError: invalid syntax` (runs 36241388349 and 36241471035).

The commits that introduced them are on `e2e/0.2.3` by jsnkle, and their own messages describe them as deliberate: `98116d1` "letters: WIP helper (deliberately breaks the build for the e2e triage test)", `c4ccc1a` "claims: WIP (deliberately breaks the build again …)", `4b293f3` "claims: WIP (third failing run, to reach tier 3 for the loop e2e)". The PR behind them is [PR #17](https://github.com/jsnkle/ai-native-sdlc-test/pull/17), "letters: salutation line for update letters (e2e test of kit 0.2.3)", open and not a draft; its description says it contains deliberate defects, must not be merged, and will be closed after the run. Being non-draft is why `ignore_draft_prs` did not exclude it.

`main` is not affected: neither `broken(` nor `also_broken(` exists in `app/` on `main`, and the last three `ci` runs on `main` (latest `c4dad32`, 2026-09-25) succeeded. The cost is noise, not an outage: a propose cycle and a human review spent on a signal with no real defect behind it.

## Proposed outcome
No change to `app/` or `tests/` on `main`; there is nothing to fix there. Recommended, in order:

1. **Close PR #17 without merging** once its e2e run is finished, as its description already promises. That stops new failing runs and lets the window roll clear.
2. **Quarantine e2e branches in the detector** by adding `"e2e/*"` to `ignore_branches` in `ops/bands.yaml` (currently `[]`). This is a one-line config change using the existing glob exclusion, following the `ops/README.md` convention that a dismissal tunes `bands.yaml`. It would also have covered the earlier probe breach (`intent/ci-failure-rate-probe-false-positive`) had that branch followed the same prefix.

If PR #17 were ever meant to merge, the fix would instead be to delete the two `def broken(:` / `def also_broken(:` stubs on `e2e/0.2.3`, but the PR says it is not.

Observable result: the next `ops/detect.py` run over the same history lists these three runs under `runs_ignored`, `z` drops back inside the band, and no proposal is opened. A genuine build or test failure on any non-`e2e/` branch still breaches.

## Affected users and systems
- `app/letters.py` and `app/claims.py` on branch `e2e/0.2.3` only — where the syntax errors live. Their `main` versions are clean.
- `make build` (the `compileall` byte-compile), the step that failed; `make test` and `make lint` never ran, so no test in `tests/` is implicated.
- The `ci` GitHub Actions workflow (`.github/workflows/ci.yml`), whose run history is the metric's source.
- `ops/bands.yaml` (`ignore_branches`) — the file that changes under recommendation 2; `ops/detect.py` reads it and does not change.
- PR #17 and its author jsnkle, who owns closing it and any branch-naming convention.
- Whoever reviews closing-the-loop proposals, who pays for each false positive.

## Constraints
- Any change goes through the normal PR review gate: a branch, a PR, code-owner approval under branch protection, reviewed against `REVIEW.md`. This intent was written by a bot from a detection report and carries no authority to merge, close PRs or edit branches.
- No change to `app/` or to any test on `main`. The broken code is not on `main`.
- Standard library only at runtime; `ops/` adds no runtime dependency.
- Out of scope: retuning `window`, `baseline`, `min_baseline_rate` or tier thresholds. The bands behaved as specified; they were fed runs that should not count.

## Open questions
This was a non-interactive run, so these are recorded rather than asked. A human must decide them.

1. Is any change wanted beyond closing PR #17? The breach will self-clear as the window rolls past these runs; doing nothing costs one dismissal.
2. Is `e2e/*` the right glob, and is the team willing to adopt the `e2e/` prefix for every intentionally-red branch? Note that the branch this intent is written from, `e2e/0.2.4-loop`, would also be excluded.
3. This is the third narrowing of what the detector counts (after `ignore_draft_prs` and the probe-branch proposal). Is excluding by branch prefix acceptable, or should intentionally-red PRs be marked explicitly (a label the detector reads) so a real failure on an e2e branch is not silently hidden?
4. The commit messages show these failures were engineered to exercise this loop ("to reach tier 3 for the loop e2e"). Should an intended e2e breach be recorded somewhere so its proposal can be dismissed as expected, rather than excluded so the loop never fires on it?
5. Side observation, not part of this breach: `ci.yml` pins Python 3.12, while `CLAUDE.md` says the project targets Python 3.14. Should CI move to 3.14, or the convention be corrected?
6. Assumed: the three evidence runs are the only failures in the window (`failures_in_window` is 3 and all three evidence entries are PR #17). Not re-derived from the full run list.
7. Assumed: the 5 `runs_ignored` are draft-PR runs excluded as intended and hide no real failure. Unverified.
