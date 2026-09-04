#!/usr/bin/env bash
# Local/CI test suite: no API keys, no network. Run from anywhere: tests/ci.sh
set -euo pipefail
SK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
R="$SK/bin/review"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export EXTERNAL_REVIEW_HOME="$TMP/state" EXTERNAL_REVIEW_CONFIG="$TMP/none.env" REVIEW_LANG=en REVIEW_DEPS=copy
pass() { echo "  ✓ $*"; }
fail() { echo "  ✗ $*" >&2; exit 1; }

echo "== syntax"
for f in "$SK"/bin/review "$SK"/bin/lib/*.sh "$SK"/bin/backends/*.sh "$SK"/tests/*.sh; do bash -n "$f"; done; pass "bash -n"
python3 -m py_compile "$SK"/bin/lib/extract.py "$SK"/bin/bundle.py "$SK"/tests/unit_extract.py; pass "py_compile"
if command -v shellcheck >/dev/null; then
  shellcheck -S warning -e SC1091,SC2086,SC2046,SC2155 "$SK"/bin/review "$SK"/bin/lib/*.sh "$SK"/bin/backends/*.sh "$SK"/tests/*.sh; pass "shellcheck"
else echo "  - shellcheck not installed, skipped"; fi

echo "== unit tests (extract.py)"
python3 -m unittest -q "$SK/tests/unit_extract.py" 2>&1 | tail -1

echo "== fixture builds and its tests pass"
FX="$TMP/fixture"; "$SK/tests/make-fixture.sh" "$FX" >/dev/null; pass "make-fixture.sh"
cd "$FX"
"$R" config | grep -q 'REVIEW_DEPS *copy'; pass "config prints defaults"
"$R" brief --lang en | grep -q '^# Brief for the reviewer'; pass "brief en"
"$R" brief --lang ru | grep -q '^# Вводная'; pass "brief ru"
! "$R" brief --lang xx >/dev/null 2>&1; pass "brief rejects unknown language"

echo "== preflight runs the command inside a snapshot"
"$R" preflight '.venv/bin/pytest -q' 2>/dev/null | grep -q 'preflight OK'; pass "preflight OK on a working command"
! "$R" preflight 'test -f THIS_FILE_DOES_NOT_EXIST' >/dev/null 2>&1; pass "preflight fails on a broken command"
"$R" preflight 'test "$(basename "$PWD")" = snapshot && test -d .venv && test ! -L .venv' >/dev/null 2>&1; pass "preflight cwd is the snapshot with copied deps"
[ -z "$(ls -d "$EXTERNAL_REVIEW_HOME"/runs/preflight-* 2>/dev/null | head -1)" ] || pass "failed preflight keeps its output for inspection"

echo "== end-to-end with the stub reviewer"
printf '# billing-lite\n\n## External review\n\n- Tests: `.venv/bin/pytest -q`\n- Known decisions: Store stub\n' > CLAUDE.md
"$R" brief --lang en --out "$TMP/brief.md" 2>/dev/null
grep -q 'Project profile (from CLAUDE.md § External review)' "$TMP/brief.md"; pass "brief seeded from CLAUDE.md section"
RUN="$("$R" run --reviewers fake --brief "$TMP/brief.md" --base main --lang en 2>"$TMP/run.err")"
[ -d "$RUN" ]; pass "run created $(basename "$RUN")"
grep -q 'deps (copy): .venv' "$TMP/run.err"; pass "deps report printed"
[ -d "$RUN/fake/snapshot/.venv" ] && [ ! -L "$RUN/fake/snapshot/.venv" ]; pass "deps copied as a real directory"
[ -f "$RUN/fake/snapshot/CLAUDE.md" ]; pass "untracked file included in snapshot"
grep -q '^# Run context' "$RUN/header.md" && grep -q 'COPIED into the snapshot' "$RUN/header.md"; pass "english header with deps note"
grep -q '^# Independent review protocol' "$RUN/prompt.md" && grep -q 'Project profile' "$RUN/prompt.md"; pass "prompt = protocol + brief + profile"
c=0; until "$R" wait "$RUN" --max 20 --interval 1 >/dev/null; do c=$((c+1)); [ $c -lt 5 ] || fail "wait never finished"; done; pass "wait returned 0"
[ "$(cat "$RUN/fake/status")" = "done" ]; pass "status done"
grep -q '^## Summary' "$RUN/fake/report.md"; pass "report extracted"
[ -f "$RUN/fake/snapshot/REVIEW.md" ]; pass "REVIEW.md written by reviewer"
grep -q '"session_id": "00000000-0000-4000-8000-000000000001"' "$RUN/fake/meta.json"; pass "session id captured"
grep -q '"tokens_in": 10500' "$RUN/fake/meta.json"; pass "tokens captured"
M="$("$R" collect "$RUN")"
grep -q '| fake | done | 4 | 3 |' "$M" && grep -q '`billing/webhooks.py:13`' "$M"; pass "merged.md table"
"$R" status "$RUN" | grep -q 'fake done'; pass "status line"
"$R" ask "$RUN" fake "why?" 2>/dev/null | grep -q 'fake reviewer got: why?'; pass "ask routed to backend"

echo "== blind, russian header, plan mode"
RUN2="$("$R" run --reviewers fake --brief "$TMP/brief.md" --base main --lang ru --blind 2>/dev/null)"
grep -q '^# Служебная вводная' "$RUN2/header.md"; pass "russian header"
! grep -q '^## Intent' "$RUN2/prompt.md"; pass "--blind strips Intent"
grep -q '^## How to run' "$RUN2/prompt.md"; pass "--blind keeps the rest"
until "$R" wait "$RUN2" --max 20 --interval 1 >/dev/null; do :; done
echo "plan body" > "$TMP/plan.md"
RUN3="$("$R" run --reviewers fake --brief "$TMP/brief.md" --mode plan --plan "$TMP/plan.md" 2>/dev/null)"
grep -q '^# Document under review' "$RUN3/prompt.md" && [ -f "$RUN3/fake/snapshot/plan.md" ]; pass "plan mode"
grep -q '^# Addendum: the subject is a design' "$RUN3/prompt.md"; pass "plan mode adds the design-review protocol"
! grep -q 'Addendum' "$RUN2/prompt.md"; pass "the addendum stays out of the other modes"
until "$R" wait "$RUN3" --max 20 --interval 1 >/dev/null; do :; done

echo "== dead wrapper is reaped from what is on disk"
RUN4="$("$R" run --reviewers fake --brief "$TMP/brief.md" --base main 2>/dev/null)"
until "$R" wait "$RUN4" --max 20 --interval 1 >/dev/null; do :; done
echo running > "$RUN4/fake/status"; echo 999999 > "$RUN4/fake/pid"; rm -f "$RUN4/fake/exit"   # pretend the wrapper vanished mid-flight
"$R" status "$RUN4" | grep -q 'fake done(killed)'; pass "died + report on disk → done(killed)"
"$R" wait "$RUN4" --max 5 >/dev/null; pass "wait does not block on a dead reviewer"

echo "== a run cut short is reported as partial, not as a clean done"
bash -c 'ER_SKILL_DIR="$1"; source "$1/bin/lib/common.sh"; source "$1/bin/lib/finalize.sh"; finalize_reviewer "$2" fake 124' _ "$SK" "$RUN4"
grep -q 'timeout or kill' "$RUN4/fake/partial"; pass "timeout leaves a partial marker"
"$R" status "$RUN4" | grep -q 'done(timeout or kill)'; pass "status shows why it is incomplete"
"$R" collect "$RUN4" >/dev/null && grep -q 'done (timeout or kill)' "$RUN4/merged.md"; pass "merged.md shows it in the reviewer table"
bash -c 'ER_SKILL_DIR="$1"; source "$1/bin/lib/common.sh"; source "$1/bin/lib/finalize.sh"; finalize_reviewer "$2" fake 0' _ "$SK" "$RUN4"
[ ! -f "$RUN4/fake/partial" ]; pass "a clean finish leaves no marker"

echo "== usage journal and feedback"
U="$EXTERNAL_REVIEW_HOME/usage.jsonl"
grep -q '"event": "run"' "$U" && grep -q '"event": "collect"' "$U" && grep -q '"event": "preflight"' "$U" && grep -q '"event": "ask"' "$U"; pass "usage.jsonl has run/collect/preflight/ask events"
grep -q '"reviewers": {"fake": {"status": "done"' "$U"; pass "collect records per-reviewer summary"
"$R" feedback "$RUN" "stub run: nothing blocked; 1 accepted, 0 rejected" | grep -q 'saved:'; pass "feedback note saved"
[ -f "$RUN/feedback.md" ] && grep -q 'stub run' "$EXTERNAL_REVIEW_HOME/feedback.jsonl"; pass "note in run dir and feedback.jsonl"
"$R" feedback --digest | grep -q '## Notes from orchestrators' && "$R" feedback --digest | grep -q '| fake |'; pass "digest lists notes and reviewer stats"
"$R" feedback --digest --since 2099-01-01 | grep -q 'runs: 0'; pass "digest --since filters"
n=$(wc -l < "$U"); EXTERNAL_REVIEW_NO_USAGE=1 "$R" status "$RUN" >/dev/null; [ "$(wc -l < "$U")" -eq "$n" ]; pass "EXTERNAL_REVIEW_NO_USAGE=1 disables the journal"
! "$R" feedback "$RUN" "" >/dev/null 2>&1; pass "empty note rejected"

echo "== two runs in the same second get distinct dirs"
A="$("$R" run --reviewers fake --brief "$TMP/brief.md" --base main 2>/dev/null)"; B="$("$R" run --reviewers fake --brief "$TMP/brief.md" --base main 2>/dev/null)"
[ "$A" != "$B" ]; pass "distinct run dirs"
until "$R" wait "$A" --max 20 --interval 1 >/dev/null; do :; done; until "$R" wait "$B" --max 20 --interval 1 >/dev/null; do :; done

echo "== clean"
"$R" clean --all >/dev/null; [ -z "$(ls -A "$EXTERNAL_REVIEW_HOME/runs" 2>/dev/null)" ] || fail "runs left after clean --all: $(ls "$EXTERNAL_REVIEW_HOME/runs")"; pass "clean --all (runs and preflight dirs)"
git -C "$FX" worktree list | grep -vq 'runs/' || fail "worktrees left behind"; pass "no worktrees left"
echo "all good"
