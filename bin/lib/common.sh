#!/usr/bin/env bash
# Общие функции для bin/review и бэкендов. Подключается через `source`.

ER_SKILL_DIR="${ER_SKILL_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ER_HOME="${EXTERNAL_REVIEW_HOME:-$HOME/.local/state/external-review}"
ER_RUNS="$ER_HOME/runs"
ER_CFG="$ER_HOME/cfg"          # изолированные CLAUDE_CONFIG_DIR для сторонних бэкендов
ER_DEFAULT_TIMEOUT="${EXTERNAL_REVIEW_TIMEOUT:-2700}"   # 45 минут на рецензента
ER_DEFAULT_LINKS="vendor node_modules .venv .env .env.local .env.test"
ER_ALL_BACKENDS="glm kimi kimi-cli grok codex opus"
source "$ER_SKILL_DIR/bin/lib/defaults.sh"

die()  { printf 'review: %s\n' "$*" >&2; exit 1; }
warn() { printf 'review: %s\n' "$*" >&2; }
now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }
py() { python3 "$ER_SKILL_DIR/bin/lib/extract.py" "$@"; }

proj_root() { git rev-parse --show-toplevel 2>/dev/null || die "не git-репозиторий: $PWD (нужен git для снапшота)"; }
proj_name() { basename "$(proj_root)"; }

# Ключ из переменной окружения или из файла (первая непустая строка).
key_from() { # key_from ENV_NAME FILE
  local v="${!1:-}"
  if [ -n "$v" ]; then printf '%s' "$v"; return 0; fi
  if [ -f "$2" ]; then head -n1 "$2" | tr -d '\r\n'; return 0; fi
  return 1
}

# Последний прогон для текущего проекта (или явно заданный путь).
resolve_run() { # resolve_run [RUN]
  local r="${1:-}"
  if [ -n "$r" ]; then
    [ -d "$r" ] && { printf '%s' "$(cd "$r" && pwd)"; return; }
    [ -d "$ER_RUNS/$r" ] && { printf '%s' "$ER_RUNS/$r"; return; }
    die "прогон не найден: $r"
  fi
  local p; p="$(proj_name)"
  local latest; latest="$(ls -1d "$ER_RUNS/$p"-* 2>/dev/null | sort | tail -n1)"
  [ -n "$latest" ] || die "нет прогонов для проекта $p (см. review runs)"
  printf '%s' "$latest"
}

run_reviewers() { # список рецензентов прогона
  ls -1 "$1" | while read -r d; do [ -f "$1/$d/status" ] && echo "$d"; done
}

status_of() { cat "$1/$2/status" 2>/dev/null || echo "unknown"; }

# Снапшот: временный коммит с рабочим деревом (включая незакоммиченное и untracked,
# кроме .gitignore) поверх HEAD. Печатает sha. Если дерево чистое — печатает HEAD.
snapshot_commit() { # snapshot_commit PROJ_ROOT
  local root="$1" idx tree head
  head="$(git -C "$root" rev-parse HEAD)"
  idx="$(mktemp)"
  cp "$root/.git/index" "$idx" 2>/dev/null || true
  GIT_INDEX_FILE="$idx" git -C "$root" add -A >/dev/null 2>&1
  tree="$(GIT_INDEX_FILE="$idx" git -C "$root" write-tree)"
  rm -f "$idx"
  if [ "$tree" = "$(git -C "$root" rev-parse "$head^{tree}")" ]; then
    printf '%s' "$head"
  else
    git -C "$root" commit-tree "$tree" -p "$head" -m "external-review snapshot $(now_iso)"
  fi
}

# Detached worktree на снапшот-коммит + симлинки на игнорируемые зависимости.
make_worktree() { # make_worktree PROJ_ROOT COMMIT DEST LINKS...
  local root="$1" commit="$2" dest="$3"; shift 3
  git -C "$root" worktree add --detach --quiet "$dest" "$commit" 2>/dev/null \
    || git -C "$root" worktree add --detach "$dest" "$commit" >/dev/null
  local l
  for l in "$@"; do
    if [ -e "$root/$l" ] && [ ! -e "$dest/$l" ]; then
      mkdir -p "$(dirname "$dest/$l")"
      ln -s "$root/$l" "$dest/$l"
    fi
  done
}

remove_worktree() { # remove_worktree PROJ_ROOT DEST
  [ -d "$2" ] || return 0
  git -C "$1" worktree remove --force "$2" >/dev/null 2>&1 || rm -rf "$2"
  git -C "$1" worktree prune >/dev/null 2>&1 || true
}

# Базовый ref для diff-режима: явный, иначе merge-base с main/master.
detect_base() { # detect_base PROJ_ROOT [BASE]
  local root="$1" base="${2:-}" c
  if [ -n "$base" ]; then git -C "$root" rev-parse --verify -q "$base^{commit}" >/dev/null || die "base не найден: $base"; printf '%s' "$base"; return; fi
  for c in origin/HEAD main master origin/main origin/master develop; do
    if git -C "$root" rev-parse --verify -q "$c^{commit}" >/dev/null; then printf '%s' "$c"; return; fi
  done
  return 1
}

# JSON deny-правил для claude-семейства: писать можно только в снапшот.
claude_deny_settings() { # claude_deny_settings PROJ_ROOT — компактный JSON одной строкой (иначе claude примет аргумент за путь)
  python3 - "$1" "$HOME" <<'PYJSON'
import json, sys
root, home = sys.argv[1], sys.argv[2]
deny = ["Bash(git push:*)", "Bash(git push *)"]
for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
    deny += [f"{tool}(/{root}/**)", f"{tool}(/{home}/.claude/**)"]
print(json.dumps({"permissions": {"deny": deny}}))
PYJSON
}

uuid() { python3 -c 'import uuid; print(uuid.uuid4())'; }
