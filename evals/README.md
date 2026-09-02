# evals/ — regression tests for the agent configuration

CLAUDE.md, REVIEW.md, the hooks and the plugin's skills steer the agent, so they get regression tests like code. Each `*.json` here is one eval: a prompt, optional `setup` commands that stage the situation, and the checks that define acceptable. `evals/run.sh` runs the suite; `.github/workflows/agent-evals.yml` runs it on any PR that touches the configuration, and nightly.

The first five cases come from real events in this repo:

| Eval | Origin | What it protects |
|---|---|---|
| `verify-before-done` | CLAUDE.md's Verifying your work rule | the agent runs and pastes build/test/lint output before reporting done |
| `fix-task-locks-tests` | the test-first bug-fix rule and the plugin's protect-tests hook | during a fix task the failing test is proof, not something to edit |
| `protected-paths-hold` | the protected-paths hook, after the adopt run left `.github/workflows/**` unguarded until the decisions PR | the agent cannot edit workflows without a change ticket |
| `no-secrets-in-diff` | the plugin's no-secrets hook | a literal API key never lands in the code |
| `new-route-follows-policy` | PR #8, where the secure-api-review skill shaped the spec | a new route ships with tests and the no-store header rule |

Fields: `prompt`; `allowedTools`; `setup` (shell, run before the agent); `checks.commands` (each must exit 0 afterwards); `checks.files_changed_match` (at least one changed file per prefix); `checks.files_unchanged` (no changed file under these); `checks.output_contains` / `output_not_contains` (substrings of the agent's final text).

Every incident gets an eval, written by the team that owned it. When a case stops discriminating, retire it.

When a new case goes red for the first time, verify the check before blaming the agent. The checks were written before anyone saw the agent do the task, so read the transcript and the diff and confirm what a correct outcome actually looks like; only then decide whether the agent or the case is wrong. Two cases in this suite were wrong on their first run and were corrected: one demanded a diff from a fix that restored the file byte for byte, so there was nothing to diff (assert the content instead); the other forbade changes under `intent/`, contradicting CLAUDE.md's rule that every change starts there. The opposite mistake is just as costly: a genuine agent failure dismissed as an eval bug, or CLAUDE.md "fixed" to make a wrong check pass.

The suite's first CI run also caught a hook bug no local test had: the protected-paths hook read its payload with `jq < /dev/stdin`, which sees nothing on a Linux runner, so the hook exited 0 and allowed the edit it blocks on a Mac. Hooks now read `$(cat)`. That is the eval suite doing its job on the configuration.
