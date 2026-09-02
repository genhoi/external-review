## Summary
Intent as understood: deduplicate webhook redeliveries. Verdict: **not ready**. Top must-fix: dedupe key.

## Findings

### 1. [critical] [confidence 95] billing/webhooks.py:13 — dedupe key uses event id, regenerated on redelivery
- What breaks: a redelivered event with a new id and the same payment_id is credited again.
- Evidence (ran): `.venv/bin/python repro.py` → `payments[pay_1] = 200.00`.
- Impact: money — every redelivery double-credits.
- Fix: key on `payment_id`.
- How to verify the fix: `.venv/bin/pytest -q tests/test_webhooks.py`.

## Checked, fine
- Full suite: `.venv/bin/pytest -q` → 11 passed.

## Could not verify
- Real provider payloads.

## Verification log
| Hypothesis | How checked | Result |
|---|---|---|
| Redelivery double-credits | ran repro | confirmed |

## Machine block
```json
{"verdict": "not ready", "findings": [{"id": 1, "severity": "critical", "confidence": 95, "file": "billing/webhooks.py", "line": 13, "title": "dedupe key uses event id, regenerated on redelivery", "evidence": "ran", "repro": ".venv/bin/python repro.py"}], "checked_ok": ["full suite green"], "unverified": ["real provider payloads"]}
```
