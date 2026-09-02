#!/usr/bin/env bash
# Local usage journal: one JSON line per command in $ER_HOME/usage.jsonl. No code, no report contents —
# only what is needed to see how the skill is used across projects and harnesses. Disable with
# EXTERNAL_REVIEW_NO_USAGE=1. Read back with `review feedback --digest`.

# Best-effort guess of the orchestrator harness (override with ER_ORCHESTRATOR).
usage_harness() {
  if [ -n "${ER_ORCHESTRATOR:-}" ]; then printf '%s' "$ER_ORCHESTRATOR"; return; fi
  if [ -n "${CLAUDECODE:-}" ] || [ -n "${CLAUDE_CODE_ENTRYPOINT:-}" ]; then
    case "${ANTHROPIC_BASE_URL:-}" in
      *z.ai*) printf 'claude-code(glm)';; *kimi*) printf 'claude-code(kimi)';; "") printf 'claude-code';; *) printf 'claude-code(other)';;
    esac; return
  fi
  if env | grep -qE '^CODEX_'; then printf 'codex'; return; fi
  if env | grep -qE '^KIMI_'; then printf 'kimi'; return; fi
  if env | grep -qE '^GROK_'; then printf 'grok'; return; fi
  printf 'shell'
}

usage_log() { # usage_log EVENT [key=value ...]   (values are strings; key=@FILE reads JSON from FILE)
  [ -z "${EXTERNAL_REVIEW_NO_USAGE:-}" ] || return 0
  local ev="$1"; shift
  mkdir -p "$ER_HOME"
  python3 - "$ER_HOME/usage.jsonl" "$ev" "$(usage_harness)" "$(proj_name 2>/dev/null || basename "$PWD")" "$@" <<'PY' 2>/dev/null || true
import json, sys, datetime, os
path, event, harness, project, *kv = sys.argv[1:]
rec = {"ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
       "event": event, "project": project, "harness": harness, "host": os.uname().nodename}
for item in kv:
    k, _, v = item.partition("=")
    if v.startswith("@") and os.path.exists(v[1:]):
        try: v = json.load(open(v[1:]))
        except Exception: v = None
    elif v.isdigit(): v = int(v)
    rec[k] = v
with open(path, "a", encoding="utf-8") as fh: fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
PY
}
