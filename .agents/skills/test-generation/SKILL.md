---
name: test-generation
description: Generate and maintain project-aligned tests (unit + real-data verification hooks).
---

# test-generation

## Purpose
Generate, expand, and maintain test code and verification commands aligned with this repository's test policy.

## Input
- Source code files to test
- Expected behavior/requirements
- Existing test files (if any)

## Output (respond in Japanese)
- New or updated test files (e.g., `test_*.py`)
- Test execution results
- Real-data verification command/result (if behavior parity is relevant)

## Steps
1) Read `docs/REGRESSION_TEST_WORKFLOW.md` and follow its policy first.
2) Analyze the target source code to understand logic and edge cases.
3) Decide placement:
   - `tests/` for actively maintained lightweight tests
   - `tests_legacy/` only when heavy/special dependencies are unavoidable
4) Implement tests using project conventions (`unittest` or `pytest` as already used in the target area).
5) Run required checks from the workflow doc (`make format`, `make lint`, minimum test target).
6) If needed, add/update reproducible real-data verification command under `tools/verification/`.
7) Report results and log locations.

## Required commands/permissions
- `make format`
- `make lint`
- `python3 -m unittest ...` (or project-equivalent target)
- file operations: to write test files/scripts/docs

## Example commands
- `python3 -m unittest tests.test_pipeline_detection -v`
- `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- `docker exec sr_eval_gpu bash -lc "cd /workspace && /opt/venv_sr/bin/python tools/verification/run_probe_detector_parity_check.py ..."`

## Notes
- Keep lightweight tests deterministic and runnable by default.
- Document heavy verification paths explicitly (environment + command + output log path).
- Do not leave test policy implicit; link back to `docs/REGRESSION_TEST_WORKFLOW.md`.
