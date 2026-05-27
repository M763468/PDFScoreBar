# Branch Policy

This document defines the repository-wide branch policy. It is a standing rule for new work and release promotion; issue-specific decisions should be recorded in the relevant issue or PR by applying this policy, not by changing the general rule.

## Branch roles

- `develop` is the active integration branch.
- `main` is the stable/release branch.
- Normal feature, fix, refactor, documentation, and performance work must branch from `develop` and open PRs against `develop`, unless the issue explicitly states that the work is a release, hotfix, or promotion task.
- `develop -> main` must be done through a dedicated promotion PR. Do not promote changes to `main` through incidental feature PRs.

## Default issue and PR base

For normal work, use:

- Base branch: `develop`
- PR base: `develop`

If an older issue says `Base branch: main` or `PR base: main`, treat that text as stale unless the issue is explicitly about release, hotfix, or promotion work.

When starting older work, restate the effective branch decision in the working session or issue comment. Edit the issue body only when the stale branch text is likely to cause execution mistakes.

## Release, hotfix, and promotion exceptions

Use `main` directly only when the issue explicitly requires release-branch work, hotfix work, or promotion management.

For a `develop -> main` promotion PR, include at minimum:

- the normal compile, lint, test, or smoke checks relevant to the included changes
- the current canonical regression contract for the promoted scope
- a clear statement of which metrics are promotion gates and which metrics are reported as informational only
- links or references to the issues and PRs whose accepted changes are being promoted

Do not embed one issue's acceptance numbers as a permanent repository-wide rule. If a specific issue defines a canonical contract, apply that contract in the promotion PR for the relevant promotion cycle and cite the issue or PR where the contract was accepted.

## Documentation precedence

`AGENTS.md` is the operational entry point for AI agents. Agents must read this document through the `AGENTS.md` reference before starting issue work or opening PRs.

If an issue body, older comment, or ad-hoc instruction conflicts with this document, use this document as the default policy and call out the conflict before modifying files or opening a PR.
