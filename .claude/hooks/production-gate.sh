#!/bin/bash
# Production deploys require a named release authorization.
# PreToolUse hook on Bash. Exit 2 blocks the action; the message on stderr goes to Claude.
#
# claims-portal has no deploy command yet. The pattern below (a command mentioning both
# "deploy" and "production") is the playbook default; narrow it to the real deploy command
# when one exists.
cmd=$(jq -r '.tool_input.command // empty' < /dev/stdin)
if [[ "$cmd" == *"deploy"* && "$cmd" == *"production"* ]]; then
  if [ -z "$RELEASE_APPROVAL" ]; then
    echo "Production deploys need a release authorization. Ask the release manager to set RELEASE_APPROVAL=<change-ticket-id> for this session, then retry." >&2
    exit 2
  fi
  echo "Production deploy authorized by RELEASE_APPROVAL=$RELEASE_APPROVAL" >&2
fi
exit 0
