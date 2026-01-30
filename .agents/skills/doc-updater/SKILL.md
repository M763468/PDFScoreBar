# doc-updater

## Purpose
Update documentation (README, API docs, inline comments) to reflect code changes and maintain accuracy.

## Input
- Changed source code files
- Existing documentation (README.md, docs/*.md)
- PR description or change summary

## Output (respond in Japanese)
- Updated markdown files
- Updated docstrings
- Verification that docs match the code

## Steps
1) Identify which parts of the code have changed (new features, changed parameters, etc.).
2) Scan existing documentation for outdated information.
3) Update `README.md`, `docs/`, and inline docstrings to match the new reality.
4) Verify formatting and clarity of the documentation.

## Required commands/permissions
- file operations: to read and write documentation files
- grep/search: to find relevant documentation sections

## Example commands
- `grep -r "OldFunctionName" docs/`

## Notes
- Keep documentation concise and up-to-date.
- Check for broken links if filenames changed.
