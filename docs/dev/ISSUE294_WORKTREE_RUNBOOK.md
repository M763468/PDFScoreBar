# Issue #294 worktree runbook

Use the dedicated worktree and container for Issue #294 representative runs:

- Worktree: `/home/masaki_muramatsu/ws_PDFScoreBar_issue294`
- Branch: `perf/issue294-homr-baseline-refresh`
- Container: `pdfscore_issue294_profile_worktree`
- Container `/workspace`: the Issue #294 worktree

## Required local inputs

The worktree must contain the evaluation images and fixtures under
`data/evaluation2/`. The manager worktree is the source of the retained local
inputs when the Issue #294 worktree was created without them. The two runtime
weights are ignored local files and must exist at:

- `external/realesrgan/weights/RealESRGAN_x4plus.pth`
- `external/omr_dln/models/public_models/YOLOv8m_Measures.pt`

The worktree may share `logs/` and `temp/` through symlinks to the manager
worktree. The profiling container therefore needs both worktrees mounted at
their host absolute paths, plus manager `data` mounted over `/workspace/data`
when the worktree data is incomplete.

## Representative command

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar_issue294
PYTHON=/home/masaki_muramatsu/ws_PDFScoreBar_issue294/.venv_pdf/bin/python

$PYTHON tools/issue294/run_downstream_candidate_matrix_host.py \
  --run-tag issue294_downstream_matrix_rep_01 \
  --page 012 --page 013 --page 014 \
  --latest-homr-commit 457e7c6518a10ba755db2e60883419e56c4d7369
```

Before a fresh run, verify the container `/workspace` source and all requested
images from inside the container. Do not reuse a completed run when a fresh
representative execution is required; use a new `--run-tag`.

## Provenance note

The host wrapper validates a clean checkout and the fixed Issue #294 branch
base. It also uses the dedicated container name in
`tools/issue294/run_same_original_ab_host.py`. `container_path()` preserves
paths that resolve through shared worktree symlinks so container-created
artifacts remain addressable from the host.
