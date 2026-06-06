# Handover to Training Agent (experiment/cnn_classifier)

This document is historical. It records the old `experiment/cnn_classifier` worktree handover and should not be used as current operating guidance without checking active issues and the current branch policy.

## Historical context

- Original branch: `experiment/cnn_classifier`
- Original goal: train a lightweight CNN classifier to distinguish true barlines from false positives using accumulated local data.
- Original constraints included limited local GPU memory and local training artifacts under `logs/`.

## Current guidance

For current work, use:

- `docs/README.md` for the documentation map.
- `docs/BRANCH_POLICY.md` for branch policy.
- `AGENTS.md` for agent operating rules.
- `docs/dev/VALIDATION_POLICY.md` for validation selection.
- Active GitHub issues and PRs for current scope and acceptance.
- `docs/DEVLOG_CNN_TRAINING.md` and issue-specific docs for historical CNN context.

Do not use this file to decide current worktree, branch, or handoff behavior.
