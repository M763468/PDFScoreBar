#!/usr/bin/env python3
import argparse
import os
import re
import shutil
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(
        description="Initialize a new Long-Horizon Task directory from templates."
    )
    parser.add_argument("task_id", help="The ID of the task (e.g., REFACTOR-001)")
    parser.add_argument("--issue", help="Associated GitHub Issue number", type=int)
    args = parser.parse_args()

    # Security: Validate task_id to prevent path traversal
    if not re.match(r"^[a-zA-Z0-9_-]+$", args.task_id):
        print(
            f"Error: Invalid task_id '{args.task_id}'. Only alphanumeric, hyphens, and underscores are allowed."
        )
        return

    task_dir = os.path.join("docs", "long-horizon-tasks", args.task_id)
    template_dir = os.path.join("docs", "ai-workflow", "templates", "task")

    if os.path.exists(task_dir):
        print(f"Error: Task directory '{task_dir}' already exists.")
        return

    os.makedirs(task_dir, exist_ok=True)
    print(f"Created directory: {task_dir}")

    templates = ["Prompt.md", "Plan.md", "Implement.md", "Log.md", "Benchmarks.md"]
    for template in templates:
        src = os.path.join(template_dir, template)
        dst = os.path.join(task_dir, template)
        if os.path.exists(src):
            shutil.copy(src, dst)
            print(f"  - Created {template}")

            # Customizing Log.md with current date
            if template == "Log.md":
                with open(dst, "r") as f:
                    content = f.read()
                today = datetime.now().strftime("%Y-%m-%d")
                content = content.replace("[YYYY-MM-DD]", today)
                with open(dst, "w") as f:
                    f.write(content)
        else:
            print(f"Warning: Template '{src}' not found.")

    # Customizing Prompt.md if issue is provided
    if args.issue:
        prompt_path = os.path.join(task_dir, "Prompt.md")
        with open(prompt_path, "r") as f:
            lines = f.readlines()

        with open(prompt_path, "w") as f:
            for line in lines:
                if line.startswith("# Task:"):
                    f.write(f"# Task: {args.task_id} (Issue #{args.issue})\n")
                else:
                    f.write(line)
        print(f"  - Linked Issue #{args.issue} in Prompt.md")

    print(f"\nTask {args.task_id} initialized successfully in {task_dir}")
    print("Next steps:")
    print(f"1. Define task specification in {task_dir}/Prompt.md")
    print(f"2. Generate milestone plan in {task_dir}/Plan.md")


if __name__ == "__main__":
    main()
