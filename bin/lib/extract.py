#!/usr/bin/env python3
"""Parse the output of different CLIs, assemble the prompt, build the merged report.

    extract.py report   FORMAT RAW        # final report text of a reviewer
    extract.py meta     FORMAT RAW        # JSON: session_id, turns, tool_calls, cost_usd, duration_ms
    extract.py progress FORMAT RAW        # one progress line for `review status`
    extract.py assemble --header H --protocol P --brief B [--lens L]... [--blind]
    extract.py merge    RUN_DIR           # merged.md to stdout
    extract.py profile  ROOT [--source]   # project review profile text (or its source name)

FORMAT: claude-stream-json | codex-jsonl | grok-messages | kimi-stream-json | text
Standard library only.
"""
import json
import os
import re
import sys
from pathlib import Path


# ---------- raw log parsing ----------

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
        self.texts = []        # assistant texts in order
        self.final = None      # explicit final result when the format provides one
        self.tools = []        # tool-call labels in order
        self.session_id = None
        self.turns = None
        self.cost = None
        self.duration_ms = None
        self.model = None
        self.errors = []
        self.tokens_in = None      # total input tokens including cached
        self.tokens_cached = None  # of which served from cache
        self.tokens_out = None     # output tokens (reasoning included where reported)

    def report(self):
        if self.final and self.final.strip():
            return self.final.strip()
        # otherwise the last non-empty assistant text (the report is usually last)
        for t in reversed(self.texts):
            if t.strip():
                return t.strip()
        return ""

    def meta(self):
        return {
            "session_id": self.session_id, "turns": self.turns, "tool_calls": len(self.tools),
            "cost_usd": self.cost, "duration_ms": self.duration_ms, "model": self.model,
            "tokens_in": self.tokens_in, "tokens_cached": self.tokens_cached, "tokens_out": self.tokens_out,
            "errors": self.errors[-3:],
        }

    def add_usage(self, usage):
        """Accumulate a usage dict from any of the CLIs (field names differ)."""
        if not isinstance(usage, dict):
            return
        cached = usage.get("cache_read_input_tokens", usage.get("cached_input_tokens", 0)) or 0
        created = usage.get("cache_creation_input_tokens", usage.get("cache_write_input_tokens", 0)) or 0
        raw_in = usage.get("input_tokens", 0) or 0
        # Anthropic-style input_tokens excludes cache hits; Codex-style includes them.
        total_in = raw_in + cached + created if "cache_read_input_tokens" in usage else max(raw_in, cached)
        out = (usage.get("output_tokens", 0) or 0)
        self.tokens_in = (self.tokens_in or 0) + total_in
        self.tokens_cached = (self.tokens_cached or 0) + cached
        self.tokens_out = (self.tokens_out or 0) + out


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
            p.add_usage(ev.get("usage"))
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
            p.add_usage(ev.get("usage"))
        elif t in ("error", "turn.failed"):
            p.errors.append(json.dumps(ev)[:300])
    # the -o file with the last message is more reliable when present
    last = Path(path).with_name("last_message.md")
    if last.exists() and last.read_text(encoding="utf-8", errors="replace").strip():
        p.final = last.read_text(encoding="utf-8", errors="replace")
    return p


def parse_grok_messages(path):
    """NDJSON in Anthropic Messages wire format (stream): collect text per message."""
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
        elif t == "message":  # whole messages without streaming
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
    """kimi --output-format stream-json: lines like {"role":"assistant","content":"...","tool_calls":[...]}
    plus meta events {"role":"meta","type":"session.resume_hint","session_id":...}."""
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
        sys.exit(f"extract.py: unknown format {fmt}")
    if not os.path.exists(path):
        return Parsed()
    return PARSERS[fmt](path)


# ---------- prompt assembly ----------

BLIND_HEADERS = ("интент", "intent", "сознательн", "известные решения", "known decisions")


def strip_blind(brief):
    """Strip the intent and known-decisions sections from the brief (for a blind reviewer)."""
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


# ---------- project profile ----------

PROFILE_SOURCES = ("AGENTS.md", "CLAUDE.md", "agents.md", "claude.md")
PROFILE_HEADING = re.compile(r"^(#{1,6})\s*(external review|внешнее ревью)\b.*$", re.I | re.M)


def project_profile(root):
    """Return (source, text) of the project's review profile, or (None, ''): the section headed
    'External review' / 'Внешнее ревью' in AGENTS.md or CLAUDE.md, up to the next heading of the
    same or higher level."""
    root = Path(root)
    for name in PROFILE_SOURCES:
        f = root / name
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        m = PROFILE_HEADING.search(text)
        if not m:
            continue
        level = len(m.group(1))
        rest = text[m.end():]
        stop = re.search(rf"^#{{1,{level}}}\s", rest, re.M)
        body = rest[: stop.start()] if stop else rest
        if body.strip():
            return f"{name} § {m.group(0).lstrip('#').strip()}", body.strip()
    return None, ""


# ---------- findings and merged report ----------

def findings_from_report(text):
    """Last ```json block of the report → dict (or {})."""
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


def _k(n):
    """1234 -> '1.2k', 1234567 -> '1.2M', None -> '—'."""
    if n is None:
        return "—"
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def tokens_line(m):
    """'in 1.2M (cached 1.0M) out 45.1k' or '' when nothing was reported."""
    if not m or m.get("tokens_in") is None and m.get("tokens_out") is None:
        return ""
    return f"in {_k(m.get('tokens_in'))} (cached {_k(m.get('tokens_cached'))}) out {_k(m.get('tokens_out'))}"


def _norm_file(f):
    return (f or "").strip().lstrip("./")


def merge(run_dir):
    run = Path(run_dir)
    meta_run = json.loads((run / "meta.json").read_text()) if (run / "meta.json").exists() else {}
    reviewers = sorted(d.name for d in run.iterdir() if d.is_dir() and (d / "status").exists())
    out = [f"# External review — merged report — {meta_run.get('project', run.name)}", ""]
    out.append(f"Run: `{run}`  ")
    out.append(f"Mode: {meta_run.get('mode')} · base: `{meta_run.get('base')}` · snapshot: `{meta_run.get('snapshot_commit', '')[:12]}` · lang: {meta_run.get('lang', '?')}  ")
    out.append("")
    out.append("| Reviewer | Status | Turns | Tool calls | Duration | Tokens in (cached) / out | Cost | Files changed in snapshot |")
    out.append("|---|---|---|---|---|---|---|---|")
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
        dur_s = f"{dur // 60000}m {dur % 60000 // 1000}s" if dur else "—"
        cost = f"${m['cost_usd']:.2f}" if isinstance(m.get("cost_usd"), (int, float)) else "—"
        tok = f"{_k(m.get('tokens_in'))} ({_k(m.get('tokens_cached'))}) / {_k(m.get('tokens_out'))}" if m.get("tokens_in") is not None else "—"
        out.append(f"| {r} | {st} | {m.get('turns') or '—'} | {m.get('tool_calls') or '—'} | {dur_s} | {tok} | {cost} | {len(changes)} |")
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

    # grouping: same file and line within ±15
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

    out.append("## Findings (grouped by file and line; those flagged by several reviewers first)")
    out.append("")
    out.append("| # | Sev | Who | File:line | Summary | Evidence | My verdict |")
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
        out.append("| — | — | — | — | no JSON findings block in any report: read the reports manually | — | |")
    out.append("")
    for r in reviewers:
        d = run / r
        data = findings_from_report(reports.get(r, ""))
        if data.get("verdict"):
            out.append(f"**Verdict ({r}):** {data['verdict']}  ")
    out.append("")
    out.append("## Full reports")
    for r in reviewers:
        out += ["", f"### {r}", ""]
        if r in reports:
            out.append(reports[r])
        else:
            out.append(f"_no report (status: {(run / r / 'status').read_text().strip()}); see {run / r / 'stderr.log'}_")
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
        m = p.meta()
        tl = tokens_line(m)
        cost = f" ${m['cost_usd']:.2f}" if isinstance(m.get("cost_usd"), (int, float)) else ""
        tail = f" · {tl}{cost}" if tl else ""
        print(f"{len(p.tools)} tool calls; last: {last}; text: {snippet}{err}{tail}")
    elif cmd == "assemble":
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--header"); ap.add_argument("--protocol"); ap.add_argument("--brief")
        ap.add_argument("--lens", action="append"); ap.add_argument("--blind", action="store_true")
        print(assemble(ap.parse_args(rest)))
    elif cmd == "merge":
        print(merge(rest[0]), end="")
    elif cmd == "profile":
        src, text = project_profile(rest[0])
        if not src:
            sys.exit(1)
        print(src if len(rest) > 1 and rest[1] == "--source" else text)
    elif cmd == "findings":
        print(json.dumps(findings_from_report(Path(rest[0]).read_text(encoding="utf-8")), ensure_ascii=False, indent=1))
    else:
        sys.exit(f"extract.py: unknown command {cmd}")


if __name__ == "__main__":
    main(sys.argv[1:])
