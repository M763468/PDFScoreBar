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
## Output (respond in Japanese)
- Task directory initialization
- Status report (Plan progress, Log summary)
- Log entry creation
- **Artifacts**: `artifacts/task_init.txt`, `artifacts/task_status.txt`

## Capabilities

### 1. `init-task`
Initialize a new task directory in `docs/refactors/<TASK-ID>/` using templates.
- **Action**: Run `./run.sh init <TASK_ID> [ISSUE_NUMBER]`.
- **Artifact**: `artifacts/task_init.txt`

### 2. `check-status`
Review the progress of an existing long-horizon task.
- **Action**: Run `./run.sh check <TASK_ID>`.
- **Artifact**: `artifacts/task_status.txt`

### 3. `record-log`
Help the user or agent record a new entry in the `Log.md` file.
- **Action**: Append a timestamped entry to `docs/refactors/<TASK-ID>/Log.md`.

## Required commands/permissions
- `./run.sh`: script to initialize or check task status into `artifacts/`
- python3: for the initialization tool

## Example commands
- `./run.sh init BAR-001 42`
- `./run.sh check BAR-001`


## Execution Loop for Agents
When this skill is active, the agent should:
1.  Verify the task directory and state files.
2.  Strictly follow `Implement.md` directives.
3.  Update `Log.md` after every successful milestone or significant decision.
4.  Run benchmarks and record results in `Benchmarks.md` if applicable.

## Notes
- This skill complements `issue-solver` for complex scenarios.
- Always use `Prompt.md` as the source of truth for requirements.
