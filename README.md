# external-review

**EN, TL;DR.** A harness-agnostic skill for getting a real second opinion on code or a plan from
*other* model families (GLM-5.3, Kimi K3, Grok 4.6, Codex, Claude Opus). Each reviewer runs as an
autonomous agent inside a disposable git worktree snapshot of your repo: it reads the code, runs
the tests, writes throwaway repro scripts and returns a report where every finding carries
evidence (`ran | read | inferred`). The orchestrator (Claude Code, GLM or Kimi running Claude
Code, Codex — anything with a shell) writes a brief, launches all available reviewers in parallel,
merges the reports and triages them against the real code. Docs are in Russian.

---

Скилл для **второго мнения от других моделей**. Рецензент — не линтер: он запускает тесты,
пишет одноразовые скрипты для воспроизведения гипотез и возвращает отчёт с уликами. Оркестратор
(тот, кто заказывает ревью) может быть любой моделью — скрипты требуют только bash, git и python3.

## Быстрый старт

```bash
git clone https://github.com/genhoi/external-review ~/.claude/skills/external-review
R=~/.claude/skills/external-review/bin/review
$R doctor                          # кто доступен; ключи — references/setup.md
$R brief --out /tmp/brief.md       # заполнить вводную: интент, цена ошибки, как запускать тесты
$R run --brief /tmp/brief.md       # снапшот + все доступные рецензенты в фоне
$R status                          # прогресс
$R collect                         # merged.md: таблица находок × рецензент + полные отчёты
```

Дальше — триаж по `references/triage.md`: вердикт по каждой находке с проверкой по коду.

## Рецензенты

| Рецензент | Как запускается | Что нужно |
|---|---|---|
| glm | Claude Code → z.ai, `glm-5.3[1m]`, effort max | ключ GLM Coding Plan |
| kimi | Claude Code → api.kimi.com, `k3[1m]`, effort max | ключ подписки Kimi Code |
| opus | Claude Code, `opus`, effort max | подписка Claude |
| grok | grok CLI, `grok-4.6`, effort xhigh, kernel-sandbox | подписка xAI |
| codex | codex CLI, `codex exec`, `gpt-5.6-sol`, effort xhigh, sandbox workspace-write | подписка ChatGPT |
| kimi-cli | kimi-code CLI (OAuth) | запасной путь |

## Как это устроено

- **Снапшот**: detached git worktree на временный коммит с рабочим деревом (включая
  незакоммиченное). Writable: рецензент гоняет тесты и правит ради воспроизведения, оригинал не
  трогается. Зависимости (`vendor`, `node_modules`, `.venv`, `.env*`) — симлинками.
- **Один протокол для всех** (`prompts/reviewer.md`): четыре фазы — ориентация, гипотезы,
  проверка исполнением, отчёт с уликами и журналом проверки. Различия в отчётах объясняются
  моделью, а не промптом.
- **Вводная** (`prompts/brief.md`) — главный вход: интент, цена ошибки, команды запуска, что
  недоступно, известные решения. `--blind` прячет интент от рецензента.
- **Сводка** (`review collect`): находки группируются по файлу и строке, совпавшие у нескольких
  рецензентов — первыми.

## Структура

```
SKILL.md                 инструкция оркестратору (её читает агент)
bin/review               CLI: doctor | brief | run | status | wait | collect | ask | logs | runs | clean
bin/backends/*.sh        по одному скрипту на рецензента
bin/lib/                 снапшот, запуск в фоне, разбор вывода CLI, сборка сводки
bin/bundle.py            один HTTP-запрос без агента (план без репозитория)
prompts/                 протокол ревью, шаблон вводной, линзы (correctness, security, ops, tests)
references/              backends.md (флаги и грабли CLI), triage.md, setup.md
```

## Лицензия

MIT.
