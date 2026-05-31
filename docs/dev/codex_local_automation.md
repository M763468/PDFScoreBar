# Codex Local Automation

Issue #173 adds optional local automation entrypoints for Codex app, Codex CLI, WSL, and GitHub CLI work. These helpers are intended to make local validation repeatable without replacing normal manual development.

## Roles

- Codex app: local implementation, file edits, lightweight command execution, PR and issue context.
- WSL/Linux shell: authoritative local runtime for Docker, GPU, datasets, and long-running validation.
- Codex CLI: optional focused review or fix loop through `codex exec`.
- GitHub CLI: PR comments, review context collection, and authenticated GitHub operations.
- GitHub/web ChatGPT/Codex Cloud: static review and small GitHub edits. Treat those results as non-final for GPU and pipeline behavior.
- Human: final full evaluation decision, result interpretation, and merge to `main`.

## Baseline Workflow

1. Keep the existing main clone on its current work. If it is already serving another issue, do not checkout branches or edit files there.
2. Fetch from the main clone, then create a dedicated issue worktree:

   ```bash
   cd /home/masaki_muramatsu/ws_PDFScoreBar
   git fetch origin
   git worktree add ../ws_PDFScoreBar_issue173 -b issue-173-codex-local-automation origin/main
   cd ../ws_PDFScoreBar_issue173
   ```

3. If local-only assets are needed, link them into the worktree:

   ```bash
   make setup-local-worktree-links LOCAL_DATA_ROOT=/path/to/pdfscore-local-assets
   ```

4. Implement changes using the usual repository commands. The automation scripts are optional.
5. Run the lightest relevant validation first:

   ```bash
   make test-fast
   ```

6. For pipeline or GPU-sensitive changes, run:

   ```bash
   make verify-gpu-smoke
   ```

7. If full evaluation should start early, use the explicit long-running entrypoint:

   ```bash
   make verify-full-eval
   ```

8. For PR validation and optional posting:

   ```bash
   scripts/local_pr_validation.sh --pr 123 --with-gpu --post-comment
   ```

## Local Actions for Codex App

Useful commands to expose or run from Codex app:

- `make test-fast`
- `make verify-pipeline-smoke`
- `make verify-gpu-smoke`
- `make verify-full-eval`
- `scripts/gpu_smoke.sh --metadata-only`
- `scripts/local_pr_validation.sh --pr <number> --with-gpu --with-full-eval --post-comment`
- `scripts/respond_to_pr_review.sh --pr <number>`
- `scripts/setup_local_worktree_links.sh --source <path>`

Codex app sandbox approvals are session-level behavior. The repository cannot grant automatic sandbox-outside execution for only one script. If GPU, Docker, `gh`, or network access requires approval, run the command with the app's normal approval flow and document the command and log path.

## Validation Levels

- Fast tests: `make test-fast`. Intended for ordinary code and docs-adjacent changes; it runs no-real-data unit tests and intentionally excludes the real-data integration test. In a worktree, it uses local `.venv_pdf` when present and falls back to the sibling manager clone's `.venv_pdf` if available.
- Pipeline smoke: `make verify-pipeline-smoke`. Wraps the existing `make run-smoke`.
- GPU smoke: `make verify-gpu-smoke`. Records branch, commit, Python version, GPU info, command, exit code, and log path under `logs/system/`.
- Full evaluation: opt-in long run through `make verify-full-eval` or `scripts/local_pr_validation.sh --with-full-eval`. Start it early when the change clearly needs long evaluation, but do not make it a default PR requirement.

## GitHub CLI Requirements

Run once in the local environment:

```bash
gh auth login
gh auth status
```

Scripts that post comments use `gh pr comment --body-file`. If `gh` is missing, unauthenticated, or blocked by network/sandbox limits, the scripts should leave a local summary and report the skipped posting reason.

## Review Comment Loop

Use the PR review entrypoint to collect context:

```bash
scripts/respond_to_pr_review.sh --pr <number>
```

This writes artifacts under `artifacts/`. A human or Codex app can read the artifact, apply only actionable requested fixes, run targeted validation, and post a summary. Use `--codex` only when `codex exec` is installed and the checkout is clean enough for review planning.

## Web ChatGPT or GitHub Edits

Web-based edits are acceptable for small docs or code changes, but they do not have local dataset, Docker, or GPU context. After web edits:

1. Pull the branch into a dedicated local worktree.
2. Inspect the diff locally.
3. Run `make test-fast` or stronger validation as appropriate.
4. Post local validation results to the PR.

## Safety Boundaries

- These scripts do not merge to `main`.
- They do not require GPU smoke for docs-only or trivial changes.
- They do not update evaluation values, thresholds, filters, seeds, dataset selection, or metrics.
- They do not move or delete local datasets, logs, models, or caches.
- Normal manual development remains valid without using these scripts.
