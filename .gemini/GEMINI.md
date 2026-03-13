# Gemini Behavioral Mandates

## Core Principles
- **Explicit Commit Authorization**: You **MUST NOT** execute `git commit` or `git push` unless specifically requested by the user's Directive (e.g., "Execute the commit"). You must not combine the inquiry ("Shall I commit?") and the execution (`git commit`) in the same turn.
    - **Interactive Tasks**: For normal/interactive requests, stop after implementation/verification and wait for the user's review and commit approval. **NEVER** assume a "Shall I commit?" question implies immediate permission to commit in the same response.
    - **Long-Horizon Exceptions**: Only when executing within the `long-horizon-task` skill framework (following `Plan.md`), you are permitted to commit at defined milestones to persist progress, provided all changes are logged in `Log.md`.
- **Mandatory Planning**: Always use \`enter_plan_mode\` for non-trivial tasks before modification.
- **Vision-First Debugging**: When debugging geometric or visual issues, prioritize the analysis of visual evidence by leveraging multi-modal capabilities whenever relevant images are available (e.g., in `debug_outputs/` or `logs/` subdirectories). If such artifacts are present, use them to confirm hypotheses and identify root causes.
- **Sub-agent Delegation**: Actively use \`codex exec\` via the \`codex-delegation\` skill for precision file edits, complex repository audits, and local test verification. Treat Codex as a specialized implementation and verification lead to minimize context overhead in the main Gemini session.
- **Resolution Independence**: Strictly adhere to the \`unit_size\` (staff spacing) scaling rule for all geometric calculations.
- **Tool Preference over Shell Tricks**: **ALWAYS** use dedicated tools (like `write_file`, `replace`, etc.) instead of shell redirections (`>`), heredocs (`<<EOF`), or `cat` inside `run_shell_command`. This prevents syntax errors and excessive security confirmation prompts for the user. (Note: Using `>` or other standard shell features inside dedicated `.sh` scripts like those in `.agents/skills/` is perfectly fine and expected).
- **PR Creation Standard**: When creating or editing a Pull Request via `gh pr create` or `gh pr edit`, you **MUST** first read `.github/pull_request_template.md` and strictly format your PR body according to its structure and headings.
- **Safe Command Input**: When posting PR/Issue comments, issue descriptions, or any text containing code snippets (backticks) via `gh`, you **MUST** use `--body-file` with a temporary file to avoid shell expansion errors and data corruption.

## Verification & Quality Bar
- **PR Review Retrieval Standard**: When checking PR feedback, use `gh pr view <number> --json title,body,comments,reviews` to fetch all context (including inline comments) in a single turn. Avoid multiple calls to `gh pr view --comments` and `gh api`.
- **Pre-Delivery Check**: Before finalizing any code change or creating a Pull Request, you **MUST** run `make format` and `make lint` to ensure adherence to project-wide standards.
- **Zero-Tolerance for Lint/Format Errors**: If `make format` or `make lint` fails, do not report completion. Fix all issues before providing the final report.
- **Task Integrity (Long-Horizon)**: For any task using the `long-horizon-task` skill, ensure that `task_id` is always validated against the regex `^[a-zA-Z0-9_-]+$` to prevent security vulnerabilities.

## Specialized Skills
- **Multi-modal Review**: Analyze OMR overlay images to identify the root cause of False Positives/Negatives.
- **Heuristic Feedback**: Refer to `docs/ai-workflow/LESSONS.md` before finalizing design changes to avoid regression.

## Agent Workflow & Skill Evolution
- **No Temporary Docs in `docs/`**: Do NOT create temporary or issue-specific planning documents (e.g., `docs/ISSUE59_PLAN.md`) directly in the `docs/` directory. All transient files MUST be placed in `temp/` or `artifacts/` to avoid confusion regarding their completion status. For multi-step tasks, strictly follow the `long-horizon-task` skill structure (`docs/refactors/<TASK_ID>/`).
- **Artifacts First**: Standard outputs for repetitive or verbose commands MUST be redirected to `artifacts/` to prevent polluting the context window (e.g., `pytest > artifacts/test_results.txt`).
- **Make-First Approach**: Always check `make help` for available targets. Use Make targets as the primary entry point for executing tasks.
- **Self-Evolving Skills**: If you repeat the same shell command sequence 2-3 times, propose turning it into a new Make target or a new skill in `.agents/skills/`.
- **Skill Creation**: Use the `skill-creator` tool to standardize and document new skills as they emerge, rather than prematurely attempting to unify complex scripts.

## Tool & Shell Permissions
- **Trusted Commands**: The following commands are pre-approved and do not require explicit user confirmation for each execution:
  - `cat`: For reading file contents (especially artifacts).
  - `./run.sh`: All `run.sh` scripts within `.agents/skills/` subdirectories.
  - `make help`, `make repo-tree`: Standard read-only Makefile targets.
- **Artifact Access**: Always prefer using `cat` or `read_file` to inspect the contents of `artifacts/` generated by skills.

# GEMINI.md - Project Specific Context

## Current Status (2026-03-14)
- **Issue #13 (Full Pipeline & Batch Optimization)**: Completed.
    - `src/pipeline/main.py` is the primary entry point.
    - Batch MMR processing and model persistence are verified.
    - Resource efficient execution (RTX 4060 8GB) is the baseline.
- **Issue #95 (Repo Mapping)**: Completed.
    - Repository structure and asset registry defined in `docs/MANIFEST.md`.

## Repository Navigation (Mandatory)
1. **Always check `git log -n 10`** at the start of a session. Static docs (like `NEXT_SESSION_NOTES.md`) may be stale.
2. **Prioritize `docs/MANIFEST.md`** for official model paths and configurations.
3. **Follow the Repository Map** in `README.md` to find the correct entry points.
4. **Update on Discovery**: If you find discrepancies between documentation and reality (wrong paths, outdated specs) during your task, **you MUST update the documentation immediately.**

## Strategic Priorities
1. **Mainline First**: Always use `src/pipeline/main.py` and `configs/evaluation2_e2e_verification_full.yaml` for end-to-end tasks.
2. **VRAM Efficiency**: Maintain the 8GB limit for batch processing. Load heavy models (Homr, MMR) once using the orchestrator's persistence mechanism.
3. **Collaborative Reasoning**:
   - Use `Codex` as a "Deep Auditor" for VRAM optimization and architectural changes.
   - Actively seek second opinions on high-complexity logic (see `AGENTS.md` Section 9).

## Project Memories
- MMR classifier (best_textnoise) achieves 98.7% Precision and 87.5% Recall on the evaluation dataset.
- Focus on VRAM efficiency (limit: 8GB) for batch processing.
