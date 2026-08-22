# Two-HOMR High-Accuracy Production Milestone

This document records the accepted Issue #274 / PR #279 production architecture as a
reproducible comparison milestone for later work, including Issue #281 performance
optimization. It is a compact durable contract; the long Issue #274 investigation remains
historical evidence.

The intent is not to make every large evaluation/model artifact part of Git. The milestone
is reproducible when the accepted source revision is checked out, the named external/local
assets below are staged at their canonical paths, and their identity is recorded before a
comparison run.

## Accepted revision

- Accepted squash merge: `df130d12a71a8e7f65382f3e9d97e1ea9c3ee9ca`
- PR: #279
- Production config: `configs/dense_full_pipeline.yaml`
- Canonical architecture: `docs/PIPELINE_ARCHITECTURE.md`
- HOMR profile: `configs/detector_profiles/stage_e_verified_homr.json`

The two preceding architecture comparison refs were:

- 4-HOMR: `63ea1aca82e04fd167c3006eefc98aed35be5767`
- 3-HOMR: `3b2c8fce6445dad8a6057a04fc0ebb2f14e099ac`
- accepted 2-HOMR: `df130d12a71a8e7f65382f3e9d97e1ea9c3ee9ca`

## Pinned Stage-E profile provenance

`stage_e_verified` is machine-readable. At the accepted revision it records:

- PDFScoreBar evaluator source commit:
  `bd6ae56f8be6c87088143cfbf0ba09dee94fe0d7`
- compatibility origin commit:
  `3b9f5c4c74f284dab0e09816e1983fd81109adbc`
- HOMR repository commit:
  `864e2882f7a41afcf8f16654728a473ae56826d6`
- NumPy `2.2.6`
- OpenCV headless `4.12.0.88`
- ONNX Runtime GPU `1.22.0`
- pinned SegNet/encoder/decoder model SHA-256 values in the profile JSON.

The profile also records the expected pinned runtime paths under `/opt/` and the verified
full-68 baseline/Stage-E metrics. Do not copy those values into another profile by hand;
use the JSON as the provenance source.

## Architecture reproduction contract

For every dense production page, all of the following must hold:

1. HOMR neural inference purpose count is exactly **2**.
2. Exactly one HOMR inference is on the original/source page using the pinned
   `stage_e_verified` profile.
3. Exactly one HOMR inference is on the persisted x4 support image using the current
   runtime.
4. `current_x4_support` owns the x4 HOMR output and publishes detection, staff, and the
   complete connector semantic pair.
5. detector consensus reuses `current_x4_support.current_sr_detection`.
6. dense MMR reuses Phase-A topology/x plus current-x4 staff y support.
7. there is no downstream original-image current-HOMR rerun for MMR.
8. there is no MMR-specific second numbering rebuild.

Lightweight architecture guards can be rerun from the accepted checkout without GPU data:

```bash
PYTHONPATH=. python -m pytest \
  tests/test_issue274_two_homr_profile.py \
  tests/test_issue274_connector_support_contract.py \
  tests/test_current_homr_worker.py \
  tests/test_issue264_phase_a_connector_geometry.py
```

These tests are guards for ownership/contract structure. They are not substitutes for the
full accuracy milestone.

## Runtime assumptions

The maintained full-pipeline environment is:

- Docker image: `pdfscore_pipeline_gpu`
- GPU runtime: Docker with `--gpus all`
- working directory in container: `/workspace`
- project interpreter: `/opt/venv_pipeline/bin/python`
- repository mounted at `/workspace`
- `PYTHONPATH=/workspace`

Build with:

```bash
make docker-build
```

A direct fresh run shape is:

```bash
docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python src/pipeline/main.py \
  --config configs/dense_full_pipeline.yaml \
  --run-id two_homr_milestone_reproduction
```

Do not use `--skip-existing` when the purpose is a fresh production reproduction.

## Required local/external assets and staging contract

Large evaluation images and the Issue #44 CNN checkpoint intentionally remain outside Git.
That is part of the repository's artifact policy, not an unresolved requirement to commit
them. A milestone comparison must stage the following assets at the paths expected by the
accepted config.

### Canonical evaluation2 page set

The canonical full-68 page selection is the `SCORES` mapping in
`tools/issue120/eval_full68_from_intermediates.py`. It is the mechanically authoritative
work/page list for this milestone. The image tree must contain the corresponding files at:

```text
data/evaluation2/images/<score>/<page>.png
```

and the tracked GT must contain the matching annotation pages under:

```text
data/evaluation2/annotations/<score>/<page>/
```

The evaluation2 history is Issue #16: five works were assembled and the usable score-page
subset was reduced to 68 pages after non-score/omitted pages. Do not evaluate all filenames
found under `data/evaluation2/images/` and call that the milestone; use the committed
`SCORES` selection.

A lightweight staging check is:

```bash
PYTHONPATH=. python - <<'PY'
from pathlib import Path
from tools.issue120.eval_full68_from_intermediates import SCORES

root = Path("data/evaluation2")
missing_images = []
missing_gt = []
count = 0
for score, pages in SCORES.items():
    for page in pages:
        count += 1
        image = root / "images" / score / f"{page}.png"
        gt = root / "annotations" / score / page / "boxes_sorted.json"
        if not image.is_file():
            missing_images.append(str(image))
        if not gt.is_file():
            missing_gt.append(str(gt))

print(f"canonical_pages={count}")
print(f"missing_images={len(missing_images)}")
print(f"missing_gt={len(missing_gt)}")
if missing_images or missing_gt:
    raise SystemExit(1)
PY
```

Expected precondition is `canonical_pages=68`, `missing_images=0`, `missing_gt=0`.

### CNN barline classifier checkpoint

The production config expects:

```text
logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth
```

This is the Issue #44 / PR #57 **Iter 7 final rescue** model. Its durable provenance and
reconstruction procedure are already committed in `docs/ISSUE44_ITER7_FINAL_REPORT.md`:

```bash
.venv_cnn_classifier/bin/python tools/cnn_classifier/build_iter7_hard_samples.py
cp -r datasets/cnn_classifier_v7_hard_mining/* datasets/cnn_classifier_v7_base/
CNN_DATASET_ROOT=datasets/cnn_classifier_v7_base \
  .venv_cnn_classifier/bin/python experiments/cnn_classifier/train.py \
  --config configs/cnn_barline_runs/issue44_iter7_final_rescue/train.yaml
```

The exact checkpoint used by an existing accepted/local run should be reused from the
canonical path above. Before a new comparison, record its content identity rather than
relying only on the filename:

```bash
sha256sum \
  logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth
```

The historical work did not commit that large checkpoint or a durable SHA-256 for its
specific local bytes. Therefore:

- if the canonical checkpoint is still retained locally, its SHA-256 is the comparison-run
  identity and should be copied into that run's small provenance summary;
- if it has been lost, the committed Issue #44 Iter 7 procedure above is the canonical
  reconstruction route;
- a newly reconstructed checkpoint must be labelled as a reconstructed Iter 7 checkpoint,
  not claimed to be byte-identical to the lost historical file unless its hash has been
  independently matched.

This is sufficient for the purpose of this milestone: future work can either compare using
the retained accepted checkpoint or mechanically reconstruct the same Iter 7 training
contract without reopening the Issue #44 investigation.

### Other required model/runtime assets

The canonical config additionally expects:

- MMR classifier: `tools/mmr_training/models/mmr_classifier_best.pth`;
- pinned Stage-E runtime/model material described by
  `configs/detector_profiles/stage_e_verified_homr.json`.

The pinned HOMR profile carries its model hashes. Do not substitute a newly trained CNN, a
different evaluation page selection/export, or another HOMR profile while reporting the
accepted milestone; that constitutes a new experiment and must be labelled accordingly.

## Accepted accuracy evidence

Issue #274 established the final same-input causal gate after correcting verifier-contract
mistakes encountered during the investigation.

Accepted downstream gate:

- pages: **68 / 68**
- candidate CPU reconstruction exact vs actual fresh `numbering_base.json`: **68 / 68**
- retained control C vs candidate two-HOMR B numbering topology exact: **68 / 68**
- source contract: **PASS**
- errors: **0**
- overall gate: **PASS**

The gate intentionally treats numbering topology as the acceptance contract. Raw detector
multiplicity can differ while collapsing to the same downstream physical x identity; do
not replace this with a stricter or weaker metric without a new issue and evidence.

The retained Issue #274 utilities relevant to MMR replay/scoring include:

```text
tools/issue274/run_full68_mmr_reuse.py
tools/issue274/run_full68_mmr_reuse_logged.sh
tools/issue274/rescore_full68_mmr_reuse_geometry_rebased.py
tools/issue274/validate_mmr_support_mapping.py
```

Use their `--help` and the Issue #274 record to reconstruct the MMR-only replay when the
required retained run roots are present. The clean PR intentionally did not retain every
forensic verifier created during the investigation; the accepted metrics and comparison
contract above are the durable result.

Relevant focused guards include the Issue #244 five-override acceptance and the
connector-aware Phase-A grouping tests. If either fails, do not declare the milestone
reproduced even if detector-only metrics look good.

## Accepted performance evidence

The final comparison used the same representative input page, the same Docker environment,
the same `configs/dense_full_pipeline.yaml` content, and the same resource sampler across
three architecture refs.

Representative page:

```text
Shostakovich-Sym5-Va_page_013.png
```

Same-environment results:

| architecture | ref | wall time | peak process-tree RSS | peak GPU memory |
| --- | --- | ---: | ---: | ---: |
| 4-HOMR | `63ea1aca82e04fd167c3006eefc98aed35be5767` | 399.126 s | 7.038 GiB | 7541 MB |
| 3-HOMR | `3b2c8fce6445dad8a6057a04fc0ebb2f14e099ac` | 382.355 s | 8.092 GiB | 7556 MB |
| 2-HOMR | accepted branch leading to PR #279 | 313.699 s | 6.961 GiB | 7547 MB |

The accepted production code is the PR #279 squash merge `df130d12...`; the original
2-HOMR benchmark was taken on its clean pre-merge branch state.

For a new causal performance comparison:

1. stage the canonical page/model assets above and record the CNN checkpoint SHA-256;
2. use the same `pdfscore_pipeline_gpu` image/hardware state for every compared ref;
3. preserve the same `configs/dense_full_pipeline.yaml` content;
4. run the production path through MMR so both removed inference boundaries are covered;
5. capture wall time, process-tree RSS, GPU memory, and the architecture source contract;
6. label whether the run is cold or warm with respect to image/model caches.

A practical shell skeleton for each ref is:

```bash
/usr/bin/time -v docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python src/pipeline/main.py \
  --config configs/dense_full_pipeline.yaml \
  --run-id "perf_<ref>"
```

Use the project resource sampler when available to obtain process-tree and GPU peaks;
`/usr/bin/time -v` alone does not reproduce the accepted GPU metric. Record the exact
sampler command/commit in the new result.

The single-page benchmark is a bounded causal comparison. **Do not linearly extrapolate
its wall time to full68.** Full68 correctness and representative performance answer
different questions.

## Artifact retention policy for this milestone

Keep in Git:

- this milestone document and `docs/PIPELINE_ARCHITECTURE.md`;
- `configs/dense_full_pipeline.yaml`;
- `docs/ISSUE44_ITER7_FINAL_REPORT.md` and the Iter 7 train config/scripts needed to
  reconstruct the CNN training contract;
- `tools/issue120/eval_full68_from_intermediates.py` as the canonical 68-page selection;
- the pinned HOMR profile JSON and its model hashes;
- focused architecture/ownership tests;
- small reusable Issue #274 replay/scoring utilities that remain useful.

Keep outside Git under the existing local/ignored data and log policy:

- evaluation page image bytes;
- the large Issue #44 CNN checkpoint;
- full detector/HOMR run trees;
- x4 page images;
- worker logs;
- full68 generated `numbering_base`, `mmr_support`, and override trees;
- resource-sampling streams and large visual overlays.

For each future retained comparison, preserve a small provenance summary containing at
least: source commit, config content/hash, canonical page selection, CNN checkpoint SHA-256,
HOMR profile/model hashes, container/image identity, command, result summary, and paths to
any intentionally retained external artifact. This provides a durable comparison contract
without committing large transient runs.

## Tag status

Issue #280 does **not** create or move a tag automatically. A tag can be useful because
this milestone is intended as the comparison base for later performance work. A reasonable
candidate is:

```text
two-homr-high-accuracy-df130d12
```

Before creating it, inspect the repository's existing tag naming convention and obtain
maintainer approval. The tag must point to the accepted squash merge, never to a moving
branch.
