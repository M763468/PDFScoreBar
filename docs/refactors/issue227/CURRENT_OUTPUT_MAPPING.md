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
| final assembled PDF, once #228 exists | `final/<output-name>_score_numbered.pdf` | `final` | This is the only final-profile deliverable. `<output-name>` defaults to the sanitized input PDF stem. |
| `run_dir/pipeline.log` | `debug/<debug-run-id>/pipeline.log` | `debug` | Diagnostic only. Must not appear in `final/` or `review/`. |
| `run_dir/manifest.json` | `debug/<debug-run-id>/manifest.json`; selected stable fields in `review/run_summary.json` | `debug` / `review` | Internal manifest may include raw paths and command traces. Review summary should expose only stable user-facing fields. |
| `run_dir/filters.json` | `debug/<debug-run-id>/filters.json`; user-actionable subset in `review/warnings.json` | `debug` / `review` | Warnings belong in review/debug, not final. |
| `run_dir/inputs/images/` | `review/pages/<page_id>/source.png` and/or `debug/<debug-run-id>/inputs/images/` | `review` / `debug` | Review needs a stable coordinate-space image. Final must not retain source renders. |
| `run_dir/intermediate/<page_id>/numbering_base.json` | `debug/<debug-run-id>/intermediate/<page_id>/numbering_base.json` | `debug` | Base numbering before MMR/manual correction is debug evidence. |
| `run_dir/intermediate/<page_id>/barlines_corrected.json` | `review/pages/<page_id>/barlines_review.json`; optional debug copy | `review` / `debug` | Review may use a normalized user-inspectable subset. |
| `run_dir/intermediate/<page_id>/overrides_mmr.json` | `review/pages/<page_id>/mmr_overrides.json`; optional debug copy | `review` / `debug` | MMR evidence is relevant for correction but is not final user output. |
| `run_dir/intermediate/<page_id>/overrides_combined.json` | `debug/<debug-run-id>/intermediate/<page_id>/overrides_combined.json` | `debug` | Applied merge detail is debug evidence. Review should use cleaner correction input. |
| `run_dir/outputs/<page_id>/numbering_final.json` | `review/pages/<page_id>/numbering_final.json` | `review` | Page-level detail remains available in review. |
| `run_dir/outputs/<page_id>/numbering_overlay.png` | `review/pages/<page_id>/review_overlay.png` | `review` | Current overlay is review-oriented until #228 defines the final PDF format. |
| `run_dir/outputs/numbering_final.json` | `review/score_numbering.json` | `review` | Stable machine-readable final numbering is review/tooling output, not final deliverable. |
| current page-level final images, if produced before PDF assembly | `review/pages/<page_id>/final_page.png` or debug equivalent | `review` / `debug` | Transitional page images must not be placed in `final/`. |
| `logs/hybrid_generalization/<run_id>/...` | `debug/<debug-run-id>/detection/hybrid/` or `debug/<debug-run-id>/artifact_index.json` reference | `debug` | Detection internals must not appear in final/review by default. |
| `run_dir/intermediate/probe_scan/...` | `debug/<debug-run-id>/detection/probe_scan/` | `debug` | Detector evidence. |
| Issue-specific `logs/issue*/...` | outside user output; optional `debug/<debug-run-id>/artifact_index.json` reference | debug reference only | Historical investigation artifacts are not normal CLI output. |
| Evaluation contracts / GT reports / experiment zips | outside user output | none by default | Keep separate from user-facing output. |

## Rules for materialization

A future materializer should follow these rules:

1. Build `final/` first and keep it to the final PDF only.
2. Name the final PDF `<output-name>_score_numbered.pdf`, where `<output-name>` defaults to the sanitized input PDF stem unless the caller supplies an explicit output name.
3. Treat `review/` as a curated inspection/correction surface, including warnings, summaries, final numbering JSON, and page images.
4. Treat `debug/<debug-run-id>/` as the only profile location where noisy, large, timestamped, or implementation-specific artifacts are allowed.
5. Make `<debug-run-id>` include a timestamp and include the explicit run id when one is provided.
6. Never require a normal user to inspect `logs/`, `logs/issue*/`, Stage E artifact directories, or the current internal `outputs/` tree to find the final PDF.
7. Do not overwrite `review/corrections/measure_overrides.json` if it already contains user edits unless the caller explicitly requests overwrite.
