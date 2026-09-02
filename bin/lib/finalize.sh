#!/usr/bin/env bash
# Finalize one reviewer directory: extract the report, write meta.json, snapshot changes and the status.
# Shared by launch.sh (normal completion) and bin/review (a wrapper that died without writing a status).
# Usage: finalize_reviewer RUN REVIEWER EXIT_CODE   (EXIT_CODE may be "died")

nonblank() { [ -n "$(tr -d '[:space:]' < "$1" 2>/dev/null)" ]; }

finalize_reviewer() {
  local run="$1" r="$2" code="$3" d="$1/$2"; : "$r"
  local fmt; fmt="$(cat "$d/format" 2>/dev/null || echo text)"
  local snap="$d/snapshot"
  [ -f "$d/finished" ] || now_iso > "$d/finished"
  py report "$fmt" "$d/raw" > "$d/report.md" 2>> "$d/stderr.log" || true
  py meta   "$fmt" "$d/raw" > "$d/meta.json" 2>> "$d/stderr.log" || true
  ( cd "$snap" 2>/dev/null && git status --porcelain --untracked-files=all 2>/dev/null ) \
    | grep -v -F -f <(sed 's#^#?? #' "$run/links" 2>/dev/null; echo '?? REVIEW.md') > "$d/snapshot_changes" || true
  # the reviewer is told to duplicate the report into REVIEW.md in the snapshot — fallback when stream extraction fails
  if ! nonblank "$d/report.md" && nonblank "$snap/REVIEW.md"; then cp "$snap/REVIEW.md" "$d/report.md"; fi
  echo "$code" > "$d/exit"
  if nonblank "$d/report.md"; then echo "done" > "$d/status"          # a report exists → finished, whatever the exit code says
  elif [ "$code" = 124 ] || [ "$code" = 137 ]; then echo timeout > "$d/status"
  elif [ "$code" = died ]; then echo died > "$d/status"
  else echo "failed:$code" > "$d/status"; fi
}
