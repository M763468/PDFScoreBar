# Local Worktree Data Links

Worktrees often need local-only data that is intentionally not tracked by git: datasets, generated logs, model artifacts, and caches. Do not copy or commit those assets just to make a worktree run.

## Shared worktree setup

For a worktree that should retain logs and artifacts after the worktree is removed,
use the repository helper from the manager worktree:

```bash
make setup-shared-worktree \
  BRANCH=perf/issue294-homr-baseline-refresh \
  WORKTREE=/home/masaki_muramatsu/ws_PDFScoreBar_issue294 \
  SHARED_ROOT=/home/masaki_muramatsu/ws_PDFScoreBar
```

The helper creates the Git worktree and symlinks available local-only directories,
including `logs`, `artifacts`, `datasets`, caches, and virtual environments. It
never overwrites an existing destination. `SHARED_ROOT` defaults to the current
manager worktree.

When removing a worktree, move any outputs that must be retained into the shared
`logs/` or `artifacts/` directory first. The shared directories are ignored by Git;
their operational documentation is maintained in `docs/LOGGING.md`.

## Recommended Layout

Keep a local asset root outside issue worktrees, for example:

```bash
/home/masaki_muramatsu/pdfscore-local-assets/
  datasets/
  logs/models/
  cache/
```

For a pre-existing worktree, link selected items into the issue worktree:

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar_issue173
scripts/setup_local_worktree_links.sh --source /home/masaki_muramatsu/pdfscore-local-assets
```

Equivalent Makefile wrapper:

```bash
make setup-local-worktree-links LOCAL_DATA_ROOT=/home/masaki_muramatsu/pdfscore-local-assets
```

## Custom Items

By default the helper tries:

- `datasets`
- `logs/models`
- `cache`

Override the list with an environment variable:

```bash
PDFSCORE_LINK_ITEMS="datasets logs/models external/homr external/omr_dln cache" \
  scripts/setup_local_worktree_links.sh --source /home/masaki_muramatsu/pdfscore-local-assets
```

The script skips missing sources and existing destinations. It does not overwrite, move, or delete files.

## Docker Mounts

Symlinks that point outside the worktree are useful on the WSL host, but Docker only sees paths mounted into the container. If a pipeline command runs inside Docker and follows a symlink to `/home/...` or another host-only path, the target may be missing inside `/workspace`.

For Docker-based validation, pass an explicit bind mount instead of relying on the symlink alone:

```bash
DOCKER_EXTRA_ARGS="-v /home/masaki_muramatsu/ws_PDFScoreBar/data/evaluation2/pdfs:/workspace/data/evaluation2/pdfs:ro" \
  make run-pipeline CONFIG=configs/evaluation2_e2e_verification_full.yaml
```

For the complete procedure when the manager worktree is occupied, including the Docker
mount layout and host-only execution choice, see
[`docs/dev/codex_local_automation.md`](codex_local_automation.md#when-the-manager-worktree-is-busy).

Keep machine-specific paths in local commands or PR comments, not in committed configs.

## Notes

- Avoid linking the whole `data/` directory unless you know it will not hide tracked placeholders and metadata.
- Keep secrets, private tokens, paid API keys, and large generated files out of git.
- Record machine-specific paths in local shell history, `.env` files ignored by git, or PR comments when relevant. Do not commit those paths into reusable configs.
