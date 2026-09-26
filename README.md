# claims-portal

A tiny claims status service used to test AI-native SDLC adoption.

> **Why this repository is public.** The AI-native SDLC kit is for private repositories whose contributors are all trusted, and this sandbox is the exception. It is public only because branch protection, which the kit's code-owner gate relies on, needs a public repository on GitHub's free plan. It has no outside contributors, and its Claude workflows stay disabled except during a test run. Do not open pull requests here unless you are the owner. Pull requests from anyone else are not reviewed, and closing the loop would read their CI logs.

## Status: automation switched off (2026-09-03)

This sandbox ran every stage of the AI-native SDLC playbook end to end, including the unattended ones. To stop it spending Console credits, every workflow that calls Claude is **disabled**; only the plain `ci` check (build, test, lint) still runs.

| Workflow | Play | Re-enable with |
|---|---|---|
| Agent evals | Test: continuous evals | `gh workflow enable "Agent evals"` |
| closing-the-loop | Maintain: closing the loop | `gh workflow enable closing-the-loop` |
| Spec on intent merge | Design | `gh workflow enable "Spec on intent merge"` |
| Claude review | Deploy: PR review | `gh workflow enable "Claude review"` |
| Claude mention | Deploy: fix loop | `gh workflow enable "Claude mention"` |
| Build | Deploy: build triage | `gh workflow enable Build` |

Each still needs `ANTHROPIC_API_KEY`; the bot-opened PRs and pushes need `LOOP_GH_TOKEN` (a fine-grained token; the current one was created 2026-09-26 with a 30-day expiry, and the one before it expired after 7 days, which is how the 2026-09-26 test run found it) to trigger CI and review on themselves. The by-hand plays (`/ai-native-sdlc:intent`, `:spec`, `:plan`, `:babysit-pr`) run under your own Claude Code login and cost nothing extra.
