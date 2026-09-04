# Проверка рецензентов на фикстуре

`make-fixture.sh DEST` создаёт мини-сервис биллинга (Python, pytest, 11 зелёных тестов) с
веткой `feature/webhook-retries`, в которой заложены дефекты, невидимые линтеру:

| # | Где | Что | Как найти |
|---|---|---|---|
| A | `billing/webhooks.py` | дедупликация по `event.id`, а `docs/provider.md` говорит: повтор приходит с новым `id`, стабилен `payment_id` → двойное начисление | прочитать контракт, воспроизвести двумя событиями |
| B | `billing/subscriptions.py` | `expires_at` (UTC, aware) сравнивается с наивным локальным `datetime.now()`; серверы в UTC+5 → подписка гаснет на 5 часов раньше | `TZ=Asia/Almaty` + репро |
| C | `tests/test_webhooks.py` | тест «не двойное начисление» проверяет `processed_count >= 1` — проходит и на сломанном коде | прочитать assert |
| D | `billing/pricing.py` | `quantize` без `rounding=` → half-even, а `docs/invoicing.md` требует half-up | `apply_discount(Decimal("4.69"), 50)` → 2.34 вместо 2.35 |
| — | `billing/refunds.py` | **приманка**: `refund()` не валидирует сумму, но единственный вызов `api.post_refund` валидирует | ожидается: не находка или `minor` «нет защиты в глубину» |

Прогон:
```bash
tests/make-fixture.sh /tmp/fixture-billing && cd /tmp/fixture-billing
R=~/.claude/skills/external-review/bin/review
$R run --reviewers glm --prompt-file ~/.claude/skills/external-review/tests/smoke-prompt.md   # 1) флаги и доступ
$R run --reviewers glm --brief ~/.claude/skills/external-review/tests/fixture-brief.md --base main   # 2) само ревью
$R wait && $R collect
```
Что смотреть в отчёте: найдены ли A–D, что с приманкой, есть ли `ran`-улики и журнал проверки,
есть ли JSON-блок в конце (иначе сводка не соберётся), сколько вызовов инструментов и минут.

Результаты 02.09.2026 (новый протокол, писать сюда при смене моделей):
см. `results.md`.

## Фикстура plan-режима

`tests/fixture-design.md` — намеренно дефектный дизайн под ту же billing-фикстуру, чтобы гонять
`--mode plan`. Он опирается на пять названных утверждений; четыре решаются по коду и докам
фикстуры, пятое — приманка.

```bash
tests/make-fixture.sh /tmp/fixture-billing && cd /tmp/fixture-billing
R=~/.claude/skills/external-review/bin/review
$R run --reviewers glm,opus --brief ~/.claude/skills/external-review/tests/fixture-brief.md \
       --mode plan --plan ~/.claude/skills/external-review/tests/fixture-design.md
$R wait && $R collect
```

| Утверждение | Должно вернуться | Почему решаемо |
|---|---|---|
| C1 сравнение сроков сегодня корректно | **ломается** | дефект B: aware UTC `expires_at` против наивного локального `datetime.now()`; переиспользование тащит баг в джобу |
| C2 `event.id` стабилен между ретраями | **ломается** | `docs/provider.md` говорит, что повтор приходит с новым `id`, стабилен `payment_id`; вся идемпотентность стоит на обратном |
| C3 набор тестов покрывает двойное списание | **ломается** | дефект C: тест проверяет `processed_count >= 1` и проходит на сломанном коде |
| C4 `apply_discount` округляет по докам | **ломается** | дефект D: `quantize` без `rounding=` — half-even, доки требуют half-up |
| C5 `refund()` небезопасен для нового вызывающего | держится, либо `minor` | приманка: единственный текущий вызывающий валидирует, но дизайн правда добавляет второго |

На что смотреть: есть ли в `merged.md` таблица `## Утверждения плана` с колонкой на рецензента;
уезжают ли расхождения наверх; попало ли каждое «ломается» ещё и в `## Находки` с записью или
входом; стоят ли теги `ran`/`read`, а не `inferred` (рецензент со снапшотом может прочитать
`docs/provider.md` и выполнить `apply_discount` — `inferred` на C2 или C4 значит, что работа не сделана).
