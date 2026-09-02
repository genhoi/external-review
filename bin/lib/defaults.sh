#!/usr/bin/env bash
# shellcheck disable=SC2034  # variables here are used by the scripts that source this file
# The single place for model/effort/language defaults. Precedence: environment variable →
# ~/.config/external-review/config.env (KEY=VALUE, applied only to unset keys) → values below.
# Inspect/change: `review config`, `review config set CODEX_MODEL gpt-5.7-sol`.

ER_CONFIG_FILE="${EXTERNAL_REVIEW_CONFIG:-$HOME/.config/external-review/config.env}"
if [ -f "$ER_CONFIG_FILE" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"; line="${line#"${line%%[![:space:]]*}"}"
    [[ "$line" =~ ^([A-Z_][A-Z0-9_]*)=(.*)$ ]] || continue
    k="${BASH_REMATCH[1]}"; v="${BASH_REMATCH[2]}"; v="${v%"${v##*[![:space:]]}"}"
    v="${v#\"}"; v="${v%\"}"; v="${v#\'}"; v="${v%\'}"
    [ -n "${!k:-}" ] || export "$k=$v"
  done < "$ER_CONFIG_FILE"
fi

# --- language of prompts and reviewer reports: en | ru ---
: "${REVIEW_LANG:=en}"
# --- how ignored dependencies (vendor, node_modules, .venv, .env*) get into the snapshot: copy | hardlink | symlink | none ---
: "${REVIEW_DEPS:=copy}"
# --- models ---
: "${GLM_MODEL:=glm-5.3[1m]}";      : "${GLM_SMALL_MODEL:=glm-5.3-flash}"
: "${KIMI_MODEL:=k3[1m]}";          : "${KIMI_CLI_MODEL:=kimi-code/k3}"
: "${OPUS_MODEL:=opus}"
: "${GROK_MODEL:=grok-4.6}"
: "${CODEX_MODEL:=gpt-5.6-sol}"
# --- effort (claude family: `review run --effort`, default max) ---
: "${GROK_EFFORT:=xhigh}";          : "${CODEX_EFFORT:=ultra}"
# --- endpoints ---
: "${ZAI_BASE_URL:=https://api.z.ai/api/anthropic}"
: "${KIMI_BASE_URL:=https://api.kimi.com/coding/}"
export REVIEW_LANG REVIEW_DEPS GLM_MODEL GLM_SMALL_MODEL KIMI_MODEL KIMI_CLI_MODEL OPUS_MODEL GROK_MODEL CODEX_MODEL GROK_EFFORT CODEX_EFFORT ZAI_BASE_URL KIMI_BASE_URL

ER_CONFIG_KEYS="REVIEW_LANG REVIEW_DEPS GLM_MODEL GLM_SMALL_MODEL KIMI_MODEL KIMI_CLI_MODEL OPUS_MODEL GROK_MODEL CODEX_MODEL GROK_EFFORT CODEX_EFFORT ZAI_BASE_URL KIMI_BASE_URL"
