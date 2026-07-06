---
name: python-api-explorer
description: Extract classes, methods, and docstrings from a Python file to understand its API without reading the full source.
---

# python-api-explorer

## Purpose
Quickly understand the interface of a Python module or class. This is more token-efficient than reading the entire file, as it only extracts definitions and high-level documentation.

## Output (respond in Japanese)
- API Index including class names, method signatures, and first-line docstrings.
- **Artifact**: `artifacts/api_index.txt`

## Steps

Run commands from the repository root.
1) Run `bash .agents/skills/python-api-explorer/run.sh path/to/python_file.py` to extract API info.
2) Read `artifacts/api_index.txt` to understand available functions and methods.
3) Use this information to decide how to call or modify the module.

## Required commands/permissions
- `bash .agents/skills/python-api-explorer/run.sh`: script using Python AST to extract API info into `artifacts/`
- python3: for the extractor script

## Example commands
- `bash .agents/skills/python-api-explorer/run.sh src/common/utils.py`
