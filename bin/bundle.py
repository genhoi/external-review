#!/usr/bin/env python3
"""bundle.py — запасной режим без агента: один HTTP-запрос с планом/диффом в GLM-5.3 через z.ai
(Anthropic-совместимый эндпоинт) и печатает текст ревью в stdout.

Зависимостей нет — только стандартная библиотека Python 3.

Использование:
    bundle.py <file> [file ...]   # ревью одного или нескольких файлов
    cat plan.md | bundle.py       # ревью из stdin

Настройка через окружение:
    ZAI_API_KEY    ключ z.ai (или положить в ~/.claude/zai_api_key)
    ZAI_MODEL      модель (по умолчанию glm-5.3; суффикс [1m] только в агентном режиме)
    ZAI_BASE_URL   база (по умолчанию https://api.z.ai/api/anthropic)
    ZAI_MAX_TOKENS лимит ответа (по умолчанию 65536: reasoning при effort=max съедает бюджет ДО текста ответа)
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("ZAI_BASE_URL", "https://api.z.ai/api/anthropic").rstrip("/")
MODEL = os.environ.get("ZAI_MODEL", "glm-5.3")
MAX_TOKENS = int(os.environ.get("ZAI_MAX_TOKENS", "65536"))
# Уровень "размышления" GLM: max|xhigh|high|medium|low|minimal|none|off (по умолчанию max).
REASONING_EFFORT = os.environ.get("ZAI_REASONING_EFFORT", "max")

SYSTEM = (
    "Ты — придирчивый staff-инженер, делаешь независимое ревью плана реализации "
    "(или дизайна/диффа) другого инженера. Отвечай по-русски. Не льсти и не пересказывай план. "
    "Ищи: логические ошибки, упущенные edge-cases, риски для прод-данных и обратной "
    "совместимости, гонки/конкурентность, проблемы производительности, неверные допущения, "
    "более простые альтернативы. Каждое замечание оформляй строкой вида: "
    "[severity: blocker|major|minor] — конкретное место в плане — в чём проблема — что предложить. "
    "В конце дай короткий вердикт в 1-2 предложениях. Если план действительно хорош — "
    "так и скажи прямо, без выдумывания проблем."
)


def get_key() -> str:
    key = os.environ.get("ZAI_API_KEY", "").strip()
    if key:
        return key
    path = os.path.expanduser("~/.claude/zai_api_key")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    return ""


def read_input(files: list[str]) -> str:
    if files:
        chunks = []
        for f in files:
            with open(f, encoding="utf-8") as fh:
                chunks.append(f"===== {f} =====\n{fh.read()}\n")
        return "\n".join(chunks)
    return sys.stdin.read()


def send(body: dict, key: str) -> tuple[str, str]:
    """Стримит ответ Anthropic-совместимого эндпоинта (SSE).

    Стриминг обязателен: при reasoning_effort=max генерация длинная, и нестримовый
    запрос рвёт шлюз по idle-таймауту (RemoteDisconnected). Возвращает (текст, stop_reason).
    Текст рассуждения (thinking) опускаем — нужен только финальный текст ревью.
    """
    req = urllib.request.Request(
        f"{BASE_URL}/v1/messages",
        data=json.dumps({**body, "stream": True}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "accept": "text/event-stream",
        },
        method="POST",
    )
    parts: list[str] = []
    stop_reason = ""
    with urllib.request.urlopen(req, timeout=600) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                ev = json.loads(payload)
            except json.JSONDecodeError:
                continue
            etype = ev.get("type")
            if etype == "content_block_delta":
                delta = ev.get("delta", {})
                if delta.get("type") == "text_delta":
                    parts.append(delta.get("text", ""))
            elif etype == "message_delta":
                stop_reason = ev.get("delta", {}).get("stop_reason") or stop_reason
            elif etype == "error":
                raise RuntimeError(ev.get("error", {}).get("message", "stream error"))
    return "".join(parts), stop_reason


def send_with_retry(body: dict, key: str, tries: int = 2) -> tuple[str, str]:
    """Обёртка с ретраем на обрыв соединения (HTTP-ошибки пробрасываем как есть)."""
    last_exc: Exception | None = None
    for attempt in range(tries):
        try:
            return send(body, key)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, OSError) as exc:  # вкл. RemoteDisconnected
            last_exc = exc
            if attempt + 1 < tries:
                print(f"WARN: обрыв соединения ({exc}), повтор...", file=sys.stderr)
    raise last_exc  # type: ignore[misc]


def main() -> None:
    key = get_key()
    if not key:
        sys.exit("ERROR: задайте ZAI_API_KEY или положите ключ в ~/.claude/zai_api_key")

    text = read_input(sys.argv[1:]).strip()
    if not text:
        sys.exit("ERROR: пустой вход — нечего ревьюить")

    body = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM,
        "messages": [
            {"role": "user", "content": "Сделай ревью следующего плана/материала:\n\n" + text}
        ],
    }
    if REASONING_EFFORT and REASONING_EFFORT.lower() not in ("off", ""):
        body["reasoning_effort"] = REASONING_EFFORT

    stop_reason = ""
    try:
        text, stop_reason = send_with_retry(body, key)
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", "replace")
        # Anthropic-совместимый эндпоинт может не принять reasoning_effort — повторяем без него
        # (у GLM effort по умолчанию = max, поэтому качество не падает).
        if exc.code == 400 and "reasoning_effort" in body and "effort" in err_body.lower():
            del body["reasoning_effort"]
            print(
                "WARN: reasoning_effort отклонён эндпоинтом, повтор без него (дефолт GLM = max)",
                file=sys.stderr,
            )
            try:
                text, stop_reason = send_with_retry(body, key)
            except (urllib.error.URLError, OSError) as exc2:
                sys.exit(f"ERROR: повтор не удался: {exc2}")
        else:
            sys.exit(f"ERROR: HTTP {exc.code} от z.ai:\n{err_body}")
    except (urllib.error.URLError, OSError) as exc:
        sys.exit(f"ERROR: проблема соединения: {exc}")

    out = text.strip()
    if not out:
        hint = " — весь бюджет ушёл в reasoning, увеличь ZAI_MAX_TOKENS" if stop_reason == "max_tokens" else ""
        sys.exit(f"ERROR: пустой ответ модели (stop_reason={stop_reason or '?'}){hint}")

    print(out)


if __name__ == "__main__":
    main()
