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
- Coverage report (if requested)
- Real-data verification command/result (if behavior parity is relevant)
- **Artifact**: `artifacts/test_results.txt`

## Steps

Run commands from the repository root.
1) Read `docs/REGRESSION_TEST_WORKFLOW.md` and follow its policy first.
2) Analyze the target source code to understand logic and edge cases.
3) **Identify the correct execution environment** by referring to `docs/ENVIRONMENTS.md` (Docker vs Host) to ensure tests run in the intended environment.
4) Decide placement:
   - `tests/` for actively maintained lightweight tests
   - Do not add new tests to `tests_legacy/` (archive for historical tests only)
   - If a heavy verification is required, add reproducible command/script under `tools/verification/`
5) Implement tests using project conventions (`unittest` or `pytest` as already used in the target area). Generate test cases using `pytest` conventions where possible.
6) Run `bash .agents/skills/test-generation/run.sh [test_path]` for targeted pytest output to `artifacts/test_results.txt`, then run `make test-fast` when applicable. For real-data parity or pipeline-sensitive changes, run the issue-specific verification command.
7) Read `artifacts/test_results.txt` to confirm success or debug failures.
8) Verify test code style with `make format` and `make lint`.
9) Refine tests if they fail or if coverage is insufficient. Report results and log locations.

## Required commands/permissions
- `bash .agents/skills/test-generation/run.sh`: script to run pytest and output to `artifacts/`
- make: to run `make format`, `make lint`, `make test-fast`, plus issue-specific pytest or smoke commands
- file operations: to write test files/scripts/docs

## Example commands
- `bash .agents/skills/test-generation/run.sh tests/test_pipeline_detection.py`
- `make test-fast` plus issue-specific pytest or smoke commands as required by the issue
- `docker exec sr_eval_gpu bash -lc "cd /workspace && /opt/venv_sr/bin/python tools/verification/run_probe_detector_parity_check.py ..."`
- `make format && make lint`

## Notes
- Keep lightweight tests deterministic and runnable by default. Mock external dependencies where appropriate.
- Document heavy verification paths explicitly (environment + command + output log path).
- Do not leave test policy implicit; link back to `docs/REGRESSION_TEST_WORKFLOW.md`.
- Refer to `docs/ai-workflow/LESSONS.md` for known testing pitfalls in this project.
- Follow the `Quality Bar` section in `AGENTS.md`.
