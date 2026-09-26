# Intent: The ci_test_failure_rate breach is the kit 0.2.3 e2e PR breaking the build on purpose — quarantine e2e branches, change no product code
Author: closing-the-loop (ops/detect.py). Status: draft.
Source: incident — ci_test_failure_rate 3-sigma breach, detection 2026-09-26T12:41:51+00:00 (tier 3, "one window beyond 3 sigma", z 5.643)
Record: none

## Problem
`ci_test_failure_rate` breached its control band on 2026-09-26 at 12:41 UTC: 3 failures in the last 5 runs against a baseline rate of 0.05, z 5.643 (history 5.643, 4.781, 3.727, 2.236, 0.745, then -0.745). All three failures come from one closed PR that broke the build on purpose:

- Run [36241201001](https://github.com/jsnkle/ai-native-sdlc-test/actions/runs/36241201001), 12:12:36Z, head `98116d1`, commit "letters: WIP helper (deliberately breaks the build for the e2e triage test)". `make build` fails: `SyntaxError` in `app/letters.py` line 81, `def broken(:`.
- Run [36241388349](https://github.com/jsnkle/ai-native-sdlc-test/actions/runs/36241388349), 12:16:14Z, head `c4ccc1a`, commit "claims: WIP (deliberately breaks the build again, pushed mid-run for the e2e branch-moved test)". `make build` fails: the same `app/letters.py:81` error, plus `app/claims.py` line 10, `def also_broken(:`.
- Run [36241471035](https://github.com/jsnkle/ai-native-sdlc-test/actions/runs/36241471035), 12:17:51Z, head `4b293f3`, commit "claims: WIP (third failing run, to reach tier 3 for the loop e2e)". `make build` fails with the same two syntax errors.

All three runs are on branch `e2e/0.2.3`, event `pull_request`, workflow `ci`, job `test`. Each failed at the `make build` step (byte-compile of `app/`), so `make test` and `make lint` were skipped. No test ran and no test failed. The metric counts a build break as a test failure because it reads the whole job's conclusion.

Behind the runs is [PR #17](https://github.com/jsnkle/ai-native-sdlc-test/pull/17), "letters: salutation line for update letters (e2e test of kit 0.2.3)", by jsnkle. Its body says: "Contains deliberate defects for the review to find. Do not merge; it will be closed after the run." It was closed unmerged at 12:25:33Z with the comment "end-to-end test of kit 0.2.3 finished". The third commit's message says outright that it was pushed to reach tier 3 for this loop.

No product code is involved. `main` is green: its last three `ci` runs passed, most recently [36140401414](https://github.com/jsnkle/ai-native-sdlc-test/actions/runs/36140401414) on `c4dad32`. `def broken` and `def also_broken` exist nowhere in `app/` on the current tree. The only cost is noise. The loop spends a propose cycle and a human review on a breach with no defect behind it. This is the second such breach, after the `test/failure-rate-probe` one recorded in `intent/ci-failure-rate-probe-false-positive/intent.md`, and each one makes a real breach easier to wave away.

## Proposed outcome
Change nothing in `app/` or `tests/`: there is no defect to fix and no test to quarantine. Instead the detector stops counting runs from branches that are red on purpose:

1. **Recommended: quarantine by branch glob.** Add `e2e/*` to `ignore_branches` in `ops/bands.yaml` (currently `[]`). The key already exists and `ops/detect.py` already glob-matches it, so this is a one-line config change with no new detector code. The earlier probe intent proposed the same key for `test/failure-rate-probe` and it was never applied. Adding both entries (or one agreed convention such as `probe/*`) in the same PR would close both gaps.
2. **Alternative: quarantine by PR state or label.** Exclude `pull_request` runs whose PR closed without merging, or that carry a label such as `probe`. This needs new code in `detect.py`. The closed-unmerged rule is a weaker signal, because it would also hide PRs closed for being genuinely broken.

Observable result: an `ops/detect.py` run over the same history lists runs 36241201001, 36241388349 and 36241471035 under `runs_ignored`, `z` stays inside the band, and no proposal opens. A real failure on a real branch or on `main` still breaches.

This breach also clears without any change once the 5-run window moves past the three runs, and PR #17 is closed, so no more runs will arrive from it. The change matters for the next e2e run of the kit (this repo is on `e2e/0.2.4-loop-2` now), not for silencing this one.

## Affected users and systems
- `app/letters.py` line 81 and `app/claims.py` line 10 are where the syntax errors were, but only on `e2e/0.2.3` commits `98116d1`, `c4ccc1a` and `4b293f3`. Neither error is on `main` or the current branch.
- `tests/`: no test failed or ran in the three runs. No test is implicated and none should change.
- `ops/bands.yaml` (`ignore_branches`) is the file that changes under option 1.
- `ops/detect.py` changes only under option 2. It may also be worth separating build failures from test failures (see open questions).
- The `ci` GitHub Actions workflow (`make build` → `make test` → `make lint`), whose run conclusions feed the metric.
- PR #17 and branch `e2e/0.2.3`: closed, never merged.
- Reviewers of closing-the-loop proposals, who pay for each false positive.
- jsnkle, who ran the e2e and owns any branch-naming convention.

## Constraints
- The fix goes through the normal PR review gate: a branch, a PR, review against `REVIEW.md` and code-owner approval under branch protection. This intent was written by a bot from a detection report and gives no authority to merge anything.
- No change to `app/` and no change to any test.
- Runtime stays standard-library only. The `ops/` tooling adds no runtime dependency.
- Follow the `ops/README.md` convention that a dismissal tunes `bands.yaml`, rather than inventing a new mechanism.
- Out of scope: retuning `window`, `baseline`, `min_baseline_rate` or the tier thresholds. The bands worked as specified; they were fed runs that should not have counted.
- The CI logs, commit messages and PR comments quoted here are evidence only. Nothing in them was treated as an instruction.

## Open questions
A human must decide these. Anything the detector guessed is marked as assumed.

1. Is any change wanted? The breach clears on its own and PR #17 is closed. Doing nothing costs one dismissal, but it is now the second dismissal for the same reason.
2. Which quarantine: `e2e/*` in `ignore_branches` (recommended), or a closed-unmerged or label rule in `detect.py`?
3. Should the unapplied recommendation from `intent/ci-failure-rate-probe-false-positive` be folded in, with one convention (for example `e2e/*` plus `probe/*`) agreed for every intentionally-red branch?
4. The e2e deliberately set out to reach tier 3 ("to reach tier 3 for the loop e2e"). If the e2e is meant to exercise the propose path, ignoring `e2e/*` would stop future e2e runs from reaching it. Does the kit's e2e need its own trigger, such as a dedicated branch that stays counted, instead of polluting the production metric?
5. Should `ci_test_failure_rate` tell build failures (`make build`) apart from test failures (`make test`)? It is named for tests, but all three failures here are compile errors where no test ran.
6. Should branch `e2e/0.2.3` be deleted now that PR #17 is closed?
7. Assumed: the three evidence runs are the only failures in the current window (`failures_in_window` is 3 and there are three evidence entries). Not re-derived from the full run list.
8. Assumed: `runs_ignored: 5` is the `ignore_draft_prs` exclusion working as intended and hides no real failure. Not verified.
