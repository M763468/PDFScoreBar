# Fresh upstream HOMR probe

## Confirmed reconstruction

The recovered local snapshot probe reproduced the retained page-001 baseline exactly:

```text
historical=87
candidate=87
matched=87
historical-only=0
candidate-only=0
semantic_equal=true
```

The reproducing condition was:

```text
PDFScoreBar source bd6ae56
HOMR source 864e288
SegNet 155 fp32
Transformer encoder/decoder 220
NumPy 2.2.6
OpenCV headless 4.12.0.88
ONNX Runtime GPU 1.22.0
CUDAExecutionProvider selected
```

That probe copied model files from the recovered ignored checkout. It established the exact source/model/runtime boundary, but did not yet prove a fresh public-upstream build.

## Purpose

This probe removes the recovered local checkout and retained local models from the candidate build inputs.

The Docker image:

1. clones `https://github.com/liebharc/homr.git`;
2. checks out `864e2882f7a41afcf8f16654728a473ae56826d6`;
3. pins NumPy 2.2.6, OpenCV headless 4.12.0.88, and ONNX Runtime GPU 1.22.0;
4. calls that HOMR revision's public `download_weights()` route;
5. verifies the downloaded SegNet and transformer model hashes against the exact models that produced the 87/87 reconstruction;
6. runs the historical PDFScoreBar evaluator source `bd6ae56` on the canonical page-001 image;
7. compares the fresh result with the retained baseline as evidence only.

No local `external/homr` source or model file is copied into the image.

## Run

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar_issue245

git fetch origin
git reset --hard \
  origin/investigate/issue245-fresh-upstream-detector-route

python3 -m py_compile \
  tools/issue245/run_fresh_upstream_homr_probe.py \
  tools/issue245/collect_local_homr_probe_provenance.py

PYTHONPATH=. python3 -m pytest \
  tests/test_issue245_fresh_upstream_homr_probe.py

bash tools/issue245/run_fresh_upstream_homr_probe.sh \
  --force \
  --rebuild \
  --keep-image
```

`--rebuild` adds `docker build --no-cache`, so the HOMR source and release assets are fetched again rather than reused from an earlier probe layer.

## Output

```text
logs/issue245_fresh_upstream_homr_probe/
  fresh_upstream_homr_probe_report.json
  docker_build.log
  provenance.json
  provenance.log
  evaluator.log
  evaluator/...
  pdfscore_source_snapshot/...
```

## Decision gate

- If the image builds, all public model hashes match, and page-001 remains 87/87, the baseline HOMR route is reproducible from public upstream inputs without retained historical detector artifacts or recovered local model files.
- If a public asset is missing or its hash differs, preserve the build log and do not substitute the local recovered model silently.
- After the fresh page-001 gate passes, run a small representative-page detector set before full-68.
- Do not change the production default until full-68 detector, physical measure, MMR, and corrected-final gates pass.
