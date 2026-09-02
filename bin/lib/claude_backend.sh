#!/usr/bin/env bash
# Shared logic for backends running on Claude Code (glm, kimi, opus): env → claude -p.
# A backend script defines backend_env and sources this file.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"

claude_common_args() {
  local sid="$1"
  printf '%s\n' -p --output-format stream-json --verbose \
    --permission-mode bypassPermissions --effort "${ER_EFFORT:-max}" \
    --settings "$(claude_deny_settings "$ER_PROJ_ROOT")" \
    --session-id "$sid"
}

claude_run() {
  backend_env || exit 1
  local sid; sid="$(cat "$ER_DIR/session")"
  cd "$ER_SNAPSHOT" || exit 1
  mapfile -t args < <(claude_common_args "$sid")
  exec "$CLAUDE_BIN" "${args[@]}" ${CLAUDE_EXTRA_ARGS:-} < "$ER_PROMPT"
}

claude_ask() { # claude_ask "message"
  backend_env || exit 1
  local sid; sid="$(cat "$ER_DIR/session")"
  cd "$ER_SNAPSHOT" || exit 1
  exec "$CLAUDE_BIN" -p --resume "$sid" --output-format text \
    --permission-mode bypassPermissions --effort "${ER_EFFORT:-max}" \
    --settings "$(claude_deny_settings "$ER_PROJ_ROOT")" ${CLAUDE_EXTRA_ARGS:-} "$1"
}

claude_dispatch() { # claude_dispatch CMD [ARG]
  case "$1" in
    run)    claude_run ;;
    ask)    claude_ask "$2" ;;
    format) echo claude-stream-json ;;
    check)  command -v "$CLAUDE_BIN" >/dev/null || { echo "claude binary not found"; exit 1; }; backend_check ;;
    *) die "claude backend: unknown command $1" ;;
  esac
}
