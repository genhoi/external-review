#!/usr/bin/env bash
# Claude Opus через собственную подписку пользователя (OAuth в ~/.claude).
source "$(dirname "${BASH_SOURCE[0]}")/../lib/claude_backend.sh"
backend_env() {
  unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_MODEL ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL ANTHROPIC_DEFAULT_HAIKU_MODEL CLAUDE_CODE_SUBAGENT_MODEL
  # без пользовательских настроек (плагины, хуки, модель по умолчанию) — только проектные
  export CLAUDE_EXTRA_ARGS="--model $OPUS_MODEL --setting-sources project,local"
}
backend_check() {
  [ -f "$HOME/.claude/.credentials.json" ] || [ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "нет логина Claude (claude auth login) и нет ANTHROPIC_API_KEY"; exit 1; }
  echo "ok — $OPUS_MODEL через подписку Claude"
}
claude_dispatch "$@"
