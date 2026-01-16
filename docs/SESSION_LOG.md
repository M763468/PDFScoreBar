# Session Log

### Operational Rules
- Do not overwrite `docs/SESSION_LOG.md`; append new findings.
- Record commit hash + command + output path for major results.

---
## 2026-01-16: Pipeline Planning (plan/full_pipeline_workflow)

### Scope
- Consolidate full pipeline plan into `docs/NEXT_SESSION_NOTES.md`.
- Remove separate `docs/PIPELINE_WORKFLOW.md` to avoid duplication.

### Changes
- Rewrote `docs/NEXT_SESSION_NOTES.md` with end-to-end pipeline steps, inputs/outputs, user correction points, artifact layout, and next actions.
- Deleted `docs/PIPELINE_WORKFLOW.md`.

### Notes
- This branch is planning-only; implementation will happen in child branches.
- Submodule `external/oemer/oemer_src` points to a commit unavailable in the submodule repo; ignored in this worktree via git config.

## 2026-01-16: Pipeline Planning (Contracts + CLI)

### Additions
- Added draft data contracts for barline overrides and measure overrides.
- Added a draft single-entry CLI plan (`tools/run_full_pipeline.py`) and expected inputs/outputs.

### Notes
- Contracts are placeholders; exact IoU matching rules and schema validation still to be defined.
- CLI should be a thin wrapper around existing scripts, not a rewrite.

## 2026-01-16: Pipeline Planning (Output Formats)

### Additions
- Documented current output formats for barlines JSON, numbering JSON, and MMR overrides JSON.
- Added notes on staff/notehead mask formats and common output path conventions.
