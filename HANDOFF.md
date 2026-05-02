# Session Handoff (Epic #120 Rebuild Roadmap)

## 1. 全体目標
Epic #120 の最終目標は、すべてのステップを統合した E2E パイプラインにおいて、過去の最高精度である **`TP=3580, FN=1, FP=0` を完全に復元すること**です。(ISSUE#044関連でその記述あり。過去数回の調査結果も参照。)

## 2. 現在の状況（直近の調査結果）
過去の v12 ベースライン（`scoring_input_eval2_v12`）と同じ中間シードを生成すべく、様々な仕様差異（DPI、OMR-DLN結合、幾何学フィルタの実装漏れ等）をパイプライン（`src/pipeline`）に反映し、最新のコミット（`fix/probe_seeds` ブランチ）に適用しました。

しかし、この修正版（実験 V9）で `Va_Prokofiev_Symphony1` の3ページを対象に検証した結果、依然として多数の False Negative (FN) が発生しており、その要因として以下の事象が観測・報告されています。

1. **シード生成フェーズでの欠落**: パイプライン前半の初期シード生成（未フィルタ）の段階で、すでに GT（正解データ）の **3.7% が取り逃がされています**。
2. **CNN スコアリングフェーズでの過小評価**: シード生成を無事に通過した GT 枠に対して、**CNN モデルが合格スコア（0.1）を与えられずに約 9% の正解を破棄**（スコア 0.1 未満）しています。
3. **NMS・後処理フェーズでの消失**: スコア 0.1 を超えた正解であっても、その後の NMS や空間整合性チェックで消去されている可能性があります。

※ 詳細は `docs/ISSUE120_E2E_REPRODUCTION_REPORT.md` を参照してください。

## 3. 次セッションへの指示（Next Steps）
**【重要】次セッションでは、いきなり CNN スコアリング等のコード修正（実装）には入らないでください。**
CNN 自体は既にテスト済みのコンポーネントであり、内部ロジックやモデル自体に手を入れることは極力避けるべき方針です。次セッションの AI アシスタントは以下の手順で「検証」と「方針の再検討」を進めてください。

### タスク1: ここまでの調査結果の検証と深掘り
1. 前セッションのレポート（`docs/ISSUE120_E2E_REPRODUCTION_REPORT.md`）で指摘された「シード生成での漏れ」および「CNNスコアリングでの過小評価」について、実際のデータ（ログや json 出力等）を確認し、その調査結果の妥当性を検証してください。
2. 特に「CNN が GT に対して低いスコアを出している」という点について、「v12 構築当時はどうやってこれを通過していたのか（あるいはそもそも CNN にかけられていなかったのか？）」を解明してください。CNN への入力画像パッチの切り出され方（クロップ領域、座標系のズレ、スケールの影響など）、E2E と v12 の間の**CNNに対する入力条件の差異**がないか分析してください。

### タスク2: TP=3580, FN=1, FP=0 達成に向けた設計・方針の再検討
1. タスク1の検証結果を踏まえ、**既存の CNN モデル自体には手を入れずに**目標精度を完全に復元するための、新しい設計や修正方針を検討してください。
2. シード生成ロジックの改善、CNN への入力前処理（クロップ・センタリング）の適正化、あるいは NMS や後処理ヒューリスティクスの見直しなど、どのレイヤーをどう修正するのが最もアーキテクチャとして適切か、方針をドキュメント化してください。
3. 方針が固まったら、ユーザーに提示して合意形成を行ってください。

### 前提知識・読むべきコード
* **パイプライン実行環境とコマンド**:
  OMR-DLN を含む完全なパイプラインは `pdfscore_pipeline_gpu` コンテナ内で実行する必要があります。以下の手順で実行可能です（DPI 360, OMR-DLN 有効化、過剰フィルタ無効化済みの設定を使用）。

  ```bash
  # 1. コンテナが起動していない場合は起動する
  docker run --gpus all -d --name pdfscore_pipeline_gpu -v "$(pwd):/workspace" -w /workspace pdfscore_pipeline_gpu tail -f /dev/null

  # 2. コンテナ内でパイプラインを実行する
  docker exec -e PYTHONPATH=/workspace:/workspace/external/homr pdfscore_pipeline_gpu /opt/venv_pipeline/bin/python src/pipeline/main.py --config configs/evaluation2_e2e_verification_full_v12_restore.yaml
  ```
* **シード生成ロジック**: `src/pipeline/steps/probe_scan.py`
* **CNNスコアリング**: `src/pipeline/steps/cnn_scoring.py`
* **評価スクリプト**: `tools/re_evaluate_global.py` および評価ロジック `tools/evaluate_e2e_predictions.py`

---

## 4. 2026-05-02 更新: full 68-page v12 restore 固定結果

上記の古い V9 調査後、CNNモデル自体は変更せず、E2E と v12 baseline の入力条件差を潰す方針で以下を実装・検証しました。

* `src/pipeline/steps/cnn_scoring.py` に crop recenter 条件、NMS x距離設定、unit基準の低身長候補抑制を追加。
* `tools/eval2_full_detection_report.py` を追加し、`center_anchor` ルールで full 68-page の `TP/FP/FN/FN_cnn/FN_det` と FP/FN crop/overlay を生成可能にした。
* `tools/create_eval2_full_restore_configs.py` を追加し、full 68-page の per-score config/manifest を再生成可能にした。
* `tools/eval2_residual_measure_impact.py` を追加し、検出残差を小節数カウント影響候補別に分類可能にした。
* `tools/eval2_measure_count_kpi.py` を追加し、同じ 68-page 出力を `MeasureNumberingPipeline` に通して GT box 起点の小節数カウント KPI と比較可能にした。

固定レポート:

* `docs/ISSUE120_E2E_FULL68_RESTORE_REPORT.md`

再現入口:

```bash
PYTHONPATH=.:external/homr .venv_pdf/bin/python tools/create_eval2_full_restore_configs.py \
  --output-dir logs/issue120_e2e_recovery/eval2_full_configs
```

最終 full 68-page 検出結果:

* `filtered_cnn_json`: `TP=3561, FP=125, FN=20, FN_cnn=17, FN_det=3, GT=3581`
* `probe_candidates`: `TP=3574, FP=59298, FN=7`
* `score>=0.5`: `TP=3559, FP=77, FN=22`

小節数カウント観点の残差分類:

* FN 20件のうち 12件は近接する matched prediction に覆われており、検出評価上はFNだが小節境界としては `likely_count_neutral`。
* 残り FN 8件は `likely_count_affecting` として優先確認対象。
* FP 125件のうち 25件は近接GT重複で numbering dedup 依存、100件は remote/tall 系で小節数カウントに影響しやすい。

下流小節数カウント KPI:

* `filtered`: 68 pages, pred measures 3394, GT measures 3384, net delta +10, abs delta sum 18, delta pages 9, measure precision 0.9932, recall 0.9962。
* `score>=0.5`: 68 pages, pred measures 3388, GT measures 3384, net delta +4, abs delta sum 12, delta pages 6, measure precision 0.9956, recall 0.9967。
* `score>=0.5 + min_height>=2.8 unit`: 68 pages, pred measures 3382, GT measures 3384, net delta -2, abs delta sum 6, delta pages 4, measure precision 0.9979, recall 0.9973。
* `Shostakovich-Festival_Overture_Va` は検出残差があるが小節数では 349/349 で差分なし。
* 現在の最良候補で残る count-delta 優先確認ページは `Sibelius-Violin_Concerto-Viola/page_006` (-3), `Shostakovich-Sym5-Va/page_018` (+1), `Va_Prokofiev_Symphony1/page_005` (-1), `Va__Prokofiev_Symphony5/page_019` (+1)。

レビュー入口:

* `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_count_kpi/measure_count_review.md`
* `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_impact/measure_impact_review.md`
* `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/visuals/fp_crops/`
* `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/visuals/fn_crops/`
* `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/visuals/overlays/`

次の優先方針:

1. `score>=0.5 + cnn_min_height_unit_ratio=2.8` を次の下流動作候補として扱い、4件の count-delta ページを overlay で確認する。
2. FP は `Shostakovich/page_018` と `Va__Prokofiev_Symphony5/page_019` の over-count を優先する。max-height 抑制と x-distance NMS は小節数 KPI に効かなかった。
3. FN は `Sibelius/page_006` と `Va_Prokofiev_Symphony1/page_005` の under-count に限定して検証する。`Sibelius/page_006` は candidate-stage miss を含むため CNN threshold では戻らない。複線・終端片側FNは 12/20 が count-neutral なので、広域 left-shift 回復は採用しない。
4. 今後の採否は検出 `TP/FP/FN/FN_cnn/FN_det` と小節数 `measure_delta/abs_delta` の両方で判断する。
