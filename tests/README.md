# Tests directory policy

`tests/` is development and validation code; no test or fixture is part of the minimum
executable package. The exact test-module roles are classified in
`docs/MINIMAL_MAINLINE_SURFACE.json`: maintained runtime contracts, validation harnesses,
developer tools, and retained reproduction checks. An Issue-numbered filename does not by
itself make a test obsolete.

Use `make test-fast` for the maintained lightweight pre-PR gate. Other tests may need
different dependencies or retained evidence; select them according to
`docs/dev/VALIDATION_POLICY.md` and their specific contract. Keep tests deterministic and
use synthetic or temporary inputs where practical. OpenCV-backed unit tests are acceptable
under those conditions.

If a test requires a server/network dependency, GPU/model runtime, or large real data, first reduce it
to a deterministic unit/contract test where possible. Otherwise track it as an explicit integration
test with documented environment requirements; do not create a second `tests_legacy/` surface.


## Execution gates

`make test-fast` runs the maintained CPU-only subset. `make test-node-contract`
requires both Python/pytest and Node and exercises JavaScript in a simulated DOM; it
is not a browser acceptance test. The persistent pytest container may not have Node:
use an existing host with both dependencies, or a runner providing both. Use the
prepared Playwright/Chromium image for actual browser acceptance as described in
`docs/dev/LOCAL_VALIDATION.md`.

`make test` collects all tests; it does not establish that GPU, real-data or browser
acceptance ran. The real PDF pipeline integration test is explicitly opt-in with
`PDFSCORE_RUN_REAL_INTEGRATION=1`; it requires the configured PDF, model assets and
compatible GPU runtime. It uses a temporary run, config and output directories. Record
skipped tests separately from passed tests; an opt-in skip is not a passing E2E gate.
Before running, verify input and runtime identity and preserve existing data. GPU smoke
and real-data integration remain separate from the lightweight PR jobs.
