# Session Handoff (Epic #120 Rebuild Roadmap)

## 1. 全体目標
Epic #120 の最終目標は、すべてのステップを統合した E2E パイプラインにおいて、過去の最高精度である **`TP=3580, FN=1, FP=0` を完全に復元すること**です。

## 2. 現在の状況（直近の調査結果）
過去の v12 ベースライン（`scoring_input_eval2_v12`）と同じ中間シードを生成すべく、様々な仕様差異（DPI、OMR-DLN結合、幾何学フィルタの実装漏れ等）をパイプライン（`src/pipeline`）に反映し、最新のコミット（`fix/probe_seeds` ブランチ）に適用しました。

しかし、この修正版（実験 V9）で `Va_Prokofiev_Symphony1` の3ページを対象に検証した結果、**依然として多数の False Negative (FN) が発生する真の原因**が以下の通り判明しました。

1. **シード生成フェーズでの欠落**: パイプライン前半の初期シード生成（未フィルタ）の段階で、すでに GT（正解データ）の **3.7% が取り逃がされています**。FN=1 を達成するにはここでの取り逃しはほぼ 0% でなければなりません。
2. **CNN スコアリングフェーズでの過小評価**: シード生成を無事に通過した GT 枠に対しても、**CNN モデルが合格スコア（0.1）を与えられずに約 9% の正解を破棄**（スコア 0.1 未満）しています。
3. **NMS・後処理フェーズでの消失**: スコア 0.1 を超えた正解であっても、その後の NMS（`src/pipeline/steps/cnn_scoring.py` の `_apply_nms`）で、少しズレた誤った枠にスコア負けして消去されたり、空間整合性チェック（`tools/re_evaluate_global.py` の `greedy_barline_match` 等）で弾かれている可能性があります。

詳細は `docs/ISSUE120_E2E_REPRODUCTION_REPORT.md` を参照してください。

## 3. 次セッションへの指示（Next Steps）
目標（FN=1, FP=0）の達成には、上記で判明した各フェーズにおける「脱落原因」を一つずつ潰していく必要があります。次セッションの AI アシスタントは以下の手順で調査・修正を進めてください。

### タスク1: シード生成漏れの救済（Recall 100% への引き上げ）
1. `tools/evaluate_e2e_predictions.py` や自作スクリプト等を用いて、「未フィルタのシード（`pipeline2_no_peak_candidates_unfiltered.json`）の時点で取り逃がしている GT 枠」を具体的に数個特定してください。
2. それらの GT 枠がなぜ `run_probe_scan_batch`（`src/pipeline/steps/probe_scan.py`）や Hybrid Consensus で見つからなかったのか、ログや画像出力を用いて原因（スキャンパラメータの不足、ハイブリッドロジックの漏れ等）を特定し、救済ロジックを実装してください。

### タスク2: CNN スコアリングでの FN 救済
1. シードとしては抽出されているのに、CNNスコアが `0.1` 未満になって破棄される GT 枠を特定してください。
2. その GT 枠の切り出し画像（パッチ）を実際に確認し、「なぜ CNN が低スコアを出すのか（センタリングがズレているのか、スケールがおかしいのか等）」を診断してください。
3. 必要であれば CNN の入力前処理（クロップやリサイズ方法）を修正し、正解枠に対して確実に 0.1 以上のスコアが出るように改善してください。

### 前提知識・読むべきコード
* **パイプライン実行設定**: 現在は `configs/evaluation2_e2e_verification_full_v12_restore.yaml` を使用して `PYTHONPATH=.:external/homr .venv_pdf/bin/python src/pipeline/main.py --config configs/evaluation2_e2e_verification_full_v12_restore.yaml` で実行可能です（DPI 360, OMR-DLN 有効化済み）。
* **シード生成ロジック**: `src/pipeline/steps/probe_scan.py`
* **CNNスコアリング**: `src/pipeline/steps/cnn_scoring.py`
* **評価スクリプト**: `tools/re_evaluate_global.py` および評価ロジック `tools/evaluate_e2e_predictions.py`

不要な一時スクリプト（`temp_*.py` 等）は前セッションで削除済みです。パイプラインの恒久的な修正コードのみがコミットされています。