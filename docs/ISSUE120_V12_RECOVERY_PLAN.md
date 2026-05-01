# V12 Baseline Generation Investigation & E2E Recovery Plan

## 目的
本ドキュメントは、Epic #120 の目標である「高精度パイプラインの再構築」に向けて、過去のベースラインとして利用されていた `scoring_input_eval2_v12` 相当のシード（中間生成物）がどのように生成されていたかを解明し、現状の E2E パイプラインをそれに合致させるための修正方針をまとめたものです。

---

## タスク 1: v12 ベースラインの生成方法の全貌

過去のコミット履歴と `tools/repro_accuracy/reproduce_clean_seed_v12.py` の解析から、v12 ベースライン生成の完全なプロセスが判明しました。

### 1. 実行スクリプトと順序
シード生成は、主に単一のスクリプト `tools/repro_accuracy/reproduce_clean_seed_v12.py` を用いてバッチ処理として実行されていました。
内部での処理順序は以下の3ステップです。

1. **Hybrid Consensus (UNION & Scale)**:
   - 各スコアの `baseline`, `sr`, `omr_sr` の推論結果（JSON）を読み込む。
   - 参照元の推論解像度（424 DPI 等）から、評価対象のオリジナル画像（1x / 300 DPI）へと座標をダウンスケール・アップスケール補正（`dyn_scale = eval_w / ref_w`）。
   - すべての枠を結合（UNION）し、IoU > 0.8 で Greedy Deduplication を行い、初期の `hybrid_boxes` とする。
2. **Probe Scan (1x解像度, フィルター無効化)**:
   - 1x解像度のオリジナル画像に対して `run_probe_scan_batch` を実行。
   - この際、**内部のヒューリスティックフィルターを完全無効化**（`enable_heuristic_filters=False`）し、すべての候補枠を一旦出力する（Recallの最大化）。
   - マスク画像も渡さない（`staff_mask_dir=None`）ため、`band_source` は `row_stats` にフォールバックされる。
3. **後処理での手動フィルタリング (Post-filtering)**:
   - スキャンで得られた生候補 (`raw_candidates`) 全てに対し、後から `filter_probe_candidates` を実行。
   - この際、既に確定した枠を保護する引数 `existing_boxes` に空リスト `[]` を渡し、**Hybrid 出力の既存枠と新規生成枠を区別せず、すべて平等に**フィルタリングしていた。

### 2. 入力画像とマスクの形状
- **入力画像**: `data/evaluation2/images/` 等にある **1x解像度 (オリジナル)** の画像。
- **マスク画像 (最大の違い)**:
  - フィルタリングには、HOMR が出力した `*_debug_3_staff.png` が使用されていました。
  - これは五線譜の領域を塗りつぶした「リージョン（領域）マスク」ではなく、**五線の線だけが黒く残った「ライン（線）マスク」** です。
  - 解像度合わせのため、このラインマスクを `cv2.INTER_NEAREST` で 1x 画像のサイズに強制リサイズして使用していました。

### 3. 具体的なパラメータ設定
- **Hybrid Consensus**: Deduplication IoU threshold = 0.8
- **Probe Scan (`run_probe_scan_batch`)**:
  - `min_ratio=0.1`
  - `min_height_ratio=0.0`, `min_width_ratio=0.0` (制限なし)
  - `input_image_scale=1.0`
  - `vertical_closing=4`
  - `detect_probe_kwargs` (抜粋): `max_per_band: 100`, `band_scan_line_ratio: 0.6`, `band_scan_min_lines: 5`, `band_source: "row_stats"`
- **Heuristic Filtering (`filter_probe_candidates`)**:
  - `left_margin_ratio=0.12`, `clef_left_ratio=0.25`
  - `min_height_median_ratio=0.4`
  - `ink_threshold=180`, `min_ink_ratio=0.18`
  - `paper_threshold=200`, `min_paper_overlap_ratio=0.6`
  - `min_staff_overlap_ratio=0.02`

---

## タスク 2: E2E パイプラインの修正方針 (Recovery Plan)

調査結果に基づき、現在の E2E パイプラインを v12 ベースラインと同等の結果を出力するように修正するための方針です。

### 修正方針 1: Hybrid Consensus の UNION 化
現在の E2E (`HybridDetector`) は `INTERSECTION`（論理積：各モデルの合意が取れたものだけ残す）として実装されていますが、v12 のように初期シードの Recall を最大化するためには、これを **UNION（論理和）** に変更する必要があります。
- **方針**: `apply_hybrid_consensus_filter` に `mode="union"` オプションを追加し、Pass 1 (シード生成) ではこれを呼び出す。重複排除は v12 同様 IoU > 0.8 を基準とする。

### 修正方針 2: シード生成 (Pass 1) の 1x 解像度への分離
現在の E2E は `enable_sr=True` だと、シード生成の段階からすべて 2x (SR) 解像度で実行し、さらに `input_image_scale=2.0` を二重適用してしまうバグが内在しています。
- **方針**: `orchestrator.py` における `_run_probe_scan` (Pass 1) は、**必ず 1x のオリジナル画像 (`self.images`) を用いて実行**するようにコードを分離する。これによりスケーリングの二重適用バグも回避される。

### 修正方針 3: フィルタリングのタイミングと適用対象の是正
現在の E2E は `run_probe_scan_batch` 内部でフィルター (`enable_heuristic_filters=True`) をかけ、さらに既存の Hybrid 枠は保護 (`existing_boxes=...`) しています。
- **方針**: Orchestrator の Pass 1 では `enable_heuristic_filters=False` として `run_probe_scan_batch` を実行する。直後に、Orchestrator 上で `filter_probe_candidates` を `existing_boxes=[]` として全候補に対して一括で適用し直す。

### 修正方針 4: Staff Mask の形状問題（※重要検討事項）
v12 では「ライン（線）マスク (`debug_3_staff.png`)」が使われていたため、`min_paper_overlap_ratio=0.6`（紙領域との重なり）や `min_staff_overlap_ratio=0.02` の挙動が、現在の E2E が動的に生成する「領域（リージョン）マスク」とは全く異なります。
- **方針**: E2E に v12 を完全再現させるなら、E2E のパイプライン内部で一時的に `debug_3_staff.png` （またはそれと同等の線マスク）をロードまたは生成し、フィルタリング時にのみそれを渡す必要があります。
- **パイプライン組み込みの困難さと懸念**:
  1. **ラインマスクへの依存は脆い**: v12 のフィルタリングは、たった数ピクセルの「線」との重なり（0.02 = 2%）に依存していました。これは画像のスケーリングや微妙な解像度の違いで容易に 0% になり、正解候補が破棄される原因になります。
  2. **Paper Overlap の意味の変質**: ラインマスクを使用すると五線の間も「紙」と判定されるため、`min_paper_overlap_ratio` が実質的に「黒インクでない部分の割合」と同義になってしまい、本来意図した「紙領域かどうか」の幾何学的チェックとして機能していません。
  3. **統合の歪さ**: E2E パイプラインは一貫した動的領域マスク生成を目指して構築されています。v12 の精度（TP=3580）を一時的に「復元」するためだけに、過去のレガシーなラインマスク（HOMR の一時的なデバッグ出力）にパイプラインの根幹を依存させることは、中長期的なアーキテクチャの安定性を損なう恐れがあります。

**結論**:
まずは「完全互換モード」として、上記 1〜3 を実装し、4 についても `debug_3_staff.png` を外部から明示的に注入（Injection）できる口を `orchestrator.py` に設けることで v12 シードの完全再現を達成する計画とします。ただし、将来的にはこのラインマスク依存のルールセット自体を再学習・再調整（CNN の再学習など）して撤廃することが望ましいです。
