# Gemini Behavioral Mandates

## Core Principles
- **Explicit Commit Authorization**: You **MUST NOT** execute `git commit` or `git push` unless specifically requested by the user's Directive (e.g., "Execute the commit"). You must not combine the inquiry ("Shall I commit?") and the execution (`git commit`) in the same turn.
- **Mandatory Planning**: Always use \`enter_plan_mode\` for non-trivial tasks before modification.
- **Vision-First Debugging**: When debugging geometric or visual issues, prioritize the analysis of visual evidence by leveraging multi-modal capabilities whenever relevant images are available (e.g., in `debug_outputs/` or `logs/` subdirectories). If such artifacts are present, use them to confirm hypotheses and identify root causes.
- **Sub-agent Delegation**: Actively use \`codex exec\` via the \`codex-delegation\` skill for precision file edits, complex repository audits, and local test verification. Treat Codex as a specialized implementation and verification lead to minimize context overhead in the main Gemini session.
- **Resolution Independence**: Strictly adhere to the \`unit_size\` (staff spacing) scaling rule for all geometric calculations.
- **Tool Preference over Shell Tricks**: **ALWAYS** use dedicated tools (like `write_file`, `replace`, etc.) instead of shell redirections (`>`), heredocs (`<<EOF`), or `cat` inside `run_shell_command`. This prevents syntax errors and excessive security confirmation prompts for the user.
- **PR Creation Standard**: When creating or editing a Pull Request via `gh pr create` or `gh pr edit`, you **MUST** first read `.github/pull_request_template.md` and strictly format your PR body according to its structure and headings.

## Verification & Quality Bar
- **PR Review Retrieval Standard**: When checking PR feedback, use `gh pr view <number> --json title,body,comments,reviews` to fetch all context (including inline comments) in a single turn. Avoid multiple calls to `gh pr view --comments` and `gh api`.
- **Pre-Delivery Check**: Before finalizing any code change or creating a Pull Request, you **MUST** run `make format` and `make lint` to ensure adherence to project-wide standards.
- **Zero-Tolerance for Lint/Format Errors**: If `make format` or `make lint` fails, do not report completion. Fix all issues before providing the final report.
- **Task Integrity (Long-Horizon)**: For any task using the `long-horizon-task` skill, ensure that `task_id` is always validated against the regex `^[a-zA-Z0-9_-]+$` to prevent security vulnerabilities.

## Specialized Skills
- **Multi-modal Review**: Analyze OMR overlay images to identify the root cause of False Positives/Negatives.
- **Heuristic Feedback**: Refer to `docs/ai-workflow/LESSONS.md` before finalizing design changes to avoid regression.

## Agent Workflow & Skill Evolution
- **Artifacts First**: Standard outputs for repetitive or verbose commands MUST be redirected to `artifacts/` to prevent polluting the context window (e.g., `pytest > artifacts/test_results.txt`).
- **Make-First Approach**: Always check `make help` for available targets. Use Make targets as the primary entry point for executing tasks.
- **Self-Evolving Skills**: If you repeat the same shell command sequence 2-3 times, propose turning it into a new Make target or a new skill in `.agents/skills/`.
- **Skill Creation**: Use the `skill-creator` tool to standardize and document new skills as they emerge, rather than prematurely attempting to unify complex scripts.
