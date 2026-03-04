# AI Agent Workflow Documentation

This directory contains guidelines and methodologies for AI-driven development in this repository.

## Table of Contents

- [AI Agent Strategy 2026](AI_AGENT_STRATEGY_2026.md): High-level strategy for Gemini and Codex collaboration.
- [Long-Horizon Task Workflow](LONG_HORIZON_WORKFLOW.md): Detailed methodology for complex, multi-step development tasks. (NEW)
- [General Workflow](WORKFLOW.md): Standard GitHub issue-based development loop.
- [Codex & Gemini Collaboration](CODEX_GEMINI_COLLAB.md): Practical tips for using both agents together.
- [Lessons Learned](LESSONS.md): Repository of anti-patterns and heuristics.
- [Label Dictionary](LABELS.md): Standardized GitHub labels for AI tasks.
- [Prompt Library](PROMPTS.md): Useful prompt snippets and patterns.

## Which workflow to use?

| Task Complexity | Recommended Workflow |
| :--- | :--- |
| Simple bug fix, minor feature | [General Workflow](WORKFLOW.md) (Issue -> Branch -> PR) |
| Large refactor, optimization, multi-step migration | [Long-Horizon Task Workflow](LONG_HORIZON_WORKFLOW.md) (File-based State) |

---

**TIP:** 開発効率を最大化するために、`.agents/skills/` にある専用の AI スキル（`issue-solver`, `pr-review` など）を積極的に活用してください。詳細は [General Workflow](WORKFLOW.md) のスキルセクションを参照してください。
