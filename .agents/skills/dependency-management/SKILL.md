# dependency-management

## Purpose
Ensure consistency between `requirements.txt`, `pyproject.toml`, and actual imports in the codebase.

## Input
- `requirements.txt` / `pyproject.toml`
- Source code imports
- `uv` or `pip` environment status

## Output (respond in Japanese)
- Updated `requirements.txt` or `pyproject.toml`
- Report on missing or unused dependencies
- Verification of successful installation

## Steps
1) Scan the codebase for all import statements.
2) Compare imports against declared dependencies in `requirements.txt` or `pyproject.toml`.
3) Identify missing dependencies (used but not listed) and unused dependencies (listed but not used).
4) Update the dependency files accordingly.
5) Verify installation using `uv sync` or `pip install`.

## Required commands/permissions
- uv / pip: to manage packages
- grep/search: to find imports

## Example commands
- `uv sync`
- `pip freeze`
- `grep -rE "^\s*(import|from) " src/`

## Notes
- Distinguish between production and development dependencies.
- Prefer `uv` if available as per project policy.
