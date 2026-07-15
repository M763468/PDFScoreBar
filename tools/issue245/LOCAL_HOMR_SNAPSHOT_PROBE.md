# Recovered local HOMR snapshot probe

## Boundary

The retained 2026-01-31 baseline was generated through `Dockerfile.sr_eval`, which installed the ignored local checkout at `external/homr` without pinning a commit.

Local read-only inventory recovered:

- repository HEAD `864e2882f7a41afcf8f16654728a473ae56826d6`;
- SegNet 155 fp32 and the matching transformer encoder/decoder models;
- NumPy 2.2.6, OpenCV 4.12.0, and ONNX Runtime 1.22.0 in the local venv;
- three dirty files.

The dirty files are not copied into this candidate:

- `homr/segmentation/inference_segnet.py` was modified on 2026-01-17 only to print provider diagnostics;
- `homr/autocrop.py` was modified on 2026-03-10, after the retained artifact;
- `pyproject.toml` was modified on 2026-03-14, after the retained artifact.

The probe therefore reconstructs the strongest artifact-time candidate as:

```text
clean HOMR commit 864e288
+ retained SegNet 155 fp32 model
+ retained transformer encoder/decoder models
+ NumPy 2.2.6
+ OpenCV 4.12.0.88
+ onnxruntime-gpu 1.22.0
+ PDFScoreBar source bd6ae56
```

The recovered local checkout is read only. The build context is created with `git archive`; no checkout, reset, clean, fetch, or install is performed in the original checkout.

## Run

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar_issue245

git fetch origin
git reset --hard \
  origin/investigate/issue245-fresh-upstream-detector-route

python3 -m py_compile \
  tools/issue245/run_local_homr_snapshot_probe.py \
  tools/issue245/collect_local_homr_probe_provenance.py

PYTHONPATH=. python3 -m pytest \
  tests/test_issue245_local_homr_snapshot_probe.py

bash tools/issue245/run_local_homr_snapshot_probe.sh \
  --force \
  --rebuild \
  --keep-image
```

## Output

```text
logs/issue245_local_homr_snapshot_probe/
  local_homr_snapshot_probe_report.json
  docker_build.log
  provenance.json
  provenance.log
  evaluator.log
  evaluator/...
  build_context/...
  pdfscore_source_snapshot/...
```

The retained historical detection JSON is comparison evidence only. It is not copied into the candidate detector or used as a production input.

## Decision gate

- If the recovered candidate reproduces or materially approaches the retained 87 records, narrow the remaining difference between source, model, and dependency layers before testing representative pages.
- If it reproduces the prior SegNet 155 result (`82` matches, `5` historical-only, `12` candidate-only), the older September HOMR source does not explain the artifact by itself; move to the remaining exact historical container/dependency differences.
- Do not run full-68 or change a production default from this page-001 experiment.
