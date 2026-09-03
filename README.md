# claims-portal

A tiny claims status service used to test AI-native SDLC adoption.

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

Each still needs `ANTHROPIC_API_KEY`; the bot-opened PRs and pushes need `LOOP_GH_TOKEN` (a fine-grained token, expires 7 days after creation) to trigger CI and review on themselves. The by-hand plays (`/ai-native-sdlc:intent`, `:spec`, `:plan`, `:babysit-pr`) run under your own Claude Code login and cost nothing extra.
