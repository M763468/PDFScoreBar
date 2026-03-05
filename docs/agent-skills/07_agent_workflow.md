# Agent Workflow

Typical coding-agent workflow:

task: fix failing test

Steps:

1 Analyze repository structure

make repo-tree

2 Run tests

make tests

3 Inspect artifact

artifacts/test_results.txt

4 Modify code

5 Run tests again

6 Commit changes

This pattern allows long-running automated workflows.

Agent loop:

while task_not_complete:

    analyze state
    choose skill
    execute command
    read artifacts
    update plan

This architecture supports long-running agents that can work for
extended periods.
