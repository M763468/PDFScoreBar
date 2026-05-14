# Issue 120 Stage D Drift Recovery

## Purpose

This document starts #147: recover Stage D upstream provenance or explain/repair regenerated `bands_from` drift.

#140 established that the current Stage D upstream regeneration path can produce structurally complete 68-page artifacts, but does not reproduce the selected detector target.

```text
Target: TP=3580 FP=0 FN=1
Best current Stage D composition tested: baseline source
Observed: TP=3543 FP=288 FN=38
```

The unresolved historical artifact remains:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

This issue does not change detector, scoring, NMS, HOMR, SR, OMR, or full-pipeline behavior. It defines a local inspection path for comparing historical and regenerated artifacts before proposing any repair.

Detector-level metrics and downstream measure-count metrics must remain separate.

## Working hypothesis

The Stage D gap may come from one or more of these boundaries:

1. missing historical provenance for `scoring_input_eval2_v12`;
2. regenerated upstream HOMR/SR/OMR geometry drift;
3. source-composition differences among `baseline`, `sr`, `omr_sr`, `hybrid`, or `first_available`;
4. schema normalization differences when composing a score-aware `bands_from` tree;
5. probe-rescue assumptions that were valid for the historical artifact but not for regenerated upstream outputs.

The first step is to determine whether the local historical artifact is present and has the same page/file layout shape as regenerated Stage D artifacts.

## Initial local finding

The first #147 layout and box-tree inspection found that both roots are structurally present for the canonical 68-page manifest:

```text
manifest_pages=68
historical_resolved=68
historical_missing=0
regenerated_resolved=68
regenerated_missing=0
```

This means the immediate failure mode is not a missing local historical artifact and not a missing regenerated page tree.

However, regenerated baseline-source artifacts contain far fewer box-like items than the historical artifact on many pages. Largest observed losses include:

```text
Sibelius-Violin_Concerto-Viola/page_006: 675 -> 89  (ratio 0.132)
Shostakovich-Sym5-Va/page_020:           618 -> 66  (ratio 0.107)
Va_Prokofiev_Symphony1/page_001:         565 -> 133 (ratio 0.235)
Sibelius-Violin_Concerto-Viola/page_007: 592 -> 168 (ratio 0.284)
Va_Prokofiev_Symphony1/page_003:         612 -> 202 (ratio 0.330)
```

Geometry statistics also show large median-height and median-center shifts on multiple pages. Examples:

```text
Va__Prokofiev_Symphony5/page_022: median h delta = -40.0
Va__Prokofiev_Symphony5/page_023: median h delta = -40.0
Shostakovich-Sym5-Va/page_020:    median h delta = -28.5, median cy delta = -598.2
Sibelius-Violin_Concerto-Viola/page_006: median cy delta = -690.0
Shostakovich-Festival_Overture_Va/page_007: median cy delta = 1427.0
```

Current interpretation:

- Historical `scoring_input_eval2_v12` is available locally and resolves 68/68 pages.
- Regenerated baseline-source Stage D artifacts also resolve 68/68 pages.
- The drift is therefore inside the content of the regenerated bands/candidates, not directory layout completeness.
- The baseline-source regenerated artifact is under-generating relative to historical on many pages.
- Large center/height shifts suggest source-selection, geometry normalization, coordinate scaling, or schema normalization drift rather than a pure CNN/NMS issue.

Next diagnostic priority:

1. compare all regenerated composition sources (`baseline`, `sr`, `omr_sr`, `hybrid`, `first_available`) against the historical root using the same layout and box-tree tools;
2. determine whether any source has historical-like candidate counts and geometry;
3. if no source matches, inspect `run_stage_d_upstream_regen.py` composition/schema normalization and the upstream HOMR/SR/OMR coordinate frame.

## Lightweight local inspector

Use:

```bash
PYTHONPATH=. python3 tools/issue120/inspect_stage_d_artifact_layout.py
```

Default comparison:

```text
historical:
  logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
regenerated:
  logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_baseline
output:
  logs/issue120_e2e_recovery/stage_d_artifact_layout
```

The inspector writes:

```text
logs/issue120_e2e_recovery/stage_d_artifact_layout/stage_d_artifact_layout.csv
logs/issue120_e2e_recovery/stage_d_artifact_layout/stage_d_artifact_layout.md
```

These are generated diagnostics and must not be committed.

## Recommended local workflow

### 1. Ensure Stage D regenerated artifacts exist

Run the Stage D upstream generation and baseline-source verification if they are not already present:

```bash
make regen-issue120-stage-d-upstream ISSUE120_CLEAN_OUTPUT=1 ISSUE120_STAGE_D_COMPOSE_SOURCE=baseline
make verify-issue120-stage-d ISSUE120_STAGE_D_COMPOSE_SOURCE=baseline
make summarize-issue120-stage-d ISSUE120_STAGE_D_COMPOSE_SOURCE=baseline
```

### 2. Inspect historical-vs-regenerated artifact layout

```bash
PYTHONPATH=. python3 tools/issue120/inspect_stage_d_artifact_layout.py \
  --historical logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12 \
  --regenerated logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_baseline \
  --output-dir logs/issue120_e2e_recovery/stage_d_artifact_layout
```

Report these fields back to #147:

```text
manifest_pages
historical_resolved
historical_missing
regenerated_resolved
regenerated_missing
largest item-count deltas
largest box-like count deltas
```

### 3. Compare geometry statistics

If both roots resolve page files, run:

```bash
PYTHONPATH=. python3 tools/issue120/compare_box_tree_stats.py \
  --left logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12 \
  --right logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_baseline \
  --output-dir logs/issue120_e2e_recovery/stage_d_box_tree_stats_historical_vs_baseline
```

Report:

```text
largest count loss
largest median-height deltas
largest median-width deltas
pages with missing left or right files
```

### 4. Compare source-specific regenerated compositions

Repeat the layout and geometry comparisons for alternate composition sources:

```bash
for source in hybrid baseline sr omr_sr first_available; do
  PYTHONPATH=. python3 tools/issue120/inspect_stage_d_artifact_layout.py \
    --historical logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12 \
    --regenerated logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_${source} \
    --output-dir logs/issue120_e2e_recovery/stage_d_artifact_layout_${source}

  PYTHONPATH=. python3 tools/issue120/compare_box_tree_stats.py \
    --left logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12 \
    --right logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_${source} \
    --output-dir logs/issue120_e2e_recovery/stage_d_box_tree_stats_historical_vs_${source}
done
```

For `hybrid`, the default composed directory may be `bands_from_candidate` rather than `bands_from_candidate_hybrid`. If the loop reports missing regenerated pages for `hybrid`, rerun that source with:

```bash
PYTHONPATH=. python3 tools/issue120/inspect_stage_d_artifact_layout.py \
  --historical logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12 \
  --regenerated logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate \
  --output-dir logs/issue120_e2e_recovery/stage_d_artifact_layout_hybrid
```

Repeat the Stage D verifier and summary for alternate composition sources:

```bash
make verify-issue120-stage-d ISSUE120_STAGE_D_COMPOSE_SOURCE=hybrid
make summarize-issue120-stage-d ISSUE120_STAGE_D_COMPOSE_SOURCE=hybrid

make verify-issue120-stage-d ISSUE120_STAGE_D_COMPOSE_SOURCE=sr
make summarize-issue120-stage-d ISSUE120_STAGE_D_COMPOSE_SOURCE=sr

make verify-issue120-stage-d ISSUE120_STAGE_D_COMPOSE_SOURCE=omr_sr
make summarize-issue120-stage-d ISSUE120_STAGE_D_COMPOSE_SOURCE=omr_sr

make verify-issue120-stage-d ISSUE120_STAGE_D_COMPOSE_SOURCE=first_available
make summarize-issue120-stage-d ISSUE120_STAGE_D_COMPOSE_SOURCE=first_available
```

Record detector metrics separately for each source:

```text
GT / Pred / TP / FP / FN / FN_det / FN_cnn
Precision / Recall
cnn_apply_nms setting
```

Do not mix these with downstream measure-count metrics.

## Interpretation rules

### Historical artifact missing or incomplete

If `historical_resolved < 68`, the next task is provenance recovery, not algorithm repair. Search historical commits, PRs, branches, local logs, or external artifact stores for the exact producer of:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

### Historical artifact present, regenerated artifact incomplete

If historical resolves 68 pages but regenerated does not, the drift is in Stage D composition or upstream generation. Prioritize page-missing diagnostics and `run_stage_d_upstream_regen.py` provenance.

### Both roots resolve, but counts/geometry diverge

If both roots resolve 68 pages but counts or geometry diverge strongly, prioritize:

1. source selection (`baseline` vs `sr` vs `omr_sr` vs `hybrid`);
2. schema normalization;
3. coordinate scaling and page-stem collision handling;
4. probe-rescue assumptions that depend on historical band shape.

### Detector FNs dominated by FN_det

High `FN_det` indicates candidate-generation or upstream-band coverage loss before CNN scoring.

### Detector FNs dominated by FN_cnn

High `FN_cnn` indicates scoring/filtering loss after candidate generation. Do not route this into #142 unless the evidence specifically involves NMS behavior.

### High FP with reasonable recall

High FP with improved recall suggests over-generation or geometry drift. This should be repaired with upstream geometry/source constraints, not by silently weakening detector evaluation.

## Current non-goals

- Do not change global NMS behavior. NMS policy belongs to #142.
- Do not run or claim full-pipeline validation. That belongs to #141.
- Do not merge targeted accuracy repair here unless the root cause is fully isolated and the change is narrow.
- Do not commit generated logs, JSON, CSV, crops, or image artifacts.

## Minimum #147 report template

```text
Branch / commit:
Command(s):
Historical root:
Regenerated root:
Layout summary:
  manifest_pages:
  historical_resolved:
  historical_missing:
  regenerated_resolved:
  regenerated_missing:
Geometry summary:
  largest count loss:
  largest median-height deltas:
  largest median-width deltas:
Detector summary:
  GT / Pred / TP / FP / FN / FN_det / FN_cnn:
  cnn_apply_nms:
Interpretation:
Next routed issue or repair candidate:
```
