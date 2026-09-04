# Testing reviewers on the fixture

`make-fixture.sh DEST` creates a mini billing service (Python, pytest, 11 green tests) with a
`feature/webhook-retries` branch containing planted defects that a linter cannot see:

| # | Where | What | How to find |
|---|---|---|---|
| A | `billing/webhooks.py` | deduplication by `event.id`, while `docs/provider.md` says: a retry arrives with a new `id`, `payment_id` is stable → double charge | read the contract, reproduce with two events |
| B | `billing/subscriptions.py` | `expires_at` (UTC, aware) is compared with naive local `datetime.now()`; servers are in UTC+5 → the subscription expires 5 hours early | `TZ=Asia/Almaty` + repro |
| C | `tests/test_webhooks.py` | the "no double charge" test asserts `processed_count >= 1` — passes on broken code too | read the assert |
| D | `billing/pricing.py` | `quantize` without `rounding=` → half-even, while `docs/invoicing.md` requires half-up | `apply_discount(Decimal("4.69"), 50)` → 2.34 instead of 2.35 |
| — | `billing/refunds.py` | **decoy**: `refund()` does not validate the amount, but the only caller `api.post_refund` does | expected: no finding, or `minor` "no defense in depth" |

Run:
```bash
tests/make-fixture.sh /tmp/fixture-billing && cd /tmp/fixture-billing
R=~/.claude/skills/external-review/bin/review
$R run --reviewers glm --prompt-file ~/.claude/skills/external-review/tests/smoke-prompt.md   # 1) flags and access
$R run --reviewers glm --brief ~/.claude/skills/external-review/tests/fixture-brief.md --base main   # 2) the review itself
$R wait && $R collect
```
What to look for in the report: whether A–D were found, what happened with the decoy, whether there is `ran` evidence and a verification log,
whether there is a JSON block at the end (otherwise the merged report will not assemble), how many tool calls and minutes.

Results from 2026-09-02 (new protocol; record new runs here when models change):
see `results.md`.


## Plan mode fixture

`tests/fixture-design.md` is a deliberately flawed design for the same billing fixture, used to
exercise `--mode plan`. It rests on five named claims; four are decidable from the fixture's code
and docs, and the fifth is the decoy.

```bash
tests/make-fixture.sh /tmp/fixture-billing && cd /tmp/fixture-billing
R=~/.claude/skills/external-review/bin/review
$R run --reviewers glm,opus --brief $R/../tests/fixture-brief.md \
       --mode plan --plan ~/.claude/skills/external-review/tests/fixture-design.md
$R wait && $R collect
```

| Claim | Should come back | Why it is decidable |
|---|---|---|
| C1 expiry comparison is correct today | **breaks** | defect B: aware UTC `expires_at` vs naive local `datetime.now()`; reusing it propagates the bug into the job |
| C2 `event.id` is stable across retries | **breaks** | `docs/provider.md` says a retry arrives with a new `id` and a stable `payment_id`; the whole idempotency design rests on the opposite |
| C3 the suite covers double-charging | **breaks** | defect C: the test asserts `processed_count >= 1`, which passes on broken code |
| C4 `apply_discount` rounds per the docs | **breaks** | defect D: `quantize` without `rounding=` is half-even, the docs require half-up |
| C5 `refund()` is unsafe for a new caller | holds, or `minor` | the decoy: the only current caller validates, but the design does add a second caller |

What to look for: whether `merged.md` has a `## Design claims` table with a column per reviewer;
whether disagreements sort to the top; whether every `breaks` verdict also appears under
`## Findings` with the record or input it breaks on; whether verdicts are tagged `ran`/`read` rather
than `inferred` (a reviewer with the fixture in a snapshot can read `docs/provider.md` and run
`apply_discount` — `inferred` on C2 or C4 means the reviewer did not do the work).


## Without API keys

`tests/ci.sh` runs the whole suite locally in ~15 s: syntax and shellcheck, unit tests for `bin/lib/extract.py` on the recorded samples in `tests/samples/`, the fixture build, and an end-to-end run with the stub reviewer (`--reviewers fake`) covering snapshot, copied dependencies, project profile, `--blind`, `--lang ru`, plan mode, dead-wrapper reaping, same-second run dirs and `clean`. GitHub Actions runs the same script.
