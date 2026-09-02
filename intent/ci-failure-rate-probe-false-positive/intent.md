# Intent: The ci_test_failure_rate breach is a deliberate probe, not a broken test — stop counting probe PRs
Author: closing-the-loop (ops/detect.py). Status: draft.
Source: incident — ci_test_failure_rate 3-sigma breach, detection 20260902T220201Z (`ops/log/20260902T220201Z-detect.json`)
Record: none

## Problem
`ci_test_failure_rate` breached its control band on 2026-09-02 at 22:02 UTC: z 1.859 on the current window, on the tier-3 rule "two of three windows beyond 2 sigma" (recent history reached z 4.781). Both failures in the window are the same failure, and neither is a real defect:

- Run [33684100563](https://github.com/jsnkle/ai-native-sdlc-test/actions/runs/33684100563), branch `test/failure-rate-probe`, event `pull_request`, conclusion `failure`.
- Run [33684060415](https://github.com/jsnkle/ai-native-sdlc-test/actions/runs/33684060415), same branch and event, conclusion `failure`.

Both failed in the `make test` step, on one test: `tests/test_claims.py::test_probe_red_on_purpose` — `AssertionError: closing-the-loop probe`, 1 failed / 60 passed. The test's own comment says it is deliberate: "Deliberately failing: probes the closing-the-loop workflow's propose path. Close this PR after the test."

Behind those runs is [PR #7](https://github.com/jsnkle/ai-native-sdlc-test/pull/7), "probe: closing-the-loop propose path (red on purpose)", by jsnkle, three commits (`4b83a6f`, `f6c3f94`, `b770b10`, "probe: push 1/3 … 3/3"). Its body reads: "Not for merge. Three pushes of a failing test on a ready PR, so ci_test_failure_rate breaches 3 sigma with draft runs excluded." The PR was opened non-draft on purpose, which is exactly what defeats the `ignore_draft_prs` tuning added in [PR #6](https://github.com/jsnkle/ai-native-sdlc-test/pull/6). PR #7 is now closed and the branch was never merged.

No product code is implicated. `main` is green: `tests/test_claims.py` on `main` contains only `test_known_claim` and `test_unknown_claim`, and `test_probe_red_on_purpose` never existed anywhere but the probe branch. The cost of the breach is therefore not an outage but noise: the loop spends a propose cycle and a human review on a signal that had no defect behind it, and every such cycle makes the next real breach easier to wave away.

## Proposed outcome
Nothing in `app/` or `tests/` changes — there is nothing to fix and nothing to quarantine. Instead the detector stops counting runs from PRs that are red on purpose, in the same way a dismissal tuned `ignore_draft_prs`. Two options, in order of preference:

1. **Quarantine by branch convention.** Agree a prefix for intentionally-red branches and add it to `ignore_branches` in `ops/bands.yaml` — `probe/*` if the convention changes, or `test/failure-rate-probe` pinned exactly if the intent is only to retire this one branch. `ignore_branches` already exists and is glob-matched in `ops/detect.py:79`, so this is a one-line config change with no new detector code.
2. **Quarantine by PR state.** Exclude `pull_request` runs whose PR was closed without merging. This needs new code in `detect.py` and is strictly weaker as a signal: a PR closed for being genuinely broken would also stop counting, which is a failure the loop should see.

Observable result: the next `ops/detect.py` run over the same history reports these two runs under `runs_ignored`, `z` falls back inside the band, and no proposal is opened for them. A genuinely failing test on a genuine branch still breaches.

Note that this breach also self-clears without any change: `z` has already decayed from 4.781 to 1.859 as the window rolls past the probe, and PR #7 is closed so no further probe runs will arrive. The change is worth making for the *next* probe, not to silence this one.

## Affected users and systems
- `tests/test_claims.py::test_probe_red_on_purpose` — the failing test. It exists only on `test/failure-rate-probe`, not on `main`.
- `app/claims.py`, `app/server.py` — named for completeness: both are uninvolved, the 60 other tests passed.
- `ops/bands.yaml` — the file that changes under option 1 (`ignore_branches`, currently `[]`).
- `ops/detect.py` — reads the config; changes only under option 2.
- The `ci` GitHub Actions workflow, whose run history is the metric's source.
- Whoever reviews closing-the-loop proposals, who pays the cost of each false positive.
- jsnkle, as the originator of the probe and the owner of any branch-naming convention.

## Constraints
- The fix goes through the normal PR review gate: a branch, a PR, and code-owner approval under branch protection, reviewed against `REVIEW.md`. This intent is written by a bot from a detection report and carries no authority to merge anything.
- No change to `app/` and no change to any test. The failing test is not ours to edit and is not on `main`.
- Standard library only at runtime; `ops/` tooling adds no runtime dependency.
- `ops/README.md` records that a dismissal should tune `bands.yaml`; this follows that convention rather than inventing a new mechanism.
- Out of scope: retuning `window`, `baseline`, `min_baseline_rate` or the tier thresholds. The bands behaved as specified — they were fed runs that should not have counted.

## Open questions
A human must decide these; the detector guessed nothing it did not mark.

1. Is any change wanted at all? The breach self-clears and the probe is closed. Doing nothing is defensible and costs one dismissal.
2. Which quarantine: the branch glob (option 1) or the closed-PR rule (option 2)? The detector recommends option 1 but cannot agree a naming convention on the team's behalf.
3. If option 1, what is the glob? `test/*` would be the literal match for this branch but is dangerously broad — it would silence any branch a developer happens to name `test/…`. `probe/*` is narrower but needs the convention to be adopted and the existing branch renamed.
4. How many exclusions is too many? This would be the second tuning that narrows what the detector counts (after `ignore_draft_prs` in PR #6), and this probe was built specifically to defeat the first. Each exclusion trades a false positive for a blind spot, and someone should say where that stops.
5. Should intentionally-red PRs be a first-class concept instead — a label the detector reads, or a required `[probe]` title prefix — rather than a branch-name convention that is easy to forget?
6. Should the probe branch `test/failure-rate-probe` be deleted now that PR #7 is closed, so it cannot produce further runs?
7. Assumed: the two evidence runs are the only failures in the current window, since `failures_in_window` is 2 and both evidence entries are the probe. Not independently re-derived from the full run list.
8. Assumed: `runs_ignored: 4` is the existing draft-PR and branch-glob exclusion working as intended, and none of those four hide a real failure. Unverified.
