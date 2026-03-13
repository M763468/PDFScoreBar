# Worktree Manager Skill

## Purpose
Manage git worktrees for different GitHub issues to allow parallel work without context contamination.

## Input
- `add <issue_number> <branch_name>`: Create a new worktree named `../ws_PDFScoreBar_issue<issue_number>` with the specified branch.
- `remove <issue_number>`: Remove the worktree associated with the issue.
- `list`: List all active worktrees.

## Steps
1. Call `./run.sh <command> <args>` from the project root.
2. The skill automatically handles directory naming (`../ws_PDFScoreBar_issueNNN`).

## Notes
- `artifacts/`, `logs/`, and other git-ignored files are NOT copied to the new worktree.
- Use `ln -s` manually if you need access to these directories in the worktree.
