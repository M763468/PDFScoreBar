---
name: dependency-management
description: Ensure consistency between dependency declarations and actual imports in the codebase.
---

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
- **Artifact**: `artifacts/dependency_status.txt`

## Steps
1) Run `./run.sh` to gather the current dependency status into an artifact.
2) Read `artifacts/dependency_status.txt` to analyze the environment.
3) Scan the codebase for all import statements.
4) Compare imports against declared dependencies.
5) Identify missing or unused dependencies.
6) Update the dependency files if required.
7) Verify installation using `uv sync` or `pip install`.

## Required commands/permissions
- `./run.sh`: script to gather dependency status into `artifacts/`
- uv / pip: to manage packages
- grep/search: to find imports

## Example commands
- `./run.sh`
- `uv sync`

## Notes
- Distinguish between production and development dependencies.
- Prefer `uv` if available as per project policy.
