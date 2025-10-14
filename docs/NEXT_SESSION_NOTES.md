# 次回セッションへの引き継ぎノート

## セッションログ

### 2025-09-27 23:38 JST
- homr と oemer の比較検証体制を整備し、page_3 GT を用いた評価を進める計画を策定。
- 次アクション: homr チューニング範囲の棚卸し、oemer ベースラインの再確認、双方の成果物整理ルールの確立。
- 留意事項: 評価成果物は JST タイムスタンプ付きで `logs/homr_eval/` 等に保存し、再現手順を docs に記録する。
- oemer 改造メモ: `src/archive/oemer/run_omerer.py` に `layers.get_layer("barlines")` の JSON 出力を追加し、`logs/oemer_eval/<timestamp>_baseline/` で metrics・オーバーレイを管理する。

### 2025-10-06 01:59 JST
- onnxruntime の CUDA プロバイダ設定（`cudnn_conv_use_max_workspace=1`, `cudnn_conv_algo_search=EXHAUSTIVE`）を `src/archive/oemer/run_omerer.py` へ組み込み、`logs/oemer_eval/20251006T015540JST_baseline/ort_profiles/` と `runtime/` にプロファイル・プロバイダ情報を保存。
- homr (`logs/homr_eval/20251006T015717JST_official-gpu/`) と oemer (`logs/oemer_eval/20251006T015540JST_baseline/`) を再評価し、`logs/compare_homr_oemer_20251006T0159.md` に指標まとめを追加。

### 2025-10-06 02:35 JST
- `data/workbench/preprocessing/20251006T0218/` で vertical closing / top-hat の前処理を作成。homr は `20251006T021820JST_preproc-vclose` (TP104/FP4/FN48), `20251006T022024JST_preproc-tophat` (TP23/FP0/FN129)。oemer は `20251006T022205JST_baseline` (TP133/FP0/FN19) と `20251006T022313JST_baseline` (TP45/FP1/FN107)。
- vertical closing の手法は `src/common/preprocessing.py` の `vertical_closing_blend` へ実装済み。CLI `tools/apply_vertical_closing.py` を (例: `homr/.venv/bin/python tools/apply_vertical_closing.py ...`) から `--kernel-height 7` / `--closing-blend 0.4` で再生成できる。現行成果物の再現例は `output/preprocessing_tests/page_3_vclose_test.png`。
- homr 閾値スイープ (`20251006T022434JST_tune-min12-max08`, `20251006T022635JST_tune-min08-max12`) と oemer `OEMER_MIN_BARLINE_UNIT_RATIO` 調整 (`20251006T022916JST_baseline`, `20251006T023028JST_baseline`) を実施。結果サマリは `logs/experiments/20251006_preproc_threshold/README.md` に整理。


### 2025-10-06 22:15 JST
- PDF→PNG 変換パラメータをスイープし、`src/pdf_to_images.py` の CLI 化と `.venv_pdf` 環境整備（`pymupdf`, `opencv-python-headless`, `onnxruntime` など）を実施。出力は `data/workbench/pdf_render/20251006T2038/` に保存。
- homr (`logs/homr_eval/20251006T21xxxxJST_pdfdpi*`) と oemer (`output/oemer_eval_tests/20251006T21xxxxJST_pdfdpi*`) を CPU 実行で再評価。`dpi=200` + area リサイズが現状ベスト (homr F1=0.786, oemer F1=0.908)。高 DPI × lanczos/linear はリコールが悪化。
- 詳細メトリクスは `logs_user/experiments/20251006_pdf_render/README.md` に集約。GPU 再検証時は `OEMER_IMAGE_OVERRIDE` と `tools/apply_vertical_closing.py` で同一画像を生成する。

### 2025-10-13 13:50 JST
- `common/ort_config.py` を追加し、`HOMR_ORT_LOG_SEVERITY_LEVEL` / `OEMER_ORT_LOG_SEVERITY_LEVEL` で `transformer_memcpy` 警告を抑制できるようにした（=3 で抑制を確認）。`*_CUDA_ENABLE_CUDA_GRAPH=1` は "graph capture unsupported" で失敗することを記録。
### 2025-10-14 01:30 JST
- homr/oemer 共通 FN を抽出し、`logs/night_run/common_fn_20251014T005323JST/` に FN オーバーレイとパターンメモを作成。共有 FN は幅 4 px のリピート柱群 (gt_index {21,69,97,101,103,147})。
**優先タスク (2025-10-14 更新):**
1. 共通 FN (gt {21,69,97,101,103,147}) 向けの再検出策を設計・実装し、homr ランで再評価する。
2. homr の薄バー抑制ロジックを oemer パイプラインへ移植し、精度/再現率の影響を比較する。
3. `thin_barline_finder` の新ガードに対するテスト追加とドキュメント更新を行う。
4. `tools/barline_gt_helper.py` を活用して page_004 以降の GT を作成し、両パイプラインで評価する。
5. onnxruntime-gpu 1.24.x 公開を監視し、公開後は sandbox 手順 (`logs/night_run/ort_1_24_plan.md`) で CUDA Graph/警告挙動を再検証する。

- homr 薄バーライン補完に std/左右暗度フィルタを追加 (`src/common/thin_barline_finder.py`)。新ラン `logs/homr_eval/20251014T010752JST_fpfilter/` で TP 118 / FP 4 / FN 34 (F1 0.861) まで改善し、FP #74/#115/#117 を解消。
- onnxruntime-gpu 1.24 は未公開のため導入不可。ホイール公開後に隔離インストール→トランスフォーマー ONNX で `transformer_memcpy` / CUDA Graph を再評価する手順を `logs/night_run/ort_1_24_plan.md` に記載。
- クリックで検出矩形を採択できる GT 補助ツール `tools/barline_gt_helper.py` を追加。`poetry run python ../tools/barline_gt_helper.py --image <img> --detections <json> --output <dst> [--preload <gt>]` で利用可能。

- 細幅バーライン補完ヒューリスティク (`common/thin_barline_finder.py`) を homr / oemer に適用。`logs/homr_eval/20251013T224304JST_fn_heuristic_v3` (TP116/FP7/FN36, F1=0.844) と `logs/oemer_eval/20251013T224534JST_fn_heuristic_v3` (TP135/FP6/FN17, F1=0.922)。共通 FN は {21, 69, 97, 101, 103, 147}。
- homr ヒューリスティク由来の FP を高さフィルタ (18–24 px) と既存検出の置換で抑制し、FP=7、precision=0.943 まで改善。
- oemer の長時間ジョブは当面保留。page_003 の精度向上を優先し、追加ページが必要になった段階でアノテーション支援ツール（既存検出の下絵提示など）の整備を検討する。

## プロジェクトの目標
楽譜PDFを読み込み、小節番号を付与して新しいPDFとして出力するプログラムを作成する。

## 現在の主要アプローチ
`homr` 評価パイプラインと `oemer` ベースラインを並行運用し、共通のマッチングロジックで精度を比較・改善する。`src/ml_detector/barline_detector.py` は oemer のアーキテクチャを踏まえた派生実装として維持しつつ、評価成果物を `logs/` 配下に統一フォーマットで保存する。

## 現在の課題と次のタスク

**課題:**
1.  **未回収 FN の分類:** 共通 FN {21, 69, 97, 101, 103, 147} と homr 固有の落ち (例: 26, 97, 112) を可視化し、パターン毎の対処方針を検討する。
2.  **ヒューリスティク起因の FP 抑制:** 追加された縦線 (例: x≈212,179,315) を stem などと切り分けるフィルタ（左右濃度差や notehead マスク）を設計する。
3.  **onnxruntime アップグレード調査:** 1.24 系などで CUDA Graph が有効化されるか、`transformer_memcpy` ノード挿入が改善するかを検証し、更新可否を判断する。
4.  **GT 作成支援ツールの試作:** 既存検出を下絵にしてクリックで GT を確定できる軽量ツールを試作し、操作感と出力形式を検証する。


### 次回タスクリスト (優先度順)
1. **共通 FN 再検出の実装**
   - gt {21,69,97,101,103,147} を中心に paired-pillars や margin 調整を試し、homr で再ラン→metrics 更新。
2. **oemer への薄バー抑制移植**
   - homr の std/暗度フィルタを oemer evaluator へ移植し、`logs/oemer_eval/` に比較ランを作成。
3. **テスト・ドキュメント強化**
   - `thin_barline_finder` にユニットテストを追加し、`docs/BARLINE_MATCHER.md` へ最新ヒューリスティクを追記。
4. **GT 拡張フロー確立**
   - `tools/barline_gt_helper.py` を使って page_004+ の GT を整備し、両パイプラインで評価ログを追加。
5. **onnxruntime-gpu 1.24 ウォッチ**
   - PyPI 公開を監視し、公開後に `logs/night_run/ort_1_24_plan.md` の手順で CUDA Graph / 警告挙動を再検証。


