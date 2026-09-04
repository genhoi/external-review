#!/usr/bin/env python3
"""Unit tests for bin/lib/extract.py — no network, no CLIs. Run: python3 -m unittest tests/unit_extract.py"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin" / "lib"))
import extract  # noqa: E402

S = ROOT / "tests" / "samples"
REPORT = (S / "report.md").read_text(encoding="utf-8")


class ParsersTest(unittest.TestCase):
    def test_claude_stream(self):
        p = extract.parse("claude-stream-json", S / "claude-stream.jsonl")
        self.assertEqual(p.report().strip(), REPORT.strip())
        m = p.meta()
        self.assertEqual(m["session_id"], "00000000-0000-4000-8000-000000000001")
        self.assertEqual(m["turns"], 4)
        self.assertEqual(m["tool_calls"], 3)
        self.assertAlmostEqual(m["cost_usd"], 0.0123)
        self.assertEqual((m["tokens_in"], m["tokens_cached"], m["tokens_out"]), (10500, 9000, 700))
        self.assertEqual(p.tools[1], "Bash(.venv/bin/pytest -q)")

    def test_codex_jsonl(self):
        p = extract.parse("codex-jsonl", S / "codex.jsonl")
        self.assertEqual(p.report().strip(), REPORT.strip())
        m = p.meta()
        self.assertEqual(m["session_id"], "0190aaaa-bbbb-7ccc-8ddd-eeeeeeeeeeee")
        self.assertEqual(m["tool_calls"], 2)          # command_execution + file_change
        self.assertEqual((m["tokens_in"], m["tokens_cached"], m["tokens_out"]), (280059, 247808, 18931))

    def test_codex_prefers_last_message_file(self):
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d) / "raw"
            raw.write_bytes((S / "codex.jsonl").read_bytes())
            (Path(d) / "last_message.md").write_text("FROM -o FILE", encoding="utf-8")
            self.assertEqual(extract.parse("codex-jsonl", raw).report(), "FROM -o FILE")

    def test_kimi_stream(self):
        p = extract.parse("kimi-stream-json", S / "kimi-stream.jsonl")
        self.assertEqual(p.report().strip(), REPORT.strip())
        m = p.meta()
        self.assertEqual(m["session_id"], "session_0000-stub")
        self.assertEqual(m["tool_calls"], 1)
        self.assertEqual(p.tools[0], "Bash(.venv/bin/pytest -q)")

    def test_missing_raw_is_empty(self):
        p = extract.parse("claude-stream-json", "/nonexistent/raw")
        self.assertEqual(p.report(), "")
        self.assertEqual(p.meta()["tool_calls"], 0)


class ReportTest(unittest.TestCase):
    def test_findings_block(self):
        d = extract.findings_from_report(REPORT)
        self.assertEqual(d["verdict"], "not ready")
        self.assertEqual(d["findings"][0]["file"], "billing/webhooks.py")
        self.assertEqual(extract.findings_from_report("no json here"), {})

    def test_strip_blind(self):
        brief = "# Brief\n\n## Intent\nsecret\n\n## System\nkeep\n\n## Known decisions\nhidden\n\n## Priorities\n1. x\n"
        out = extract.strip_blind(brief)
        self.assertNotIn("secret", out)
        self.assertNotIn("hidden", out)
        self.assertIn("keep", out)
        self.assertIn("1. x", out)

    def test_tokens_line(self):
        self.assertEqual(extract.tokens_line({"tokens_in": 1234567, "tokens_cached": 1000, "tokens_out": 999}), "in 1.2M (cached 1.0k) out 999")
        self.assertEqual(extract.tokens_line({}), "")


class ProfileTest(unittest.TestCase):
    def test_section_in_claude_md(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "CLAUDE.md").write_text("# P\n\nauthor notes\n\n## External review\n\n- Tests: `make test`\n\n## Other\nno\n", encoding="utf-8")
            src, text = extract.project_profile(d)
            self.assertEqual(src, "CLAUDE.md § External review")
            self.assertEqual(text, "- Tests: `make test`")

    def test_russian_heading_and_agents_priority(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "CLAUDE.md").write_text("## External review\nfrom claude\n", encoding="utf-8")
            (Path(d) / "AGENTS.md").write_text("## Внешнее ревью\nfrom agents\n", encoding="utf-8")
            self.assertEqual(extract.project_profile(d), ("AGENTS.md § Внешнее ревью", "from agents"))

    def test_absent(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(extract.project_profile(d), (None, ""))


class FirstErrorTest(unittest.TestCase):
    def _meta(self, errors):
        d = tempfile.mkdtemp()
        p = Path(d) / "meta.json"
        p.write_text(json.dumps({"errors": errors}), encoding="utf-8")
        return p

    def test_codex_style_json_string(self):
        e = json.dumps({"type": "error", "message": "You've hit your usage limit. Try again at 2 AM."})
        self.assertIn("usage limit", extract.first_error(self._meta([e])))

    def test_nested_error_message(self):
        e = json.dumps({"type": "turn.failed", "error": {"message": "API Error: 529 Overloaded"}})
        self.assertEqual(extract.first_error(self._meta([e])), "API Error: 529 Overloaded")

    def test_bare_marker_is_not_a_message(self):
        self.assertEqual(extract.first_error(self._meta(["error"])), "")

    def test_no_errors_and_no_file(self):
        self.assertEqual(extract.first_error(self._meta([])), "")
        self.assertEqual(extract.first_error("/nonexistent/meta.json"), "")


class MergeTest(unittest.TestCase):
    def test_merge_groups_and_table(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d)
            (run / "meta.json").write_text(json.dumps({"project": "p", "mode": "diff", "base": "abc", "snapshot_commit": "def0123456789", "lang": "en"}))
            for r in ("a", "b"):
                (run / r).mkdir()
                (run / r / "status").write_text("done")
                (run / r / "report.md").write_text(REPORT, encoding="utf-8")
                (run / r / "meta.json").write_text(json.dumps({"turns": 2, "tool_calls": 3, "cost_usd": 0.5, "duration_ms": 65000, "tokens_in": 100, "tokens_cached": 50, "tokens_out": 10}))
            (run / "c").mkdir(); (run / "c" / "status").write_text("failed:1")
            out = extract.merge(run)
            self.assertIn("| a | done | 2 | 3 | 1m 5s | 100 (50) / 10 | $0.50 | 0 |", out)
            self.assertIn("| 1 | critical | a, b | `billing/webhooks.py:13` |", out)   # grouped: same file/line from both
            self.assertIn("**Verdict (a):** not ready", out)
            self.assertIn("_no report (status: failed:1)", out)


CLAIM_REPORT = """## Machine block
```json
{"verdict": "not ready", "findings": [],
 "claims": [{"claim": "The lockfile is the only record of the override", "verdict": "holds"},
            {"claim": "Re-resolving reproduces the build", "verdict": "%s"}]}
```
"""


class ClaimsMergeTest(unittest.TestCase):
    """Plan mode: per-claim verdicts must cross the reviewer boundary, and stay out of diff mode."""

    def _run(self, dirpath, reports):
        run = Path(dirpath)
        (run / "meta.json").write_text(json.dumps({"project": "p", "mode": "plan", "base": "abc", "lang": "en"}))
        for name, text in reports.items():
            (run / name).mkdir()
            (run / name / "status").write_text("done")
            (run / name / "report.md").write_text(text, encoding="utf-8")
        return extract.merge(run)

    def test_disagreement_sorts_first_and_every_reviewer_gets_a_column(self):
        with tempfile.TemporaryDirectory() as d:
            out = self._run(d, {"glm": CLAIM_REPORT % "breaks", "opus": CLAIM_REPORT % "unverifiable"})
            self.assertIn("| # | Claim | glm | opus |", out)
            body = out[out.index("| # | Claim |"):]
            rows = [ln for ln in body.splitlines() if ln.startswith("| 1 |") or ln.startswith("| 2 |")]
            self.assertIn("Re-resolving reproduces the build", rows[0])        # disagreement first
            self.assertIn("**breaks**", rows[0])
            self.assertIn("unverifiable", rows[0])
            self.assertIn("holds | holds", rows[1])                            # agreement below

    def test_diff_mode_report_has_no_claims_section(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertNotIn("Design claims", self._run(d, {"a": REPORT, "b": REPORT}))


if __name__ == "__main__":
    unittest.main()
