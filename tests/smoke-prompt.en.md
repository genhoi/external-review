# Smoke task (not a review)

Do exactly this and nothing else:
1. Run `pwd`, `git log --oneline -3`, `git status --short`.
2. Run the tests: `.venv/bin/pytest -q`.
3. Create a file `smoke.txt` in the current directory with a single line `ok`.
4. As the final message, give a 5-line report: pwd; last commit; git status output; pytest result (how many passed); whether the file was created.
