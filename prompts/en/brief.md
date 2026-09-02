# Brief for the reviewer

<!-- Filled in by the orchestrator (whoever requests the review). Delete the comments.
     The more precise the brief, the less the reviewer wanders and the fewer false findings.
     Do not paste code or the diff here: the reviewer reads them in the snapshot. -->

## Intent
<!-- What changed and why, 2–5 lines. Which behaviour should change, which should stay.
     Link to the task or spec if it lives in the repository. -->

## System and cost of failure
<!-- Domain, who the users are, what happens on failure: money, personal data, downtime,
     legal consequences. 2–5 lines. -->

## Stack and non-obvious properties
<!-- Versions and whatever cannot be derived from the code: "SELECTs go to a read replica and do
     not see uncommitted rows", "workers run in a different time zone", "the provider retries with
     a new id". -->

## How to run
<!-- Exact commands. What is available (DB, docker, external services) and what is not — say so. -->
- Full test suite: `...`
- Targeted tests: `...`
- Static analysis / type checking / linter: `...`
- Not available in this environment: ...

## Repository map
<!-- 2–3 lines per directory: domain, infrastructure, tests, docs. Only what is needed to
     avoid wandering. -->

## Do not review
vendor/, node_modules/, generated code, snapshots, migrations older than the current task

## Priorities for this run
<!-- In order of importance for THIS project, e.g.:
     1. money correctness and idempotency  2. authn/authz  3. migrations and consistency
     4. operations: dependency failures, logs  5. gaps in tests -->
1.
2.
3.

## Known decisions
<!-- Deliberate trade-offs, known debt, things already in the backlog. The reviewer must not report
     these as findings. This section and "Intent" are what the --blind flag hides. -->
