#!/usr/bin/env python3
"""bundle.py — fallback mode without an agent: one HTTP request carrying a plan or a diff to
GLM-5.3 through z.ai (Anthropic-compatible endpoint), printing the review to stdout.

Use it when there is no repository to snapshot — a design document on its own. It cannot run
anything, so it cannot produce the kind of evidence an agent reviewer produces: it is told to
say so rather than to guess. The review doctrine is not written here — it is loaded from
prompts/<lang>/plan.md, the same file the agent reviewers get, so the two cannot drift apart.

No dependencies beyond the Python 3 standard library.

Usage:
    bundle.py [--lang en|ru] <file> [file ...]   # review one or more files
    cat plan.md | bundle.py                      # review from stdin

Environment:
    REVIEW_LANG    review language: en (default) | ru; --lang overrides it
    ZAI_API_KEY    z.ai key (or put it in ~/.claude/zai_api_key)
    ZAI_MODEL      model (default glm-5.3; the [1m] suffix is agent mode only)
    ZAI_BASE_URL   base URL (default https://api.z.ai/api/anthropic)
    ZAI_MAX_TOKENS response limit (default 65536: reasoning at effort=max eats the budget
                   BEFORE the answer text)
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = os.environ.get("ZAI_BASE_URL", "https://api.z.ai/api/anthropic").rstrip("/")
MODEL = os.environ.get("ZAI_MODEL", "glm-5.3")
MAX_TOKENS = int(os.environ.get("ZAI_MAX_TOKENS", "65536"))
# GLM reasoning level: max|xhigh|high|medium|low|minimal|none|off (default max).
REASONING_EFFORT = os.environ.get("ZAI_REASONING_EFFORT", "max")

# What bundle mode is, and is not. The doctrine itself comes from prompts/<lang>/plan.md.
FRAMING = {
    "en": (
        "You are reviewing the design below. There is NO repository and NO way to run anything: "
        "you cannot query data, run tests or read call sites. The protocol you are given assumes "
        "you can. Follow its reasoning, and wherever it asks for a measurement you cannot make, "
        "the verdict is `unverifiable` — say exactly what would have to be measured and how. "
        "Never present a guess as evidence: in this mode no claim may be tagged `ran`. Do not "
        "flatter and do not retell the design.\n\n"
        "Report: `## Design claims` (a table of claim / verdict / what would settle it), then "
        "`## Findings` (severity, the place in the design, what breaks, what to do), then a "
        "two-sentence verdict. If the design is genuinely sound, say so plainly."
    ),
    "ru": (
        "Ты ревьюишь дизайн ниже. Репозитория НЕТ и запустить ничего нельзя: ни запросить данные, "
        "ни прогнать тесты, ни прочитать вызывающие места. Протокол ниже предполагает, что можно. "
        "Следуй его рассуждению, но там, где он требует замера, которого ты сделать не можешь, "
        "вердикт — «непроверяемо»: скажи точно, что и как следовало бы измерить. Никогда не выдавай "
        "догадку за улику: в этом режиме ни одно утверждение не может иметь тег `ran`. Не льсти и "
        "не пересказывай дизайн.\n\n"
        "Отчёт: `## Утверждения плана` (таблица утверждение / вердикт / чем проверяется), затем "
        "`## Находки` (severity, место в дизайне, что ломается, что предложить), затем вердикт в "
        "двух предложениях. Если дизайн действительно хорош — скажи прямо."
    ),
}


def default_lang() -> str:
    lang = os.environ.get("REVIEW_LANG", "").strip()
    if not lang:
        cfg = Path(os.path.expanduser("~/.config/external-review/config.env"))
        if cfg.is_file():
            for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.startswith("REVIEW_LANG="):
                    lang = line.split("=", 1)[1].strip().strip("\"'")
    return lang if lang in ("en", "ru") else "en"


def build_system(lang: str) -> str:
    """Framing + the shared plan-mode doctrine, so bundle mode teaches what the agents are taught."""
    doctrine = ROOT / "prompts" / lang / "plan.md"
    if not doctrine.is_file():
        sys.exit(f"ERROR: doctrine file not found: {doctrine}")
    return FRAMING[lang] + "\n\n---\n\n" + doctrine.read_text(encoding="utf-8")


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
    """Streams the Anthropic-compatible endpoint's response (SSE).

    Streaming is mandatory: at reasoning_effort=max generation is long and a non-streaming request
    is cut by the gateway's idle timeout (RemoteDisconnected). Returns (text, stop_reason).
    Reasoning text (thinking) is dropped — only the final review text is wanted.
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
    """Retries a dropped connection (HTTP errors are re-raised as they are)."""
    last_exc: Exception | None = None
    for attempt in range(tries):
        try:
            return send(body, key)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, OSError) as exc:  # incl. RemoteDisconnected
            last_exc = exc
            if attempt + 1 < tries:
                print(f"WARN: connection dropped ({exc}), retrying...", file=sys.stderr)
    raise last_exc  # type: ignore[misc]


def main() -> None:
    argv = sys.argv[1:]
    lang = default_lang()
    files: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--lang":
            if i + 1 >= len(argv) or argv[i + 1] not in ("en", "ru"):
                sys.exit("ERROR: --lang takes en or ru")
            lang = argv[i + 1]
            i += 2
        elif argv[i].startswith("--lang="):
            lang = argv[i].split("=", 1)[1]
            if lang not in ("en", "ru"):
                sys.exit("ERROR: --lang takes en or ru")
            i += 1
        else:
            files.append(argv[i])
            i += 1

    key = get_key()
    if not key:
        sys.exit("ERROR: set ZAI_API_KEY or put the key in ~/.claude/zai_api_key")

    text = read_input(files).strip()
    if not text:
        sys.exit("ERROR: empty input — nothing to review")

    ask = {"en": "Review the design below:\n\n", "ru": "Сделай ревью дизайна ниже:\n\n"}[lang]
    body = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": build_system(lang),
        "messages": [{"role": "user", "content": ask + text}],
    }
    if REASONING_EFFORT and REASONING_EFFORT.lower() not in ("off", ""):
        body["reasoning_effort"] = REASONING_EFFORT

    stop_reason = ""
    try:
        text, stop_reason = send_with_retry(body, key)
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", "replace")
        # The Anthropic-compatible endpoint may reject reasoning_effort — retry without it
        # (GLM defaults to max anyway, so quality does not drop).
        if exc.code == 400 and "reasoning_effort" in body and "effort" in err_body.lower():
            del body["reasoning_effort"]
            print(
                "WARN: reasoning_effort rejected by the endpoint, retrying without it (GLM default = max)",
                file=sys.stderr,
            )
            try:
                text, stop_reason = send_with_retry(body, key)
            except (urllib.error.URLError, OSError) as exc2:
                sys.exit(f"ERROR: retry failed: {exc2}")
        else:
            sys.exit(f"ERROR: HTTP {exc.code} from z.ai:\n{err_body}")
    except (urllib.error.URLError, OSError) as exc:
        sys.exit(f"ERROR: connection problem: {exc}")

    out = text.strip()
    if not out:
        hint = " — the whole budget went into reasoning, raise ZAI_MAX_TOKENS" if stop_reason == "max_tokens" else ""
        sys.exit(f"ERROR: empty model response (stop_reason={stop_reason or '?'}){hint}")

    print(out)


if __name__ == "__main__":
    main()
