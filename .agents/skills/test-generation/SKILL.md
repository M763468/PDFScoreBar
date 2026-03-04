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

## Steps
1) Analyze the target source code to understand its logic and edge cases.
2) **Identify the correct execution environment** by referring to `docs/ENVIRONMENTS.md` (Docker vs Host) to ensure tests run in the intended environment.
3) Determine the test strategy (unit tests, integration tests) following existing patterns in the `tests/` directory.
4) Generate test cases using `pytest` conventions.
5) Run tests using `pytest` (or `make test` if available) to verify they pass and cover the target code.
6) Verify test code style with `make lint` and `make format`.
7) Refine tests if they fail or if coverage is insufficient.

## Required commands/permissions
- pytest: to run tests
- make: to run `make lint`, `make format`
- file operations: to write test files

## Example commands
- `pytest tests/test_my_module.py`
- `pytest --cov=src tests/`
- `make lint && make format`

## Notes
- Ensure tests are independent and deterministic.
- Mock external dependencies where appropriate.
- Refer to `docs/ai-workflow/LESSONS.md` for known testing pitfalls in this project.
- Follow the `Quality Bar` section in `AGENTS.md`.
