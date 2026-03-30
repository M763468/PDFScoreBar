# Handoff: Issue #117 Resolution Status & Pending Verification

## 1. 現状のステータス (Status Summary)
- **達成された部分**: `Shostakovich-Festival_Overture_Va` にて、パイプライン単独での **Recall 100.0% / Precision 100.0% (FP=0)** を確認しました。
- **未達成の部分**: 他のデータセット（Sibelius, Symphony 5等）では依然として数件の FN（未検出）が残存しており、**全データセットでの 100% 再現という #117 の最終目標はまだ完全には完了していません。**

## 2. 実施済みの実装と修正 (Implemented Changes)
コード上に以下の修正をコミット済みですが、**「バグ修正後の最終的な動作確認（End-to-End評価）」はまだ行われていません。**

1. **[未検証] CNN画像ダウンスケールバグの修正**: 
   - **問題**: `cnn_scoring.py` で、1x画像が渡されているのに SRスケール（2.0等）で誤って0.5倍に縮小されてしまう致命的バグがありました。これにより画像と候補座標に完全なズレが生じていました。
   - **対策**: `candidate_rescale_factor` を導入し、画像のスケーリングと座標のスケーリングを完全に分離しました。（これにより他データセットの FN も解消されることが期待されますが、**未確認**です）。
2. **VOV不一致の修正**: インク密度に基づいてボックスをタイトにする `trim_box_to_ink` を実装。
3. **ネイティブ・フィルタの実装**: 外部ツールが担っていたFP除去フィルタ（`candidate_filters.py`）を統合。
4. **全パラメータの網羅と固定**: パイプライン上のすべてのパラメータをリストアップし、検証済みの設定をデフォルトとして固定（詳細は `docs/notes/issue117_parameter_inventory.md` 参照）。

## 3. 次のセッションへの引き継ぎ事項 (Next Steps)
次のセッションでは、**新しい機能追加やパラメータ調整を行う前に、必ず以下の検証を行ってください。**

1. **バグ修正版の動作確認 (CRITICAL)**:
   - コミット済みの「CNN画像ダウンスケールバグ修正」が含まれた状態で、全データセットの評価を再実行してください。
   - 実行コマンド:
     ```bash
     docker run --rm --gpus all -v $(pwd):/workspace -w /workspace -e PYTHONPATH=/workspace \
       pdfscore_pipeline_gpu /opt/venv_pipeline/bin/python src/pipeline/main.py \
       --config configs/verify_fixed_v10.yaml
     ```
   - 評価スクリプト（全データセット対象）:
     ```bash
     source .venv_pdf/bin/activate
     python tools/repro_accuracy/verify_pipeline_accuracy.py --run-dir [生成された最新ディレクトリ]
     ```
2. **結果の分析と #117 の完了判定**:
   - 上記の修正によって Sibelius 等の FN が解消され、全データセットで 100% 精度が確認できれば、Issue #117 は完了です。
   - もしそれでも FN が残る場合は、さらなる調査が必要です（ただし安易なパラメータ調整ではなく、抽出されたログやパッチ画像を直接確認して原因を特定してください）。

## 4. 万が一の再調査用：過去のコンテキストと証跡 (Fallback Investigation Context)
もし上記の修正でも 100% 再現に至らず、リファクタリング過程でのデグレードを再追跡する必要が生じた場合は、以下の歴史的情報を起点に調査を行ってください。

*   **関連Issue/PR**:
    *   **Epic Issue #5**: 100%精度達成の本来の目的。
    *   **Epic Issue #13**: パイプラインのモジュール化・リファクタリング作業（この過程でデグレードが発生）。
    *   **Issue #44 / PR #77**: 過去に「Recall 100% / Precision 100%」を報告した時点。
*   **重要な過去コミットハッシュとファイル**:
    *   `150ba36` 付近: 100%達成が報告されたタイミング。
    *   評価スクリプト: 当時はパイプライン統合前であり、`experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py` が最終評価を担っていた。
    *   クリーンデータ: 当時はパイプラインの自律処理ではなく、`logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12` という「外部から注入されたクリーンな中間データ」に依存していた。
    *   GT準備スクリプト: `d2072eb` などのコミットに含まれる `tools/verification/issue36_gt_prep/suggest_candidate_drops.py` が、上記の `v12` データを生成するための強力なフィルタとして機能していたと推測される。
*   **DPIの歴史的背景**:
    *   #25等の過去の検証は **300 または 360 DPI** の画像で行われていた。
    *   現在のパイプラインは SRx2 を通しているため **600 DPI相当** になっており、ハードコードされたピクセル定数や許容誤差（例：`x_merge_tol` 等）がスケールの違いによって機能しなくなっていた可能性がある。
*   **調査アプローチの指針**:
    やみくもにパラメータを調整するのではなく、「#25 (PR #77) のコミットにチェックアウトして動作確認」→「大規模なマージコミットごとに二分探索で動作確認」という手法で、どこでロジックが壊れたかを特定することを推奨します。
