# Intent: Stop the red WIP test on PR #3 from tripping the CI failure-rate alarm
Author: closing-the-loop (ops/detect.py). Status: draft.
Source: monitoring breach, `ops/log/20260902T114044Z-detect.json` (ci_test_failure_rate, tier 3, z = 4.199, one window beyond 3 sigma)
Record: none

## Problem
The CI test failure rate breached its 3-sigma control band at 11:40 UTC on 2026-09-02: 4 of the last 5 runs failed against a baseline rate of 0.14 over 12 runs. All four failures are the same deterministic error on the same branch, `wip/status-history`, which backs draft PR #3 "WIP: status history" (https://github.com/jsnkle/ai-native-sdlc-test/pull/3, author jsnkle, marked "not for review yet").

Evidence, one run per push to that branch:

| Run | Commit | Created | Result |
|---|---|---|---|
| [33625553397](https://github.com/jsnkle/ai-native-sdlc-test/actions/runs/33625553397) | f8fadbc "wip: start on status history (test first)" | 11:37:18Z | failure |
| [33625599545](https://github.com/jsnkle/ai-native-sdlc-test/actions/runs/33625599545) | 60db04b "wip: second attempt" | 11:37:49Z | failure |
| [33625751683](https://github.com/jsnkle/ai-native-sdlc-test/actions/runs/33625751683) | aa2a075 "wip: attempt 3" | 11:39:37Z | failure |
| [33625784404](https://github.com/jsnkle/ai-native-sdlc-test/actions/runs/33625784404) | 66aa4f6 "wip: attempt 4" | 11:40:00Z | failure |

Every run fails in the `make test` step with exactly this, and the other 43 tests pass:

```
FAILED tests/test_claims.py::test_status_history_is_recorded
ImportError: cannot import name 'get_status_history' from 'app.claims'
1 failed, 43 passed
```

The first commit adds `test_status_history_is_recorded` to `tests/test_claims.py`. It imports `get_status_history`, which does not exist in `app/claims.py`, and its own comment says status history is out of scope for claims-status-self-service and does not exist yet. The three later commits only append comments, so each push re-runs the same red test. Build and lint are not reached. `main` is green; the last run on `main` (50d8dfc, 11:22Z) passed, and no commit on `main` or any other branch is involved. This is a real, reproducible failure, not a flaky test or an infrastructure fault. The cost is that one draft branch pushed four times in three minutes is enough to page the ops loop at tier 3 and consume a Claude invocation, and it will do so again on every further push.

## Proposed outcome
Quarantine, not implementation. On the `wip/status-history` branch the test is marked as an expected failure until the function exists, so that pushes to PR #3 go green and the failure-rate metric returns inside its band:

```python
@pytest.mark.xfail(strict=True, raises=ImportError, reason="status history not implemented; see intent/")
def test_status_history_is_recorded():
```

`strict=True` keeps the test-first discipline: the moment `get_status_history` lands and the assertion holds, the xfail itself fails and the marker has to come off in the same change. Skipping or deleting the test is not proposed. Implementing `get_status_history` is not proposed either, because the feature has no intent, spec or plan and the test's own comment says it is out of scope.

The observable result: the next push to PR #3 runs 44 tests with 1 xfailed and 0 failed, the next detector window is inside 1 sigma, and no further tier 3 detections are logged for this cause.

## Affected users and systems
- `tests/test_claims.py::test_status_history_is_recorded` on branch `wip/status-history`, the only test that changes.
- `app/claims.py`, which the test imports from and which does not change under this intent.
- Draft PR #3 and its author, jsnkle, who own the branch and the decision.
- The ops loop (`ops/detect.py`, `ops/bands.yaml`, `ops/log/`), whose ci_test_failure_rate metric currently counts draft-PR runs the same as every other run.
- The `ci` GitHub Actions workflow, which runs on every `pull_request` event including drafts.

## Constraints
- The fix goes through the normal PR review gate (`REVIEW.md` passes, branch protection) like any other change. Nothing is pushed directly to `wip/status-history` or `main` by the ops loop; this intent is a proposal, not an action.
- No change to `main` is needed; `main` is green and its tests are untouched.
- The tested contract in CLAUDE.md stands: unknown claim ids raise `KeyError`, and no failing test is deleted. An xfail is a declared, strict expectation, not a skip.
- Standard library only at runtime; the fix touches one test file.
- Out of scope: building status history. If it is wanted, it starts as its own `intent/<slug>/intent.md`.

## Open questions
- Does the author want status history at all, or was the red test only an experiment? If the former, the branch should carry an intent before more work; if the latter, closing PR #3 resolves the breach without any code change.
- Should the ops detector exclude, or weight separately, runs whose event is a draft pull request? Draft branches are where red tests legitimately live, and the earlier tier 2 diagnosis on this same branch (`ops/log/20260902T113831Z-diagnosis.md`, only on `wip/status-history`) raised the same point. That is a change to `ops/detect.py` and needs its own decision by whoever owns the loop.
- Should the `ci` workflow run on draft PRs at all, or wait for "ready for review"? That trades earlier feedback for a cleaner metric and is a team choice, not an ops one.
