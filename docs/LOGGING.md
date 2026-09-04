# Logs and Generated Artifacts

`logs/` contains execution logs, experiment results, and debug outputs. Keep runs
under a descriptive directory with a timestamp when practical, for example:

- `logs/<experiment>/<YYYYMMDD_description>/`
- `logs/<experiment>/<YYYYMMDDThhmmssZ_description>/`

Use `logs/` for pipeline, evaluation, experiment, model, and large generated
outputs. Use `artifacts/` for small, disposable reports produced by local
validation or agent tooling. Do not commit generated files from either directory.

The directories are intentionally ignored by Git. A worktree that shares local
outputs can symlink both directories to a persistent directory in the manager
worktree:

```bash
make setup-shared-worktree \
  BRANCH=perf/issue294-homr-baseline-refresh \
  WORKTREE=/home/masaki_muramatsu/ws_PDFScoreBar_issue294 \
  SHARED_ROOT=/home/masaki_muramatsu/ws_PDFScoreBar
```

## Categories

Use descriptive top-level names such as `evaluation`, `experiments`, `analysis`,
`system`, and `archive`. Keep the original run name and provenance in the run
directory rather than relying on the worktree name.

For Docker-based commands, remember that a host symlink target must also be
visible inside the container mount. Prefer an explicit bind mount for data that
is not below the repository path.

## Maintenance

- Keep generated output out of Git.
- Preserve important conclusions in tracked documentation or the relevant Issue/PR.
- Move durable retained evidence to the documented `logs/` path before removing a
  temporary worktree.
