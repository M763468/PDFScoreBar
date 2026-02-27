# Gemini Behavioral Mandates

## Core Principles
- **Mandatory Planning**: Always use \`enter_plan_mode\` for non-trivial tasks before modification.
- **Vision-First Debugging**: When debugging geometric or visual issues, prioritize the analysis of visual evidence by leveraging multi-modal capabilities whenever relevant images are available (e.g., in `debug_outputs/` or `logs/` subdirectories). If such artifacts are present, use them to confirm hypotheses and identify root causes.
- **Sub-agent Delegation**: Actively use \`codex exec\` for precision file edits and verification, treating Codex as a specialized implementation lead.
- **Resolution Independence**: Strictly adhere to the \`unit_size\` (staff spacing) scaling rule for all geometric calculations.

## Specialized Skills
- **Multi-modal Review**: Analyze OMR overlay images to identify the root cause of False Positives/Negatives.
- **Heuristic Feedback**: Refer to \`docs/ai-workflow/LESSONS.md\` before finalizing design changes to avoid regression.
