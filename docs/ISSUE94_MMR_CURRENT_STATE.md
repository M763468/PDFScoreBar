# Issue #94: MMR current-state investigation

## Scope

This note records the current state of multi-measure-rest (MMR) handling around measure numbering. The issue was originally broad enough to imply a full accuracy fix, but this pass intentionally limits the work to current-state analysis and an MMR-only evaluation path. The active integration branch is `develop`; old `main` references in the historical issue context are not used for this work.

Out of scope for this pass:

- Full pipeline validation.
- Stage E detector contract or 68-page detector evaluation.
- Detector thresholds, candidate generation, NMS, CNN scoring, or canonical metric changes.
- Large OCR heuristics or model changes.
- Manual correction UI implementation.

## Historical context from `feature/measure_numbering`

`docs/DEVLOG_MEASURE_NUMBERING.md` shows that multi-measure rests were initially treated as a measure-numbering rule question: a rest should increment by the number printed above the rest rather than by one printed measure.

The old branch then introduced a manual override model:

- `MeasureAttribute.skip` adjusts the increment after a measure.
- For a rest count `N`, the override uses `skip = N - 1`.
- `tools/add_measure_numbers.py --config overrides.json` applies those overrides.

The historical OCR investigation also found that HOMR and OEMER did not provide rest-count digits. The branch therefore introduced ROI extraction, OCR with RapidOCR, digit filtering, and generation of measure overrides.

## Current code path on `develop`

The current implementation keeps the same high-level architecture, but it is split between pipeline orchestration and reusable MMR classes:

1. Base numbering creates measures from barline intervals.
   - `src/measure_numbering/numbering.py`
   - `MeasureNumberer.number_score()` builds an override map keyed by `(page, system, measure)`.
   - `MeasureNumberer.number_system()` creates measure objects and increments by `1 + skip` when a matching override exists.

2. Pipeline Phase A creates base numbering JSON.
   - `src/pipeline/orchestrator.py`
   - `run_base_numbering_and_barline_correction()` writes per-page `numbering_base.json` files.

3. Pipeline Phase B runs MMR detection on the base numbering output.
   - `src/pipeline/orchestrator.py`
   - `run_mmr_batch_detection()` calls `src.pipeline.steps.numbering.run_mmr_batch()`.

4. `run_mmr_batch()` wires provider-aware RapidOCR.
   - `src/pipeline/steps/numbering.py`
   - It uses `src.measure_numbering.rapidocr_provider.create_mmr_rapidocr()` and passes the resulting OCR engine into `MMROCREngine`.
   - This preserves the #189 / PR #192 provider-selection path.

5. `src/measure_numbering/mmr.py` performs MMR classification and OCR.
   - `MMRClassifier.predict()` assigns an MMR/rest probability to the measure crop.
   - `MMROCREngine` masks the H-bar, preprocesses OCR variants, merges split OCR boxes, filters blacklisted text, and selects a geometric best digit candidate.
   - `MMRProcessor.process_pages()` emits `measure_overrides` entries using `skip = found_num - 1`.

6. Phase C merges detected overrides with optional user overrides and reruns numbering.
   - Final numbering should reflect the larger increment when the MMR override is present.

## Failure taxonomy for #94

Use the following categories when inspecting a page or artifact:

- `candidate_missing`: the target printed rest interval is absent from `numbering_base.json`, usually because barlines/staves/system grouping did not create a corresponding measure interval. This is upstream of MMR OCR.
- `cnn_rejected`: the interval exists but the MMR classifier probability does not reach `rescue_threshold`; OCR is not attempted.
- `ocr_missing`: OCR is attempted but no valid integer >= 2 is selected.
- `ocr_wrong`: OCR emits an integer but it differs from the expected rest count.
- `override_missing`: OCR appears correct in logs or debug data, but no override entry is emitted.
- `override_wrong_target`: an override is emitted for the wrong `(page, system, measure)` key.
- `numbering_not_applied`: an override exists, but the final numbering did not increment by `1 + skip`.
- `manual_needed`: the page is ambiguous enough that a hand-authored override is the safer short-term path.

## MMR-only evaluation path

The added `tools/issue94/eval_mmr_overrides.py` script avoids full pipeline and Stage E evaluation. It reuses existing per-page base numbering JSON and image files, runs only the MMR override generator, and optionally compares the detected overrides with a small expected-overrides JSON.

Minimal command:

```bash
PYTHONPATH=. python tools/issue94/eval_mmr_overrides.py \
  --numbering-json logs/<run>/intermediate/<page_id>/numbering_base.json \
  --image data/<score>/page_010.png \
  --model-path tools/mmr_training/models/mmr_classifier_best.pth \
  --output-dir logs/issue94_mmr_eval/page_010
```

With expected overrides:

```bash
PYTHONPATH=. python tools/issue94/eval_mmr_overrides.py \
  --numbering-json logs/<run>/intermediate/<page_id>/numbering_base.json \
  --image data/<score>/page_010.png \
  --model-path tools/mmr_training/models/mmr_classifier_best.pth \
  --expected-overrides docs/examples/issue94_expected_overrides.page010.json \
  --output-dir logs/issue94_mmr_eval/page_010
```

The script writes:

- `mmr_overrides.json`: raw MMR-detected overrides.
- `mmr_eval_summary.json`: counts, matched/missed/unexpected overrides, and taxonomy hints.
- `mmr_debug/`: optional debug overlays emitted by `MMRProcessor`.

These outputs are local artifacts and should not be committed unless a deliberately tiny fixture is added later.

## Current reproduction status

This pass establishes a way to check #94 without rerunning the detector or the full pipeline. The current code path still depends on two gates before OCR can affect numbering:

1. the base numbering must contain the target measure interval, and
2. the MMR classifier probability must exceed `rescue_threshold`.

Therefore #94 can still appear through several distinct mechanisms. The current repository has the override application path in place, so a correctly emitted override should update numbering. The highest-risk remaining areas are:

- MMR candidate not entering OCR because the CNN gate is too low-confidence.
- OCR failing or selecting nearby rehearsal/tempo/instrument text.
- OCR being correct but attached to the wrong system/measure index when system grouping differs from the historical branch assumptions.

No detector, CNN, Stage E, or canonical metric change was made in this pass.

## Follow-up candidates

### 1. Manual MMR override workflow

Priority: high if #94 still blocks practical use.

Suggested scope:

- Define a stable JSON schema for manual MMR overrides.
- Add documentation and examples for specifying `(page, system, measure, skip)`.
- Ensure manual overrides merge cleanly with automatically detected MMR overrides.
- Add a small regression fixture showing that a hand-authored override changes final numbering.

### 2. MMR OCR accuracy improvement

Priority: medium/high, but should be separate from the current investigation.

Suggested scope:

- Collect local MMR-only failure summaries produced by `tools/issue94/eval_mmr_overrides.py`.
- Classify misses by CNN gate, OCR miss, wrong OCR value, wrong target, or candidate-missing.
- Only then decide whether to tune crop geometry, OCR post-processing, rescue thresholds, or model data.

### 3. MMR regression fixture

Priority: medium.

Suggested scope:

- Add a deliberately small fixture that does not depend on full pipeline execution.
- Cover `skip = N - 1` application and at least one OCR/classifier mocked path.

## Local run investigation: 2026-06-06

- 選択した run: `logs/issue120_e2e_recovery/stage_e_full_pipeline` (69ページ, mtime: 2026-06-05 01:05:51)
- 評価ページ: 全68ページ
- ローカルログ保存先: `logs/issue94_mmr_current_state/`
- サマリ:
  - 68ページ全体のデータセット評価を `tools/issue94/eval_all_mmr.py` を使用して GPU 上で実行。
  - 総小節数 3,325 のうち、49ページにわたり 176 件の MMR overrides が検出された。
  - 今回の実行では expected overrides (グラウンドトゥルース) は使用していない。
- 再現ステータス:
  - MMR プロセッサはバッチモードで問題なく動作し、複数の MMR 候補を正常にリストアップできた。
  - OCR の誤認識 (`ocr_wrong`) や認識漏れ (`ocr_missing`)、また CNN 確信度が境界線付近（ページ9のsystem 2 measure 1では確信度 0.51）で却下される `cnn_rejected` のリスクは依然として高い。
- Follow-up 推奨アクション:
  - 検出された 176 件のケースを分類・評価するため、期待値データ (ground-truth) を含む小さな回帰テスト用の fixture を構築する。
  - 誤検出や検出漏れを修正できるよう、手動 MMR override ワークフローを実装する。

