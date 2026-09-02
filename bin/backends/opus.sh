#!/usr/bin/env bash
# Claude Opus via the user's own subscription (OAuth in ~/.claude).
source "$(dirname "${BASH_SOURCE[0]}")/../lib/claude_backend.sh"
backend_env() {
  unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_MODEL ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL ANTHROPIC_DEFAULT_HAIKU_MODEL CLAUDE_CODE_SUBAGENT_MODEL
  # no user settings (plugins, hooks, default model) — project settings only
  export CLAUDE_EXTRA_ARGS="--model $OPUS_MODEL --setting-sources project,local"
}
backend_check() {
  [ -f "$HOME/.claude/.credentials.json" ] || [ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "not logged in to Claude (claude auth login) and no ANTHROPIC_API_KEY"; exit 1; }
  echo "ok — $OPUS_MODEL via Claude subscription"
}
claude_dispatch "$@"

exit $?
