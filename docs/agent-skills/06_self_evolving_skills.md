# Self-Evolving Skill System

Agents can improve the skill library over time.

Basic loop:

task → run commands → detect repeated pattern → propose new skill → add
to skill registry

Example:

Agent repeatedly runs:

tree cloc pip freeze

It may propose:

skills/repo-summary/

run.sh

tree -L 3 \> artifacts/tree.txt cloc . \> artifacts/loc.txt pip freeze
\> artifacts/deps.txt

SKILL.md

name: repo-summary

purpose: Generate a quick repository overview

This converts repeated workflows into reusable capabilities.

Self-evolution rules:

1.  Detect repeated command sequences
2.  Extract them into a new skill
3.  Document the skill
4.  Add to registry
5.  Reuse in future tasks
