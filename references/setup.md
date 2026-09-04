# Installation and keys

The skill is the `external-review/` directory. The scripts require only `bash`, `git`, `python3` (3.10+),
`timeout` (coreutils). Reviewers are optional — it works with just one; the more model
families, the more useful the overlap between reports.

## 1. Install the skill

```bash
git clone https://github.com/genhoi/external-review ~/.claude/skills/external-review
```
So that other orchestrator agents see the same skill:
```bash
mkdir -p ~/.agents/skills ~/.grok/skills
ln -sfn ~/.claude/skills/external-review ~/.agents/skills/external-review   # kimi, codex, gemini, copilot
ln -sfn ~/.claude/skills/external-review ~/.grok/skills/external-review     # grok
```
A convenient alias: `ln -sfn ~/.claude/skills/external-review/bin/review ~/.local/bin/external-review`.

## 2. Reviewer keys and logins

| Reviewer | What is needed | Where to get it |
|---|---|---|
| glm | `~/.claude/zai_api_key` (single line) or `ZAI_API_KEY` | z.ai, GLM Coding Plan |
| kimi | `~/.claude/kimi_api_key` or `KIMI_API_KEY` | kimi.com/code/console → Create API Key (Kimi Code subscription) |
| opus | regular Claude Code login (`claude auth login`) | Claude subscription |
| grok | grok CLI + OAuth login (`grok`, then `/login`) | xAI subscription |
| codex | codex CLI + `codex login` or `codex login --device-auth` | ChatGPT Plus/Pro subscription |
| kimi-cli | kimi-code CLI + `kimi login` | Kimi Code subscription (OAuth expires — this is the fallback path) |

Key files: `printf '%s' 'KEY' > ~/.claude/kimi_api_key && chmod 600 ~/.claude/kimi_api_key`.

Installing the CLIs without node: `claude` — Anthropic's official installer; `codex` —
`curl -fsSL https://chatgpt.com/codex/install.sh | sh` (puts the binary in `~/.local/bin`);
`grok` and `kimi` — their own installers. Check: `bin/review doctor`.

## 3. Optional

- `sudo apt install -y bubblewrap` — enables the kernel sandbox for grok (`--sandbox workspace`).
- For Kimi via kimi-cli with maximum effort: `[thinking] effort = "max"` in `~/.kimi-code/config.toml`.

## Changing the model or effort

Defaults live in one place — `bin/lib/defaults.sh`. There is no need to modify the skill itself:
```bash
review config                                # effective values and the path to the overrides file
review config set CODEX_MODEL gpt-5.7-sol    # permanent: ~/.config/external-review/config.env
CODEX_MODEL=gpt-5.7-sol review run ...       # for a single run
```
Precedence: environment variable → `config.env` → skill default. The file survives a `git pull`
of the skill. Where to find new ids: codex — `/model` in the TUI or `~/.codex/config.toml` after selecting one;
z.ai and Kimi — their Claude Code docs (the `[1m]` suffix only through Claude Code); grok — `grok --help`
and `~/.grok/models_cache.json`; claude — the `opus`/`sonnet`/`fable` aliases always point to the latest.
After changing a model, run the fixtures (`tests/README.md`) — a quick way to see that the new
model does not hallucinate and follows the protocol.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `REVIEW_DEPS` | `copy` | how ignored dependencies get into the snapshot: `copy` (safe, docker-friendly), `hardlink` (instant; an in-place edit changes the original), `symlink` (dangling inside containers), `none` |
| `REVIEW_LANG` | `en` | language of the protocol and reports: `en` or `ru` (`review config set REVIEW_LANG ru`) |
| `EXTERNAL_REVIEW_NO_USAGE` | — | `1` disables the local usage journal (`usage.jsonl`) |
| `EXTERNAL_REVIEW_REPO` | `genhoi/external-review` | where `review feedback --issue` posts |
| `EXTERNAL_REVIEW_HOME` | `~/.local/state/external-review` | runs, snapshots, config dirs |
| `EXTERNAL_REVIEW_TIMEOUT` | `5400` | seconds per reviewer (a kill before the report is written loses the run) |
| `GLM_MODEL` / `KIMI_MODEL` / `OPUS_MODEL` / `GROK_MODEL` / `CODEX_MODEL` / `KIMI_CLI_MODEL` | `review config` | reviewer model (prefer `review config set`) |
| `GROK_EFFORT` | `xhigh` | grok effort (maximum) |
| `CODEX_EFFORT` | `ultra` | codex effort; `ultra`/`max` exist only on `gpt-5.6-sol`/`-terra`, older models cap at `xhigh` |
| `GROK_SANDBOX` | `workspace` if bwrap is present, otherwise `off` | grok sandbox profile |
| `CODEX_NO_SANDBOX` | — | `1` → codex without sandbox (if it does not start in this environment) |
| `ZAI_BASE_URL` / `KIMI_BASE_URL` | z.ai / api.kimi.com | endpoints |
| `CLAUDE_BIN` / `GROK_BIN` / `CODEX_BIN` / `KIMI_BIN` | from PATH | path to the binary |

`bin/bundle.py` (agentless mode) is configured via `ZAI_API_KEY`, `ZAI_MODEL`,
`ZAI_REASONING_EFFORT`, `ZAI_BASE_URL`, `ZAI_MAX_TOKENS` — see the file's docstring.
