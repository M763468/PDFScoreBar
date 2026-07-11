# PR slice validation workflow

This document defines the lightweight local validation path for focused PRs.
It is intended to prevent formatter-only follow-up commits and to make focused pytest sets reusable across review iterations.

## Before pushing a focused PR

Run the slice validation command from the repository root:

```bash
bash scripts/check_pr_slice.sh issue236-apply-corrections
```

The command runs:

1. `make lint`
2. the pytest entries listed in `scripts/pr_validation_profiles/issue236-apply-corrections.txt`

A run summary and logs are written under `artifacts/pr_slice_validation/`.

## Avoiding formatter-only commits

Before committing or before pushing review updates, run:

```bash
make format
bash scripts/check_pr_slice.sh issue236-apply-corrections
```

or use the runner's mutating convenience option:

```bash
bash scripts/check_pr_slice.sh issue236-apply-corrections --fix
```

`--fix` runs `make format` before validation. It may modify files, so inspect `git diff` before committing.

For a lint-only check, use:

```bash
bash scripts/check_pr_slice.sh issue236-apply-corrections --lint-only
```

For a focused pytest rerun after lint is already known to pass, use:

```bash
bash scripts/check_pr_slice.sh issue236-apply-corrections --pytest-only
```

## Adding a focused test profile

Create a new text file under `scripts/pr_validation_profiles/`:

```text
scripts/pr_validation_profiles/<profile-name>.txt
```

Rules:

- Use one pytest argument per line.
- Blank lines and lines starting with `#` are ignored.
- Keep profile names tied to issue or feature scope, for example `issue241-pr-validation` or `issue236-apply-corrections`.
- Prefer stable, lightweight tests that do not require GPU, Docker, model artifacts, or full evaluation data.
- If a slice needs heavier validation, keep that requirement in the PR body and in `docs/dev/VALIDATION_POLICY.md` terms instead of hiding it inside the lightweight profile.

List available profiles with:

```bash
bash scripts/check_pr_slice.sh --list-profiles
```

## Optional local hook

Hooks are opt-in. Do not commit `.git/hooks/` files.

A local pre-push hook can run a lint-only check:

```bash
cat > .git/hooks/pre-push <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
bash scripts/check_pr_slice.sh issue236-apply-corrections --lint-only
HOOK
chmod +x .git/hooks/pre-push
```

Use a full profile hook only when the focused pytest set is fast enough for normal pushes.

## GitHub Actions coverage

The PR validation workflow in `.github/workflows/pr-validation.yml` currently runs `make lint` on pull requests and manual dispatches.

Focused pytest is intentionally not enabled in GitHub Actions yet. This repository can require optional or heavy dependencies such as PyMuPDF, OpenCV, torch-related packages, OCR backends, Docker, GPU, or model artifacts depending on which tests are selected. Until a stable CI dependency layer is defined, focused pytest remains a local profile-based check.

When CI dependency setup becomes reliable, extend the workflow with a profile command such as:

```bash
bash scripts/check_pr_slice.sh issue236-apply-corrections --pytest-only
```

Document the selected profile and dependency assumptions in the same PR.
