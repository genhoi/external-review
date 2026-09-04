#!/usr/bin/env bash
# Finalize one reviewer directory: extract the report, write meta.json, snapshot changes and the status.
# Shared by launch.sh (normal completion) and bin/review (a wrapper that died without writing a status).
# Usage: finalize_reviewer RUN REVIEWER EXIT_CODE   (EXIT_CODE may be "died")

nonblank() { [ -n "$(tr -d '[:space:]' < "$1" 2>/dev/null)" ]; }

# Why the run did not complete cleanly, if it did not: a report may exist and still be a fragment
# (killed on the timeout, out of quota half-way). Empty output = clean finish.
partial_reason() { # partial_reason DIR EXIT_CODE
  local d="$1" code="$2" reason="" err=""
  case "$code" in
    0|"")        ;;
    124|137|143) reason="timeout or kill";;
    died)        reason="killed";;
    *)           reason="exit $code";;
  esac
  # the error message explains a bad exit; on a clean exit a transient one (a reconnect) is not a defect
  if [ -n "$reason" ] && [ -f "$d/meta.json" ]; then
    err="$(py error "$d/meta.json" 2>/dev/null)"
    [ -z "$err" ] || reason="$reason; $err"
  fi
  printf '%s' "$reason"
}

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
  partial_reason "$d" "$code" > "$d/partial"
  nonblank "$d/partial" || rm -f "$d/partial"
  if nonblank "$d/report.md"; then echo "done" > "$d/status"          # a report exists → finished, whatever the exit code says
  elif [ "$code" = 124 ] || [ "$code" = 137 ]; then echo timeout > "$d/status"
  elif [ "$code" = died ]; then echo died > "$d/status"
  else echo "failed:$code" > "$d/status"; fi
}
