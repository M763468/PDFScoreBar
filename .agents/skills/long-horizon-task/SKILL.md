---
name: long-horizon-task
description: Initialize and manage long-horizon development tasks with externalized state.
---

# long-horizon-task

## Purpose
Manage complex, multi-step development tasks by externalizing task state into repository-stored Markdown files. This allows for persistent progress tracking and agent-agnostic execution.

## Input
- Task ID (e.g., `BAR-001`)
- Optional Issue Number

## Output (respond in Japanese)
- Task directory initialization
- Status report (Plan progress, Log summary)
- Log entry creation

## Capabilities

### 1. `init-task`
Initialize a new task directory in `docs/refactors/<TASK-ID>/` using templates.
- **Action**: Run `tools/ai-workflow-tools/init_long_horizon_task.py <TASK_ID> [--issue <ISSUE_NUMBER>]`.

### 2. `check-status`
Review the progress of an existing long-horizon task.
- **Action**: 
    1. Read `docs/refactors/<TASK-ID>/Plan.md` to see completed/pending milestones.
    2. Read `docs/refactors/<TASK-ID>/Log.md` for the latest updates.
    3. Read `docs/refactors/<TASK-ID>/Benchmarks.md` for performance metrics.

### 3. `record-log`
Help the user or agent record a new entry in the `Log.md` file.
- **Action**: Append a timestamped entry to `docs/refactors/<TASK-ID>/Log.md`.

## Execution Loop for Agents
When this skill is active, the agent should:
1.  Verify the task directory and state files.
2.  Strictly follow `Implement.md` directives.
3.  Update `Log.md` after every successful milestone or significant decision.
4.  Run benchmarks and record results in `Benchmarks.md` if applicable.

## Notes
- This skill complements `issue-solver` for complex scenarios.
- Always use `Prompt.md` as the source of truth for requirements.
