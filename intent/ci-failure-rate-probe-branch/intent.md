# Intent: The CI failure-rate alarm is firing on a deliberately red probe test, not on a real defect
Author: closing-the-loop (ops/detect.py). Status: draft.
Source: control-band breach on `ci_test_failure_rate`, detected 2026-09-02T21:52:28Z (z = 4.781, tier 3, "one window beyond 3 sigma")
Record: none

## Problem
`ci_test_failure_rate` breached its 3-sigma band: 3 failures in the 5-run window against a baseline rate of 0.0667, z = 4.781. The z history (`-0.845, -0.791, -0.745, 0.849, 2.562, 4.389, 4.589, 4.781`) shows a clean history that goes bad in one step, which is the signature of a single new cause rather than a drift.

All three failing runs are the same failure, on the same branch, from the same author:

| Run | Created | Head SHA | URL |
|---|---|---|---|
| 33684019306 | 2026-09-02T21:14:30Z | `4b83a6f` "probe: red test to exercise the closing-the-loop propose path (1/3)" | https://github.com/jsnkle/ai-native-sdlc-test/actions/runs/33684019306 |
| 33684060415 | 2026-09-02T21:14:56Z | `f6c3f94` "probe: push 2/3" | https://github.com/jsnkle/ai-native-sdlc-test/actions/runs/33684060415 |
| 33684100563 | 2026-09-02T21:15:20Z | `b770b10` "probe: push 3/3" | https://github.com/jsnkle/ai-native-sdlc-test/actions/runs/33684100563 |

Branch `test/failure-rate-probe`, event `pull_request`, workflow `ci`, all three within 50 seconds of each other. Each one fails in the `test` job at `make test` with the same assertion:

```
FAILED tests/test_claims.py::test_probe_red_on_purpose - AssertionError: closing-the-loop probe
1 failed, 60 passed in 0.92s
```

The test is red by design. `git diff origin/main...origin/test/failure-rate-probe` adds only this to `tests/test_claims.py`:

```python
def test_probe_red_on_purpose():
    # Deliberately failing: probes the closing-the-loop workflow's propose path. Close this PR after the test.
    assert False, "closing-the-loop probe"
```

plus two no-op comment lines (`# push 2`, `# push 3`) whose only purpose was to produce a second and third CI run. No `app/` file is touched on the branch, and the other 60 tests pass in every run.

So the alarm is true (CI really did go red three times) but the cause is not a product defect: it is a test harness deliberately exercising this detector's propose path. The cost is a false-positive tier-3 proposal, and — left in place — a permanently poisoned baseline, because these three failures stay in the 30-run baseline window and raise the "normal" failure rate for every later comparison.

There is a near miss here worth naming. `ops/bands.yaml` already sets `ignore_draft_prs: true`, added in `b742913` as tuning from dismissed proposal #4, precisely because "runs on draft PRs are where red tests legitimately live". That exclusion did not catch this probe, so the PR behind `test/failure-rate-probe` was not a draft. `ignore_branches` is still `[]`, so nothing else filtered it either.

## Proposed outcome
Quarantine, not a code fix. There is nothing wrong with `app/`.

1. **Remove the probe.** Close the pull request on `test/failure-rate-probe` and delete the branch, as the test's own comment instructs ("Close this PR after the test."). `test_probe_red_on_purpose` must never reach `main`; `tests/test_claims.py` on `main` is correct as it stands and needs no change.
2. **Stop the next probe from alarming.** Add a branch glob to `ignore_branches` in `ops/bands.yaml` so deliberately-red probe branches are excluded the way draft PRs already are — the same tuning shape as `b742913`. `test/*` is the obvious candidate given the branch name, but see the open questions: `test/*` is a plausible name for a genuine test-only change, and excluding it would blind the detector to real breakage in tests.

Afterwards, `ops/detect.py` on the same history should report `z` back inside the band and `action` below `propose`, with these three runs counted under `runs_ignored`. That is the observable check that the tuning worked.

## Affected users and systems
- **`tests/test_claims.py`** — holds `test_probe_red_on_purpose` at line 16 on branch `test/failure-rate-probe` only. This is the sole failing test; nothing in the file on `main` is at fault.
- **`app/claims.py`, `app/server.py`** — named only to rule them out. Untouched by the probe branch; their tests are among the 60 that pass.
- **`ops/bands.yaml`** — the file that would change, at `ignore_branches`.
- **`ops/detect.py`** — the detector that raised this. Its `is_ignored`/`ignore_branches` path is the mechanism the fix uses; no change to the script itself is proposed.
- **Branch `test/failure-rate-probe` and its pull request** — to be closed.
- **The repo's CI history** — the three failures sit in the baseline for the next 30 runs.
- **jsnkle**, who authored the probe and is the person who knows whether it has finished serving its purpose.

## Constraints
- **This fix goes through the normal PR review gate.** Branch, PR, code-owner approval under `REVIEW.md`. No direct push to `main`, and no self-merge by the detector. The detector proposes; a human decides.
- Detection stays deterministic: no model in the detection path. Any change here is to `ops/bands.yaml` configuration, not to the logic in `ops/detect.py`.
- Do not delete or edit a failing test to make CI green. The rule in `CLAUDE.md` is to fix the code, not the test. This case is the narrow exception and it is worth being explicit about why: the failing test is not asserting anything about the product, it was authored to fail, and it is being removed by closing its PR rather than edited on a branch heading for `main`.
- Do not silence the metric wholesale. Excluding too broad a branch glob turns off the alarm that is working correctly.
- Out of scope: any change to `app/`, and any change to how CI itself runs.

## Open questions
Written from evidence by a non-interactive detector run; a human decides all of these.

1. **Is the probe finished?** Its commit message says it exists to exercise the propose path, and this intent is that path producing output — which suggests yes. jsnkle should confirm before the PR is closed.
2. **What glob goes in `ignore_branches`?** `test/*` matches this branch but would also hide a real regression on a legitimately-named test branch. A dedicated prefix reserved for probes (`probe/*`, or the `wip/*` / `spike/*` already suggested in the `bands.yaml` comment) is narrower and safer, but only works if probe branches are renamed to match by convention. This is a naming-convention decision, not a technical one.
3. **Should the probe PR simply have been a draft?** `ignore_draft_prs: true` was added for exactly this case and would have suppressed the alarm at no cost in coverage. "Probes are opened as drafts" may be the whole fix, with no change to `bands.yaml` at all. Worth deciding before adding a second, overlapping exclusion.
4. **What about the poisoned baseline?** Even after the probe is gone, the three failures remain in the 30-run baseline unless excluded, inflating the baseline rate and desensitising the detector for the next 30 runs. Retroactive exclusion via `ignore_branches` fixes this as a side effect; closing the PR alone does not. Someone should confirm which of the two outcomes they actually want.
5. **Should a deliberately-red test be blocked earlier?** A hook or CI check rejecting `assert False` in `tests/` would stop probes from reaching the metric at all, but would also block the technique this probe relied on. Probably out of scope; recorded so the option is not lost.
