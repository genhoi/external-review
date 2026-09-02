# Backends: verified flags and pitfalls

Everything below has been verified on real runs; the date is in parentheses. Before changing a flag in
`bin/backends/*.sh`, re-verify it on a smoke task (see "Adding a new reviewer").

| Reviewer | Engine | Default model | Effort | Output format | Session for `ask` |
|---|---|---|---|---|---|
| glm | `claude -p` → z.ai | `glm-5.3[1m]` (`GLM_MODEL`) | `--effort max` | stream-json | `--session-id` our uuid → `--resume` |
| kimi | `claude -p` → api.kimi.com/coding | `k3[1m]` (`KIMI_MODEL`) | `--effort max` (= K3 max) | stream-json | same as glm |
| opus | `claude -p`, Claude subscription | `opus` (`OPUS_MODEL`) | `--effort max` | stream-json | same as glm |
| grok | `grok --prompt-file` | `grok-4.6` (`GROK_MODEL`) | `--effort xhigh` (maximum) | streaming-messages-json = claude stream-json format | `-s` our uuid → `--resume` |
| codex | `codex exec` | `gpt-5.6-sol` (`CODEX_MODEL`) | `-c model_reasoning_effort="ultra"` | `--json` JSONL + `-o` last message | `thread_id` from the `thread.started` event → `codex exec resume` |
| kimi-cli | `kimi -p` (OAuth) | `kimi-code/k3` (`KIMI_CLI_MODEL`) | from config.toml (`effort = "high"|"max"`) | stream-json (lines without `type`) | `session_id` from `session.resume_hint` → `-S` |

Default models and effort live in `bin/lib/defaults.sh`; override with `review config set KEY VALUE`
(file `~/.config/external-review/config.env`) or an environment variable for a single run.

Isolation is the same for all: a detached git worktree at a temporary commit of the working tree
(uncommitted and untracked files included, .gitignore respected). The snapshot is writable — the reviewer
can run tests and edit files to reproduce issues. Additionally, where the CLI supports it:
claude family — deny rules for writes to the original repository and `~/.claude`, plus `git push`
is blocked; grok — kernel sandbox `workspace` (requires `bubblewrap`, otherwise `off`);
codex — `workspace-write`. The symlinks `vendor`, `node_modules`, `.venv`, `.env*` point into the
original tree: the reviewer is instructed not to modify them.

## claude family (glm, kimi, opus)

- `--settings` accepts JSON only as a **single line**: with newlines it treats the argument as a
  file path and fails with `Settings file not found` (2026-09-02).
- `--permission-mode bypassPermissions` works headless without extra flags when not running as
  root (2026-09-02). As root you need `--allow-dangerously-skip-permissions`.
- The prompt is passed via stdin (`claude -p < prompt.md`) — no quoting or length issues.
- `--output-format stream-json --verbose`: progress is visible as it happens; the final text is in the
  `result` event, together with `session_id`, `num_turns`, `total_cost_usd`, `duration_ms`. If `result`
  is empty — take the last assistant text, then `REVIEW.md` from the snapshot.
- `review ask` for the claude family = `claude -p --resume <uuid>` in the same snapshot and environment: the reviewer
  sees its own session, can run further checks and update `REVIEW.md` (verified on glm 2026-09-02, reply in ~1 min).
- glm and kimi run with a separate `CLAUDE_CONFIG_DIR` (`~/.local/state/external-review/cfg/<name>`):
  user settings, plugins and hooks are not loaded; reviewer sessions are stored separately.
- opus uses the regular `~/.claude` (OAuth), but with `--setting-sources project,local` so it does not
  pull in user plugins and the default model.
- z.ai: the `[1m]` suffix works only through Claude Code (`ANTHROPIC_MODEL`); on the raw API,
  `glm-5.3` / `glm-5.2` without the suffix are valid (2026-08-26). Occasional disconnects
  `API Error: Connection closed mid-response` happen — restart the reviewer. In stderr,
  `[claude-code:unrecognized_model] ... generate_session_title` is not an error.
- Kimi Code: the key comes from kimi.com/code/console (subscription), not platform.moonshot.ai (per-token).
  The variable is `ANTHROPIC_API_KEY`; a leftover `ANTHROPIC_AUTH_TOKEN` in the environment breaks
  the connection, so the backend `unset`s it. Effort: `xhigh|max` → K3 `max`. Do not disable thinking —
  without it the request is routed to K2.6.

## grok

- Headless: `-p/--single` or `--prompt-file`; `--cwd` instead of `cd`; `--effort` is an alias for
  `--reasoning-effort`, maximum is `xhigh` (there is no `max`).
- `--output-format`: `plain | json | streaming-json | streaming-messages-json`. The value `text`
  is invalid. `streaming-messages-json` is in fact the claude stream-json format (`system/init`,
  `assistant`, `user`, `result`), so it is parsed by the same code (2026-09-02).
- `--sandbox workspace|read-only|strict` on Linux require `bubblewrap`: without it grok
  refuses to start (`bwrap exec failed`). The backend automatically falls back to `off` and prints a
  warning to stderr. `sudo apt install -y bubblewrap` enables the kernel sandbox.
- `-s <uuid>` sets the session id up front — the same id appears in `system/init`; `--resume <uuid>` continues it.
- `plain` output includes the agent's intermediate messages before the report — not used.

## codex

- `codex exec [PROMPT|-]`: `-` reads the prompt from stdin. `-C DIR` — working directory,
  `--skip-git-repo-check` — do not complain about the detached worktree.
- Sandbox: `-s read-only | workspace-write | danger-full-access`; in `workspace-write` the network
  is off by default — enable it with `-c sandbox_workspace_write.network_access=true`.
  `-c approval_policy="never"` — otherwise it may hang waiting for approval. On WSL2 (kernel 6.6)
  the sandbox works: pytest and apply_patch passed (2026-09-02). If the sandbox does not start —
  `CODEX_NO_SANDBOX=1` switches to `--dangerously-bypass-approvals-and-sandbox`.
- `--json` — JSONL of events (`thread.started`, `item.completed` with `agent_message` /
  `command_execution` / `file_change`, `turn.completed`); `-o FILE` — the agent's last message
  in full. The report is taken from `-o`, progress from the JSONL.
- Effort: `-c model_reasoning_effort="ultra"` (`CODEX_EFFORT`). The ladder is model-dependent —
  read it from `~/.codex/models_cache.json` (`supported_reasoning_levels`). `gpt-5.6-sol` and
  `gpt-5.6-terra`: low, medium, high, xhigh, max, **ultra** ("maximum reasoning with automatic
  task delegation"); older models stop at `xhigh` (2026-09-02). An unsupported value makes the
  run fail — lower `CODEX_EFFORT` when you switch `CODEX_MODEL`.
- Login: `codex login` (browser) or `codex login --device-auth`; `codex login status` — check.
- `codex exec review --uncommitted|--base REF|--commit SHA` — built-in review with its own
  prompt; for uniform reports we use plain `exec` with our protocol.

## kimi-cli

- `-p` is incompatible with `--plan` and `--auto` (`Cannot combine --prompt with ...`). In print mode
  no approvals are requested: the agent runs with the full toolset (2026-09-02).
- `--output-format stream-json`: lines `{"role":"assistant","content":"...","tool_calls":[...]}`
  without a `type` field; meta events `{"role":"meta","type":"session.resume_hint","session_id":...}`.
- Effort only via `~/.kimi-code/config.toml` (`[thinking] effort = "max"`); there is no flag.
- OAuth expires every few days → `kimi login`. That is why the primary path for Kimi is the
  `kimi` backend through Claude Code with the subscription API key.

## If hard isolation is needed: docker

When the reviewer must not get access to host services, the claude family runs in a container
over a `:ro` mount of the snapshot (verified 2026-08-26):
```bash
docker run --rm -v "$SNAP:/work:ro" -v "$PWD/vendor:/work/vendor:ro" -v prompt.md:/prompt.md:ro \
  -e ANTHROPIC_BASE_URL=... -e ANTHROPIC_AUTH_TOKEN=... -e ANTHROPIC_MODEL='glm-5.3[1m]' \
  -w /work node:24 sh -lc 'npm i -g @anthropic-ai/claude-code >/dev/null 2>&1 && claude -p "$(cat /prompt.md)" --permission-mode plan --effort max --output-format stream-json --verbose'
```
The `vendor` mount point inside the `:ro` root must already exist in the snapshot
(`mkdir -p "$SNAP/vendor"`). In this mode the reviewer cannot run tests.

## Adding a new reviewer

A script `bin/backends/<name>.sh` with the commands `run` (stdout = raw log), `ask "text"`,
`format` (parser name from `bin/lib/extract.py`), `check` (exit 0 + a status line).
Before enabling it, verify and record here with a date:
1. the headless flag and how to pass a long prompt (stdin / file / argument);
2. output format: what is printed — only the final message or all of them; where the session id is;
3. when output appears: streamed or all at once at the end;
4. what effort is called and what its maximum value is;
5. whether it can write files and whether there is a kernel sandbox; how to restrict writes outside the snapshot;
6. where the credentials live and whether they survive a separate config dir.
Then a smoke task (`review run --prompt-file smoke.md`), then a run on a fixture with
known defects — that shows whether the reviewer hallucinates.
