#!/usr/bin/env bash
# Stub reviewer for CI and dry runs: replays a canned claude-stream-json log with a canonical report.
# Never selected by `--reviewers auto` (check fails unless EXTERNAL_REVIEW_FAKE=1); use `--reviewers fake`.
# The log's "reviewer" also writes REVIEW.md into the snapshot, like a real one would.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
SAMPLE="$ER_SKILL_DIR/tests/samples/claude-stream.jsonl"
case "$1" in
  run)
    cd "$ER_SNAPSHOT" || exit 1
    python3 "$ER_SKILL_DIR/bin/lib/extract.py" report claude-stream-json "$SAMPLE" > REVIEW.md
    sleep "${FAKE_DELAY:-1}"
    cat "$SAMPLE" ;;
  ask)    echo "fake reviewer got: $2" ;;
  format) echo claude-stream-json ;;
  check)  [ -n "${EXTERNAL_REVIEW_FAKE:-}" ] || { echo "stub backend (set EXTERNAL_REVIEW_FAKE=1 or use --reviewers fake)"; exit 1; }; echo "ok — stub" ;;
  *) die "fake backend: unknown command $1" ;;
esac
exit 0
