#!/usr/bin/env bash
# Создаёт фикстур-репозиторий billing-lite с заложенными дефектами для проверки рецензентов.
# Использование: tests/make-fixture.sh /path/to/dest   (каталог будет создан; нужны git, python3, uv или pip)
set -euo pipefail
DEST="${1:?укажи каталог назначения}"
[ ! -e "$DEST" ] || { echo "уже существует: $DEST" >&2; exit 1; }
mkdir -p "$DEST"; cd "$DEST"
git init -q -b main; git config user.email fixture@example.com; git config user.name fixture; git config core.autocrlf false
w() { mkdir -p "$(dirname "$1")"; cat > "$1"; }
# ---- main: исходная версия ----
w '.gitignore' <<'FILE'
.venv/
__pycache__/
*.pyc
.pytest_cache/
FILE
w 'README.md' <<'FILE'
# billing-lite

Мини-сервис биллинга: приём вебхуков платёжного провайдера, статус подписок, расчёт скидок.

## Запуск тестов
```
.venv/bin/pytest -q
```
(venv создаётся `uv venv .venv && uv pip install --python .venv/bin/python pytest`)
FILE
w 'billing/__init__.py' <<'FILE'
FILE
w 'billing/api.py' <<'FILE'
from decimal import Decimal

from billing.refunds import Payment, refund


def post_refund(payment: Payment, body: dict) -> dict:
    """HTTP-обработчик POST /refunds. Единственная точка входа для refund()."""
    amount = Decimal(body["amount"])
    if amount <= 0 or amount > payment.amount - payment.refunded:
        return {"error": "invalid amount"}
    remaining = refund(payment, amount)
    return {"remaining": str(remaining)}
FILE
w 'billing/pricing.py' <<'FILE'
from decimal import Decimal


def apply_discount(amount: Decimal, percent: int) -> Decimal:
    """Сумма после скидки percent%, два знака после запятой."""
    factor = Decimal(100 - percent) / Decimal(100)
    return (amount * factor).quantize(Decimal("0.01"))
FILE
w 'billing/refunds.py' <<'FILE'
from decimal import Decimal


class Payment:
    def __init__(self, payment_id: str, amount: Decimal):
        self.payment_id = payment_id
        self.amount = amount
        self.refunded = Decimal("0")


def refund(payment: Payment, amount: Decimal) -> Decimal:
    """Начисляет возврат. Валидация суммы выполняется на входе API (см. api.py)."""
    payment.refunded += amount
    return payment.amount - payment.refunded
FILE
w 'billing/store.py' <<'FILE'
class Store:
    """In-memory хранилище для тестов и локального запуска."""

    def __init__(self):
        self.processed_events = set()
        self.payments = {}
        self.processed_count = 0

    def mark_processed(self, key):
        self.processed_events.add(key)

    def is_processed(self, key):
        return key in self.processed_events

    def credit(self, payment_id, amount):
        self.payments[payment_id] = self.payments.get(payment_id, 0) + amount
        self.processed_count += 1
FILE
w 'billing/webhooks.py' <<'FILE'
from decimal import Decimal

from billing.store import Store


def handle_payment_event(event: dict, store: Store) -> bool:
    """Обрабатывает событие провайдера. Возвращает True, если событие применено."""
    if event["type"] != "payment.succeeded":
        return False
    if store.is_processed(event["id"]):
        return False
    store.credit(event["payment_id"], Decimal(event["amount"]))
    store.mark_processed(event["id"])
    return True
FILE
w 'docs/invoicing.md' <<'FILE'
# Правила расчёта сумм

- Все суммы — `Decimal` с двумя знаками.
- Округление при расчёте скидок и налогов — **арифметическое (half-up)**, как в бухгалтерии.
  Пример: 2.345 → 2.35, 2.355 → 2.36.
- Серверы работают в таймзоне Asia/Almaty (UTC+5); в БД все даты хранятся в UTC.
FILE
w 'docs/provider.md' <<'FILE'
# Платёжный провайдер PayGate: вебхуки

- Провайдер доставляет события `payment.succeeded`, `payment.failed`, `refund.succeeded`.
- Доставка at-least-once. **При повторной доставке провайдер генерирует НОВЫЙ `id` события**,
  стабильным остаётся только `payment_id` (и `type`). Повторы приходят в течение 24 часов.
- Тело события: `{"id": "evt_...", "type": "payment.succeeded", "payment_id": "pay_...", "amount": "100.00"}`.
FILE
w 'tests/__init__.py' <<'FILE'
FILE
w 'tests/test_pricing.py' <<'FILE'
from decimal import Decimal

from billing.pricing import apply_discount


def test_discount_basic():
    assert apply_discount(Decimal("100.00"), 10) == Decimal("90.00")


def test_discount_zero():
    assert apply_discount(Decimal("59.99"), 0) == Decimal("59.99")
FILE
w 'tests/test_refunds.py' <<'FILE'
from decimal import Decimal

from billing.api import post_refund
from billing.refunds import Payment


def test_refund_over_amount_rejected():
    p = Payment("pay_1", Decimal("50.00"))
    assert post_refund(p, {"amount": "60.00"}) == {"error": "invalid amount"}


def test_refund_ok():
    p = Payment("pay_1", Decimal("50.00"))
    assert post_refund(p, {"amount": "20.00"}) == {"remaining": "30.00"}
FILE
w 'tests/test_webhooks.py' <<'FILE'
from decimal import Decimal

from billing.store import Store
from billing.webhooks import handle_payment_event


def make_event(eid="evt_1", pid="pay_1", amount="100.00", etype="payment.succeeded"):
    return {"id": eid, "type": etype, "payment_id": pid, "amount": amount}


def test_success_credits_once():
    store = Store()
    assert handle_payment_event(make_event(), store) is True
    assert store.payments["pay_1"] == Decimal("100.00")


def test_duplicate_same_id_ignored():
    store = Store()
    handle_payment_event(make_event(), store)
    assert handle_payment_event(make_event(), store) is False
    assert store.payments["pay_1"] == Decimal("100.00")


def test_failed_event_not_credited():
    store = Store()
    assert handle_payment_event(make_event(etype="payment.failed"), store) is False
    assert "pay_1" not in store.payments
FILE
git add -A && git commit -qm "billing-lite: initial"
git checkout -qb feature/webhook-retries
# ---- ветка с заложенными дефектами ----
w 'billing/pricing.py' <<'FILE'
from decimal import Decimal


def apply_discount(amount: Decimal, percent: int) -> Decimal:
    """Сумма после скидки percent%, два знака после запятой (правила в docs/invoicing.md)."""
    if not 0 <= percent <= 100:
        raise ValueError("percent must be within 0..100")
    factor = Decimal(100 - percent) / Decimal(100)
    return (amount * factor).quantize(Decimal("0.01"))
FILE
w 'billing/subscriptions.py' <<'FILE'
from datetime import datetime, timezone


class Subscription:
    def __init__(self, user_id: str, expires_at: datetime):
        # expires_at хранится в БД в UTC (aware datetime)
        self.user_id = user_id
        self.expires_at = expires_at


def is_active(sub: Subscription, now: datetime | None = None) -> bool:
    """Подписка активна, пока не наступил момент expires_at."""
    if now is None:
        now = datetime.now()
    return sub.expires_at.replace(tzinfo=None) > now


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
FILE
w 'billing/webhooks.py' <<'FILE'
from decimal import Decimal

from billing.store import Store


def handle_payment_event(event: dict, store: Store) -> bool:
    """Обрабатывает событие провайдера с учётом повторных доставок (см. docs/provider.md).

    Возвращает True, если событие применено.
    """
    if event["type"] != "payment.succeeded":
        return False
    dedupe_key = f"{event['type']}:{event['id']}"
    if store.is_processed(dedupe_key):
        return False
    store.credit(event["payment_id"], Decimal(event["amount"]))
    store.mark_processed(dedupe_key)
    return True
FILE
w 'tests/test_pricing.py' <<'FILE'
from decimal import Decimal

from billing.pricing import apply_discount


def test_discount_basic():
    assert apply_discount(Decimal("100.00"), 10) == Decimal("90.00")


def test_discount_zero():
    assert apply_discount(Decimal("59.99"), 0) == Decimal("59.99")


def test_discount_invalid_percent():
    import pytest
    with pytest.raises(ValueError):
        apply_discount(Decimal("10.00"), 101)
FILE
w 'tests/test_subscriptions.py' <<'FILE'
from datetime import datetime, timedelta, timezone

from billing.subscriptions import Subscription, is_active


def test_active_far_future():
    sub = Subscription("u1", datetime.now(timezone.utc) + timedelta(days=30))
    assert is_active(sub)


def test_expired_far_past():
    sub = Subscription("u1", datetime.now(timezone.utc) - timedelta(days=30))
    assert not is_active(sub)
FILE
w 'tests/test_webhooks.py' <<'FILE'
from decimal import Decimal

from billing.store import Store
from billing.webhooks import handle_payment_event


def make_event(eid="evt_1", pid="pay_1", amount="100.00", etype="payment.succeeded"):
    return {"id": eid, "type": etype, "payment_id": pid, "amount": amount}


def test_success_credits_once():
    store = Store()
    assert handle_payment_event(make_event(), store) is True
    assert store.payments["pay_1"] == Decimal("100.00")


def test_duplicate_same_id_ignored():
    store = Store()
    handle_payment_event(make_event(), store)
    assert handle_payment_event(make_event(), store) is False
    assert store.payments["pay_1"] == Decimal("100.00")


def test_failed_event_not_credited():
    store = Store()
    assert handle_payment_event(make_event(etype="payment.failed"), store) is False
    assert "pay_1" not in store.payments


def test_retry_with_new_event_id_is_not_double_credited():
    """Провайдер повторяет доставку с новым id (docs/provider.md)."""
    store = Store()
    handle_payment_event(make_event(eid="evt_1"), store)
    handle_payment_event(make_event(eid="evt_2"), store)
    assert store.processed_count >= 1
FILE
git add -A && git commit -qm "webhooks: dedupe retries; subscriptions: is_active; pricing: validate percent"
# незакоммиченная правка — проверяет, что снапшот включает рабочее дерево
cat >> README.md <<'FILE'

## Изменения в ветке feature/webhook-retries
Дедупликация повторных вебхуков, проверка активности подписки, валидация процента скидки.
FILE
if command -v uv >/dev/null; then uv venv -q .venv && uv pip install -q --python .venv/bin/python pytest
else python3 -m venv .venv && .venv/bin/pip install -q pytest; fi
.venv/bin/pytest -q
echo "фикстур готов: $DEST (ветка feature/webhook-retries, база main)"
