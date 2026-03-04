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
3) **Identify the correct execution environment** by referring to `docs/ENVIRONMENTS.md` (Docker vs Host) to ensure tests run in the intended environment.
4) Decide placement:
   - `tests/` for actively maintained lightweight tests
   - Do not add new tests to `tests_legacy/` (archive for historical tests only)
   - If a heavy verification is required, add reproducible command/script under `tools/verification/`
5) Implement tests using project conventions (`unittest` or `pytest` as already used in the target area). Generate test cases using `pytest` conventions where possible.
6) Run required checks from the workflow doc (`make format`, `make lint`, minimum test target) or `pytest` (or `make test` if available) to verify they pass and cover the target code.
7) If needed, add/update reproducible real-data verification command under `tools/verification/`.
8) Refine tests if they fail or if coverage is insufficient. Report results and log locations.

## Required commands/permissions
- `make format`
- `make lint`
- `python3 -m unittest ...` or `pytest` (or project-equivalent target)
- file operations: to write test files/scripts/docs

## Example commands
- `python3 -m unittest tests.test_pipeline_detection -v`
- `pytest tests/test_my_module.py`
- `pytest --cov=src tests/`
- `docker exec sr_eval_gpu bash -lc "cd /workspace && /opt/venv_sr/bin/python tools/verification/run_probe_detector_parity_check.py ..."`
- `make format && make lint`

## Notes
- Keep lightweight tests deterministic and runnable by default. Mock external dependencies where appropriate.
- Document heavy verification paths explicitly (environment + command + output log path).
- Do not leave test policy implicit; link back to `docs/REGRESSION_TEST_WORKFLOW.md`.
- Refer to `docs/ai-workflow/LESSONS.md` for known testing pitfalls in this project.
- Follow the `Quality Bar` section in `AGENTS.md`.