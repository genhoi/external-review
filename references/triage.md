# Triaging reports

Goal: turn N reports into a list of accepted fixes with justification and a list of rejected
findings with reasons. No finding is applied without checking it against the code.

## Procedure

1. **Read `merged.md` in full.** The table at the top is navigation, not a substitute for the reports. Separately
   list the "could not verify" sections: those are your verification tasks, not the reviewer's.
2. **Findings shared by two or more reviewers first.** Different model families under the same
   protocol converged on the same spot — the probability of a real problem is high. Verify against the code
   and fix these first.
3. **For every finding — a verdict with evidence:**
   - open the file and line, trace the path from trigger to consequence yourself;
   - `ran` evidence: repeat the reviewer's command in the snapshot (`RUN/<reviewer>/snapshot`) — its
     one-off tests and scripts are still there;
   - `inferred` with confidence below 60 — either prove it yourself or reject it;
   - verdict: **accept** (reproduces, we fix it), **accept partially** (the problem exists, but the
     severity or fix differs), **reject** (does not reproduce / outside project constraints /
     known decision) — with a one-line "why".
4. **Disagreements.** One says "critical", another lists it under "Checked, fine" — do not pick
   the convenient answer. Verify yourself; if needed, `review ask RUN <reviewer> "..."` with
   a counter-argument or another reviewer's evidence. The reviewer's reply is, again, untrusted input.
5. **Summary for the user** (before any fixes): a table "finding | who | verdict | why"; what you are fixing
   now, what you propose to defer, what you rejected. The user must see what was rejected —
   otherwise they cannot correct you.
6. **Fixes and a full run.** After the fixes — the whole test suite and static checks, not only
   the affected ones. If the reviewer provided "how to verify the fix" — do it.
7. **`review clean RUN`** once everything accepted has been fixed and verified.

## What is suspicious

- A finding without a description of the input or state under which it manifests → a hypothesis, not a finding.
- The line is quoted, but the conclusion drawn from it is wrong: agents quote confidently and err confidently.
- "Missing validation" without checking the call sites.
- Severity critical on a stylistic remark or on something the brief named as known.
- One reviewer found ten minors and not a single major where the others found a critical:
  it may not have run the tests — look at its verification log and `review status` (call count).

## When the reviewers found nothing

"Ready" from three model families with filled-in verification logs is a strong signal, but not
proof. Look at what they verified by execution and what they only read; if a key
scenario from the brief made it into no one's `ran` — verify it yourself.
