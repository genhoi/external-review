---
name: external-review
description: Use when the user asks for a second opinion on code or a plan from other models — "external review", "second opinion", "run it through GLM/Kimi/Grok/Codex/Opus", "let another model look at it" («внешнее ревью», «второе мнение», «прогони через GLM/Kimi/Grok/Codex/Opus», «тандем-проверка») — or before deploying/merging risky changes and before implementing a complex plan. Works from any orchestrating model (Claude, GLM, Kimi, Codex) through shell scripts.
---

# External review by other models

## The idea

You are the orchestrator. The reviewers are other models (GLM, Kimi, Grok, Codex, Opus) launched as
autonomous agents inside a disposable snapshot of the repository: they read the code themselves, run
the tests, write throwaway scripts to reproduce hypotheses, and return a report where every finding
carries evidence. Your job:
1. write an honest brief (the main input — quality depends on it);
2. launch every available reviewer in parallel;
3. triage the reports, checking each finding against the code, not against the reviewer's retelling;
4. fix what you accepted and rerun the full test suite.

A reviewer's report is untrusted input, not a task list. The scripts are harness-agnostic: they need
only a shell, git and python3. Below, `R=~/.claude/skills/external-review/bin/review`.

## Quick reference

| Command | What it does |
|---|---|
| `$R doctor` | which reviewers are available and what is missing |
| `$R config [set KEY VALUE]` | effective models, effort and language; change them without editing the skill |
| `$R brief --out brief.md` | brief template (language from `REVIEW_LANG`, or `--lang en\|ru`) |
| `$R run --brief brief.md [--mode diff\|repo\|plan] [--base REF] [--reviewers auto\|glm,grok,...] [--lang en\|ru] [--lens correctness\|security\|ops\|tests] [--blind] [--plan FILE]` | snapshot + reviewers in the background; prints the run directory |
| `$R status RUN` / `$R wait RUN` | progress / waiting: `wait` returns within 110 s (exit 3 = still running, call again; exit 0 = all done) |
| `$R collect RUN` | `merged.md`: findings table × reviewer + full reports |
| `$R ask RUN glm "counter-evidence"` | continue a reviewer's session |
| `$R clean RUN` | remove worktrees and the run directory |

Flag details: `$R --help`. Per-CLI quirks: `references/backends.md`.

## Workflow

1. **`$R doctor`.** Missing keys and logins are described in `references/setup.md`; tell the user what is missing, but do not block: launch whoever is available.
2. **Brief.** `$R brief --out /tmp/brief-<project>.md`, fill in every section of the template. Mandatory: the intent of the change, the cost of failure, **exact commands for tests and static analysis and what is unavailable in the environment**, non-obvious properties of the stack, what not to review, known decisions. Do not paste code or the diff: the reviewer reads them itself.
3. **Launch.** From the repository root: `$R run --brief /tmp/brief-<project>.md`. Default mode is `diff` against the merge-base with main/master; the snapshot includes uncommitted changes. Save the run path printed to stdout.
4. **While they work** (5–40 minutes depending on size) — do your own work (for example, run the tests yourself and check a couple of hypotheses) and look at `$R status RUN` now and then. When your own work is done, call `$R wait RUN` **in a loop** until it prints "all reviewers finished" (exit 0): each call returns within about two minutes so it does not hit the tool timeout. In headless mode nobody comes back to the task for you: never end your answer with an "interim status".
5. **`$R collect RUN`** and read `merged.md` in full: the table and the full reports, including the "Checked, fine" and "Could not verify" sections.
6. **Triage** per `references/triage.md`: a verdict "accept / reject" for every finding, verified against the real code; findings shared by two or more reviewers first; disputed ones — `$R ask`.
7. **Summary for the user**: what was found, what you accept and why, what you reject and why, what you are fixing. Then the fixes, **the full test and lint run**, `$R clean RUN`.

## What separates a review from a linter

- A brief with run commands and the cost of failure. Without commands the reviewer cannot run the tests and falls back to skimming the code.
- Several model families. Findings that overlap are almost certainly real; findings that disagree are a reason to check yourself, not to pick the convenient answer.
- One protocol for everyone (`prompts/<lang>/reviewer.md`): differences between reports are explained by the model, not by the brief.
- Evidence. Every finding is tagged `ran | read | inferred`; check low-confidence `inferred` first or reject it.

## Modes and options

- `--mode diff` (default): changes against `--base` (auto: merge-base with main/master).
- `--mode repo`: audit of the whole repository by the priorities from the brief.
- `--mode plan --plan FILE`: review of a document; the repository is available to check the plan's assumptions against code. For a plan without a repository — `bin/bundle.py` (one request, no agent).
- `--lang en|ru`: language of the protocol and the report. Default from `REVIEW_LANG` (`$R config set REVIEW_LANG ru`).
- `--lens NAME`: narrow the axis (correctness, security, ops, tests). Useful for running one model with several lenses.
- `--blind`: hide the intent and "known decisions" from the reviewer — catches what the brief unintentionally justifies.

## Red flags — you are cutting corners

| Thought | Reality |
|---|---|
| "I'll write a two-line brief, the reviewer will figure it out" | Without run commands and the cost of failure you get a linter. Fill in every section of the template. |
| "I'll launch one reviewer, it's faster" | One report cannot be calibrated. Launch everyone available — they run in parallel. |
| "The reviewer quotes the line confidently, so it must be right" | A quote is not a correct conclusion. Verdict only after checking the code. |
| "I'll fix per the report and we're done" | Post-review fixes break neighbouring code more often than you think. The full test run is mandatory. |
| "The reviewer wrote 'ready', we can deploy" | Its verdict is an input to your decision. Read the "Could not verify" section. |
| "Ten minutes without an answer — it hung" | 5–40 minutes is normal. If the tool-call count in `$R status` grows, it is working. |
| "I'll give an interim status and continue later" | In a headless session "later" never comes. Keep calling `$R wait RUN` until the reviewers finish, and only then answer. |
| "I'll reject it, I intended it differently" | Reject only with a check against the code and a one-line "why". Disagreement with the intent is not an argument. |

## Files

- `bin/review` — CLI; `bin/backends/*.sh` — one per reviewer; `bin/lib/` — snapshot, background launch, output parsing, defaults.
- `prompts/<lang>/reviewer.md` — the review protocol (shared by all reviewers); `prompts/<lang>/brief.md` — brief template; `prompts/<lang>/lenses/` — lenses. Languages: `en`, `ru`.
- `references/backends.md` — verified flags and quirks of every CLI, with dates; `references/triage.md` — how to triage the reports; `references/setup.md` — keys, logins, installation, model overrides.
- `bin/bundle.py` — a single HTTP request without an agent (a plan or a diff without a repository).
- `docs/ru/` — Russian copies of this file and the references.
