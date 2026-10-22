---
name: ci-diagnose
description: Diagnose a failing GitHub Actions job when the log is truncated or the cause is unclear (timeouts, load-dependent failures, "passes locally"). Use before guessing at a fix for a red CI check.
---

# Diagnose a red CI check

1. **Find the failing job**, not the aggregate gate. `All required checks pass (v2)` only mirrors the others. List the run's jobs and take the ones with `conclusion: failure`.
2. **Read the tail first** (`get_job_logs`, `tail_lines` up to 5000; the API returns only the tail). Large results are saved to a file: parse them with `python3`, never read them whole.
3. **Check whether it is the PR's.** Compare with the same job on `main`. A job red on both is not the PR's: port or write the fix, and leave one comment on the PR naming the failing check.
4. **If the cause is not in the tail** (the runner prints a check's output as one block when it finishes, so it can be far from the end; `run-workspace-checks.mjs` does this), push a throwaway `ci/diag-*` branch with a workflow that runs the failing command alone:
   - run each step as `rc=0; cmd > "$RUNNER_TEMP/x.log" 2>&1 || rc=$?` (under `bash -e` a failing step exits before it prints anything);
   - print `== step exit $rc` and the grep'd failure lines plus `tail -60` of failed logs;
   - reproduce load-dependent failures with background CPU hogs (`while :; do :; done`, one per core).
5. **Classify before fixing.** Timeouts on a slower runner are a limit to raise (per-lane, not global); a race in a test is fixed in the test; never skip or quarantine a test. A run where only some jobs fail on the same commit is a runner-speed or flake signal, not a code bug.
6. **Ship small**: one PR per cause, `scripts/run_tests.sh` for the touched test file, merge when the run is green, then bring `main` into the other open PRs.
7. **Clean up**: diag branches are never merged; delete them when the sandbox allows, otherwise tell the user.
