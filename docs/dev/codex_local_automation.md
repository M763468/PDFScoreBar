# Codex Local Automation

Issue #173 adds optional local automation entrypoints for Codex app, Codex CLI, WSL, and GitHub CLI work. These helpers are intended to make local validation repeatable without replacing normal manual development.

Validation strength is governed by `docs/dev/VALIDATION_POLICY.md`. The scripts are helpers for applying that policy; they are not a reason to weaken required checks or ignore scope boundaries.

## Roles

- Codex app: local implementation, file edits, lightweight command execution, PR and issue context.
- WSL/Linux shell: authoritative local runtime for Docker, GPU, datasets, and long-running validation.
- Codex CLI: optional focused review or fix loop through `codex exec`.
- GitHub CLI: PR comments, review context collection, and authenticated GitHub operations.
- GitHub/web ChatGPT/Codex Cloud: static review and small GitHub edits. Treat those results as non-final for GPU and pipeline behavior.
- Human: final result interpretation and merge to the correct target branch. Normal issue work targets `develop`; `main` is for release/promotion flow.

## Baseline Workflow

1. Keep the existing manager clone on its current work. If it is already serving another issue, do not checkout branches or edit files there.
2. Fetch from the manager clone, then create a dedicated issue worktree from the correct base branch. Normal issue work uses `develop`:

   ```bash
   cd /home/masaki_muramatsu/ws_PDFScoreBar
   git fetch origin
   git worktree add ../ws_PDFScoreBar_issue173 -b issue-173-codex-local-automation origin/develop
   cd ../ws_PDFScoreBar_issue173
   ```

3. If local-only assets are needed, link them into the worktree:

   ```bash
   make setup-local-worktree-links LOCAL_DATA_ROOT=/path/to/pdfscore-local-assets
   ```

   To create the worktree and share generated outputs in one command, use:

   ```bash
   make setup-shared-worktree \
     BRANCH=issue-173-codex-local-automation \
     WORKTREE=/home/masaki_muramatsu/ws_PDFScoreBar_issue173 \
     SHARED_ROOT=/home/masaki_muramatsu/ws_PDFScoreBar
   ```

   This links `logs/` and `artifacts/` as well as available local datasets,
   caches, and virtual environments. Outputs remain in `SHARED_ROOT` after the
   issue worktree is removed.

4. Implement changes using the usual repository commands. The automation scripts are optional.
5. Run the lightest relevant validation first:

   ```bash
   make test-fast
   ```

6. For pipeline or GPU-sensitive changes, run:

   ```bash
   make verify-gpu-smoke
   ```

7. For evaluation-sensitive changes, run full evaluation when authorized by the user, issue, or PR context:

   ```bash
   make verify-full-eval
   ```

8. For PR validation and optional posting:

   ```bash
   scripts/local_pr_validation.sh --pr 123 --with-gpu --with-full-eval --post-comment
   ```

## When the manager worktree is busy

The manager worktree may be running another issue's long-lived command. Treat it as
occupied for the duration of that command. Run the new issue from its dedicated worktree
and keep its code, branch, and working directory there.

Separate the paths explicitly:

- `WORKTREE`: the issue worktree; tracked code and the command's working directory
- `MAIN_REPO`: the manager worktree; retained `logs/` and optionally read-only `data/`

For a host-only command, such as CNN training or an audit script, run it directly from
`WORKTREE`. Shared-output links or an explicit `MAIN_REPO/logs/` output path retain the
results without changing the manager checkout.

For a Docker command, mount the issue worktree as the code and `/workspace` root, then
mount manager data and logs separately:

```bash
MAIN_REPO=/home/masaki_muramatsu/ws_PDFScoreBar
WORKTREE=/home/masaki_muramatsu/ws_PDFScoreBar_issue173

docker run --rm --gpus all \
  --user "$(id -u):$(id -g)" \
  -v "$WORKTREE":/workspace \
  -v "$MAIN_REPO/data":/workspace/data:ro \
  -v "$MAIN_REPO/logs":/workspace/logs \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python <worktree-relative-script> \
  --output-root /workspace/logs/<issue>/<run>
```

An existing container whose `/workspace` is mounted from `MAIN_REPO` executes the
manager checkout and is not suitable for code from `WORKTREE`; start a dedicated
container with the worktree mount. Before a long run, record `pwd`, branch, HEAD, the
container mount source, and the output path. The code mount must be `WORKTREE`, while
retained outputs must be under `MAIN_REPO/logs/`.

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

- Fast tests: `make test-fast`. Intended for ordinary code and docs-adjacent changes; it runs no-real-data unit tests and intentionally excludes the real-data integration test. In a worktree, it uses local `.venv_pdf` when present; otherwise it uses `PYTHON`.
- Pipeline smoke: `make verify-pipeline-smoke`. Wraps the existing `make run-smoke`.
- GPU smoke: `make verify-gpu-smoke`. Records branch, commit, Python version, GPU info, command, exit code, and log path under `logs/system/`.
- Full evaluation: long run through `make verify-full-eval` or `scripts/local_pr_validation.sh --with-full-eval`. It is not a default PR requirement, but evaluation-sensitive changes need either results or an explicit human skip/defer decision under `docs/dev/VALIDATION_POLICY.md`.

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
3. Run `make test-fast` or stronger validation as required by `docs/dev/VALIDATION_POLICY.md`.
4. Post local validation results to the PR.

## Safety Boundaries

- These scripts do not merge to `develop` or `main`.
- They do not require GPU smoke for docs-only or trivial changes.
- They do not update evaluation values, thresholds, filters, seeds, dataset selection, or metrics.
- They do not move or delete local datasets, logs, models, or caches.
- Normal manual development remains valid without using these scripts.
