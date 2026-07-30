# Issue #255 fresh detector recovery tools

Issue #255 must use a newly generated authoritative fresh route. Retained Issue #244,
#245 and #252 artifacts remain forensic references and must not be cited as a fresh
production success.

## 1. Focused canonical fresh runs

Run the two required focus pages through separate fresh detector executions with one
command. The wrapper locates the official OMR-DLN measure model on the host, validates
it inside the maintained production GPU container, and runs the complete focused route
inside that same container:

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar
git fetch origin
git switch fix/issue255-fresh-detector-production-recovery
git pull --ff-only

PYTHON=/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python

bash scripts/run_issue255_focused_fresh_with_model.sh \
  --python "$PYTHON" \
  --run-tag issue255_gate_03
```

`--python` is the host interpreter used only to validate and display JSON artifacts. It
is not used for HOMR, SR, OMR-DLN or CNN inference. The production route runs in:

```text
container: pdfscore_pipeline_gpu
python:    /opt/venv_pipeline/bin/python
workspace: /workspace
```

The wrapper verifies that the container `/workspace` commit matches the host checkout.
It checks `OMR_DLN_MODEL_PATH`, the compatible repository-relative path and then
searches `$HOME` for exactly one `YOLOv8m_Measures.pt`. When automatic discovery is
ambiguous or finds nothing, specify the host weight explicitly:

```bash
bash scripts/run_issue255_focused_fresh_with_model.sh \
  --python "$PYTHON" \
  --omr-model /absolute/path/to/YOLOv8m_Measures.pt \
  --run-tag issue255_gate_03
```

A model inside the repository is used through `/workspace`. A model stored elsewhere is
copied to a temporary container path for the run and removed afterward. The preflight
loads it with the container Ultralytics runtime and requires the `systemMeasure` and
`staffMeasure` classes. Do not substitute a generic YOLO or symbol-detection weight.

The preflight writes:

```text
logs/issue255_focused_fresh/issue255_omr_dln_preflight_<run-tag>.json
```

On failure, the wrapper prints the full JSON error, including the container Python,
model paths, exception and traceback. The failed `issue255_gate_01` and
`issue255_gate_02` artifacts remain evidence and are not reused. Always choose a new
run tag.

The batch wrapper requires the Issue #255 branch and a clean tracked working tree. It
runs these pages with distinct run IDs:

```text
Va_Prokofiev_Symphony1/page_004
Shostakovich-Sym5-Va/page_014
```

It writes:

```text
logs/issue255_focused_fresh/<run-id>/issue255_focused_fresh_run_contract.json
logs/issue255_focused_fresh/<run-id>.console.log
logs/issue255_focused_fresh/issue255_focused_fresh_batch_<run-tag>.json
```

The batch summary fails unless both contracts are complete, use the same clean branch
commit, report the authoritative fresh input contract and contain every required
baseline HOMR, SR HOMR, OMR-DLN, hybrid, probe and CNN artifact.

`run_focused_fresh_detector.py` is the one-page implementation used by the batch. It
loads `configs/dense_full_pipeline.yaml`, preserves its `detection` and `steps`
mappings, and changes only the selected image directory, image glob, run ID and output
root. Direct execution must use the maintained production container; the host
`.venv_pdf` route is not authoritative for heavy inference.

The runner fails unless the detector input contract is exactly:

```text
mode = fresh_upstream
fresh_upstream_authoritative = true
override_keys = []
```

Each run contract records repository and runtime identity, canonical/effective config
hashes, coordinate spaces and generated artifact hashes. Do not use `--skip-existing`;
each focused run requires a new output identity.

## 2. First-loss inventory

`trace_focused_detector_boundaries.py` replays the production-default probe stages and
joins them with saved CNN and final detector outputs. Accepted/checkpoint barlines are
analysis references only and are never passed into detector runtime code.

Use the artifact paths and image SHA recorded in the focused fresh run contract as the
corresponding CLI arguments:

```bash
PYTHONPATH=. "$PYTHON" tools/issue255/trace_focused_detector_boundaries.py \
  --input-contract <detector_input_contract.json> \
  --image <original-page.png> \
  --probe-image <fresh-sr-page.png> \
  --expected-image-sha256 <sha256> \
  --fresh-baseline <fresh-baseline-detections.json> \
  --current-sr <fresh-sr-detections.json> \
  --current-omr <fresh-omr-predictions.json> \
  --hybrid <fresh-hybrid.json> \
  --staff-mask <fresh-sr-staff-mask.png> \
  --allow-zero-clef-mask \
  --cnn-scored <fresh-cnn-scored.json> \
  --cnn-accepted <fresh-cnn-accepted.json> \
  --final-barlines <fresh-final-barlines.json> \
  --accepted-barlines <accepted-analysis-reference.json> \
  --score <score-name> \
  --page <page-id> \
  --output-root logs/issue255_first_loss/<score>/<page>
```

Use `--allow-zero-clef-mask` only when the fresh run produced no authoritative
SR-coordinate clef mask. The inventory writes JSON, CSV and per-target probe traces.
Supply `--target-metadata` when system numbers, focused FP delta and downstream effects
are known; otherwise every accepted bbox missing from the current final set is traced.

## 3. Local code validation

Run this after every code change and before the focused GPU execution:

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar
git fetch origin develop
PYTHON=/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python

bash scripts/validate_issue255_local.sh --python "$PYTHON"
```

The wrapper runs:

- `git diff --check origin/develop...HEAD`;
- UTF-8 decoding for changed text files, covering the blob-corruption failure seen
  during the initial publication attempt;
- `bash -n` for the local validation and focused fresh batch scripts;
- `py_compile` for the Issue #255 tools and runtime helpers;
- `make lint`;
- the focused pytest profile, including OMR-DLN model resolution, subprocess
  diagnostics, Issue #252 detector-boundary and Issue #254 connector-artifact contract
  tests.

Use `--pytest-only` for a quicker rerun or `--lint-only` to isolate lint failures. This
validation script does not start HOMR, SR, OMR-DLN or CNN inference.
