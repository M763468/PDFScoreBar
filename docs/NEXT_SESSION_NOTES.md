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
3.  **GT 作成支援の要件整理:** 追加ページが必要になった際に備え、既存検出結果を下絵として利用できる簡易アノテーションワークフローの要件をまとめる。
4.  **onnxruntime アップグレード調査:** 1.24 系などで CUDA Graph が有効化されるか、`transformer_memcpy` ノード挿入が改善するかを検証し、更新可否を判断する。


### 次回タスクリスト (優先度順)
1. **共通 FN のオーバーレイ作成**
   - `tools/render_barline_boxes_overlay.py` で homr/oemer 双方の未検出箇所を比較し、原因別にメモを作成 (`logs/night_run/common_fn_20251013.md` を予定)。
2. **ヒューリスティク FP 向けフィルタ試作**
   - 左右窓の濃度差・上下マージン・notehead マスクなどを評価し、`logs/homr_eval/20251013T224304JST_fn_heuristic_v3` をベースに FP 7→≦4 を目標に追加ランを作成する。
3. **GT 作成支援ツールの要件整理**
   - 既存検出を下絵として利用する軽量アノテーション UI/スクリプトの仕様案をまとめ、必要な作業量を見積もる。
4. **onnxruntime 1.24 系のテスト計画作成**
   - サンドボックスで新バージョンを試し、`transformer_memcpy` 挙動と CUDA Graph 対応の可否を評価。影響が大きい場合のみ Dockerfile 更新を検討する。

## 完了済みタスク
- **GPU 再評価・ランナー拡張 (2025-10-07):** `src/pdf_to_images.py` で生成した `20251007T011612JST_gpu` の PNG を用いて homr/oemer を GPU 実行。`logs/homr_eval/20251007T015010JST_pdfdpi_gpu` と `logs/oemer_eval/20251007T021852JST_pdfdpi_gpu_dpi144_area` 〜 `20251007T022310JST_pdfdpi_gpu_dpi288_lanczos` に成果物を整理し、`run_omerer.py` に出力先・画像・GT の環境変数サポートと MusicXML 例外処理を追加。`logs_user/experiments/20251006_pdf_render/README.md` に GPU 指標を追記。
- **Docker イメージの再ビルド (2025-10-07):** `pdf_score_dev_gpu:20251007b` / `homr_eval:20251007b` を構築し、各コンテナを再作成。pip / poetry で依存導入を確認し、onnxruntime と torch の GPU 利用を検証済み。tzdata も同梱し、ZoneInfo('Asia/Tokyo') の利用エラーを解消。
- **homr / oemer 判定ロジック改修と再評価:**
  - 共通のバーラインマッチャを整備し、細幅線のパディング・重複判定・リピート例外処理を導入。詳細仕様は `docs/BARLINE_MATCHER.md` を参照。既存ログで TP/FP が期待通りに再分類されることを確認した。
- **ML検出器の復元:**
  - 動作しなくなっていた`src/ml_detector/barline_detector.py`を、正常に実行できる状態まで復旧させた。
- **MLベース検出器の実装とデバッグ:**
  - `oemer`の2モデルアーキテクチャに基づき、`barline_detector.py`を実装し、実行できる状態にした。
- **OpenCVによる小節線候補検出の試行:**
  - Hough変換、輪郭検出、垂直射影法を試みたが、安定した候補検出には至らなかったため、アプローチを保留とした。

## 将来的な検討事項（長期展望）

### 精度向上戦略

-   **機械学習アプローチの調査:**
    -   `oemer`が利用している`CVC-MUSCIMA++`のような、音楽認識に特化した公開データセットや学習済みモデルを調査する。既存の特化モデルを利用することで、高精度な検出が期待できる。
-   **LLMの役割変更（画像生成タスクへの転換）:**
    -   Geminiに座標を直接出力させるのではなく、「画像上で小節線を赤色で描き直させる」というタスクを依頼する。生成された画像から赤色の線を検出するのはOpenCVにとって容易なため、LLMが苦手な座標特定を、得意な画像生成タスクに置き換える。
-   **他のLLMとの比較・連携:**
    -   ChatGPTやMicrosoft Copilotなど、他の画像認識能力を持つLLMに同じタスクを行わせ、結果を比較検討する。
    -   複数のLLMによる合議制（アンサンブル学習）で、さらに正確な検出を目指す。
-   **専用モデルの作成:**
    -   IMSLP等の公開ライブラリから大量の番号付き楽譜を収集し、それを教師データとして、小節線検出に特化した独自の機械学習モデルをファインチューニングまたは新規作成する。
        -   *課題:* データ収集の自動化と、サイトへの負荷の問題を考慮する必要がある。また、既存モデルの使用するならば何を使うのか、独自モデルの場合はモデル構造自体を検討する必要がある。
        - oemerのページを見ると、以下のデータセットを使っている。
            - https://zenodo.org/records/4012193
            - https://pages.cvc.uab.es/cvcmuscima/index_database.html

### 機能拡張

-   **不完全小節の認識:** アウフタクトや終止小節を認識し、番号付けのルールを調整する。
-   **複数小節をまとめた休みの認識** 数小節の休みは休符記号の上に数字を書くことでその数字分の小節数を省略して記譜することがある。この記譜法を認識する。
-   **複数ページ対応:** PDF全体のページをループ処理し、一括で番号を付与する。
-   **CLIツールの作成:** コマンドライン引数で入力PDFや出力先を指定できるようにし、ツールの利便性を向上させる。

### 最終的なアーキテクチャ

-   スクリプト内部から専用モデル（またはGemini APIなどのLLMのAPIなど）を呼び出し、座標取得から描画、PDFとして再結合しての出力までをワンストップで行う、スクリプト化を目指す。
- 最終的には PDF 入力から小節番号付き PDF 出力までを一貫処理できるパイプラインを構築する。
- 評価ページを拡充し、多楽章スコアでも一致精度と処理時間が維持できるかを検証する。
- LLM / ML の再導入可能性を残し、既存ログを活用した finetuning / prompt design を将来フェーズで再検討する。


## 開発環境

-   **Dockerコンテナ:** 
    - `pdf_score_dev_gpu` : `pdf_score_dev_gpu:20251008b_sklearn120` を使用し、`/workspace` をマウント。`pip list` で `numpy==1.26.4`, `scikit-learn==1.2.0` 等の依存を確認済み。
    - `homr_eval_gpu` : `homr_eval:20251008c_sklearn120` を使用し、Poetry venv に homr 依存を導入。`poetry run python -m pip list` で同じ依存セットを確認済み。
    - いずれも GPU 実行 (`--gpus all`) を前提とし、成果物は `logs/` 配下へ保存。必要な数値は Markdown / JSON に抽出してリポジトリへ残す。

-   **プロジェクトディレクトリ:** `/workspace` (各コンテナ共通)
-   **Python環境:** コンテナ内の Python 3.10 (`homr_eval_gpu` では homr 専用 venv を利用)
-   **主要ライブラリ:** `opencv-python`, `numpy`, `Pillow`, `google-generativeai`, `pymupdf`, `onnxruntime` など

## 申し送り事項

-   **Serenaの利用について:**
    -   SerenaのMCPサーバーとプロジェクトインデックスは、セッション開始時に自動起動されるはずだが、うまくいかないときは`start.sh`により起動する必要がある。
    - 　編集機能などでエラーが発生したらserenaを停止してAIエージェント自身の機能を使う。
-   **Dockerコンテナの起動:**
    - セッション開始時は `docker start pdf_score_dev_gpu homr_eval_gpu` を実行し、`git status` で既存変更を確認してから作業する。
    - 評価ランの成果物は JST タイムスタンプ付きディレクトリ（例: `logs/homr_eval/20251008T195044JST_gpu_sklearn120/`）に保存し、`logs/night_run/night-run.log` と `logs/night_run/steps.ndjson` にコマンドと結果を追記する。
-   **ドキュメント更新:**
    - 作業終了時は `DEVELOPMENT_LOG.md`・`NEXT_SESSION_NOTES.md` を更新し、必要に応じて `README.md` もメンテナンスする。
-   **テスト／型注釈の進め方:**
    -   現在は技術検証中のコードが多く、将来的に不要になる実装も含まれるため、`pytest` や型注釈 (`mypy`) の整備は重要な箇所から少しずつ段階的に進める。日々の作業の合間に気付いた範囲で対応し、完全移行は急がない。

### homr / oemer 比較実験計画 (2025-09-27)
- 2025-09-28 01:05 JST: homr evaluator で `barline_min_height_factor`×`barline_max_width_factor` を再スイープ (`logs/homr_eval/20250928T00*`)。F1 は 0.104 (13TP/85FP/139FN) で頭打ち、まずはオーバーレイで TP/FP/FN を分類して要因を整理し、その後に stem/clef 除去マスクの再設計を個別タスクとして進める。
- 2025-09-28 01:06 JST: oemer 版 evaluator (`src/archive/oemer/run_omerer.py`) を整備し、`logs/oemer_eval/20250928T005938JST_baseline/` で TP=10 / FP=126 / FN=142 (Precision 0.074, Recall 0.066) を確認。`symbol_extraction.parse_barlines` の `min_height_unit_ratio` や `group_map` マスク調整を次ステップ候補に追加。
- 2025-09-28: homr CLI (`logs/homr_eval/20250928T001723JST_homr_cli_page3/`) と evaluator (`logs/homr_eval/20250928T001916JST_evaluator_page3_default/`) の検出本数がともに105本で一致することを確認。次は `barline_min_height_factor` や前処理ロジックの調整、および oemer パイプラインのバウンディングボックス JSON 化を実施する。
- 2025-10-06 01:32 JST: homr official evaluator (`logs/homr_eval/20251006T013220JST_official/`) => TP=95 / FP=2 / FN=57 (Precision 0.979, Recall 0.625, F1 0.763)。FP index 45 は system 5 付近の細片、index 83 は左端リピート柱 (GT25) 強制 FP。細片除去ロジックの再調整候補として記録。
- 2025-10-06 01:35 JST: oemer baseline rerun (`logs/oemer_eval/20251006T013456JST_baseline/`) => TP=120 / FP=2 / FN=32 (Precision 0.984, Recall 0.789, F1 0.876)。FP index 29 は staff 0 上部の孤立縦片、index 58 は x=410px 付近の共通ノイズ。`min_height_unit_ratio` や連結成分フィルタでの除去を検討。
- 2025-10-06 02:06 JST: oemer baseline (`logs/oemer_eval/20251006T020616JST_baseline/`) で `detections/`・`overlays/`・`params.json`・`run_config.json` を生成し、homr 互換レイアウトを確認。
- 2025-10-06 02:35 JST: 前処理 (vertical closing / top-hat) と閾値スイープの結果を `logs/experiments/20251006_preproc_threshold/README.md` に集約。homr は vertical closing で TP104/FP4、oemer は TP133/FP0 まで改善。
- homr 評価: `tools/run_homr_tuning.py` を `--images data/evaluation/images/page_3.png` と `--ground-truth page_3:data/evaluation/annotations/page_003/boxes_sorted.json` で実行し、各トライアルの `barline_min_height_factor` / `barline_max_width_factor` を記録。必ず `poetry run homr --debug` の結果と検出件数を突き合わせる。
- homr 成果物: `logs/homr_eval/<timestamp>_homr_<desc>/` に `metrics.json` / `metrics.csv` / `compare.md` / `README.md` / オーバーレイ画像 (`tools/generate_barline_overlay.py`, `tools/render_barline_boxes_overlay.py`) を保存。タイムスタンプは JST。
- oemer baseline: `docker exec pdf_score_dev_gpu bash -lc 'cd /workspace && python src/archive/oemer/run_omerer.py'` をベースに `layers.get_layer("barlines")` を JSON に書き出す処理を追加し、`logs/oemer_eval/<timestamp>_baseline/` に保存。必要に応じて `draw_teaser.py` を利用してオーバーレイを生成。
- 共通指標: GT (`data/evaluation/annotations/page_003/boxes_sorted.json`) に対する Precision / Recall / F1 と、漏れ・誤検出の目視キャプチャを `compare.md` に整理。
- ドキュメント更新: 各実験終了後に `docs/DEVELOPMENT_LOG.md` と `docs/NEXT_SESSION_NOTES.md` を更新し、次回の再現手順と改善ポイントを明記する。
