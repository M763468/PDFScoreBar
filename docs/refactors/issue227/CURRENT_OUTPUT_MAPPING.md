# Issue 227: Current Output Mapping

This file records how the current implementation-oriented pipeline artifacts should map into the #227 public output profile contract.

It is not a migration script. It is an implementation handoff for a later CLI/materializer PR.

## Current implementation-oriented run layout

The integrated pipeline currently writes artifacts under an internal run directory. The common shape is:

```text
run_dir/
  pipeline.log
  manifest.json
  filters.json
  inputs/
    images/
  intermediate/
    <page_id>/
      numbering_base.json
      barlines_corrected.json
      overrides_mmr.json
      overrides_combined.json
  outputs/
    numbering_final.json
    <page_id>/
      numbering_final.json
      numbering_overlay.png
```

Detector, OCR, MMR, and issue-specific evaluation flows may also write under `logs/`, `logs/hybrid_generalization/`, `logs/issue*/`, or tool-specific directories.

## Mapping table

| Current / legacy artifact | Public profile location | Target profile | Notes |
| --- | --- | --- | --- |
| `run_dir/pipeline.log` | `debug/pipeline.log` | `debug` | Diagnostic only. Must not appear in `final/`. |
| `run_dir/manifest.json` | `debug/manifest.json`; selected stable fields in `run_summary.json` | `debug` / root | Internal manifest may include raw paths and command traces. Root summary should expose only stable user-facing fields. |
| `run_dir/filters.json` | `debug/filters.json`; user-actionable subset in `final/warnings.json` | `debug` / `final` | Keep detailed page filter state out of final unless it is actionable. |
| `run_dir/inputs/images/` | `review/pages/<page_id>/source.png` and/or `debug/inputs/images/` | `review` / `debug` | Review needs a stable coordinate-space image. Final should not retain source renders unless required by the final deliverable format. |
| `run_dir/intermediate/<page_id>/numbering_base.json` | `debug/intermediate/<page_id>/numbering_base.json` | `debug` | Base numbering before MMR/manual correction is debug evidence. |
| `run_dir/intermediate/<page_id>/barlines_corrected.json` | `review/pages/<page_id>/barlines_review.json`; optional debug copy | `review` / `debug` | Review may use a normalized user-inspectable subset. |
| `run_dir/intermediate/<page_id>/overrides_mmr.json` | `review/pages/<page_id>/mmr_overrides.json`; optional debug copy | `review` / `debug` | MMR evidence is relevant for correction but is not final user output. |
| `run_dir/intermediate/<page_id>/overrides_combined.json` | `debug/intermediate/<page_id>/overrides_combined.json` | `debug` | Applied merge detail is debug evidence. Review should use cleaner correction input. |
| `run_dir/outputs/<page_id>/numbering_final.json` | `review/pages/<page_id>/numbering_final.json`; aggregate into `final/score_numbering.json` | `review` / `final` | Page-level detail remains available in review. |
| `run_dir/outputs/<page_id>/numbering_overlay.png` | `review/pages/<page_id>/review_overlay.png` | `review` | Current overlay is review-oriented until #228 defines the final overlay format. |
| `run_dir/outputs/numbering_final.json` | `final/score_numbering.json` | `final` | Closest current artifact to stable final machine-readable numbering. |
| `logs/hybrid_generalization/<run_id>/...` | `debug/detection/hybrid/` or `debug/artifact_index.json` reference | `debug` | Detection internals must not leak into final/review by default. |
| `run_dir/intermediate/probe_scan/...` | `debug/detection/probe_scan/` | `debug` | Detector evidence. |
| Issue-specific `logs/issue*/...` | outside user output; optional `debug/artifact_index.json` reference | debug reference only | Historical investigation artifacts are not normal CLI output. |
| Evaluation contracts / GT reports / experiment zips | outside user output | none by default | Keep separate from user-facing output. |

## Rules for materialization

A future materializer should follow these rules:

1. Build `final/` first and keep it independent of review/debug retention.
2. Treat `review/` as a curated inspection/correction surface, not as a full dump of internals.
3. Treat `debug/` as the only profile where noisy, large, or implementation-specific artifacts are allowed.
4. Write `run_summary.json` and `resolved_config.yaml` at the root for all profiles.
5. Never require a normal user to inspect `logs/`, `logs/issue*/`, Stage E artifact directories, or the current internal `outputs/` tree to find final results.
6. Do not overwrite `review/corrections/measure_overrides.json` if it already contains user edits unless the caller explicitly requests overwrite.
