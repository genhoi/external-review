#!/usr/bin/env bash
# Kimi K3 через родной kimi-code CLI (OAuth). Запасной путь: OAuth протухает раз в несколько дней.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
KIMI_BIN="${KIMI_BIN:-$HOME/.kimi-code/bin/kimi}"; command -v kimi >/dev/null && KIMI_BIN="${KIMI_BIN:-kimi}"
case "$1" in
  run)
    cd "$ER_SNAPSHOT"
    exec "$KIMI_BIN" -p "$(cat "$ER_PROMPT")" --output-format stream-json -m "$KIMI_CLI_MODEL" ;;
  ask)
    sid="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("session_id") or "")' "$ER_DIR/meta.json")"
    [ -n "$sid" ] || die "kimi-cli: session id не найден в meta.json"
    cd "$ER_SNAPSHOT"
    exec "$KIMI_BIN" -S "$sid" -p "$2" --output-format text ;;
  format) echo kimi-stream-json ;;
  check)
    [ -x "$KIMI_BIN" ] || { echo "нет бинаря kimi (~/.kimi-code/bin/kimi)"; exit 1; }
    [ -n "$(ls -A "$HOME/.kimi-code/credentials" 2>/dev/null)" ] || { echo "нет OAuth-кредов kimi (kimi login)"; exit 1; }
    echo "ok — $KIMI_CLI_MODEL (OAuth)" ;;
  *) die "kimi-cli backend: неизвестная команда $1" ;;
esac
