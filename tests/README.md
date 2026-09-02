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
