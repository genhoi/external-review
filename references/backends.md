# Бэкенды: проверенные флаги и грабли

Всё ниже проверено на реальных прогонах; дата в скобках. Перед тем как менять флаг в
`bin/backends/*.sh`, перепроверь на smoke-задании (см. «Добавляем нового рецензента»).

| Рецензент | Движок | Модель по умолчанию | Effort | Формат вывода | Сессия для `ask` |
|---|---|---|---|---|---|
| glm | `claude -p` → z.ai | `glm-5.3[1m]` (`GLM_MODEL`) | `--effort max` | stream-json | `--session-id` наш uuid → `--resume` |
| kimi | `claude -p` → api.kimi.com/coding | `k3[1m]` (`KIMI_MODEL`) | `--effort max` (= K3 max) | stream-json | как glm |
| opus | `claude -p`, подписка Claude | `opus` (`OPUS_MODEL`) | `--effort max` | stream-json | как glm |
| grok | `grok --prompt-file` | `grok-4.6` (`GROK_MODEL`) | `--effort xhigh` (максимум) | streaming-messages-json = формат claude stream-json | `-s` наш uuid → `--resume` |
| codex | `codex exec` | из `~/.codex/config.toml` (`CODEX_MODEL`) | `-c model_reasoning_effort="xhigh"` | `--json` JSONL + `-o` последнее сообщение | `thread_id` из события `thread.started` → `codex exec resume` |
| kimi-cli | `kimi -p` (OAuth) | `kimi-code/k3` (`KIMI_CLI_MODEL`) | из config.toml (`effort = "high"|"max"`) | stream-json (строки без `type`) | `session_id` из `session.resume_hint` → `-S` |

Изоляция у всех одна: detached git worktree на временный коммит с рабочим деревом
(незакоммиченное и untracked включены, .gitignore соблюдён). Снапшот writable — рецензент
может гонять тесты и править ради воспроизведения. Дополнительно там, где CLI умеет:
claude-семейство — deny-правила на запись в оригинальный репозиторий и `~/.claude` плюс запрет
`git push`; grok — kernel-sandbox `workspace` (нужен `bubblewrap`, иначе `off`);
codex — `workspace-write`. Симлинки `vendor`, `node_modules`, `.venv`, `.env*` ведут в
оригинальное дерево: рецензенту велено их не менять.

## claude-семейство (glm, kimi, opus)

- `--settings` принимает JSON только **одной строкой**: с переводами строк он считает аргумент
  путём к файлу и падает `Settings file not found` (02.09.2026).
- `--permission-mode bypassPermissions` в headless работает без дополнительных флагов не под
  root (02.09.2026). Под root нужен `--allow-dangerously-skip-permissions`.
- Промпт подаётся через stdin (`claude -p < prompt.md`) — без проблем с кавычками и длиной.
- `--output-format stream-json --verbose`: прогресс виден по ходу; финальный текст — в событии
  `result`, там же `session_id`, `num_turns`, `total_cost_usd`, `duration_ms`. Если `result`
  пуст — берём последний текст ассистента, затем `REVIEW.md` из снапшота.
- glm и kimi запускаются с отдельным `CLAUDE_CONFIG_DIR` (`~/.local/state/external-review/cfg/<имя>`):
  пользовательские настройки, плагины и хуки не грузятся, сессии рецензентов лежат отдельно.
- opus использует обычный `~/.claude` (OAuth), но с `--setting-sources project,local`, чтобы не
  тянуть пользовательские плагины и модель по умолчанию.
- z.ai: суффикс `[1m]` работает только через Claude Code (`ANTHROPIC_MODEL`), на сыром API
  валидны `glm-5.3` / `glm-5.2` без суффикса (26.08.2026). Бывают обрывы
  `API Error: Connection closed mid-response` — перезапусти рецензента. В stderr
  `[claude-code:unrecognized_model] ... generate_session_title` — не ошибка.
- Kimi Code: ключ из kimi.com/code/console (подписка), не platform.moonshot.ai (per-token).
  Переменная — `ANTHROPIC_API_KEY`; остаток `ANTHROPIC_AUTH_TOKEN` в окружении ломает
  соединение, поэтому бэкенд его `unset`. Effort: `xhigh|max` → K3 `max`. Thinking не выключать —
  без него запрос уходит на K2.6.

## grok

- Headless: `-p/--single` или `--prompt-file`; `--cwd` вместо `cd`; `--effort` — алиас
  `--reasoning-effort`, максимум `xhigh` (`max` нет).
- `--output-format`: `plain | json | streaming-json | streaming-messages-json`. Значение `text`
  невалидно. `streaming-messages-json` — по факту формат claude stream-json (`system/init`,
  `assistant`, `user`, `result`), поэтому парсится тем же кодом (02.09.2026).
- `--sandbox workspace|read-only|strict` на Linux требуют `bubblewrap`: без него grok
  отказывается стартовать (`bwrap exec failed`). Бэкенд автоматически ставит `off` и пишет
  предупреждение в stderr. `sudo apt install -y bubblewrap` включает kernel-sandbox.
- `-s <uuid>` задаёт id сессии заранее — он же в `system/init`; `--resume <uuid>` продолжает.
- В `plain` вывод попадают промежуточные реплики агента перед отчётом — не используем.

## codex

- `codex exec [PROMPT|-]`: `-` читает промпт из stdin. `-C DIR` — рабочий каталог,
  `--skip-git-repo-check` — не ругаться на detached worktree.
- Sandbox: `-s read-only | workspace-write | danger-full-access`; в `workspace-write` сеть
  выключена по умолчанию — включаем `-c sandbox_workspace_write.network_access=true`.
  `-c approval_policy="never"` — иначе может зависнуть в ожидании апрува. На WSL2 (ядро 6.6)
  sandbox работает: pytest и apply_patch прошли (02.09.2026). Если sandbox не стартует —
  `CODEX_NO_SANDBOX=1` переключает на `--dangerously-bypass-approvals-and-sandbox`.
- `--json` — JSONL событий (`thread.started`, `item.completed` с `agent_message` /
  `command_execution` / `file_change`, `turn.completed`); `-o FILE` — последнее сообщение
  агента целиком. Отчёт берём из `-o`, прогресс из JSONL.
- Effort: `-c model_reasoning_effort="xhigh"` (значения minimal…xhigh).
- Логин: `codex login` (браузер) или `codex login --device-auth`; `codex login status` — проверка.
- `codex exec review --uncommitted|--base REF|--commit SHA` — встроенное ревью с собственным
  промптом; для единообразия отчётов используем обычный `exec` с нашим протоколом.

## kimi-cli

- `-p` несовместим с `--plan` и с `--auto` (`Cannot combine --prompt with ...`). В print-режиме
  апрувы не запрашиваются: агент ходит с полными инструментами (02.09.2026).
- `--output-format stream-json`: строки `{"role":"assistant","content":"...","tool_calls":[...]}`
  без поля `type`; мета-события `{"role":"meta","type":"session.resume_hint","session_id":...}`.
- Effort только через `~/.kimi-code/config.toml` (`[thinking] effort = "max"`); флага нет.
- OAuth протухает раз в несколько дней → `kimi login`. Поэтому основной путь для Kimi —
  бэкенд `kimi` через Claude Code с API-ключом подписки.

## Если нужна жёсткая изоляция: docker

Когда рецензенту нельзя давать хостовые сервисы, claude-семейство запускается в контейнере
поверх `:ro`-монтирования снапшота (проверено 26.08.2026):
```bash
docker run --rm -v "$SNAP:/work:ro" -v "$PWD/vendor:/work/vendor:ro" -v prompt.md:/prompt.md:ro \
  -e ANTHROPIC_BASE_URL=... -e ANTHROPIC_AUTH_TOKEN=... -e ANTHROPIC_MODEL='glm-5.3[1m]' \
  -w /work node:24 sh -lc 'npm i -g @anthropic-ai/claude-code >/dev/null 2>&1 && claude -p "$(cat /prompt.md)" --permission-mode plan --effort max --output-format stream-json --verbose'
```
Точка монтирования `vendor` внутри `:ro`-корня должна существовать в снапшоте заранее
(`mkdir -p "$SNAP/vendor"`). Тесты в таком режиме рецензент запустить не сможет.

## Добавляем нового рецензента

Скрипт `bin/backends/<имя>.sh` с командами `run` (stdout = сырой лог), `ask "текст"`,
`format` (имя парсера из `bin/lib/extract.py`), `check` (exit 0 + строка статуса).
Перед включением проверь и запиши сюда с датой:
1. headless-флаг и как подать длинный промпт (stdin / файл / аргумент);
2. формат вывода: что печатается — только финальное сообщение или все; где session id;
3. когда появляется вывод: потоково или целиком в конце;
4. как называется effort и какое значение максимальное;
5. может ли писать в файлы и есть ли kernel-sandbox; чем ограничить запись вне снапшота;
6. где креды и переживут ли они отдельный config dir.
Затем smoke-задание (`review run --prompt-file smoke.md`), потом прогон на фикстуре с
известными дефектами — так видно, галлюцинирует ли рецензент.
