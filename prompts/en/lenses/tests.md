## Lens for this run: tests
You are responsible only for the tests axis: what they actually check. For every changed behaviour,
find the test that would fail on a broken implementation; if there is none, that is a finding with a
concrete scenario and consequence. Look for vacuous asserts, order- or time-dependent tests, mocking
that removes all meaning, uncovered error branches. Verify by mutation: break the code, run the tests,
see who notices. Include findings outside this axis only at critical severity.
