#!/usr/bin/env python3
"""Разбор вывода разных CLI, сборка промпта и сводного отчёта.

    extract.py report   FORMAT RAW        # финальный текст отчёта рецензента
    extract.py meta     FORMAT RAW        # JSON: session_id, turns, tool_calls, cost_usd, duration_ms
    extract.py progress FORMAT RAW        # одна строка прогресса для `review status`
    extract.py assemble --header H --protocol P --brief B [--lens L]... [--blind]
    extract.py merge    RUN_DIR           # merged.md в stdout

FORMAT: claude-stream-json | codex-jsonl | grok-messages | kimi-stream-json | text
Только стандартная библиотека.
"""
import json
import os
import re
import sys
from pathlib import Path


# ---------- чтение сырых логов ----------

def _lines(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _blocks_text(content):
    if isinstance(content, str):
        return content
    out = []
    for b in content or []:
        if isinstance(b, dict) and b.get("type") == "text":
            out.append(b.get("text", ""))
    return "".join(out)


def _tool_label(name, inp):
    if not isinstance(inp, dict):
        return name
    for k in ("command", "cmd", "file_path", "path", "pattern", "query", "description"):
        v = inp.get(k)
        if isinstance(v, str) and v:
            return f"{name}({v[:90]})"
    return name


class Parsed:
    def __init__(self):
        self.texts = []        # тексты ассистента по порядку
        self.final = None      # явный финальный result, если формат его даёт
        self.tools = []        # метки вызовов инструментов по порядку
        self.session_id = None
        self.turns = None
        self.cost = None
        self.duration_ms = None
        self.model = None
        self.errors = []

    def report(self):
        if self.final and self.final.strip():
            return self.final.strip()
        # иначе — последний непустой текст ассистента (отчёт часто идёт последним)
        for t in reversed(self.texts):
            if t.strip():
                return t.strip()
        return ""

    def meta(self):
        return {
            "session_id": self.session_id, "turns": self.turns, "tool_calls": len(self.tools),
            "cost_usd": self.cost, "duration_ms": self.duration_ms, "model": self.model,
            "errors": self.errors[-3:],
        }


def parse_claude(path):
    p = Parsed()
    for ev in _lines(path):
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            p.session_id = ev.get("session_id") or p.session_id
            p.model = ev.get("model") or p.model
        elif t == "assistant":
            msg = ev.get("message", {})
            p.model = msg.get("model") or p.model
            txt = _blocks_text(msg.get("content"))
            if txt.strip():
                p.texts.append(txt)
            for b in msg.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    p.tools.append(_tool_label(b.get("name", "?"), b.get("input")))
        elif t == "result":
            p.session_id = ev.get("session_id") or p.session_id
            p.turns = ev.get("num_turns")
            p.cost = ev.get("total_cost_usd")
            p.duration_ms = ev.get("duration_ms")
            if ev.get("is_error"):
                p.errors.append(str(ev.get("result") or ev.get("error") or "error")[:300])
            elif isinstance(ev.get("result"), str):
                p.final = ev["result"]
    return p


def parse_codex(path):
    p = Parsed()
    for ev in _lines(path):
        t = ev.get("type", "")
        if t == "thread.started":
            p.session_id = ev.get("thread_id") or p.session_id
        elif t == "item.completed":
            item = ev.get("item", {})
            it = item.get("type")
            if it == "agent_message":
                txt = item.get("text") or _blocks_text(item.get("content"))
                if txt and txt.strip():
                    p.texts.append(txt)
            elif it in ("command_execution", "local_shell_call"):
                p.tools.append(_tool_label("shell", {"command": item.get("command", "")}))
            elif it in ("file_change", "patch"):
                p.tools.append("apply_patch")
            elif it == "mcp_tool_call":
                p.tools.append(_tool_label(item.get("tool", "mcp"), item.get("arguments")))
        elif t == "turn.completed":
            p.turns = (p.turns or 0) + 1
        elif t in ("error", "turn.failed"):
            p.errors.append(json.dumps(ev)[:300])
    # -o файл с последним сообщением надёжнее, если есть
    last = Path(path).with_name("last_message.md")
    if last.exists() and last.read_text(encoding="utf-8", errors="replace").strip():
        p.final = last.read_text(encoding="utf-8", errors="replace")
    return p


def parse_grok_messages(path):
    """NDJSON в формате Anthropic Messages (стрим): собираем текст по сообщениям."""
    p = Parsed()
    cur_text, cur_tool = [], None
    for ev in _lines(path):
        t = ev.get("type")
        if t == "message_start":
            cur_text = []
            m = ev.get("message", {})
            p.model = m.get("model") or p.model
            p.session_id = ev.get("session_id") or m.get("session_id") or p.session_id
        elif t == "content_block_start":
            cb = ev.get("content_block", {})
            if cb.get("type") == "tool_use":
                cur_tool = cb.get("name", "?")
                p.tools.append(_tool_label(cur_tool, cb.get("input")))
            elif cb.get("type") == "text" and cb.get("text"):
                cur_text.append(cb["text"])
        elif t == "content_block_delta":
            d = ev.get("delta", {})
            if d.get("type") == "text_delta":
                cur_text.append(d.get("text", ""))
        elif t == "message_stop":
            txt = "".join(cur_text)
            if txt.strip():
                p.texts.append(txt)
            p.turns = (p.turns or 0) + 1
        elif t == "message":  # цельные сообщения без стрима
            m = ev.get("message", ev)
            if m.get("role") == "assistant":
                txt = _blocks_text(m.get("content"))
                if txt.strip():
                    p.texts.append(txt)
                for b in m.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        p.tools.append(_tool_label(b.get("name", "?"), b.get("input")))
        elif t == "error":
            p.errors.append(json.dumps(ev)[:300])
    if cur_text and "".join(cur_text).strip() and ("".join(cur_text) not in p.texts):
        p.texts.append("".join(cur_text))
    return p


def parse_kimi(path):
    """kimi --output-format stream-json: строки вида {"role":"assistant","content":"...","tool_calls":[...]}
    и мета-события {"role":"meta","type":"session.resume_hint","session_id":...}."""
    p = Parsed()
    for ev in _lines(path):
        t = ev.get("type", "")
        if t == "session.resume_hint":
            p.session_id = ev.get("session_id") or p.session_id
            continue
        if ev.get("role") == "assistant":
            content = ev.get("content")
            txt = content if isinstance(content, str) else _blocks_text(content)
            if txt and txt.strip():
                p.texts.append(txt)
            for tc in ev.get("tool_calls") or []:
                fn = (tc or {}).get("function") or {}
                args = fn.get("arguments")
                try:
                    args = json.loads(args) if isinstance(args, str) else args
                except json.JSONDecodeError:
                    args = {"command": str(args)}
                p.tools.append(_tool_label(fn.get("name", "?"), args))
            p.turns = (p.turns or 0) + 1
        elif t == "error" or ev.get("role") == "error":
            p.errors.append(json.dumps(ev, ensure_ascii=False)[:300])
    return p


def parse_text(path):
    p = Parsed()
    txt = Path(path).read_text(encoding="utf-8", errors="replace")
    p.final = txt
    return p


PARSERS = {
    "claude-stream-json": parse_claude,
    "codex-jsonl": parse_codex,
    "grok-messages": parse_grok_messages,
    "kimi-stream-json": parse_kimi,
    "text": parse_text,
}


def parse(fmt, path):
    if fmt not in PARSERS:
        sys.exit(f"extract.py: неизвестный формат {fmt}")
    if not os.path.exists(path):
        return Parsed()
    return PARSERS[fmt](path)


# ---------- сборка промпта ----------

BLIND_HEADERS = ("интент", "intent", "сознательн", "известные решения", "known decisions")


def strip_blind(brief):
    """Убирает из вводной разделы с интентом и сознательными решениями (для слепого рецензента)."""
    out, skip = [], False
    for line in brief.splitlines():
        if re.match(r"^#{1,6}\s", line):
            skip = any(k in line.lower() for k in BLIND_HEADERS)
        if not skip:
            out.append(line)
    return "\n".join(out)


def assemble(args):
    def rd(p):
        return Path(p).read_text(encoding="utf-8") if p else ""
    header, protocol, brief = rd(args.header), rd(args.protocol), rd(args.brief)
    if args.blind:
        brief = strip_blind(brief)
    parts = [protocol.strip(), ""]
    for l in args.lens or []:
        parts += [rd(l).strip(), ""]
    parts += ["---", "", header.strip(), "", brief.strip(), ""]
    return "\n".join(parts)


# ---------- findings и сводка ----------

def findings_from_report(text):
    """Последний ```json-блок отчёта → dict (или {})."""
    blocks = re.findall(r"```json\s*\n(.*?)\n```", text, flags=re.S)
    for raw in reversed(blocks):
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "findings" in data:
                return data
        except json.JSONDecodeError:
            continue
    return {}


SEV_ORDER = {"critical": 0, "major": 1, "minor": 2, "info": 3}


def _norm_file(f):
    return (f or "").strip().lstrip("./")


def merge(run_dir):
    run = Path(run_dir)
    meta_run = json.loads((run / "meta.json").read_text()) if (run / "meta.json").exists() else {}
    reviewers = sorted(d.name for d in run.iterdir() if d.is_dir() and (d / "status").exists())
    out = [f"# Сводка внешнего ревью — {meta_run.get('project', run.name)}", ""]
    out.append(f"Прогон: `{run}`  ")
    out.append(f"Режим: {meta_run.get('mode')} · base: `{meta_run.get('base')}` · снапшот: `{meta_run.get('snapshot_commit', '')[:12]}`  ")
    out.append("")
    out.append("| Рецензент | Статус | Ходы | Инструменты | Длительность | Стоимость | Изменил файлов в снапшоте |")
    out.append("|---|---|---|---|---|---|---|")
    all_findings = []
    reports = {}
    for r in reviewers:
        d = run / r
        st = (d / "status").read_text().strip()
        m = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}
        changes = (d / "snapshot_changes").read_text().strip().splitlines() if (d / "snapshot_changes").exists() else []
        dur = m.get("duration_ms")
        if not dur and (d / "started").exists() and (d / "finished").exists():
            from datetime import datetime
            fmt = "%Y-%m-%dT%H:%M:%SZ"
            a = datetime.strptime((d / "started").read_text().strip(), fmt)
            b = datetime.strptime((d / "finished").read_text().strip(), fmt)
            dur = int((b - a).total_seconds() * 1000)
        dur_s = f"{dur // 60000}м {dur % 60000 // 1000}с" if dur else "—"
        cost = f"${m['cost_usd']:.2f}" if isinstance(m.get("cost_usd"), (int, float)) else "—"
        out.append(f"| {r} | {st} | {m.get('turns') or '—'} | {m.get('tool_calls') or '—'} | {dur_s} | {cost} | {len(changes)} |")
        if (d / "report.md").exists():
            text = (d / "report.md").read_text(encoding="utf-8", errors="replace")
            reports[r] = text
            data = findings_from_report(text)
            for f in data.get("findings", []) or []:
                if isinstance(f, dict):
                    f = dict(f)
                    f["_reviewer"] = r
                    all_findings.append(f)
    out.append("")

    # группировка: тот же файл и строка в пределах ±15
    groups = []
    for f in sorted(all_findings, key=lambda x: (SEV_ORDER.get(str(x.get("severity", "")).lower(), 9), _norm_file(x.get("file")))):
        placed = False
        for g in groups:
            g0 = g[0]
            same_file = _norm_file(g0.get("file")) == _norm_file(f.get("file")) and _norm_file(f.get("file"))
            try:
                close = abs(int(g0.get("line") or 0) - int(f.get("line") or 0)) <= 15
            except (TypeError, ValueError):
                close = False
            if same_file and close and f["_reviewer"] not in {x["_reviewer"] for x in g}:
                g.append(f)
                placed = True
                break
        if not placed:
            groups.append([f])

    out.append("## Находки (сгруппированы по файлу и строке; сначала совпавшие у нескольких рецензентов)")
    out.append("")
    out.append("| # | Sev | Кто | Файл:строка | Суть | Улика | Мой вердикт |")
    out.append("|---|---|---|---|---|---|---|")
    groups.sort(key=lambda g: (-len(g), SEV_ORDER.get(str(g[0].get("severity", "")).lower(), 9)))
    for i, g in enumerate(groups, 1):
        f = g[0]
        who = ", ".join(x["_reviewer"] for x in g)
        sev = "/".join(sorted({str(x.get("severity", "?")) for x in g}))
        loc = f"{f.get('file', '?')}:{f.get('line', '?')}"
        title = str(f.get("title") or f.get("summary") or "")[:110].replace("|", "/")
        ev = "/".join(sorted({str(x.get("evidence", "?")) for x in g}))
        out.append(f"| {i} | {sev} | {who} | `{loc}` | {title} | {ev} | |")
    if not groups:
        out.append("| — | — | — | — | JSON-блок с findings не найден ни в одном отчёте: разбирай отчёты вручную | — | |")
    out.append("")
    for r in reviewers:
        d = run / r
        data = findings_from_report(reports.get(r, ""))
        if data.get("verdict"):
            out.append(f"**Вердикт {r}:** {data['verdict']}  ")
    out.append("")
    out.append("## Полные отчёты")
    for r in reviewers:
        out += ["", f"### {r}", ""]
        if r in reports:
            out.append(reports[r])
        else:
            out.append(f"_отчёта нет (статус: {(run / r / 'status').read_text().strip()}); см. {run / r / 'stderr.log'}_")
    return "\n".join(out) + "\n"


# ---------- CLI ----------

def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, rest = argv[0], argv[1:]
    if cmd == "report":
        print(parse(rest[0], rest[1]).report())
    elif cmd == "meta":
        print(json.dumps(parse(rest[0], rest[1]).meta(), ensure_ascii=False))
    elif cmd == "progress":
        p = parse(rest[0], rest[1])
        last = p.tools[-1] if p.tools else "—"
        snippet = (p.texts[-1].strip().splitlines() or [""])[-1][:70] if p.texts else ""
        err = f" ERR: {p.errors[-1][:80]}" if p.errors else ""
        print(f"{len(p.tools)} вызовов инструментов; последний: {last}; текст: {snippet}{err}")
    elif cmd == "assemble":
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--header"); ap.add_argument("--protocol"); ap.add_argument("--brief")
        ap.add_argument("--lens", action="append"); ap.add_argument("--blind", action="store_true")
        print(assemble(ap.parse_args(rest)))
    elif cmd == "merge":
        print(merge(rest[0]), end="")
    elif cmd == "findings":
        print(json.dumps(findings_from_report(Path(rest[0]).read_text(encoding="utf-8")), ensure_ascii=False, indent=1))
    else:
        sys.exit(f"extract.py: неизвестная команда {cmd}")


if __name__ == "__main__":
    main(sys.argv[1:])
