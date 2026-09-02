#!/usr/bin/env bash
# Grok через grok CLI (xAI), headless, kernel-sandbox `workspace`: запись только в снапшот и /tmp.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
GROK_BIN="${GROK_BIN:-grok}"
# kernel-sandbox `workspace` на Linux требует bubblewrap; без него grok отказывается стартовать → off.
grok_sandbox() {
  if [ -n "${GROK_SANDBOX:-}" ]; then echo "$GROK_SANDBOX"; return; fi
  if command -v bwrap >/dev/null 2>&1; then echo workspace; else echo "grok: bubblewrap не найден — sandbox off (sudo apt install -y bubblewrap включит kernel-sandbox)" >&2; echo off; fi
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
  format) echo claude-stream-json ;;   # grok --output-format streaming-messages-json = формат claude stream-json
  check)
    command -v "$GROK_BIN" >/dev/null || { echo "нет бинаря grok"; exit 1; }
    [ -s "$HOME/.grok/auth.json" ] || { echo "нет авторизации grok (запусти grok и войди)"; exit 1; }
    echo "ok — $GROK_MODEL, effort $GROK_EFFORT" ;;
  *) die "grok backend: неизвестная команда $1" ;;
esac
