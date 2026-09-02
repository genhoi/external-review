# Fixture run results

Fixture: `make-fixture.sh`, branch `feature/webhook-retries` against `main`, brief
`fixture-brief.md`, protocol `prompts/reviewer.md`. Defects A–D and the decoy — see `README.md`.

## 2026-09-02 — new protocol (one run, all reviewers in parallel)

| Reviewer | Model | A dedup | B timezone | C vacuous test | D rounding | Decoy | Extra | Evidence | Tool calls | Time | Cost (nominal) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glm | glm-5.3[1m], effort max | ✓ critical | ✓ major | ✓ major | ✓ major | not flagged | TypeError on aware now (minor, ran); check-then-act race (minor, honestly `inferred` 55, repro failed) | all `ran`, repro scripts in the snapshot, fixes applied and reverted | 31 | 5m22s | $1.02 |
| opus | claude-opus-5, effort max | ✓ critical | ✓ critical | ✓ major | ✓ major | not flagged | subscription tests at ±30 days are insensitive (minor) | all `ran` | 18 | 6m18s | $1.33 |
| kimi-cli | kimi-code/k3, effort high | ✓ critical | ✓ major | ✓ major | ✓ major | not flagged | `is_active` is never called (info, read) — correct | all `ran` | 15 | 6m07s | subscription |
| grok | grok-4.6, xhigh | ✓ critical | ✓ critical | folded into evidence for A | ✓ major | not flagged | — | all `ran` | 33 | 8m17s | $0.09 |
| kimi | k3[1m] via Claude Code, effort max | ✓ critical | ✓ major | ✓ major | ✓ major | not flagged | — (separately verified compatibility of the dedup key format change and the absence of call sites) | all `ran` | 19 | 10m05s | $0.84 |
| codex | gpt-5.6-sol (from config), xhigh | ✓ critical | ✓ major | folded into A | ✓ critical | not flagged | check-then-act race as **critical/95 `ran`** — debatable (glm could not reproduce it) | all `ran` | 24 | 9m17s | subscription |

`review collect` merged report: five of five agreed on A, B, D; three reported C as a separate finding; the disagreement
on the race (codex critical vs glm inferred 55) is a typical case for `review ask`.
All five: verdict "not ready", JSON block parsed, `REVIEW.md` written in the snapshot.

## 2026-09-02 — baseline: old prompt (no protocol), same writable snapshot

| Reviewer | A | B | C | D | Decoy | Notes |
|---|---|---|---|---|---|---|
| glm | ✓ | ✓ | ✓ | ✓ | not flagged | 14 tool calls, 3m24s; ran repros; no verification log or JSON |
| grok | ✓ | ✓ | ✓ | ✓ | not flagged | 23 tool calls, 4m21s |
| codex | ✓ | ✓ | ✓ | ✗ | not flagged | 8 tool calls, 4m19s; missed the rounding |

Conclusion: with a detailed brief and the ability to run tests, even the old prompt yields a strong
review; the protocol adds evidence structure (`ran|read|inferred` + confidence), a verification log,
a "Checked, fine" section, a machine-readable block for the merged report, and a duplicate in `REVIEW.md`.
The main source of "linter-like" reports before was read-only docker + plan mode, where the reviewer
could not run anything.

## 2026-09-02 — the skill from the orchestrator's side (same task, reviewers glm + grok)

| Orchestrator | How launched | Result |
|---|---|---|
| Claude (fresh subagent) | Agent tool, SKILL.md only | doctor → full brief → run → wait → collect → triage with its own reproduction of every finding; 22 calls, 14 min; nothing rejected, did not raise the decoy |
| GLM-5.3 headless | `claude -p` via z.ai, regular `~/.claude` | first attempt: `wait` killed by the Bash tool's 2-minute timeout, GLM ended the session with an "interim status" → fixed (`wait` returns within ≤110 s, exit 3). Second attempt: `wait` in a loop 8 times, triage.md, merged.md, repro check in the snapshot; 43 calls, 15 min, full verdict table |

## 2026-09-02 — English protocol (`--lang en`, brief `fixture-brief.en.md`)

| Reviewer | A | B | C | D | Decoy | Evidence | Tool calls | Time | Notes |
|---|---|---|---|---|---|---|---|---|---|
| glm | ✓ critical | ✓ major | ✓ major | ✓ major | not flagged | all `ran` | 25 | 4m35s | + TypeError on aware `now` (minor); English section headings and JSON block parsed by `collect` |
| grok | ✓ critical | ✓ major | folded into A | ✓ major | not flagged | all `ran` | 35 | 7m11s | same shape as the Russian run |
