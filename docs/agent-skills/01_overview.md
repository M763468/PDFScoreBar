# AI Coding Agent Skill System -- Overview

This document explains how to structure a repository so that coding
agents (Codex CLI, Gemini CLI, etc.) can safely and effectively perform
long-running tasks.

Core principles from the OpenAI "Skills + Shell + Compaction" approach:

-   Skills: reusable capability modules
-   Shell: deterministic execution environment
-   Artifacts: files that store outputs instead of large stdout logs
-   Agent loop: task → choose skill → run command → inspect artifact →
    repeat

Key design idea:

LLM reasoning should **not directly generate complex shell commands
repeatedly**. Instead, it should call **stable, reusable skills** that
wrap deterministic commands.

Agent loop:

1.  Understand task
2.  Select skill
3.  Execute shell command or Make target
4.  Read artifact files
5.  Continue reasoning

This approach improves:

-   reproducibility
-   stability
-   long task execution
-   compatibility across coding agents
