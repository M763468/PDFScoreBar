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
2) Determine the test strategy (unit tests, integration tests).
3) Generate test cases using `pytest` conventions.
4) Run tests using `pytest` to verify they pass and cover the target code.
5) Refine tests if they fail or if coverage is insufficient.

## Required commands/permissions
- pytest: to run tests
- file operations: to write test files

## Example commands
- `pytest tests/test_my_module.py`
- `pytest --cov=src tests/`

## Notes
- Ensure tests are independent and deterministic.
- Mock external dependencies where appropriate.
