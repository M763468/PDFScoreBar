# Issue 120 / Issue 149: Issue36 Dense Candidate Validation Route

## Purpose

Issue #149 integrates the recovered Issue #36 v12 dense candidate producer into the current Issue #120 validation workflow.

The route is intentionally narrower than full Stage E pipeline validation:

```text
Issue #36 v12 bench inventory
  -> generate dense raw candidates
  -> compare raw candidates with recovered historical root
  -> apply clef-mask-aware filter
  -> compare filtered candidates with recovered historical roots
  -> current CNN scoring
  -> #134 full-68 detector evaluator
```

It does not change general pipeline defaults. It does not run the full slow HOMR/SR/OMR pipeline.

## Acceptance target

Detector-level target:

```text
TP=3580 / FP=0 / FN=1
```

Detector metrics and downstream measure-count metrics must remain separate.

## Reproduction-sensitive generation setting

The current `detect_probe_scan` default for `band_cluster_max_dist` no longer matches the historical `edf7bf6` Issue #36 v12 implementation. The Issue #36 route therefore pins:

```text
band_cluster_max_dist=25.0
```

This is route-local. It must not be interpreted as a general pipeline default change.

## Main wrapper

```text
tools/issue120/run_issue36_dense_candidates_then_eval.py
```

The wrapper records route provenance under ignored `logs/` output, including:

- raw and filtered candidate root summaries;
- raw / filtered / historical scoring-input candidate-root comparison summaries;
- generation parameters;
- filter parameters;
- clef-mask filtering status and clef-mask resolution;
- CNN scorer and explicit `cnn_apply_nms` setting;
- detector target and observed detector summary;
- scope guards for #141 and #142.

Default output root:

```text
logs/issue120_e2e_recovery/stage_d_issue36_dense_candidate_validation
```

## Make target

The #149 target is kept in a small include file to avoid enlarging the root Makefile while this route is under review:

```bash
make -f Makefile -f tools/issue120/Makefile.issue36_dense.mk verify-issue120-issue36-dense
```

By default, the Make target requires historical candidate-root equality before scoring:

```text
ISSUE120_ISSUE36_DENSE_REQUIRE_CANDIDATES=1
```

To make the run fail unless the detector target is exactly met:

```bash
make -f Makefile -f tools/issue120/Makefile.issue36_dense.mk \
  verify-issue120-issue36-dense \
  ISSUE120_ISSUE36_DENSE_REQUIRE_TARGET=1
```

Useful variables:

```text
ISSUE120_DOCKER_IMAGE
ISSUE120_DOCKER_PYTHON
ISSUE120_IMAGE_ROOT
ISSUE120_GT_ROOT
ISSUE120_MODEL_PATH
ISSUE120_SCORE_THRESHOLD
ISSUE120_XDIST_THRESHOLD
ISSUE120_ISSUE36_DENSE_OUTPUT_ROOT
ISSUE120_ISSUE36_DENSE_INVENTORY
ISSUE120_ISSUE36_DENSE_EXCLUDE
ISSUE120_ISSUE36_DENSE_HISTORICAL_RAW
ISSUE120_ISSUE36_DENSE_HISTORICAL_FILTERED
ISSUE120_ISSUE36_DENSE_HISTORICAL_SCORING_INPUT
ISSUE120_ISSUE36_DENSE_REQUIRE_CANDIDATES
ISSUE120_ISSUE36_DENSE_REQUIRE_TARGET
```

## Direct Docker command

```bash
docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python tools/issue120/run_issue36_dense_candidates_then_eval.py \
    --inventory logs/issue36_prep/20260208_bench_inventory.json \
    --exclude logs/issue36_prep/excluded_pages_for_gt_prep.json \
    --historical-raw-candidates-root logs/issue36_prep/probe_candidates_from_bench_v12 \
    --historical-filtered-candidates-root logs/issue36_prep/probe_candidates_filtered_v12 \
    --historical-scoring-input-root logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12 \
    --image-root data/evaluation2/images \
    --gt-root data/evaluation2/annotations \
    --model-path logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth \
    --output-root logs/issue120_e2e_recovery/stage_d_issue36_dense_candidate_validation \
    --no-pipeline-nms \
    --require-candidate-match \
    --require-detector-target
```

## Expected generated files

```text
logs/issue120_e2e_recovery/stage_d_issue36_dense_candidate_validation/
  probe_candidates_from_bench_v12/
  probe_candidates_filtered_v12/
  filter_suggestions_v12/
  raw_delta/
  filtered_delta/
  scoring_input_delta/
  probe_generation_summary_v12_current.json
  filter_apply_summary_v12_current.json
  scoring/
  eval/
  issue36_dense_candidate_route_provenance.json
```

All of these outputs are generated artifacts and must not be committed.

## Required candidate-root checks

The route writes `filter_candidate_delta_summary.json` under each delta directory.

Expected comparison properties:

```text
raw_delta.summary.mismatch_pages=0
raw_delta.summary.total_extra_in_repro=0
raw_delta.summary.total_missing_from_repro=0
filtered_delta.summary.mismatch_pages=0
filtered_delta.summary.total_extra_in_repro=0
filtered_delta.summary.total_missing_from_repro=0
scoring_input_delta.summary.mismatch_pages=0
scoring_input_delta.summary.total_extra_in_repro=0
scoring_input_delta.summary.total_missing_from_repro=0
```

## Required provenance checks

After a successful run, check:

```bash
python3 - <<'PY'
import json
from pathlib import Path
root = Path('logs/issue120_e2e_recovery/stage_d_issue36_dense_candidate_validation')
prov = json.loads((root / 'issue36_dense_candidate_route_provenance.json').read_text())
print(prov['candidate_root_summary'])
print(prov['candidate_root_comparisons'])
print(prov['clef_mask_filtering']['resolution'])
print(prov['clef_mask_filtering']['reason_counts'])
print(prov['cnn_scoring'])
print(prov['detector_summary'])
PY
```

Expected recovered filter properties:

```text
filtered candidate files=68
filtered candidate total=22565
clef_mask_resolution.resolved_pages=68
clef_mask_resolution.missing_pages=0
reason_counts.left_margin_zone=3520
reason_counts.clef_mask_overlap=4665
reason_counts.no_staff_overlap=781
cnn_apply_nms=false
```

Expected detector target:

```text
TP=3580 / FP=0 / FN=1
```

## Scope boundaries

- NMS policy and any general default change remain owned by #142.
- Full slow HOMR/SR/OMR pipeline validation remains owned by #141.
- This route validates the recovered dense candidate producer and current scoring/evaluator path only.
