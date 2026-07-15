# PDFScoreBar evaluator source-ref probe

## Purpose

The HOMR revision matrix established these focused page-001 boundaries:

- SegNet 308 with ONNX Runtime GPU 1.22.0 reproduces the current evaluator result: `85` matches, `2` historical-only, `16` candidate-only.
- SegNet 155 changes the result to `82 / 5 / 12`; reverting to the old Unet++ model is not a complete restoration.
- The upstream release currently provides SegNet 155 and 308 assets, but not the intermediate 301 and 303 weights referenced by their source revisions.
- The PR #58 feature head and merge commit produce the same `85 / 2 / 16` result.

The next controlled variable is therefore the PDFScoreBar evaluator/preprocessing source tree.

`run_pdfscore_evaluator_ref_probe.py` fixes:

- canonical `Va_Prokofiev_Symphony1/page_001.png` and its SHA-256;
- HOMR commit `2c6c65b00c836feb167d08c2553acec36ef68401`;
- SegNet 308 model selected by that commit;
- `onnxruntime-gpu==1.22.0`;
- current managed base-image dependencies;
- evaluator/default thin-barline route.

It varies only the PDFScoreBar `src/` tree:

1. current Issue #245 worktree source;
2. a historical candidate ref selected with `--historical-ref`.

The initial candidate `edf7bf610c3355c34e660192e81f35b03fe91714` produced a detection JSON identical to current source. The artifact-boundary candidate is `bd6ae56f8be6c87088143cfbf0ba09dee94fe0d7`.

## Run

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar_issue245

git fetch origin
git reset --hard \
  origin/investigate/issue245-fresh-upstream-detector-route

bash tools/issue245/run_pdfscore_evaluator_ref_probe.sh \
  --force \
  --keep-image \
  --historical-ref bd6ae56f8be6c87088143cfbf0ba09dee94fe0d7
```

The shell wrapper normalizes bind-mounted output ownership through Docker before and after the probe. Run it without `sudo`; this prevents repeated runs from failing on root-owned Docker artifacts.

The Python runner uses `git archive` to extract the historical `src/` tree under ignored `logs/`. It does not modify the worktree or create another Git worktree.

The compatibility launcher supports both evaluator CLI generations:

- newer source exports `run_evaluation(argv)`;
- pre-refactor source exports `main()` and reads `sys.argv`.

When a historical source predates `homr_eval_scripts.segnet_cache`, the launcher removes only the unsupported `--enable-segnet-cache` probe flag. SegNet caching is a runtime optimization and does not change detector inputs, model weights, or detection semantics.

Force a clean candidate-image build when necessary:

```bash
bash tools/issue245/run_pdfscore_evaluator_ref_probe.sh \
  --force \
  --rebuild
```

Keep the temporary candidate image only for diagnostics:

```bash
bash tools/issue245/run_pdfscore_evaluator_ref_probe.sh \
  --force \
  --keep-image
```

## Outputs

```text
logs/issue245_pdfscore_evaluator_ref_probe/
  pdfscore_evaluator_ref_probe_report.json
  docker_build.log
  historical_source_snapshot/
  current_source_control/
    evaluator.log
    evaluator/...
  historical_source_edf7bf6/
    evaluator.log
    evaluator/...
```

The historical output directory retains its original fixed name for compatibility. Confirm the actual requested and resolved ref in `historical_source` inside the report.

The report records source hashes for:

- `src/homr_eval_scripts/homr_evaluator.py`
- `src/common/preprocessing.py`
- `src/common/thin_barline_finder.py`
- `src/common/barline_evaluation.py`

It compares both fresh outputs with the retained historical 87-record result and compares current-source output directly with historical-source output.

## Decision gate

- If the historical source removes or materially reduces `2 missing / 16 extra`, inspect the changed evaluator/preprocessing functions and narrow to one file or function.
- If the artifact-boundary source produces the same result, tracked PDFScoreBar evaluator source is not the missing variable. Move to untracked `external/homr`, exact model/runtime provenance, deleted branch tips, and uncommitted state.
- Do not run full-68 or change a production default from this one-page probe.
