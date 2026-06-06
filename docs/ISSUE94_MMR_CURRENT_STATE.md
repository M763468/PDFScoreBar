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

- **選択した run**: `logs/issue120_e2e_recovery/stage_e_full_pipeline` (69ページ, mtime: 2026-06-05 01:05:51)
- **評価ページ**: 全68ページ
- **ローカルログ保存先**: `logs/issue94_mmr_current_state/`
- **定量精度評価結果 (REST GT 再整備後)**:
  - ユーザーによる手動アノテーション（アノテーション GUI `tools/gt_relabel_gui/`）を再実行し、68ページ全件から合計 180 件の MMR 正解データ（Ground Truth）を再整備。
  - `expected_overrides` 形式への標準化・インデックスシフトの自動補正を行い、`tools/issue94/eval_all_mmr.py` を用いて評価した結果は以下の通り。

| 指標 (Metric) | 評価結果 (Value) | 備考 (Notes) |
| :--- | :--- | :--- |
| **評価ページ数** | 68 ページ | - |
| **総ベース小節数** | 3,325 小節 | - |
| **期待される MMR (GT)** | **180 件** | `rest_count >= 2` の正解総数 |
| **検出された MMR** | **176 件** | モデル（CNN+OCRHeuristic）の検出総数 |
| **完全一致 (TP)** | **163 件** | 位置・休み数ともに一致 |
| **検出漏れ (FN)** | **7 件** | MMRが存在するが検出されなかった箇所 |
| **数値誤認識 (Mismatch)**| **10 件** | 検出されたが休み数が不一致 (OCRエラー等) |
| **誤検出 (FP)** | **3 件** | 正解にはない箇所での MMR 誤検出 |
| **適合率 (Precision)** | **92.61%** | `TP / (TP + FP)` |
| **再現率 (Recall)** | **90.56%** | `TP / GT` |
| **F1-Score** | **91.57%** | - |

- **アノテーション作業時に判明した「小節・段認識」の課題 (将来の検討事項)**:
  手動アノテーションの再整備にあたり、小節線から小節領域を構成する上流のレイヤーにおいて、以下の構造的な誤認識（バグ）が確認されました。これらは将来的な小節認識エンジンの修正時に要検討項目として申し送ります。
  1. **二重段の誤連結 (Divisi誤認)**:
     - 箇所: `Va_Prokofiev_Symphony1_page_004` (R72〜R86)
     - 現象: 含まれている二段は本来別のシステム（段）であるべきだが、divisiと誤判定されて二段を一段（同一システム）として結合してしまっている。
  2. **小節外領域の誤認識**:
     - 箇所: `Va__Prokofiev_Symphony5_page_007` (R1)
     - 現象: 最初の領域 R1 は小節ではない（誤検出）。このページの実際の最初の小節は R2 となっている部分である。
  3. **小節の過剰分割**:
     - 箇所: `Va__Prokofiev_Symphony5_page_015` (R37〜R38)
     - 現象: 本来は一つの小節である領域が、途中で二つの小節（R37とR38）に分割されてしまっている。

---
*本調査結果をもって、Issue #94 に対する現状把握および定量的な精度評価導線の整理はすべて完了しました。*
