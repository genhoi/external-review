#!/usr/bin/env bash
# Background wrapper for one reviewer: status files, timeout, report extraction.
# Usage: launch.sh RUN REVIEWER   (ER_* environment is set by bin/review)
# The whole body lives in main() so bash parses the file completely before running it:
# editing this file while a review is in flight must not break the wrapper.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/finalize.sh"

main() {
  local RUN="$1" R="$2" D="$1/$2"
  export ER_RUN="$RUN" ER_REVIEWER="$R" ER_DIR="$D" ER_SNAPSHOT="$D/snapshot" ER_PROMPT="$RUN/prompt.md"
  export ER_PROJ_ROOT="$(cat "$RUN/project_root")" ER_TIMEOUT="$(cat "$RUN/timeout")"
  local BACKEND="$ER_SKILL_DIR/bin/backends/${R%%:*}.sh"   # "glm", "kimi", ... (after ':' — a variant, e.g. a lens)
  [ -x "$BACKEND" ] || { echo "failed:no-backend" > "$D/status"; return 1; }
  echo running > "$D/status"; now_iso > "$D/started"
  timeout -k 60 "$ER_TIMEOUT" bash "$BACKEND" run > "$D/raw" 2> "$D/stderr.log"
  local code=$?
  finalize_reviewer "$RUN" "$R" "$code"
}
main "$@"
exit $?
