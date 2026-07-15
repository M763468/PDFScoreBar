# Fresh public-upstream HOMR full-68 probe

## Scope

This gate regenerates the baseline HOMR detections for all 68 canonical evaluation images with the already verified public-upstream image:

```text
PDFScoreBar source: bd6ae56f8be6c87088143cfbf0ba09dee94fe0d7
HOMR source:        864e2882f7a41afcf8f16654728a473ae56826d6
SegNet:             155 fp32 from the public HOMR release
Transformer:        encoder/decoder 220 from the public HOMR release
NumPy:              2.2.6
OpenCV headless:    4.12.0.88
ONNX Runtime GPU:   1.22.0
```

Retained 2026-01-31 baseline detections are comparison evidence only. They are not detector inputs.

This gate does not run SR-side HOMR, OMR-DLN, consensus, dense reconstruction, CNN scoring, MMR, or numbering. It does not change the production default.

## Preflight

Run the inventory-only preflight before GPU inference:

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar_issue245

git fetch origin
git reset --hard \
  origin/investigate/issue245-fresh-upstream-detector-route

python3 -m py_compile \
  tools/issue245/run_fresh_upstream_full68_probe.py

PYTHONPATH=. python3 -m pytest \
  tests/test_issue245_fresh_upstream_full68_probe.py \
  tests/test_issue245_fresh_upstream_representative_probe.py

bash tools/issue245/run_fresh_upstream_full68_probe.sh \
  --force \
  --preflight-only
```

Preflight must establish:

```text
expected_pages=68
discovered_pages=68
all_images_exist=true
all_image_keys_unique=true
all_historical_detections_resolved=true
```

If preflight fails, do not start inference. Inspect `fresh_upstream_full68_probe_report.json` and correct the inventory or retained-artifact lookup first.

## Full run

After preflight succeeds, preserve the preflight output and start or resume inference:

```bash
bash tools/issue245/run_fresh_upstream_full68_probe.sh \
  --resume
```

Each image runs in a separate Docker invocation and writes its own checkpoint under `pages/`. The report is updated after every page. If a page fails, the runner continues with the remaining pages and records the error. Re-running with `--resume` reuses completed detections and retries incomplete or failed pages.

To discard all previous full-68 output and start from zero:

```bash
bash tools/issue245/run_fresh_upstream_full68_probe.sh \
  --force
```

## Output

```text
logs/issue245_fresh_upstream_full68_probe/
  fresh_upstream_full68_probe_report.json
  pdfscore_source_snapshot/...
  pages/
    001_<artifact-key>/
      evaluator.log
      evaluator/...
    ...
```

The report records:

- canonical input path and SHA-256 for every image;
- normalized artifact key;
- uniquely resolved retained run and detection path;
- candidate detection path and SHA-256;
- per-image historical/current counts and tolerant comparison;
- aggregate historical/current/matched/only counts;
- aggregate thin-barline tagged counts;
- failed and differing artifact keys;
- whether all 68 pages are semantically equal.

## Decision gate

Proceed beyond baseline HOMR only when:

```text
status=completed
pages_completed=68
pages_failed=0
pages_different=0
historical_only_count=0
candidate_only_count=0
all_semantic_equal=true
```

If any page differs, stop before SR/OMR/consensus and inspect the page-level examples and evaluator log. If all 68 pages match, the baseline HOMR layer is fully reproducible from public inputs and the next investigation boundary is SR-side HOMR and OMR-DLN provenance.