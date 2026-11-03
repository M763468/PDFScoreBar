# Label Dictionary

[日本語](LABELS.ja.md)

This document standardizes label usage for this repository. Consistent labels are essential for automation, triage, and communication.
The authoritative list of existing labels is the repository's GitHub label list (`gh label list`). Issue templates under `.github/ISSUE_TEMPLATE/` apply some labels automatically.

## AI Agent Labels

| Label | Description | Usage |
| --- | --- | --- |
| `assign-to-jules` | Trigger label for Google Jules remote implementation. | Use only when you want Jules to start a remote GitHub-side implementation flow. |
| `ai:implement` | Optional metadata label for AI-implementable tasks. | Informational label for triage/search; not required for local Codex/gemini-cli collaboration. |
| `ai:review` | Optional metadata label for AI review requests. | Use on PR/Issue when you explicitly want AI review tracking. |

## Status Labels

| Label | Description | Usage |
| --- | --- | --- |
| `blocked` | Progress is blocked by an external dependency or a decision. | Apply this when work cannot proceed. Add a comment explaining the blocker. |

## Priority Labels

| Label | Description | Usage |
| --- | --- | --- |
| `priority:high` | High-priority task that should be addressed immediately. | Reserved for critical bugs or features that have a significant impact. |
| `priority:med` | Medium-priority task. | Default for most tasks that are part of the planned workflow. |
| `priority:low` | Low-priority task. | For minor improvements, refactoring, or non-urgent cleanup. |

## Scope Labels

Scope labels help estimate the effort required and decide whether an issue needs to be broken down.

| Label | Description | Usage |
| --- | --- | --- |
| `scope:small` | A small, self-contained change (e.g., <1 day of work). | Good for individual functions, bug fixes, or minor documentation updates. |
| `scope:medium` | A moderately sized change (e.g., 1-3 days of work). | Suitable for a new feature or a significant refactor. |
| `scope:large` | A large change that likely needs to be broken down (>3 days of work). | Use this for epics or complex features that should be split into smaller issues. |

## Issue Type Labels

| Label | Description | Usage |
| --- | --- | --- |
| `bug` | A bug report. | Identifies an issue that describes a defect in the code. |
| `feature` | A feature request. | For new functionality or enhancements. |
| `task` | A task or chore. | For maintenance, refactoring, documentation, or other non-feature/bug work. |

## Other labels in use

The following labels exist in the repository but have no repository-specific usage rule beyond their name
and GitHub description. Apply them descriptively; do not rely on them for automation.

| Label | Notes |
| --- | --- |
| `documentation` | Documentation improvements or additions; commonly combined with `task`. |
| `enhancement` | GitHub default; overlaps with `feature`. |
| `investigation` | Investigation-only work. |
| `refactor`, `regression`, `follow-up` | Descriptive classification. |
| `ready for review`, `has-pr`, `review-addressed`, `completed` | Status markers; no automation sets or reads them. |
| `duplicate`, `invalid`, `wontfix`, `question`, `good first issue`, `help wanted` | GitHub defaults. |
