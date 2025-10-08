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

## プロジェクトの目標
楽譜PDFを読み込み、小節番号を付与して新しいPDFとして出力するプログラムを作成する。

## 現在の主要アプローチ
`homr` 評価パイプラインと `oemer` ベースラインを並行運用し、共通のマッチングロジックで精度を比較・改善する。`src/ml_detector/barline_detector.py` は oemer のアーキテクチャを踏まえた派生実装として維持しつつ、評価成果物を `logs/` 配下に統一フォーマットで保存する。

## 現在の課題と次のタスク

**課題:**
1.  **transformer_memcpy 警告の緩和:** homr / oemer の CUDA 実行で継続する `transformer_memcpy` 警告を抑制するため、ONNX Runtime 設定やバージョンアップ、CUDA Graph 化の可否を検証する。
2.  **FN ホットスポットの削減:** GT 18, 26, 31–36, 40, 46, 60, 63, 70, 74 の縦片が両パイプラインで未検出。前処理・マッチャ補正・評価ロジックを見直し、改善案を試作する。
3.  **homr 偽陽性の抑制:** `--barline-min-height-factor` を緩めると FP が増えるため、stem マスクや post-filter など追加フィルタでリコールと Precision を両立させる。
4.  **oemer 長尺ジョブの安定化:** 環境変数スモークテストは追加済み。複数ページ実行時のログ採取・失敗時の復旧手順整備を進める。
### 次回タスクリスト (優先度順)

1. **transformer_memcpy 対策の検証**
   - onnxruntime のセッション設定や 1.24 系へのアップデートを試し、`providers.json` / ORT プロファイルで差分を記録する。
2. **FN ホットスポットの改善案を試作**
   - 前処理・マッチャ例外・閾値調整を組み合わせ、homr / oemer の比較ランを作成して `logs/compare_homr_oemer_*.md` に差分を追記する。
3. **homr の偽陽性抑制フィルタ実装**
   - stem マスクや幅フィルタ、post-filter を試し、リコールと Precision のトレードオフを評価する。
4. **oemer 長尺ジョブの実地テスト**
   - 複数ページの夜間ジョブを走らせ、`logs/night_run/` に失敗時の復旧手順・ログ整理手順を追記する。


### 2025-10-08 20:10 JST
- Dockerfile 2イメージを scikit-learn 1.2.0 系に揃え、GPU 再評価を実施 (homr 20251008T195044JST_gpu_sklearn120, oemer 20251008T195311JST_gpu_sklearn120)。
- transformer_memcpy 警告は継続。ORT_DISABLE_MEMCPY=1 の試行では差分なし。
- FN ホットスポット (GT 18,26,31–36,40,46,60,63,70,74) をオーバーレイ化し、homr チューニングの回帰も確認。
- tools/smoke_test_run_omerer_env.py で OEMER_* 環境変数のスモークテストを追加。
