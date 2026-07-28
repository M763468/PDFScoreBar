# Issue #255 fresh detector recovery tools

Issue #255 must use a newly generated authoritative fresh route. Retained Issue #244,
#245 and #252 artifacts remain forensic references and must not be cited as a fresh
production success.

## 1. Focused canonical fresh runs

Run the two required focus pages through separate fresh detector executions with one
command:

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar
git fetch origin
git switch fix/issue255-fresh-detector-production-recovery
git pull --ff-only

PYTHON=/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python

bash scripts/run_issue255_focused_fresh.sh \
  --python "$PYTHON" \
  --run-tag issue255_gate_01
```

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

For a one-page rerun, `run_focused_fresh_detector.py` loads
`configs/dense_full_pipeline.yaml` and preserves its `detection` and `steps` mappings.
It changes only the selected image directory, image glob, run ID and output root:

```bash
PYTHONPATH=. "$PYTHON" tools/issue255/run_focused_fresh_detector.py \
  --image data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png \
  --score Va_Prokofiev_Symphony1 \
  --page page_004 \
  --run-id issue255_prokofiev_page004_fresh_01 \
  --output-root logs/issue255_focused_fresh
```

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
- `py_compile` for the Issue #255 tools and tests;
- `make lint`;
- the focused pytest profile, including Issue #252 detector-boundary and Issue #254
  connector-artifact contract tests.

Use `--pytest-only` for a quicker rerun or `--lint-only` to isolate lint failures. This
validation script does not start HOMR, SR, OMR-DLN or CNN inference.
