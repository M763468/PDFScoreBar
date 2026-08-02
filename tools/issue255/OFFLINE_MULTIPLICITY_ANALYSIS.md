# Issue #255 offline candidate multiplicity analysis

## Why this gate exists

The focused detector runs must not be repeated after every local hypothesis.
Gate 06 and gate 08 produced the same candidate counts and TP/FP/FN metrics;
gate 07 only removed part of that recovery and lost one required target. This
shows that the recent changes oscillated between broad recovery and partial
suppression without first fixing the candidate representation contract.

Gate 08 recovered all eight required targets. Its count deltas are fully
accounted for by newly matched accepted barlines and extra representations of
accepted barlines. The next question is therefore not whether the probe can
find the targets. It is whether low-paper rescue output can be normalized
without merging distinct accepted boundaries.

Do not start another focused GPU run until the offline analysis below has
completed and its report explicitly authorizes it.

## Invariants

The analysis is not a detector runtime route. Accepted and gate 05 artifacts
are analysis references only. A later production implementation must retain:

```text
mode = fresh_upstream
fresh_upstream_authoritative = true
override_keys = []
accepted_reference_runtime_input = false
```

The intended implementation direction is rescue-aware normalization:

- preserve candidates reproduced by the established pre-repair route;
- consider only low-paper rescue additions suppressible;
- collapse only geometrically equivalent representations;
- do not enable global CNN NMS as a substitute;
- do not merge distinct accepted close or double barlines.

## Offline command

Update and validate the branch first:

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar
git fetch origin
git switch fix/issue255-fresh-detector-production-recovery
git pull --ff-only

PYTHON=/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python
bash scripts/validate_issue255_local.sh --python "$PYTHON"
```

Confirm that the accepted reference root contains the complete 68-page set:

```bash
ACCEPTED_ROOT="logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/probe_scan"

find "$ACCEPTED_ROOT" \
  -name pipeline2_no_peak_filtered_cnn.json \
  -type f \
  | sort \
  | tee /tmp/issue255_accepted_reference_files.txt \
  | wc -l
```

The count must be `68`. Then run only the retained-artifact analysis:

```bash
PYTHONPATH=. "$PYTHON" \
  tools/issue255/analyze_focused_candidate_multiplicity.py \
  --current-batch \
    logs/issue255_focused_fresh/issue255_focused_fresh_batch_issue255_gate_08.json \
  --accepted-root "$ACCEPTED_ROOT" \
  --output \
    logs/issue255_first_loss/issue255_gate_08_candidate_multiplicity.json
```

This does not run HOMR, SR, OMR-DLN, probe detection, or CNN inference.

## Required report conditions

A production deduplication implementation may be written only when the report
shows all of the following:

```text
status = completed
accepted_root_safety_inventory.page_count = 68
policy_sweep.passing_policy_count > 0
policy_sweep.recommended_policy != null
next_gpu_run_authorized = true
```

Every passing policy must also satisfy, on both focused pages:

- all four page targets remain recovered;
- FP does not exceed the gate 05 baseline;
- FN does not exceed the gate 05 baseline;
- TP does not fall below the gate 05 baseline;
- no suppressed pair maps to two different accepted references.

Across the complete accepted reference set, the same geometry policy must
produce zero collisions between distinct accepted boxes.

If no policy passes, do not tune production thresholds and do not start a new
GPU run. Inspect the nearest-policy diagnostics and redesign the candidate
representation or provenance handling first.

## Why the existing evaluator is insufficient for this decision

The gate 07/08 evaluator used prediction-order greedy matching. An approximate
new candidate could consume a reference before an exact retained baseline box
was visited, causing the exact baseline box to be labelled as an addition.
The multiplicity analyzer instead locks exact matches first and applies a
deterministic maximum-cardinality match to the remaining graph.

This correction changes diagnostics, not the core requirement: multiple final
predictions for one accepted physical barline remain a real production defect
and count as FP under one-to-one evaluation.
