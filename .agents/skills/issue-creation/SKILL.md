---
name: issue-creation
description: Draft a clear issue with Goal/Scope/Acceptance Criteria so AI can implement it.
---

# issue-creation

## Purpose
Draft a clear issue with Goal/Scope/Acceptance Criteria so AI can implement it, aligned with the project's GitHub Issue Templates.

## Input
- Background/goal
- Expected outcome
- Constraints
- Issue type (Bug / Feature / Task)

## Output (respond in Japanese)
Generate the content for one of the following templates located in `.github/ISSUE_TEMPLATE/`:
- **Feature**: For new features or implementation tasks.
- **Bug**: For bug reports and fixes.
- **Task**: For small chores, refactoring, or documentation.

The output should provide values for the template fields (e.g., `goal`, `scope`, `acceptance`, `base_branch`, etc.).
- 出力結果は、必ず `artifacts/issue-creation_output.txt` 等のファイルパスを明記して保存すること。

## Steps
1) Identify the issue type (Bug, Feature, or Task).
2) Refer to the corresponding template in `.github/ISSUE_TEMPLATE/`.
3) Draft the content:
   - **Goal/Background**: Clear statement of what and why.
   - **Scope (In / Out)**: Explicitly define boundaries.
   - **Acceptance Criteria**: Verifiable checklist.
   - **Branch Operations**: Suggest `base_branch` and `branch_name` (e.g., `feature/xxx` or `fix/xxx`).
4) Format the output so it can be easily used with `gh issue create`.
5) 標準出力が長い場合は `artifacts/` 以下のファイルにリダイレクトし、それを読み込むこと。

## Required commands/permissions
- gh: create issue (`gh issue create`)
- git: not required in most cases

## Example commands
To create an issue using a template:
- `gh issue create --template <template_file_name> --title "[Type] <summary>" --body-file <path_to_body_file>`
- Example for a Task: `gh issue create --template task.yml --title "[Task] Update documentation" --body-file drafted_issue.md`
- `<command> > artifacts/issue-creation_results.txt`

## Notes
- Always include Out-of-scope items to prevent scope creep.
- Ensure the `branch_name` follows the project's naming convention.
- The "Branch Operations" section is CRITICAL for the AI agent to know where to start and where to PR.
