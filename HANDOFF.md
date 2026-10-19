# Handoff: hermes-agent (strauss-visuals/hermes-agent)

Written 2026-10-19. Committed on `ci/standard-runners` so it survives the container; delete it before that branch merges.

## Done

- **PR #1 merged** into `main` as squash commit `1ad6b90` (the 16 code-review fixes).
  - Fixes: router `_DISK_TTL_SECONDS`, hardline `rm`/wrapper spellings, plugin-catalog hardening,
    curator snapshot extract, google_meet constant-time token, extract-plugins JSON safety.
  - Each fix has a test: `tests/tools/test_hardline_spellings.py`,
    `tests/hermes_cli/test_plugin_catalog_hardening.py`,
    `tests/plugins/model_providers/test_router_disk_cache.py`,
    `tests/agent/test_curator_extract_snapshot.py`,
    `tests/website/test_extract_plugins_raw_entries.py`.
- **Local verification of merged `main`:** `tests/tools` + `tests/agent` + `tests/plugins` gave
  22,949 passed / 33 failed. The same 33 fail on the pre-merge commit `0e427d78`, so none come from the PR.
  They look environmental (sandbox runs as root, no network): SSH, MCP supervisor, web tools,
  browser-use, file-safety mirror, vision routing, Windows paths, `test_approval.py::TestSensitiveRedirectPattern`.
  Also failing identically on `main`: 6 tests in `tests/tui_gateway/test_connector_*` and
  `tests/website/test_extract_plugins.py` (git dates).
- `python scripts/check` (12 checks) passes.

## Open problem: CI never runs the Python suite on this fork

The `*-32-core` runner labels have no runners here. Jobs on them (Python tests 1/2 and 2/2,
Windows-only tests x64/arm64, JS & TS checks, Rust tests) sat unassigned and the whole CI run on
`main` was **cancelled by GitHub at the 24h mark** (run 38860674958). Standard-runner jobs
(lint, docs, macOS, installer, remote backends) run and pass. So PR #1 was verified locally, not by CI.

## In progress

Branch `ci/standard-runners` (commit `ad8d60ab`, **pushed, no PR yet**) repoints those jobs:

| File | Change |
|---|---|
| `.github/workflows/tests.yml` | `test` job: `ubuntu-latest`, timeout 120, removed `HERMES_TEST_WORKERS: 32` (falls back to cpu_count) |
| `.github/workflows/tests-os.yml` | Windows rows: `windows-latest` and `windows-11-arm`, timeout 90 |
| `.github/workflows/js-tests.yml` | `ubuntu-latest`, timeout 60 |
| `.github/workflows/rust-tests.yml` | `ubuntu-latest`, timeout 60 |

`python scripts/check` passes on it. It has not been run in Actions yet.

Left alone on purpose: e2e jobs, `docker.yml`, `nix.yml`, `desktop-bundled-release.yml`, `sandbox-image.yml`,
`pm-bundle.yml`, `install-e2e-windows-run.yml`, and the Windows E2E job in `tests-os.yml`. They only run on dispatch or release.

## Next steps

1. Open a PR from `ci/standard-runners` into `main`. The PR's own CI run is the validation.
2. Watch the Python test shards. They were sized from my local runs (about 30 min for roughly 40% of the suite
   at 4 workers), so expect 40-70 min per slice. If a slice hits the 120 min timeout, raise the timeout or
   change `HERMES_TEST_SLICE` from `/2` to `/3` or `/4` (the matrix lives in `tests.yml`).
3. Expect the 33 environmental failures above to show up. Triage them: some may pass on a real GitHub runner
   (not root, has network) and some may be genuinely broken on `main`.
4. Windows jobs can hit Windows-only test issues that were never exercised here. Fix per failure.
5. Alternative to all of this: add larger runners in repo Settings -> Actions -> Runners and revert the labels.
   I could not change repo settings from the sandbox (the proxy blocks settings writes).
6. Repo setting still off: Settings -> General -> Pull Requests -> Allow auto-merge.

## Notes

- Remove `HANDOFF.md` from the branch before merging the CI PR.
- Working tree is on `ci/standard-runners`; `ccr-e94c3da3-9bxsu8` (merged) is stale and can be deleted.
- Run tests only through `scripts/run_tests.sh` (not bare pytest). Pre-push check: `python scripts/check`.
- Sandbox quirks: the auto-mode classifier denied `git reset --hard` and one shell redirect to a file. Use Read/Grep on log files instead.
- Do not add a model identifier to commits, PRs or code.
