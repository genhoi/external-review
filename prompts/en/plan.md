# Addendum: the subject is a design, not a diff

What is under review is the document below (`plan.md`, also in the snapshot root). The code that
implements it does not exist yet. The rest of the protocol stands; this addendum replaces phases 1–3
and adds one section to the report.

A design review that only reads the document produces taste. Your value is the opposite: the design
rests on assumptions about a system that exists right now — and those can be measured. Verify the
assumptions, not the prose.

## How to work

### 1. Inventory before invention
For every value the design proposes to compute, first look for what the system already computes:
snapshots, caches, journals, projections, materialised columns — written by the full pipeline at the
moment of a state transition. Inheriting a filter by construction is cheaper and safer than
reproducing it by hand. If such an artifact exists and the design ignores it, that is a finding: say
who writes it, when, and what makes it stale. An artifact that looks defective is not disqualified
until you check which branch writes it — the defect may be in one branch only, and the artifact may
still be the right foundation with a staleness rule on top.

### 2. Measure on the worst rows, before any code exists
Find 3–5 of the most degenerate real records (fixtures, seeds, migrations, or the dev/stand database
named in the brief) and answer in writing: what would this design return here? Prefer the ugly ones —
the collapsed, the stale, the ones with no related row at all, the ones written by an older version.
Probing a live record inside a rolled-back transaction (`BEGIN; …; ROLLBACK`) is a normal tool, not an
exotic one: it is how you check that a state the design assumes is actually reachable and accepted by
today's code. Only on a database the brief names as a stand or a copy — never production, never a
committed write.

### 3. The invariant and the single source
State the design's invariant in one sentence ("what is shown = what is accepted = what can be
started"). Then check it: do all consumers read one source, or does the design ask two or three
places to compute the same thing correctly? N correct computations of the same value is a finding,
not a style preference — name the consumers that would drift apart.

### 4. Enumerate the state space
If the design has several dimensions (status × current value × target × presence of a plan) and their
product is under ~500, enumerate the cells and name the ones the design does not cover. "The scenario
passes" is not a check when there is more than one dimension.

### 5. A verdict on each claim
The design's claims are your hypotheses. Each ends as one of: holds (with evidence) / breaks (with the
input or record it breaks on) / unverifiable (with what is missing and how the author can check it).

## What changes in the report

- Add `## Design claims` before `## Findings`: `| Claim | Verdict | Evidence |`, one row per claim —
  holds / breaks on … / unverifiable.
- A finding here is "the design breaks on this input or state", not "this code is wrong". Its location
  is the existing code the assumption is about (`path/file.ext:LINE`), or `plan.md:<section>` when the
  flaw is in the document itself.
- Evidence tags apply to the assumptions, not to the unwritten code: `ran` — you queried the data or
  ran existing code; `read` — you traced today's call sites; `inferred` — you could not check. A
  prediction about code that does not exist yet is never `ran`.
- One rule from the protocol is relaxed here: proposing a different approach is allowed — but only
  together with the evidence that the proposed design breaks. An alternative without that evidence is
  taste, and does not belong in the report.
- The verdict is about the design: "ready" means it can be implemented as written.
