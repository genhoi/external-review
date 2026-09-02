# Brief for the reviewer

## Intent
Branch feature/webhook-retries: (1) provider webhooks are now deduplicated with redeliveries
taken into account; (2) an `is_active` subscription activity check was added; (3) percentage
validation was added to `apply_discount`. Charging behavior on the first successful event must not change.

## System and cost of failure
billing-lite: ingestion of webhooks from the PayGate payment provider, subscription status, discount
calculation for invoices. Mistakes cost money: double-charging a customer, wrong amounts on invoices
(accounting reconciles to the cent), access to the service after the subscription has ended.

## Stack and non-obvious properties
Python 3.12 without a framework, pytest. Servers run in Asia/Almaty (UTC+5), dates in the DB are in UTC.
The provider delivers events at-least-once; contract details are in docs/provider.md.
Rounding rules are in docs/invoicing.md.

## How to run
- All tests: `.venv/bin/pytest -q`
- Targeted tests: `.venv/bin/pytest -q tests/test_webhooks.py`
- Static analysis / typing / linter: none
- Not available in this environment: the real provider and DB (everything is in-memory, Store in billing/store.py)

## Repository map
- billing/ — domain: webhooks.py (event ingestion), subscriptions.py, pricing.py, refunds.py + api.py (HTTP layer)
- tests/ — pytest
- docs/ — provider contract and calculation rules

## Do not review
.venv/, .pytest_cache/

## Priorities for this run
1. Money correctness: idempotency and retries, rounding
2. Time boundaries and timezones
3. What the tests of the changed behavior actually verify

## Known decisions
- In-memory Store is intentional, a stub for tests; persistence is out of scope.
- `refund()` relies on validation in api.py — the single entry point, this is deliberate.
