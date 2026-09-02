#!/usr/bin/env bash
# OpenAI Codex CLI (подписка ChatGPT), headless `codex exec`, sandbox workspace-write.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
CODEX_BIN="${CODEX_BIN:-codex}"
sandbox_args() {
  if [ -n "${CODEX_NO_SANDBOX:-}" ]; then printf '%s\n' --dangerously-bypass-approvals-and-sandbox
  else printf '%s\n' -s workspace-write -c 'approval_policy="never"' -c 'sandbox_workspace_write.network_access=true'; fi
}
case "$1" in
  run)
    mapfile -t sb < <(sandbox_args)
    exec "$CODEX_BIN" exec -C "$ER_SNAPSHOT" "${sb[@]}" \
      -c "model_reasoning_effort=\"$CODEX_EFFORT\"" -m "$CODEX_MODEL" \
      --skip-git-repo-check --json -o "$ER_DIR/last_message.md" - < "$ER_PROMPT" ;;
  ask)
    tid="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("session_id") or "")' "$ER_DIR/meta.json")"
    [ -n "$tid" ] || die "codex: thread id не найден в meta.json"
    mapfile -t sb < <(sandbox_args)
    exec "$CODEX_BIN" exec resume "$tid" -C "$ER_SNAPSHOT" "${sb[@]}" --skip-git-repo-check "$2" ;;
  format) echo codex-jsonl ;;
  check)
    command -v "$CODEX_BIN" >/dev/null || { echo "нет бинаря codex (см. references/setup.md)"; exit 1; }
    "$CODEX_BIN" login status >/dev/null 2>&1 || { echo "codex не залогинен: codex login --device-auth"; exit 1; }
    echo "ok — $CODEX_MODEL, effort $CODEX_EFFORT" ;;
  *) die "codex backend: неизвестная команда $1" ;;
esac
