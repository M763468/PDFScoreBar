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
