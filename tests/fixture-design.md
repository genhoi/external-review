# Design: nightly subscription expiry and webhook idempotency

<!-- A DELIBERATELY FLAWED design document for the `make-fixture.sh` billing fixture, used to
     exercise `--mode plan`. Every claim below is checkable against that fixture's code and docs.
     Pass criteria live in tests/README.md. Do not "fix" this file: the flaws are the test. -->

## Problem

Subscriptions stay active past `expires_at`, and provider retries occasionally double-charge.

## Proposed change

1. Add a nightly job `billing/jobs/expire.py`. It selects subscriptions where
   `expires_at < datetime.now()` and marks them expired, reusing the comparison
   `billing/subscriptions.py` already performs so the two agree.
2. Make webhook handling idempotent by persisting every processed `event.id` in a new
   `processed_events` table, and skipping an event whose id is already stored. This replaces the
   in-memory dedup in `billing/webhooks.py`.
3. Charge amounts keep coming from `billing/pricing.py::apply_discount`; the job does not compute
   money, so rounding is out of scope for this change.
4. `billing/refunds.py::refund` is called by the new job on downgrade, so it must validate the
   refund amount; add that validation.

## Claims this design rests on

- **C1.** The expiry comparison in `billing/subscriptions.py` is correct today, so reusing it keeps
  the job and the live check in agreement.
- **C2.** `event.id` is stable across provider retries, so storing it makes webhook handling
  idempotent.
- **C3.** The existing test suite covers double-charging, so a regression would be caught.
- **C4.** `apply_discount` rounds the way `docs/invoicing.md` specifies, so the job can use it as is.
- **C5.** `refund()` has no amount validation and is therefore unsafe for a new caller.
