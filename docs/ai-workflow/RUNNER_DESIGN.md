# AI Agent Runner Design

To support multiple coding agents (Codex, Gemini CLI, Claude, etc.), we keep the workflow state tool-agnostic. The repository itself stores the task state in Markdown files.

## Principles
- **State in Markdown**: All task progress, plans, and logs live in `docs/refactors/<TASK-ID>/`.
- **Agent-Agnostic**: Any agent can read these documents and understand the context and current progress.
- **Human-Reviewable**: Humans can easily track progress via Git diffs.

## Execution Flow
1.  **Selection**: The user or a high-level agent selects an execution engine (e.g., Gemini CLI for reasoning/architecting, Codex for surgical implementation).
2.  **Context Injection**: The engine reads the `Prompt.md`, `Plan.md`, and `Implement.md` from the task directory.
3.  **Execution**: The engine performs the task milestones, updating the files as it progresses.
4.  **Logging**: All decisions and results are logged in `Log.md`.

## Integration Examples

### Gemini CLI (Architect Mode)
```bash
gemini-cli "Review docs/refactors/BAR-001/Prompt.md and generate a milestone plan in Plan.md."
```

### Codex CLI (Implementation Mode)
```bash
codex exec --sandbox read-write "Implement Milestone M1 from docs/refactors/BAR-001/Plan.md, following the rules in Implement.md."
```

## Future Extension: Multi-Agent Orchestration
We can develop a small runner script that orchestrates multiple agents based on the task type or milestone difficulty, all sharing the same repository-stored state.
