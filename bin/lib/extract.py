#!/usr/bin/env python3
"""Parse the output of different CLIs, assemble the prompt, build the merged report.

    extract.py report   FORMAT RAW        # final report text of a reviewer
    extract.py meta     FORMAT RAW        # JSON: session_id, turns, tool_calls, cost_usd, duration_ms
    extract.py progress FORMAT RAW        # one progress line for `review status`
    extract.py assemble --header H --protocol P --brief B [--lens L]... [--blind]
    extract.py merge    RUN_DIR           # merged.md to stdout
    extract.py profile  ROOT [--source]   # project review profile text (or its source name)
    extract.py error    META_JSON         # first error message from a reviewer's meta.json
    extract.py summary  RUN_DIR           # per-reviewer JSON summary for the usage journal
    extract.py digest   HOME [--since D]  # Markdown digest of usage.jsonl + feedback.jsonl

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
    all_claims = []
    reports = {}
    for r in reviewers:
        d = run / r
        st = (d / "status").read_text().strip()
        if (d / "partial").exists():
            st += f" ({(d / 'partial').read_text().strip()})"
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
            for c in data.get("claims", []) or []:
                if isinstance(c, dict):
                    c = dict(c)
                    c["_reviewer"] = r
                    all_claims.append(c)
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

    # plan mode: one row per design claim, one column per reviewer. Absent in diff mode.
    if all_claims:
        cgroups = {}
        for c in all_claims:
            key = re.sub(r"\s+", " ", str(c.get("claim") or c.get("title") or "")).strip().lower()[:120]
            cgroups.setdefault(key, []).append(c)

        def _verdict(v):
            v = str(v or "").strip().lower()
            return {"holds": "holds", "breaks": "**breaks**", "unverifiable": "unverifiable"}.get(v, v or "—")

        out.append("## Design claims (plan mode; claims the reviewers disagree on are the ones to read)")
        out.append("")
        out.append("| # | Claim | " + " | ".join(reviewers) + " |")
        out.append("|---|---|" + "---|" * len(reviewers))
        ordered = sorted(
            cgroups.items(),
            key=lambda kv: (0 if any(str(x.get("verdict", "")).strip().lower() == "breaks" for x in kv[1]) else 1,
                            -len(kv[1])))
        for i, (_key, items) in enumerate(ordered, 1):
            text = str(items[0].get("claim") or items[0].get("title") or "")[:110].replace("|", "/")
            by_rev = {x["_reviewer"]: x.get("verdict") for x in items}
            out.append(f"| {i} | {text} | " + " | ".join(_verdict(by_rev.get(r)) for r in reviewers) + " |")
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


# ---------- usage summary and digest ----------

def first_error(meta_path):
    """First error message from a reviewer's meta.json, one line, for the partial-completion note."""
    try:
        errs = json.loads(Path(meta_path).read_text(encoding="utf-8")).get("errors") or []
    except Exception:
        return ""
    for e in errs:
        msg = ""
        try:
            o = json.loads(e) if isinstance(e, str) else e
            if isinstance(o, dict):
                msg = o.get("message") or (o.get("error") or {}).get("message") or ""
        except Exception:
            msg = e if isinstance(e, str) else ""
        msg = " ".join(str(msg).split())
        if len(msg) > 8:          # bare markers like "error" carry nothing
            return msg[:100]
    return ""


def run_summary(run_dir):
    """Per-reviewer compact summary of a run (for the usage journal): no report text."""
    run = Path(run_dir)
    out = {}
    for d in sorted(p for p in run.iterdir() if p.is_dir() and (p / "status").exists()):
        m = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}
        data = findings_from_report((d / "report.md").read_text(encoding="utf-8", errors="replace")) if (d / "report.md").exists() else {}
        sev = {}
        for f in data.get("findings", []) or []:
            if isinstance(f, dict):
                sev[str(f.get("severity"))] = sev.get(str(f.get("severity")), 0) + 1
        out[d.name] = {"status": (d / "status").read_text().strip(), "exit": (d / "exit").read_text().strip() if (d / "exit").exists() else None,
                       "partial": (d / "partial").read_text().strip() if (d / "partial").exists() else None,
                       "duration_ms": m.get("duration_ms"), "tool_calls": m.get("tool_calls"), "tokens_in": m.get("tokens_in"),
                       "tokens_out": m.get("tokens_out"), "cost_usd": m.get("cost_usd"), "findings": sev or None,
                       "verdict": data.get("verdict"), "asks": len(list(d.glob("ask-*.md")))}
    return out


def digest(home, since=None):
    """Markdown digest of usage.jsonl + feedback.jsonl (this machine)."""
    home = Path(home)
    def load(name):
        p = home / name
        if not p.exists():
            return []
        rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [r for r in rows if not since or r.get("ts", "") >= since]
    usage, notes = load("usage.jsonl"), load("feedback.jsonl")
    out = [f"# external-review — field digest ({os.uname().nodename}{', since ' + since if since else ''})", ""]
    runs = [r for r in usage if r.get("event") == "run"]
    collects = [r for r in usage if r.get("event") == "collect"]
    pre = [r for r in usage if r.get("event") == "preflight"]
    asks = [r for r in usage if r.get("event") == "ask"]
    out.append(f"- runs: {len(runs)} · collected: {len(collects)} · asks: {len(asks)} · preflights: {len(pre)} "
               f"(failed: {sum(1 for r in pre if r.get('exit') not in (0, '0'))}) · notes: {len(notes)}")
    if runs:
        projects = sorted({r.get("project") for r in runs})
        harness = {}
        for r in runs:
            harness[r.get("harness")] = harness.get(r.get("harness"), 0) + 1
        out.append(f"- projects: {', '.join(p for p in projects if p)}")
        out.append("- orchestrators: " + ", ".join(f"{k} ×{v}" for k, v in sorted(harness.items(), key=lambda x: -x[1])))
        modes = {}
        for r in runs:
            key = f"{r.get('mode')}/{r.get('lang')}/{r.get('deps')}"
            modes[key] = modes.get(key, 0) + 1
        out.append("- mode/lang/deps: " + ", ".join(f"{k} ×{v}" for k, v in sorted(modes.items(), key=lambda x: -x[1])))
        out.append(f"- with project profile: {sum(1 for r in runs if r.get('profile') not in (None, 'none', ''))} · blind: {sum(1 for r in runs if str(r.get('blind')) == '1')} · custom prompt: {sum(1 for r in runs if r.get('prompt_file'))}")
    # per reviewer stats from collects
    stats = {}
    for c in collects:
        for name, r in (c.get("reviewers") or {}).items():
            if not isinstance(r, dict):
                continue
            st = stats.setdefault(name, {"n": 0, "done": 0, "dur": [], "tools": [], "tok_in": [], "tok_out": [], "cost": [], "findings": 0, "asks": 0, "partial": 0})
            st["n"] += 1
            st["done"] += 1 if str(r.get("status", "")).startswith("done") else 0
            st["partial"] += 1 if r.get("partial") else 0
            for key, field in (("dur", "duration_ms"), ("tools", "tool_calls"), ("tok_in", "tokens_in"), ("tok_out", "tokens_out"), ("cost", "cost_usd")):
                if isinstance(r.get(field), (int, float)):
                    st[key].append(r[field])
            st["findings"] += sum((r.get("findings") or {}).values()) if isinstance(r.get("findings"), dict) else 0
            st["asks"] += r.get("asks") or 0
    if stats:
        out += ["", "## Reviewers (from collected runs)", "", "| Reviewer | Runs | Done | Partial | Avg duration | Avg tool calls | Avg tokens in / out | Avg cost | Findings | Asks |", "|---|---|---|---|---|---|---|---|---|---|"]
        avg = lambda xs: (sum(xs) / len(xs)) if xs else None
        for name, st in sorted(stats.items()):
            d = avg(st["dur"]); dur = f"{int(d // 60000)}m {int(d % 60000 // 1000)}s" if d else "—"
            c = avg(st["cost"]); cost = f"${c:.2f}" if c is not None else "—"
            out.append(f"| {name} | {st['n']} | {st['done']} | {st['partial']} | {dur} | {_k(avg(st['tools']))} | {_k(avg(st['tok_in']))} / {_k(avg(st['tok_out']))} | {cost} | {st['findings']} | {st['asks']} |")
    if notes:
        out += ["", "## Notes from orchestrators", ""]
        for n in notes:
            out += [f"### {n.get('ts', '')[:10]} · {n.get('project')} · {n.get('harness')} · run {n.get('run')}", "", n.get("note", "").strip(), ""]
    else:
        out += ["", "_No notes yet: after a review, run `review feedback RUN \"what helped / what blocked / accepted vs rejected\"`._"]
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
    elif cmd == "error":
        print(first_error(rest[0]))
    elif cmd == "summary":
        print(json.dumps(run_summary(rest[0]), ensure_ascii=False))
    elif cmd == "digest":
        since = rest[rest.index("--since") + 1] if "--since" in rest else None
        print(digest(rest[0], since), end="")
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
