# Установка и ключи

Скилл — каталог `external-review/`. Скрипты требуют только `bash`, `git`, `python3` (3.10+),
`timeout` (coreutils). Рецензенты — по желанию, работает и с одним; чем больше семейств
моделей, тем полезнее пересечение отчётов.

## 1. Положить скилл

```bash
git clone https://github.com/genhoi/external-review ~/.claude/skills/external-review
```
Чтобы тот же скилл видели другие агенты-оркестраторы:
```bash
mkdir -p ~/.agents/skills ~/.grok/skills
ln -sfn ~/.claude/skills/external-review ~/.agents/skills/external-review   # kimi, codex, gemini, copilot
ln -sfn ~/.claude/skills/external-review ~/.grok/skills/external-review     # grok
```
Удобный алиас: `ln -sfn ~/.claude/skills/external-review/bin/review ~/.local/bin/external-review`.

## 2. Ключи и логины рецензентов

| Рецензент | Что нужно | Где взять |
|---|---|---|
| glm | `~/.claude/zai_api_key` (одна строка) или `ZAI_API_KEY` | z.ai, GLM Coding Plan |
| kimi | `~/.claude/kimi_api_key` или `KIMI_API_KEY` | kimi.com/code/console → Create API Key (подписка Kimi Code) |
| opus | обычный логин Claude Code (`claude auth login`) | подписка Claude |
| grok | grok CLI + вход через OAuth (`grok`, затем `/login`) | подписка xAI |
| codex | codex CLI + `codex login` или `codex login --device-auth` | подписка ChatGPT Plus/Pro |
| kimi-cli | kimi-code CLI + `kimi login` | подписка Kimi Code (OAuth протухает — это запасной путь) |

Файлы ключей: `printf '%s' 'КЛЮЧ' > ~/.claude/kimi_api_key && chmod 600 ~/.claude/kimi_api_key`.

Установка CLI без node: `claude` — официальный установщик Anthropic; `codex` —
`curl -fsSL https://chatgpt.com/codex/install.sh | sh` (ставит бинарь в `~/.local/bin`);
`grok` и `kimi` — их установщики. Проверка: `bin/review doctor`.

## 3. Опционально

- `sudo apt install -y bubblewrap` — включает kernel-sandbox для grok (`--sandbox workspace`).
- Для Kimi через kimi-cli с максимальным effort: в `~/.kimi-code/config.toml` `[thinking] effort = "max"`.

## Смена модели или effort

Дефолты лежат в одном месте — `bin/lib/defaults.sh`. Менять сам скилл не нужно:
```bash
review config                                # эффективные значения и путь к файлу переопределений
review config set CODEX_MODEL gpt-5.7-sol    # навсегда: ~/.config/external-review/config.env
CODEX_MODEL=gpt-5.7-sol review run ...       # на один запуск
```
Приоритет: переменная окружения → `config.env` → дефолт скилла. Файл переживает `git pull`
скилла. Где смотреть новые id: codex — `/model` в TUI или `~/.codex/config.toml` после выбора;
z.ai и Kimi — их доки по Claude Code (суффикс `[1m]` только через Claude Code); grok — `grok --help`
и `~/.grok/models_cache.json`; claude — алиасы `opus`/`sonnet`/`fable` всегда указывают на последнюю.
После смены модели прогони фикстур (`tests/README.md`) — это быстрый способ увидеть, что новая
модель не галлюцинирует и держит протокол.

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `REVIEW_DEPS` | `copy` | как зависимости попадают в снапшот: `copy` (безопасно, работает с docker), `hardlink` (мгновенно; правка файла на месте изменит оригинал), `symlink` (внутри контейнера висячий), `none` |
| `REVIEW_LANG` | `en` | язык протокола и отчётов: `en` или `ru` (`review config set REVIEW_LANG ru`) |
| `EXTERNAL_REVIEW_NO_USAGE` | — | `1` выключает локальный журнал использования (`usage.jsonl`) |
| `EXTERNAL_REVIEW_REPO` | `genhoi/external-review` | куда `review feedback --issue` отправляет issue |
| `EXTERNAL_REVIEW_HOME` | `~/.local/state/external-review` | прогоны, снапшоты, config dir'ы |
| `EXTERNAL_REVIEW_TIMEOUT` | `2700` | секунд на рецензента |
| `GLM_MODEL` / `KIMI_MODEL` / `OPUS_MODEL` / `GROK_MODEL` / `CODEX_MODEL` / `KIMI_CLI_MODEL` | `review config` | модель рецензента (лучше через `review config set`) |
| `GROK_EFFORT` | `xhigh` | effort grok (максимум) |
| `CODEX_EFFORT` | `ultra` | effort codex; `ultra`/`max` есть только у `gpt-5.6-sol`/`-terra`, у моделей постарше потолок `xhigh` |
| `GROK_SANDBOX` | `workspace` при наличии bwrap, иначе `off` | профиль sandbox grok |
| `CODEX_NO_SANDBOX` | — | `1` → без sandbox codex (если не стартует в этом окружении) |
| `ZAI_BASE_URL` / `KIMI_BASE_URL` | z.ai / api.kimi.com | эндпоинты |
| `CLAUDE_BIN` / `GROK_BIN` / `CODEX_BIN` / `KIMI_BIN` | из PATH | путь к бинарю |

`bin/bundle.py` (режим без агента) настраивается через `ZAI_API_KEY`, `ZAI_MODEL`,
`ZAI_REASONING_EFFORT`, `ZAI_BASE_URL`, `ZAI_MAX_TOKENS` — см. docstring файла.
