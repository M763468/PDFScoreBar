# Long-Horizon Task Workflow for AI Agents

## Overview
Long-horizon tasks (large refactoring, pipeline optimization, dependency upgrades, etc.) require multiple steps, persistent state, and iterative validation. 

Unlike simple tasks that can be solved with a single prompt, long-horizon tasks use **Externalized Task State** stored within the repository. This makes the workflow reproducible, tool-agnostic, and resumable by any agent (or human).

## Core Idea: Externalized Task State
Instead of storing progress only in the conversation history, the task state is written to specific Markdown files in `docs/refactors/<TASK-ID>/`.

### Required Documents
- **`Prompt.md`**: The task specification and "Source of Truth".
- **`Plan.md`**: Milestones and verification steps.
- **`Implement.md`**: Specific execution rules and sandbox constraints.
- **`Log.md`**: Execution history, decisions, and outcomes.
- **`Benchmarks.md`**: Metric tracking and comparison.

## Typical Workflow

1.  **Issue Creation**: Create a GitHub Issue with metrics and acceptance criteria.
2.  **Initialization**: Create a working branch `refactor/<TASK-ID>` and scaffold the task directory using `tools/ai-workflow-tools/init_long_horizon_task.py`.
3.  **Planning**: Read `Prompt.md` and generate `Plan.md` milestones. Do not modify production code yet.
4.  **Baseline**: Establish a baseline by running benchmarks and recording results in `Log.md` and `Benchmarks.md`.
5.  **Execution Loop**:
    - Implement the smallest change for the current milestone.
    - Run validation tools (tests, linters).
    - Record results and rationale in `Log.md`.
    - Update `Plan.md` progress.
6.  **PR Preparation**: Create a PR including a summary of changes, benchmark results, and compatibility notes.

## Agent Execution Loop

1.  Read `Prompt.md`
2.  Read `Plan.md`
3.  Implement smallest change
4.  Run validation tools
5.  Record results
6.  Update `Log.md`
7.  Repeat until all milestones are complete.

## Operating Policy

### Allowed Tasks
- Refactoring and structural improvements.
- Performance optimization.
- Dependency updates.
- Test improvements.

### Restrictions
- Do not change infrastructure without approval.
- Do not alter public API contracts without approval.
- Do not introduce new frameworks without explicit authorization.

### Validation Requirements
- Every change must pass CI and unit tests.
- Optimizations must be verified with benchmarks.

## Prompt Patterns for Agents

### Plan Generation
> Read `Prompt.md`. Generate `Plan.md` milestones. Do not modify production code. Stop after defining the baseline milestone.

### Execution Phase
> Follow `Plan.md` milestones. Rules: small changes only, run tests/benchmarks after each change, update `Log.md`.

## Risks and Controls

| Risk | Mitigation |
| :--- | :--- |
| **Incorrect Optimization** | Require benchmark verification. |
| **Semantic Changes** | Require golden tests / regression tests. |
| **Uncontrolled Scope** | Define "Non-Goals" in `Prompt.md`. |
| **Agent Drift** | Milestone-based validation and logging. |
| **Unreproducible Results** | Document exact benchmark commands and environment. |
