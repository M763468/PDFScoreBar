# AI Agent Strategy Guideline (2026-02-25)

## 1. Purpose
Clarify roles for Gemini CLI and Codex to maximize OMR geometric logic implementation accuracy and speed.

## 2. Environment File Roles

| File | Role | Key Content |
| :--- | :--- | :--- |
| **`AGENTS.md`** | **Constitution** | Core mandates for all agents (Jules, Codex, Gemini). |
| **`.gemini/GEMINI.md`** | **Gemini OS Config** | Gemini-specific reasoning, vision-first analysis, and sub-agent delegation. |
| **`docs/ai-workflow/LESSONS.md`** | **Memory/Lessons** | Feedback loop for anti-patterns and heuristics. |

## 3. Gemini + Codex Collaboration Protocol
Gemini as "Architect/Reasoning Lead," Codex as "Precision Implementation/Verification Lead."

### 3.1. Contextual Asymmetry Leveraging
- **Gemini (Macro)**: Focuses on architectural intent, cross-file logic, and multi-modal (visual) root causes.
- **Codex (Micro)**: Focuses on local type safety, precise pathing, and existing repository conventions (e.g., `unit_size` scaling).
- **Strategy**: Gemini proposes a high-level plan; Codex refines it via `codex exec --sandbox read-only` to catch repository-specific integration risks.

### 3.2. Implementation-Verification Separation
- **Codex (Execution)**: Performs surgical code edits and initial unit-level verification in a sandbox.
- **Gemini (Validation)**: Performs final multi-modal verification (e.g., analyzing `debug_outputs/` overlays) and metric-based evaluation.
- **Goal**: Ensure that code is not only syntactically correct but also visually and geometrically sound.

### 3.3. Continuous Feedback Loop (LESSONS.md)
- **Mandate**: Both agents are responsible for documenting "learned heuristics" in `docs/ai-workflow/LESSONS.md`.
- **Triggers**:
    - When Codex identifies a recurring pattern that causes logic errors.
    - When Gemini identifies a visual artifact that leads to OMR false positives.
    - When a collaboration pattern (e.g., a specific `codex exec` prompt) proves highly effective.

### 3.4. Long-Horizon Task Execution (Multi-Step Refactors)
For complex tasks that require more than 3 implementation steps or multi-day progress, agents **must** use the [Long-Horizon Task Workflow](LONG_HORIZON_WORKFLOW.md).
- **Mandate**: Create a `docs/long-horizon-tasks/<TASK-ID>/` directory with standardized Markdown state files (`Prompt.md`, `Plan.md`, `Log.md`).
- **Benefit**: Ensures that any agent (Gemini or Codex) can resume the task with full context from the repository-stored state.

## 4. Best Practices for Prompts
- **Gemini -> Codex**: Be explicit about the sandbox requirements and the specific symbols to analyze.
- **Codex -> Gemini**: Provide concise diff summaries and highlight any deviations from Gemini's initial plan for reasoning review.
