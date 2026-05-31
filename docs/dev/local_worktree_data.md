# Local Worktree Data Links

Worktrees often need local-only data that is intentionally not tracked by git: datasets, generated logs, model artifacts, and caches. Do not copy or commit those assets just to make a worktree run.

## Recommended Layout

Keep a local asset root outside issue worktrees, for example:

```bash
/home/masaki_muramatsu/pdfscore-local-assets/
  datasets/
  logs/models/
  cache/
```

Then link selected items into the issue worktree:

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

## Notes

- Avoid linking the whole `data/` directory unless you know it will not hide tracked placeholders and metadata.
- Keep secrets, private tokens, paid API keys, and large generated files out of git.
- Record machine-specific paths in local shell history, `.env` files ignored by git, or PR comments when relevant. Do not commit those paths into reusable configs.
