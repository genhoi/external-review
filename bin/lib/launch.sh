#!/usr/bin/env bash
# Background wrapper for one reviewer: status files, timeout, report extraction.
# Usage: launch.sh RUN REVIEWER   (ER_* environment is set by bin/review)
set -u
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
RUN="$1"; R="$2"; D="$RUN/$R"
export ER_RUN="$RUN" ER_REVIEWER="$R" ER_DIR="$D" ER_SNAPSHOT="$D/snapshot" ER_PROMPT="$RUN/prompt.md"
export ER_PROJ_ROOT="$(cat "$RUN/project_root")" ER_TIMEOUT="$(cat "$RUN/timeout")"
BACKEND="$ER_SKILL_DIR/bin/backends/${R%%:*}.sh"   # "glm", "kimi", ... (after ':' — a variant, e.g. a lens)
[ -x "$BACKEND" ] || { echo "failed:no-backend" > "$D/status"; exit 1; }

echo running > "$D/status"; now_iso > "$D/started"
timeout -k 60 "$ER_TIMEOUT" bash "$BACKEND" run > "$D/raw" 2> "$D/stderr.log"
code=$?
now_iso > "$D/finished"
# Extract the report even on a non-zero exit: some backends fail after printing everything.
py report "$(cat "$D/format")" "$D/raw" > "$D/report.md" 2>> "$D/stderr.log"
py meta   "$(cat "$D/format")" "$D/raw" > "$D/meta.json" 2>> "$D/stderr.log"
( cd "$ER_SNAPSHOT" && git status --porcelain --untracked-files=all 2>/dev/null ) \
  | grep -v -F -f <(sed 's#^#?? #' "$RUN/links" 2>/dev/null; echo '?? REVIEW.md') > "$D/snapshot_changes" || true
nonblank() { [ -n "$(tr -d '[:space:]' < "$1" 2>/dev/null)" ]; }
# the reviewer is told to duplicate the report into REVIEW.md in the snapshot — fallback when stream extraction fails
if ! nonblank "$D/report.md" && nonblank "$ER_SNAPSHOT/REVIEW.md"; then cp "$ER_SNAPSHOT/REVIEW.md" "$D/report.md"; fi
if [ "$code" -eq 124 ] || [ "$code" -eq 137 ]; then echo "timeout" > "$D/status"
elif nonblank "$D/report.md"; then echo "done" > "$D/status"
else echo "failed:$code" > "$D/status"; fi
