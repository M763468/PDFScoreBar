# Full Pipeline Orchestrator (Phase 1)

This document describes the config-driven orchestrator script and its outputs.
The goal of Phase 1 is to run the existing scripts end-to-end with a stable
run directory layout and a single YAML config.

## Script
`tools/run_full_pipeline.py`

## Quick Start
```bash
python tools/run_full_pipeline.py --config configs/full_pipeline_template.yaml
```

Validate-only (resolve inputs and filters, no numbering):
```bash
python tools/run_full_pipeline.py --config configs/full_pipeline_template.yaml --validate-only
```

## Config Overview
The template lives at `configs/full_pipeline_template.yaml`.

Key sections:
- `run`: run_id and output_root.
- `inputs`: pdf_path, pdf_to_images settings, barlines/mask resolution patterns,
  and optional overrides.
- `steps`: enable/disable each pipeline stage.
- `filters`: blank/staff filters and user exclude list.
- `mmr`: MMR model and debug options.
- `numbering`: numbering options (ex: force single system).

## Output Layout
Outputs are placed under:
`logs/full_pipeline_runs/<run_id>/`

Typical subfolders:
- `inputs/`: reserved for snapshots (not populated yet).
- `intermediate/<page_id>/`: per-page numbering_base, overrides_mmr, overrides_combined.
- `outputs/<page_id>/`: per-page numbering_final and overlay.
- `intermediate/numbering_base.json`: combined multi-page numbering (when enabled).
- `outputs/numbering_final.json`: combined multi-page numbering (when enabled).
- `manifest.json`: resolved paths, page mappings, commands.
- `filters.json`: page filter status and metrics.

## Barline Overrides
`inputs.barline_overrides` accepts a JSON file:
```json
{
  "barline_overrides": [
    {"page": 0, "op": "remove", "bbox": [x1, y1, x2, y2]},
    {"page": 0, "op": "add", "bbox": [x1, y1, x2, y2]}
  ]
}
```
Matching uses IoU with defaults from `barline_overrides_config`.

## Page Filters
- `filters.blank_page`: "auto" to compute via pixel stats.
- `filters.staff_detect`: "auto" to compute from staff mask density.
- `filters.user_exclude`: 1-based indices to skip while keeping page structure.

Excluded pages write empty `numbering_base.json` and `numbering_final.json`.

## Notes
- The orchestrator is a thin wrapper around existing scripts.
- Phase 2 will focus on removing redundant file I/O and adding parallelism.
