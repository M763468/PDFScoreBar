# Skill Design Guidelines

Skills should follow three design rules.

## 1 Small scope

Good:

repo-tree run-tests lint-fix

Bad:

full-project-automation

Small skills allow the agent to combine them flexibly.

## 2 Deterministic output

A skill should produce consistent artifacts.

Example:

pytest -q \> artifacts/test_results.txt

Artifacts should be machine-readable whenever possible.

Examples:

test_results.txt coverage.json repo_tree.txt

## 3 Explicit inputs and outputs

Example SKILL.md:

name: repo-tree

purpose: Generate a repository directory overview

input: repository path

output: artifacts/repo_tree.txt

command: ./run.sh

This allows an agent to safely choose and execute the skill.
