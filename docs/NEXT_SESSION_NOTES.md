# 次回セッションへの引き継ぎノート

## セッションログ

### 2025-09-27 23:38 JST
- homr と oemer の比較検証体制を整備し、page_3 GT を用いた評価を進める計画を策定。
- 次アクション: homr チューニング範囲の棚卸し、oemer ベースラインの再確認、双方の成果物整理ルールの確立。
- 留意事項: 評価成果物は JST タイムスタンプ付きで `logs/homr_eval/` 等に保存し、再現手順を docs に記録する。
- oemer 改造メモ: `src/archive/oemer/run_omerer.py` に `layers.get_layer("barlines")` の JSON 出力を追加し、`logs/oemer_eval/<timestamp>_baseline/` で metrics・オーバーレイを管理する。


## プロジェクトの目標
楽譜PDFを読み込み、小節番号を付与して新しいPDFとして出力するプログラムを作成する。

## 現在の主要アプローチ
**`oemer`のアーキテクチャを参考にした機械学習（ML）ベースのアプローチ (`src/ml_detector/barline_detector.py`) を採用する。**

- **役割分担:**
    - **`unet_big`モデル:** 五線譜と音楽記号（全体）を大まかに分類する。
    - **`seg_net`モデル:** 音楽記号をさらに細かく（符頭、符幹/休符、音部記号/調号など）に分類する。
    - **後処理:** `oemer`の高度なフィルタリングロジックを移植し、モデルの出力結果から小節線を高精度で抽出する。

## 現在の課題と次のタスク

**課題:**
1.  **パフォーマンス（GPU未使用）:** oemer実行時にONNX Runtimeが `ConvTranspose` 処理でCPUへフォールバックしている旨の警告を多数出力しており、GPUの性能を最大限に活用できていない。
2.  **検出漏れの存在（偽陰性）:** `oemer`のフィルタリングロジック導入により、誤検出は大幅に減ったものの、いくつかの本来検出されるべき小節線が検出されなくなっている。

### 現在の課題と次のタスク

1. **homr / oemer の判定ロジック見直し**
   - IoU 0.5 判定で発生している FP/FN を洗い出し、ボックススケールや縦方向マージン、閾値を調整して共通評価手順を確立する。(tools/render_detection_quality_overlay.pyを用いて肉眼での確認を行いつつ進める。)
   - 改善後の指標と可視化を整理し、以降の実験に適用する。

2. **oemer 実行時の GPU フォールバック解消**
   - ConvTranspose が CPU に落ちる原因（cuDNN 互換性・プロバイダ設定など）を調査し、コンテナ内ライブラリを調整して GPU 推論に戻す。
   - GPU 化後に homr と同条件で性能を比較する。

3. **oemer 出力の homr 換算・可視化整備**
   - `run_omerer.py` を拡張し、homr と同形式の detections / metrics / オーバーレイを出力する。
   - `group_map` など中間マップを保存して、判定ロジック改修時に参照できるようにする。

4. **前処理パイプライン検討とミニ実験**
   - PDF→PNG 変換時の解像度・補間方式や staff 単位クロップなどのパイプライン案を整理する。
   - 照度補正、縦線モルフォロジ、top-hat 等の前処理を homr/oemer 両方で小規模評価し、結果を統一形式で記録する。

5. **個別モデルの閾値・マスク調整**
   - homr: stem/clef 除去マスクを再設計し、`barline_min_height_factor` / `barline_max_width_factor` を再チューニングする。
   - oemer: `min_height_unit_ratio` などの閾値を調整し、可視化で検証する。


## 完了済みタスク
- **`group_map`フィルタリング導入と可視化の修正:**
  - `oemer`の高度なフィルタリングロジック (`group_map`, `parse_barlines`) を移植し、小節線の過剰検出を600件以上から137件まで大幅に削減した。
  - 結果が正しく描画されない可視化のバグ（`AttributeError`, 座標スケーリング）を修正し、検出結果を目視で検証できる状態にした。
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


## 開発環境

-   **Dockerコンテナ:** `pdf_score_dev_gpu`
-   **プロジェクトディレクトリ:** `/workspace` (コンテナ内)
-   **Python環境:** コンテナ内のPython 3.10
-   **主要ライブラリ:** `opencv-python`, `numpy`, `Pillow`, `google-generativeai`

## 申し送り事項

-   **Serenaの利用について:**
    -   SerenaのMCPサーバーとプロジェクトインデックスは、セッション開始時に`start.sh`により起動する必要がある。
    - 　編集機能などでエラーが発生したらserenaを停止してAIエージェント自身の機能を使う。
-   **Dockerコンテナの起動:**
-   セッション開始時に、`docker start pdf_score_dev_gpu` コマンドでコンテナを起動すること。
-   **ドキュメント更新:**
    -   セッションの最後に、`DEVELOPMENT_LOG.md`, `NEXT_SESSION_NOTES.md`, `README.md` を更新し、進捗を記録すること。
-   **テスト／型注釈の進め方:**
    -   現在は技術検証中のコードが多く、将来的に不要になる実装も含まれるため、`pytest` や型注釈 (`mypy`) の整備は重要な箇所から少しずつ段階的に進める。日々の作業の合間に気付いた範囲で対応し、完全移行は急がない。

### homr / oemer 比較実験計画 (2025-09-27)
- 2025-09-28 01:05 JST: homr evaluator で `barline_min_height_factor`×`barline_max_width_factor` を再スイープ (`logs/homr_eval/20250928T00*`)。F1 は 0.104 (13TP/85FP/139FN) で頭打ち、まずはオーバーレイで TP/FP/FN を分類して要因を整理し、その後に stem/clef 除去マスクの再設計を個別タスクとして進める。
- 2025-09-28 01:06 JST: oemer 版 evaluator (`src/archive/oemer/run_omerer.py`) を整備し、`logs/oemer_eval/20250928T005938JST_baseline/` で TP=10 / FP=126 / FN=142 (Precision 0.074, Recall 0.066) を確認。`symbol_extraction.parse_barlines` の `min_height_unit_ratio` や `group_map` マスク調整を次ステップ候補に追加。
- 2025-09-28: homr CLI (`logs/homr_eval/20250928T001723JST_homr_cli_page3/`) と evaluator (`logs/homr_eval/20250928T001916JST_evaluator_page3_default/`) の検出本数がともに105本で一致することを確認。次は `barline_min_height_factor` や前処理ロジックの調整、および oemer パイプラインのバウンディングボックス JSON 化を実施する。
- homr 評価: `tools/run_homr_tuning.py` を `--images data/evaluation/images/page_3.png` と `--ground-truth page_3:data/evaluation/annotations/page_003/boxes_sorted.json` で実行し、各トライアルの `barline_min_height_factor` / `barline_max_width_factor` を記録。必ず `poetry run homr --debug` の結果と検出件数を突き合わせる。
- homr 成果物: `logs/homr_eval/<timestamp>_homr_<desc>/` に `metrics.json` / `metrics.csv` / `compare.md` / `README.md` / オーバーレイ画像 (`tools/generate_barline_overlay.py`, `tools/render_barline_boxes_overlay.py`) を保存。タイムスタンプは JST。
- oemer baseline: `docker exec pdf_score_dev_gpu bash -lc 'cd /workspace && python src/archive/oemer/run_omerer.py'` をベースに `layers.get_layer("barlines")` を JSON に書き出す処理を追加し、`logs/oemer_eval/<timestamp>_baseline/` に保存。必要に応じて `draw_teaser.py` を利用してオーバーレイを生成。
- 共通指標: GT (`data/evaluation/annotations/page_003/boxes_sorted.json`) に対する Precision / Recall / F1 と、漏れ・誤検出の目視キャプチャを `compare.md` に整理。
- ドキュメント更新: 各実験終了後に `docs/DEVELOPMENT_LOG.md` と `docs/NEXTSESSION_LOG.md` を更新し、次回の再現手順と改善ポイントを明記する。
