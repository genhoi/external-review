#!/usr/bin/env bash
# Grok via the grok CLI (xAI), headless, kernel sandbox `workspace`: writes only to the snapshot and /tmp.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
GROK_BIN="${GROK_BIN:-grok}"
# the `workspace` kernel sandbox needs bubblewrap on Linux; without it grok refuses to start → off.
grok_sandbox() {
  if [ -n "${GROK_SANDBOX:-}" ]; then echo "$GROK_SANDBOX"; return; fi
  if command -v bwrap >/dev/null 2>&1; then echo workspace; else echo "grok: bubblewrap not found — sandbox off (sudo apt install -y bubblewrap enables the kernel sandbox)" >&2; echo off; fi
}
case "$1" in
  run)
    sid="$(cat "$ER_DIR/session")"
    exec "$GROK_BIN" --prompt-file "$ER_PROMPT" --cwd "$ER_SNAPSHOT" \
      --model "$GROK_MODEL" --effort "$GROK_EFFORT" \
      --sandbox "$(grok_sandbox)" --permission-mode bypassPermissions \
      --output-format streaming-messages-json -s "$sid" ;;
  ask)
    sid="$(cat "$ER_DIR/session")"
    exec "$GROK_BIN" -p "$2" --resume "$sid" --cwd "$ER_SNAPSHOT" \
      --sandbox "$(grok_sandbox)" --permission-mode bypassPermissions --output-format plain ;;
  format) echo claude-stream-json ;;   # grok --output-format streaming-messages-json = claude stream-json format
  check)
    command -v "$GROK_BIN" >/dev/null || { echo "grok binary not found"; exit 1; }
    [ -s "$HOME/.grok/auth.json" ] || { echo "grok not authenticated (run grok and log in)"; exit 1; }
    echo "ok — $GROK_MODEL, effort $GROK_EFFORT" ;;
  *) die "grok backend: unknown command $1" ;;
esac
