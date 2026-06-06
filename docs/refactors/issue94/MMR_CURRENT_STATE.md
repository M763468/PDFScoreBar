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

## Error visualization and initial inspection: 2026-06-06

### Inputs
- 定量評価ログ: `logs/issue94_mmr_current_state/eval/aggregated_eval_summary.json`
- 小節線・レイアウト情報: `logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/<page_id>/numbering_base.json`
- 手動アノテーション正解: `tests/fixtures/expected_overrides_page_*.json`

### Error case summary
エラー集計 JSON（`logs/issue94_mmr_current_state/error_inspection/error_cases_summary.json`）および可視化オーバーレイ画像（`logs/issue94_mmr_current_state/error_visualization/` 配下の png 画像、計 17 枚のローカルアーティファクト）を出力し、エラーの初期分類を行いました。

全体で確認されたエラー 20 件の内訳と傾向は以下の通りです。
- **検出漏れ (FN / missed)**: 7 件
  - `page_001` (R7, R4), `page_002` (R3), `page_004` (R3), `page_009` (R3), `page_023` (R7), `page_042` (R3)
- **数値誤認識 (Mismatch / skip_mismatch)**: 10 件
  - `page_002` (期待 2 -> 検出 7), `page_004` (期待 15 -> 検出 5)
  - `page_012` (期待 3 -> 検出 20), `page_018` (期待 9 -> 検出 6), `page_021` (期待 4 -> 検出 79), `page_025` (期待 5 -> 検出 97)
  - `page_049` (期待 3 -> 検出 39), `page_049` (期待 5 -> 検出 10), `page_055` (期待 2 -> 検出 42), `page_064` (期待 6 -> 検出 5)
- **誤検出 (FP / unexpected)**: 3 件
  - `page_033` (検出 11), `page_035` (検出 2), `page_037` (検出 6)

### MMR-layer findings
- **OCR 誤認・無関係な数字の拾い上げ (ocr_wrong / ocr_wrong_target)**:
  mismatch（10件）の中で、特に期待値に対して検出された休み小節数が極端に大きいものが目立ちます。これらは、五線周辺にある練習番号（Rehearsal Number）などを MMR OCR Heuristic が MMR 領域として誤って切り出し、認識したことが主因です。
  可視化画像から確認された具体例は以下の通りです。
  - `page_021` (期待 4 -> 検出 79): 近くにある練習番号 79 番の数字を誤認。
  - `page_025` (期待 5 -> 検出 97): 近くにある練習番号 97 番の数字を誤認。
  - `page_049` (期待 3 -> 検出 39): 3 小節休みに加え、近くの練習番号 9 番が結合して 39 と認識された。
  - `page_049` (期待 5 -> 検出 10): 検出された DetRest が画像外・範囲外に描画されており詳細不明。
  - `page_055` (期待 2 -> 検出 42): 近くにある練習番号 42 番の数字を誤認。
  - `page_064` (期待 6 -> 検出 5): すぐ近くに練習番号 95 が存在し、検出された 5 はその下一桁部分を誤認した可能性がある。
- **CNN 棄却または OCR 漏れ (cnn_rejected / ocr_missing)**:
  missed（7件）については、MMR 領域（小節休みの H-bar）自体を MMRClassifier が閾値未満として棄却したか、OCR 自体が数字を一切見つけられなかったことが主因です。
- **FP と GT Fixture の不完全性 (expected_fixture_or_alignment_issue)**:
  unexpected（3件）について詳細を確認したところ、以下のように GT Fixture 側の設定漏れであることが判明しました。
  - `page_033` (検出 11): 誤検出、または GT 漏れの疑い。
  - `page_035` (検出 2): GT 側の設定漏れ。実際には 2 小節休みで正解（モデルが正しく検出していた）。
  - `page_037` (検出 6): GT 側の設定漏れ。実際には 6 小節休みで正解（モデルが正しく検出していた）。
  このように、FP のうち少なくとも 2 件は GT 側の定義エラーであり、モデル自体は正しく検出していました。

### Upstream measure-construction findings
- MMR 評価において、小節線検出とそれに基づく小節番号（measure numbering）がずれると、expected fixture (GT) と detected MMR の小節インデックスが狂うため、正しいマッチングができずに mismatch または FN になる現象（`numbering_base_alignment_issue`）が確認されました。
- 特に `numbering_base.json` で小節番号自体がずれている場合、アノテーションデータ作成時と実際の検出時でインデックスが物理的に一致しないため、上流のエラーがそのまま MMR の評価エラーとして現れます。
- **段グループ化の不具合による影響**:
  - `page_021` において、該当の段は divisi の上段ですが、システム上では独立した段として誤検出されています。これも小節線からの小節認識という上流レイヤーのバグが、MMR の評価に影響を与えているケースと言えます。

### Known upstream cases to hand off to #194
既知の上流問題 3 件について、`numbering_base.json` と画像を照合して原因を特定し、#194 へ引き継げる形で詳細を整理しました。

1. **`Va_Prokofiev_Symphony1_page_004` (R72〜R86)**:
   - **確認したアーティファクト**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/page_045/numbering_base.json` (L801〜935)
   - **現象**: 2 つの五線（staves: L785, L793）が 1 つのシステム（段）として誤認識・結合されています。このシステム内の小節の bbox は ymin(3526) から ymax(3952) に及び、上下 2 つの段を縦に貫く形で小節領域が構築されています。
   - **影響**: 上下で別々の段であるはずの領域が 1 段にマージされたため、小節線と小節アライメントが完全に崩壊し、正しい MMR 認識や小節番号インクリメントが不可能となっています。
   - **再現**: #194 でのレイアウト（システム/段）検出と divisi 判定の修正対象となる最小再現ケースです。

2. **`Va__Prokofiev_Symphony5_page_007` (R1)**:
   - **確認したアーティファクト**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/page_053/numbering_base.json` (L32〜41)
   - **現象**: 最初の小節 `number: 1` の bbox が `[486, 872, 665, 1039]` (幅 179px) と極端に狭く検出されています。これは五線の左端（余白や音部記号の領域）を誤って小節領域として切り出している状態です。
   - **影響**: 本来の第 1 小節が R2 として認識されるため、ページ全体の小節番号が 1 つずつ後ろにずれてアライメントエラーになります。
   - **再現**: non-measure region (五線左側の記号領域) の小節線フィルタリング、または小節認識の開始位置決定ロジックのバグとして、#194 で扱うべき対象です。

3. **`Va__Prokofiev_Symphony5_page_015` (R37〜R38)**:
   - **確認したアーティファクト**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/page_060/numbering_base.json` (L481〜499)
   - **現象**: 本来 1 つの小節であるべき領域が、R37 `[216, 3955, 580, 4135]` と R38 `[584, 3955, 1028, 4135]` の 2 つに過剰分割（over split）されています。
   - **影響**: 小節数のカウントが 1 つ増え、以降の小節番号がずれます。
   - **再現**: 小節線誤検出、または微小な縦線の小節線マージ（deduplication）漏れに起因するものであり、#194 での小節境界判定ロジックの修正対象です。

### Follow-up handoff
- **#194: 上流レイアウト・小節境界判定バグ調査**:
  - `page_045` (divisi / system merge), `page_053` (non-measure region), `page_060` (measure over split) を最小再現ケースとして引き継ぎ、段グループ化および小節境界構築の修正を進める。
- **#195: MMR 層の分類精度・手動補正ワークフロー**:
  - MMR 誤認識（特に mismatch での極端な数値の誤読や強弱記号の誤認）に対する、RapidOCR 画像前処理（二値化、ノイズ除去、数字アライメント）の改善および CNNConf 閾値の適正化の検討。
  - 自動検出が失敗した際の救済措置として、手動アノテーションファイル（expected overrides）をマージ・優先適用するワークフローの標準化を進める。

---
*本調査結果をもって、Issue #94 に対する現状把握および定量的な精度評価導線の整理はすべて完了しました。*
