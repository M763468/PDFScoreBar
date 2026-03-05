---
name: test-generation
description: Generate and maintain pytest-based tests to validate behavior and quality.
---

# test-generation

## Purpose
Generate, expand, and maintain test code using pytest to ensure code quality and coverage.

## Input
- Source code files to test
- Expected behavior/requirements
- Existing test files (if any)

## Output (respond in Japanese)
- New or updated test files (e.g., `test_*.py`)
- Test execution results
- Coverage report (if requested)
- **Artifact**: `artifacts/test_results.txt`

## Steps
1) Analyze the target source code to understand its logic and edge cases.
2) **Identify the correct execution environment** by referring to `docs/ENVIRONMENTS.md`.
3) Determine the test strategy (unit tests, integration tests) following existing patterns.
4) Generate test cases using `pytest` conventions.
5) Run `./run.sh [test_path]` (or `make test`) to verify tests and output results to `artifacts/test_results.txt`.
6) Read `artifacts/test_results.txt` to confirm success or debug failures.
7) Verify test code style with `make format` and `make lint`.
8) Refine tests if they fail or if coverage is insufficient.

## Required commands/permissions
- `./run.sh`: script to run pytest and output to `artifacts/`
- make: to run `make format`, `make lint`, `make test`

## Example commands
- `./run.sh tests/test_my_module.py`
- `make test`

## Notes
- Ensure tests are independent and deterministic.
- Mock external dependencies where appropriate.
- Refer to `docs/ai-workflow/LESSONS.md` for known testing pitfalls.
- Follow the `Quality Bar` section in `AGENTS.md`.
