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


## Without API keys

`tests/ci.sh` runs the whole suite locally in ~15 s: syntax and shellcheck, unit tests for `bin/lib/extract.py` on the recorded samples in `tests/samples/`, the fixture build, and an end-to-end run with the stub reviewer (`--reviewers fake`) covering snapshot, copied dependencies, project profile, `--blind`, `--lang ru`, plan mode, dead-wrapper reaping, same-second run dirs and `clean`. GitHub Actions runs the same script.
