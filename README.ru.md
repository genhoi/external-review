<p align="center">
  <img src="docs/assets/hero.png" alt="Пять рецензентов изучают один лист кода" width="100%">
</p>

# external-review

**Второе мнение о вашем коде от других семейств моделей.** Рецензенты (GLM, Kimi, Grok, Codex,
Claude Opus) запускаются как автономные агенты в одноразовом снапшоте репозитория: читают код,
гоняют ваши тесты, пишут одноразовые скрипты для воспроизведения гипотез и возвращают отчёт, где у
каждой находки есть улика. Вы пишете вводную, запускаете всех параллельно, собираете отчёты и
разбираете их, сверяясь с реальным кодом.

<p>
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/license-MIT-1b2a41?style=flat-square"></a>
  <img alt="нужны bash, git, python3" src="https://img.shields.io/badge/requires-bash%20%C2%B7%20git%20%C2%B7%20python3-1b2a41?style=flat-square">
  <img alt="Claude Code skill" src="https://img.shields.io/badge/Claude%20Code-skill-e5674f?style=flat-square">
  <img alt="рецензенты" src="https://img.shields.io/badge/reviewers-GLM%20%C2%B7%20Kimi%20%C2%B7%20Grok%20%C2%B7%20Codex%20%C2%B7%20Opus-1b2a41?style=flat-square">
  <a href="https://github.com/genhoi/external-review/actions/workflows/ci.yml"><img alt="ci" src="https://github.com/genhoi/external-review/actions/workflows/ci.yml/badge.svg"></a>
  <a href="README.md"><img alt="English" src="https://img.shields.io/badge/docs-English-5c6b7c?style=flat-square"></a>
</p>

## Зачем

- **Разные приоры.** Модель, которая ревьюит код своего же семейства, рационализирует так же, как
  автор. GLM, Kimi, Grok и Codex пропускают разное: совпавшие находки почти наверняка реальны,
  расхождения — именно то место, куда стоит посмотреть самому.
- **Рецензенты исполняют, а не читают по диагонали.** Каждый работает в writable-снапшоте (git
  worktree) с симлинками на зависимости: прогоняет тесты, пишет репро, применяет фикс и откатывает.
  Находка без триггера и улики в отчёт не попадает.
- **Не зависит от оркестратора.** Заказывать ревью может Claude Code, или GLM/Kimi внутри Claude
  Code, когда лимиты Claude кончились, или Codex — всё, у чего есть shell. Скриптам нужны только
  `bash`, `git` и `python3`.

## Быстрый старт

```bash
git clone https://github.com/genhoi/external-review ~/.claude/skills/external-review
R=~/.claude/skills/external-review/bin/review

$R config set REVIEW_LANG ru     # протокол и отчёты на русском (по умолчанию en)
$R doctor                        # кто доступен (ключи и логины: references/setup.md)
$R brief --out /tmp/brief.md     # заполнить: интент, цена ошибки, как запускать тесты
$R run --brief /tmp/brief.md     # снапшот + все доступные рецензенты в фоне
$R wait                          # ...или заниматься своим делом и смотреть `$R status`
$R collect                       # merged.md: таблица находок × рецензент + полные отчёты
```

Дальше — триаж по [`docs/ru/references/triage.md`](docs/ru/references/triage.md): вердикт по каждой
находке с проверкой по коду. В Claude Code скилл срабатывает на «внешнее ревью», «второе мнение»,
«прогони через GLM/Grok/Codex».

## Как это устроено

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/flow-dark.svg">
  <img alt="repo → snapshot → рецензенты параллельно → merged.md → триаж" src="docs/assets/flow-light.svg" width="100%">
</picture>

1. **Снапшот.** `review run` делает временный коммит рабочего дерева (включая незакоммиченное и
   untracked) и разворачивает detached worktree на каждого рецензента. `vendor`, `node_modules`,
   `.venv`, `.env*` копируются внутрь (`--deps hardlink|symlink|none` меняет режим), поэтому тесты
   идут в снапшоте даже через docker bind-mount. Рецензент может запускать и менять что угодно, ваше
   дерево не трогается. Гардрейлы там, где CLI умеет: deny-правила для claude-семейства, kernel-sandbox у
   Grok и Codex.
2. **Один протокол для всех** ([`prompts/ru/reviewer.md`](prompts/ru/reviewer.md)): ориентация →
   гипотезы под это изменение → проверка исполнением → отчёт. Каждая находка помечена
   `ran | read | inferred` и confidence; в конце разделы «проверено, в порядке», «не удалось
   проверить», журнал проверки и машинный блок.
3. **Вводная — главный вход** ([`prompts/ru/brief.md`](prompts/ru/brief.md)): интент, цена ошибки,
   точные команды тестов и что недоступно, неочевидные свойства стека, известные решения. Стабильная
   часть живёт в репозитории: секция `## External review` в `AGENTS.md` или `CLAUDE.md` подмешивается
   в каждую вводную автоматически. `--blind` прячет интент от рецензента, чтобы поймать то, что
   вводная невольно оправдывает.
4. **Сводка.** `review collect` группирует находки по файлу и строке, совпавшие у нескольких
   рецензентов — первыми. `review ask RUN glm "..."` продолжает сессию рецензента с контраргументом.
5. **Триаж** остаётся за вами: принять или отклонить каждую находку после проверки по коду,
   починить, перегнать весь набор тестов.

## Рецензенты

| Рецензент | Как запускается | Что нужно |
|---|---|---|
| `glm` | Claude Code → z.ai, `glm-5.3[1m]`, effort max | ключ GLM Coding Plan |
| `kimi` | Claude Code → api.kimi.com, `k3[1m]`, effort max | ключ подписки Kimi Code |
| `opus` | Claude Code, `opus`, effort max | подписка Claude |
| `grok` | grok CLI, `grok-4.6`, effort xhigh, kernel-sandbox | подписка xAI |
| `codex` | codex CLI, `codex exec`, `gpt-5.6-sol`, effort xhigh, sandbox workspace-write | подписка ChatGPT |
| `kimi-cli` | kimi-code CLI (OAuth) | запасной путь |

Модели не зашиты в скрипты: `review config set CODEX_MODEL gpt-5.7-sol` пишет
`~/.config/external-review/config.env`, который переживает обновления скилла.

## Как выглядит отчёт

Фрагмент отчёта GLM-5.3 по тестовому фикстуру (`tests/make-fixture.sh`, 5м22с, 31 вызов инструментов). Каждая находка воспроизведена запуском кода в снапшоте:

```markdown
## Резюме
Интент понят так: (1) дедупликация повторных доставок вебхуков PayGate, (2) проверка активности подписки `is_active`, (3) валидация процента скидки; поведение при первом успешном событии не меняется.
Вердикт: **не готово**. Главная претензия ветки — дедупликация — не работает: ключ построен на `event['id']`, который по контракту провайдера (docs/provider.md:4-5) при повторной доставке всегда новый, поэтому ретрай дважды начисляет деньги (воспроизведено, баланс 200.00 вместо 100.00).
Топ-3 must-fix: №1 дедупликация по `payment_id`; №3 `is_active` гасит подписку за 5 часов до конца на серверах Asia/Almaty; №4 округление HALF_EVEN вместо half-up из docs/invoicing.md.

## Находки

### 1. [critical] [confidence 95] billing/webhooks.py:13 — дедупликация ключуется по `id`, который при повторной доставке всегда новый → двойное начисление
- Что ломается: провайдер доставляет событие повторно (at-least-once, в течение 24 ч) с **новым `id`**, стабильный идентификатор — `payment_id` (docs/provider.md:4-5). Ключ `f"{event['type']}:{event['id']}"` для ретрая никогда не совпадает с ключом первой доставки, `is_processed` возвращает False, и `store.credit()` выполняется второй раз. Заявленное в README «дедупликация повторных вебхуков» не выполняется; защита распространилась только на случай «точная копия события с тем же id», которого по контракту не бывает.
- Улика (ran): `.venv/bin/python repro_dedupe.py` → `first applied=True, retry applied=True`, `balance pay_42 = 200.00 (ожидалось 100.00)`, `processed_count = 2`.
- Чем грозит: прямая потеря денег — дважды начисленный платёж клиенту; именно сценарий из вводной.
- Как чинить: ключовать по стабильному полю: `dedupe_key = f"{event['type']}:{event['payment_id']}"`. Проверено в снапшоте: ретрай возвращает False, баланс 100.00, все 4 теста `tests/test_webhooks.py` остаются зелёными.
- Как проверить починку: `.venv/bin/pytest -q tests/test_webhooks.py` + добавить в тест `assert store.payments["pay_1"] == Decimal("100.00")` после двух доставок.

…

## Журнал проверки
| Гипотеза | Как проверял | Результат |
|---|---|---|
| Ретрай с новым `id` дважды начисляет (docs/provider.md:4-5) | `repro_dedupe.py` | подтверждена |
| Новый тест зелёный на сломанном коде | suite + демо в `repro_race.py` | подтверждена |
| `is_active` смешивает UTC и локальное время (сдвиг 5ч) | `repro_tz.py` в TZ=Asia/Almaty и TZ=UTC | подтверждена |
…
```

## Работает из любого оркестратора

Скилл проверен от начала до конца свежим Claude-субагентом и **GLM-5.3 в headless-режиме внутри
Claude Code** в роли оркестратора (см. [`tests/results.md`](tests/results.md)). Чтобы другие CLI видели
тот же скилл:

```bash
ln -sfn ~/.claude/skills/external-review ~/.agents/skills/external-review   # kimi, codex, gemini, copilot
ln -sfn ~/.claude/skills/external-review ~/.grok/skills/external-review     # grok
```

## Настройка

```bash
review config                          # эффективные модели, effort, язык, файл переопределений
review config set REVIEW_LANG ru       # язык протокола и отчёта: en (по умолчанию) | ru
review config set CODEX_MODEL gpt-5.7-sol
CODEX_MODEL=gpt-5.7-sol review run ... # на один запуск
```

Приоритет: переменная окружения → `~/.config/external-review/config.env` → дефолты в
`bin/lib/defaults.sh`.

## Документация

| Документ | Что внутри |
|---|---|
| [`SKILL.md`](SKILL.md) · [рус.](docs/ru/SKILL.md) | инструкция оркестратору — то, что читает агент |
| [`references/setup.md`](references/setup.md) · [рус.](docs/ru/references/setup.md) | установка CLI, ключи и логины, смена моделей |
| [`references/backends.md`](references/backends.md) · [рус.](docs/ru/references/backends.md) | проверенные флаги и грабли каждого CLI, с датами |
| [`references/triage.md`](references/triage.md) · [рус.](docs/ru/references/triage.md) | как превратить N отчётов в принятые правки |
| [`tests/README.md`](tests/README.md) · [рус.](docs/ru/tests-README.md) | фикстур с заложенными дефектами для проверки рецензента или модели |

## Профиль проекта

То, что во вводной не меняется от прогона к прогону, кладётся в репозиторий, и `review brief` это
подхватывает:

```markdown
## External review
- Тесты: `docker compose run --rm -v $PWD:/app app vendor/bin/phpunit` (монтировать снапшот, а не основной checkout)
- Нет на стенде: песочница платёжного провайдера, read-реплика
- Известные решения: outbox опрашивается поллингом, не LISTEN/NOTIFY — так задумано
```

## Проверено на фикстуре

[`tests/make-fixture.sh`](tests/make-fixture.sh) собирает мини-сервис биллинга с четырьмя заложенными
дефектами, которые линтер не видит (ключ дедупликации, ломающийся на ретраях провайдера, смешение
UTC и локального времени, пустой тест, банковское округление вместо задокументированного half-up), и
одной приманкой. Все шесть рецензентов нашли дефекты с `ran`-уликами, приманку не тронул никто.
Тайминги, число вызовов инструментов и расхождения — в [`tests/results.md`](tests/results.md)
([рус.](docs/ru/tests-results.md)). `tests/ci.sh` гоняет тот же фикстур сквозным прогоном со
stub-рецензентом без ключей — это и выполняет GitHub Actions.

## Структура

```
SKILL.md                 инструкция оркестратору (её читает агент)
bin/review               CLI: doctor | config | brief | run | status | wait | collect | ask | logs | runs | clean
bin/backends/*.sh        по одному скрипту на рецензента
bin/lib/                 снапшот, запуск в фоне, разбор вывода, дефолты
bin/bundle.py            один HTTP-запрос без агента (план без репозитория)
prompts/en, prompts/ru   протокол ревью, шаблон вводной, линзы (correctness, security, ops, tests)
references/              setup, backends, triage
tests/                   генератор фикстура, вводные, результаты
docs/ru/                 русские копии
```

## Лицензия

MIT.
