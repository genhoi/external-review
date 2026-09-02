<p align="center">
  <img src="docs/assets/hero.png" alt="Five reviewers examining the same sheet of code" width="100%">
</p>

# external-review

**A second opinion on your code from other model families.** Reviewers (GLM, Kimi, Grok, Codex,
Claude Opus) run as autonomous agents inside a disposable snapshot of your repository: they read the
code, run your tests, write throwaway scripts to reproduce hypotheses, and return a report where every
finding carries evidence. You write a brief, launch everyone in parallel, merge the reports and triage
them against the real code.

<p>
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/license-MIT-1b2a41?style=flat-square"></a>
  <img alt="requires bash, git, python3" src="https://img.shields.io/badge/requires-bash%20%C2%B7%20git%20%C2%B7%20python3-1b2a41?style=flat-square">
  <img alt="Claude Code skill" src="https://img.shields.io/badge/Claude%20Code-skill-e5674f?style=flat-square">
  <img alt="reviewers" src="https://img.shields.io/badge/reviewers-GLM%20%C2%B7%20Kimi%20%C2%B7%20Grok%20%C2%B7%20Codex%20%C2%B7%20Opus-1b2a41?style=flat-square">
  <a href="README.ru.md"><img alt="Русская версия" src="https://img.shields.io/badge/docs-%D0%A0%D1%83%D1%81%D1%81%D0%BA%D0%B8%D0%B9-5c6b7c?style=flat-square"></a>
</p>

## Why

- **Different priors.** A model reviewing code written by its own family rationalizes the same way the
  author did. GLM, Kimi, Grok and Codex miss different things; findings they agree on are almost
  certainly real, findings they disagree on are exactly where you should look yourself.
- **Reviewers execute, not skim.** Each one works in a writable git worktree snapshot with your
  dependencies symlinked in: it runs the test suite, writes a repro, applies a candidate fix and
  reverts it. A finding without a trigger and evidence does not make it into the report.
- **Harness-agnostic.** The orchestrator can be Claude Code, or GLM/Kimi running inside Claude Code
  when your Claude quota is gone, or Codex — anything with a shell. The scripts need only `bash`,
  `git` and `python3`.

## Quick start

```bash
git clone https://github.com/genhoi/external-review ~/.claude/skills/external-review
R=~/.claude/skills/external-review/bin/review

$R doctor                        # which reviewers are available (keys/logins: references/setup.md)
$R brief --out /tmp/brief.md     # fill it in: intent, cost of failure, how to run the tests
$R run --brief /tmp/brief.md     # snapshot + every available reviewer, in the background
$R wait                          # ...or keep working and check `$R status` now and then
$R collect                       # merged.md: findings table × reviewer + full reports
```

Then triage per [`references/triage.md`](references/triage.md): a verdict for every finding, verified
against the code. Inside Claude Code the skill triggers on "get a second opinion from other models",
"external review", "run it through GLM/Grok/Codex".

## How it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/flow-dark.svg">
  <img alt="repo → snapshot → reviewers in parallel → merged.md → triage" src="docs/assets/flow-light.svg" width="100%">
</picture>

1. **Snapshot.** `review run` commits your working tree (uncommitted and untracked files included) to a
   temporary commit and checks it out as a detached worktree per reviewer. `vendor`, `node_modules`,
   `.venv`, `.env*` are symlinked in. The reviewer can run and modify anything there; your tree is
   never touched. Guardrails where the CLI supports them: deny rules for the Claude family, kernel
   sandbox for Grok and Codex.
2. **One protocol for everyone** ([`prompts/en/reviewer.md`](prompts/en/reviewer.md)): orientation →
   hypotheses specific to this change → verification by execution → report. Every finding is tagged
   `ran | read | inferred` with a confidence score; the report ends with a "Checked, fine" section, a
   "Could not verify" section, a verification log and a machine-readable block.
3. **The brief is the main input** ([`prompts/en/brief.md`](prompts/en/brief.md)): intent, cost of
   failure, exact test commands and what is unavailable, non-obvious stack properties, known decisions.
   `--blind` hides the intent from the reviewer to catch what the brief unintentionally justifies.
4. **Merge.** `review collect` groups findings by file and line; those flagged by several reviewers
   come first. `review ask RUN glm "..."` resumes a reviewer's session with counter-evidence.
5. **Triage** stays with you: accept or reject each finding after checking the code, fix, rerun the
   full suite.

## Reviewers

| Reviewer | Runs as | Needs |
|---|---|---|
| `glm` | Claude Code → z.ai, `glm-5.3[1m]`, effort max | GLM Coding Plan key |
| `kimi` | Claude Code → api.kimi.com, `k3[1m]`, effort max | Kimi Code subscription key |
| `opus` | Claude Code, `opus`, effort max | Claude subscription |
| `grok` | grok CLI, `grok-4.6`, effort xhigh, kernel sandbox | xAI subscription |
| `codex` | codex CLI, `codex exec`, `gpt-5.6-sol`, effort xhigh, sandbox workspace-write | ChatGPT subscription |
| `kimi-cli` | kimi-code CLI (OAuth) | fallback path |

Models are not hard-coded into the scripts: `review config set CODEX_MODEL gpt-5.7-sol` writes
`~/.config/external-review/config.env`, which survives updates of the skill.

## What a report looks like

<!-- REPORT-EXCERPT -->

## Works from any orchestrator

The skill was tested end-to-end with a fresh Claude subagent and with **GLM-5.3 running headless inside
Claude Code** as the orchestrator (see [`tests/results.md`](tests/results.md)). To make other CLIs
discover the same skill:

```bash
ln -sfn ~/.claude/skills/external-review ~/.agents/skills/external-review   # kimi, codex, gemini, copilot
ln -sfn ~/.claude/skills/external-review ~/.grok/skills/external-review     # grok
```

## Configuration

```bash
review config                          # effective models, effort, language, override file
review config set REVIEW_LANG ru       # protocol and report language: en (default) | ru
review config set CODEX_MODEL gpt-5.7-sol
CODEX_MODEL=gpt-5.7-sol review run ... # one-off override
```

Precedence: environment variable → `~/.config/external-review/config.env` → defaults in
`bin/lib/defaults.sh`.

## Documentation

| Document | What is inside |
|---|---|
| [`SKILL.md`](SKILL.md) | the orchestrator's instructions — what the agent reads |
| [`references/setup.md`](references/setup.md) | installing the CLIs, keys and logins, model overrides |
| [`references/backends.md`](references/backends.md) | verified flags and quirks of every CLI, with dates |
| [`references/triage.md`](references/triage.md) | how to turn N reports into accepted fixes |
| [`tests/README.md`](tests/README.md) | a fixture with planted defects to check a new reviewer or model |
| [`docs/ru/`](docs/ru/) | Russian copies of the skill and references |

## Tested on a fixture

[`tests/make-fixture.sh`](tests/make-fixture.sh) builds a small billing service with four planted
defects a linter cannot see (a dedupe key that breaks on provider retries, a UTC/local time mix, a
vacuous test, banker's rounding against a documented half-up rule) and one decoy. All six reviewers
found the defects with `ran` evidence and none flagged the decoy. Timings, tool-call counts and the
odd disagreements are in [`tests/results.md`](tests/results.md).

## Layout

```
SKILL.md                 orchestrator instructions (read by the agent)
bin/review               CLI: doctor | config | brief | run | status | wait | collect | ask | logs | runs | clean
bin/backends/*.sh        one script per reviewer
bin/lib/                 snapshot, background launch, output parsing, defaults
bin/bundle.py            a single HTTP request without an agent (a plan without a repository)
prompts/en, prompts/ru   review protocol, brief template, lenses (correctness, security, ops, tests)
references/              setup, backends, triage
tests/                   fixture generator, briefs, results
docs/ru/                 Russian copies
```

## License

MIT.
