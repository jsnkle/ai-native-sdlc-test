#!/bin/bash
# Production deploys require a named release authorization.
# PreToolUse hook on Bash. Exit 2 blocks the action; the message on stderr goes to Claude.
#
# claims-portal has no deploy command yet. The pattern below (a command mentioning both
# "deploy" and "production") is the playbook default; narrow it to the real deploy command
# when one exists.
# Read the payload with $(cat), never '< /dev/stdin': on Linux that can see no input and the hook fails open.
input=$(cat)
# Fail closed without blocking every command: when jq is missing or the command cannot be read, check the whole
# payload. It holds the command's text, so this blocks everything the exact check would, and may over-match.
if command -v jq >/dev/null 2>&1 && cmd=$(printf '%s' "$input" | jq -er '.tool_input.command' 2>/dev/null); then
  exact=1
else
  cmd=$input; exact=0
fi
if [[ "$cmd" == *"deploy"* && "$cmd" == *"production"* ]]; then
  if [ -z "$RELEASE_APPROVAL" ]; then
    msg="Production deploys need a release authorization. Ask the release manager to set RELEASE_APPROVAL=<change-ticket-id> for this session, then retry."
    [ "$exact" = 1 ] || msg="$msg (jq is missing or the command could not be read, so this hook checked the whole request, which can over-match. Installing jq gives the exact check.)"
    echo "$msg" >&2
    exit 2
  fi
  echo "Production deploy authorized by RELEASE_APPROVAL=$RELEASE_APPROVAL" >&2
fi
exit 0
