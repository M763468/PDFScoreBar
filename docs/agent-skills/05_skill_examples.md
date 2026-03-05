# Skill Design Examples

These examples follow the repository-specific patterns (run.sh + artifacts).

## Generic Template (run.sh)

```bash
#!/bin/bash
set -euo pipefail
# 1. Prepare environment
mkdir -p artifacts
# 2. Execute command and redirect output
# your_command > artifacts/your_skill_output.txt
echo "Artifact generated: artifacts/your_skill_output.txt"
```

## repo-summary (Composite Skill)

Gather repository structure, dependency status, and recent logs.

- **run.sh**: `make repo-summary`
- **Output**: `artifacts/repo_summary.txt`

## tool-wrapper (Specific Tool Wrapper)

Wrap a complex script from `tools/` into a skill.

- **run.sh**: `python3 tools/your_tool.py [args] > artifacts/tool_results.txt`
- **Output**: `artifacts/tool_results.txt`

## model-eval (Evaluation Skill)

Execute evaluation suite and summarize metrics.

- **run.sh**: `./run_eval.sh > artifacts/eval_metrics.json`
- **Output**: `artifacts/eval_metrics.json`

By using these patterns, agents ensure deterministic behavior and context efficiency.
