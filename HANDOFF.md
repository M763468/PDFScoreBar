# Handoff: Issue #117 - Accuracy Reproduction & Recovery Complete

## 1. 成果概要 (Achievement)
Issue #44 で達成された過去の最高精度（Recall 100% / Precision 100%）を現在のパイプラインで再現する手法を確立し、論理的な証明を完了しました。
（※本セッションの詳細な調査レポートとエビデンスは、[docs/notes/REPRODUCE_MAX_ACCURACY.md](docs/notes/REPRODUCE_MAX_ACCURACY.md) に集約されています。次セッションの開始前に必ずご一読ください）

*   **実証結果**: 現在のコードベースに当時のシードを注入し、**Prokofiev 5 で TP: 1046 / FP: 0 / FN: 0** を復元。
*   **自律再現**: 現在の検出器から「クリーンなシード」を再生成する手順を確立。全 68 ページで **Recall 99.9% / Precision 100.0%** を達成。
*   **バグ修正**: 再現を阻んでいた 3 つの「サイレント・バグ」を特定し、`src/` 内で修正済み。

## 2. 修正済みのバグ (Bug Fixes applied to `src/`)
これらのバグ修正はすでに現在のブランチ (`fix/pipeline_architecture`) にコミット済みです（Commit: `c12c600`）。次のセッションではこれらの修正が適用された状態からパイプライン統合を開始できます。

1.  **Tall Band Dilution**: `split_box_vertically` を導入。多段ボックスによる密度希釈を解消。
2.  **Scaling Bug**: 座標変換を 1x 空間に統一。CNN パッチ抽出と幾何学フィルタの不一致を解消。
3.  **Threshold Bug**: `cnn_scoring.py` の判定を `>` から `>=` に修正。
4.  **Mask Dir Resolution**: `DetectorOrchestrator` のマスク参照先を SR/Baseline で適切に切り替えるよう修正。

## 3. 次のセッションへの引き継ぎ事項 (Next Steps)
確立された「再現レシピ」を、メインのパイプライン（`src/pipeline/main.py` 等）にデフォルト設定または正式なオプションとして統合する必要があります。現在のブランチ `fix/pipeline_architecture` にはバグ修正コミットや再現スクリプトが追加されたクリーンな状態です。

*   **統合のポイント**:
    *   `Probe Scan` 前の `split_box_vertically` の適用タイミング。
    *   `apply_nms` (X-distベース) の正式な組み込み（現在は `cnn_scoring.py` に関数として存在するが、呼び出しは未実装）。
    *   `min_ratio: 0.59` のような環境依存の微調整をどう扱うか（マージン設計の反映）。

## 4. ほぼ100%の精度が保たれていることを確認する方法 (Verification)
以下のスクリプトを実行することで、いつでも最高精度の再現性を確認できます。

1.  **シード再生成**: 
    ```bash
    PYTHONPATH=. .venv_cnn_classifier/bin/python tools/repro_accuracy/reproduce_clean_seed_v12.py
    ```
2.  **精度評価**: 
    ```bash
    PYTHONPATH=. .venv_cnn_classifier/bin/python tools/repro_accuracy/verify_repro_batch_final.py
    ```

*※許容される誤差: 統計上の FN 4件。これは GT が 1 本の線を上下 2 段に分けて定義していること（Divisi等）に起因する中心座標マッチング（`center_anchor`）上の仕様であり、物理的な検出ミスではありません。*

## 5. 調査資料
*   詳細レポート: `docs/notes/REPRODUCE_MAX_ACCURACY.md`
