#!/usr/bin/env bash
# Kimi K3 via Claude Code on the Kimi Code subscription endpoint (api.kimi.com/coding).
source "$(dirname "${BASH_SOURCE[0]}")/../lib/claude_backend.sh"
backend_env() {
  local key; key="$(key_from KIMI_API_KEY "$HOME/.claude/kimi_api_key")" || { echo "no Kimi Code key (KIMI_API_KEY or ~/.claude/kimi_api_key; create at kimi.com/code/console)" >&2; return 1; }
  export CLAUDE_CONFIG_DIR="$ER_CFG/kimi"; mkdir -p "$CLAUDE_CONFIG_DIR"
  export ANTHROPIC_BASE_URL="$KIMI_BASE_URL"
  export ANTHROPIC_API_KEY="$key"; unset ANTHROPIC_AUTH_TOKEN
  export ANTHROPIC_MODEL="$KIMI_MODEL"
  export ANTHROPIC_DEFAULT_OPUS_MODEL="$ANTHROPIC_MODEL" ANTHROPIC_DEFAULT_SONNET_MODEL="$ANTHROPIC_MODEL"
  export ANTHROPIC_DEFAULT_HAIKU_MODEL="$ANTHROPIC_MODEL" ANTHROPIC_DEFAULT_FABLE_MODEL="$ANTHROPIC_MODEL" CLAUDE_CODE_SUBAGENT_MODEL="$ANTHROPIC_MODEL"
  local win=262144; case "$ANTHROPIC_MODEL" in *"[1m]"*) win=1048576;; esac
  export CLAUDE_CODE_AUTO_COMPACT_WINDOW="$win" CLAUDE_CODE_MAX_CONTEXT_TOKENS="$win"
  export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 API_TIMEOUT_MS=3000000
}
backend_check() { backend_env >/dev/null 2>&1 || { echo "missing Kimi Code key: KIMI_API_KEY or ~/.claude/kimi_api_key (kimi.com/code/console)"; exit 1; }; echo "ok — $KIMI_MODEL via api.kimi.com"; }
claude_dispatch "$@"
