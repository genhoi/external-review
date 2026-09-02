#!/usr/bin/env bash
# GLM-5.3 via Claude Code on the z.ai backend (Anthropic-compatible endpoint).
source "$(dirname "${BASH_SOURCE[0]}")/../lib/claude_backend.sh"
backend_env() {
  local key; key="$(key_from ZAI_API_KEY "$HOME/.claude/zai_api_key")" || { echo "no z.ai key (ZAI_API_KEY or ~/.claude/zai_api_key)" >&2; return 1; }
  export CLAUDE_CONFIG_DIR="$ER_CFG/glm"; mkdir -p "$CLAUDE_CONFIG_DIR"
  export ANTHROPIC_BASE_URL="$ZAI_BASE_URL"
  export ANTHROPIC_AUTH_TOKEN="$key"; unset ANTHROPIC_API_KEY
  export ANTHROPIC_MODEL="$GLM_MODEL"
  export ANTHROPIC_DEFAULT_OPUS_MODEL="$ANTHROPIC_MODEL" ANTHROPIC_DEFAULT_SONNET_MODEL="$ANTHROPIC_MODEL"
  export ANTHROPIC_DEFAULT_HAIKU_MODEL="$GLM_SMALL_MODEL" CLAUDE_CODE_SUBAGENT_MODEL="$ANTHROPIC_MODEL"
  export CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 API_TIMEOUT_MS=3000000
}
backend_check() { backend_env >/dev/null 2>&1 || { echo "missing z.ai key: ZAI_API_KEY or ~/.claude/zai_api_key"; exit 1; }; echo "ok — $GLM_MODEL via z.ai"; }
claude_dispatch "$@"
