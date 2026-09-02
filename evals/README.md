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

Expect the first run of a new case to find a bug in the case, not in the agent. The first run of this suite found two: a fix that restored a file byte-for-byte shows no diff, so `files_changed_match` cannot prove it (assert the content instead); and an eval that forbade changes under `intent/` was contradicted by CLAUDE.md's rule that every change starts there.

The suite's first CI run also caught a hook bug no local test had: the protected-paths hook read its payload with `jq < /dev/stdin`, which sees nothing on a Linux runner, so the hook exited 0 and allowed the edit it blocks on a Mac. Hooks now read `$(cat)`. That is the eval suite doing its job on the configuration.
