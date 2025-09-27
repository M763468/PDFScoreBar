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
1.  **パフォーマンス（GPU未使用）:** 実行時にONNX Runtimeが `ConvTranspose` 処理でCPUへフォールバックしている旨の警告を多数出力しており、GPUの性能を最大限に活用できていない。
2.  **検出漏れの存在（偽陰性）:** `oemer`のフィルタリングロジック導入により、誤検出は大幅に減ったものの、いくつかの本来検出されるべき小節線が検出されなくなっている。

**次のタスク:**

1. **別のAIモデルの検討**
    -   **目標:** `oemer`のREADMEのSPECIAL MENTIONによると、`https://github.com/liebharc/homr`のリポジトリがよりrobustでよい結果をもたらすらしい。記述を確認したうえで、このリポジトリを用いて同様にmusicxmlの作成や小節線検出を実行し、精度を比較する。こちらの方が明らかに良い結果ならば、こちらを利用する。
    -   **アプローチ:**
        -   この作業専用のブランチを作成し`oemer`の結果と分離して作業をできるようにする。
        -   `homr`を適切なディレクトリにサブモジュールとしてgit cloneする。
        -   musicxml作成結果や小節線抽出に特化した結果、適切な中間画像などを出力し、`oemer`を使用した場合と比較する。必要ならばこの作業のために専用のdockerコンテナを新たに作成してもよい。(その場合、dockerコンテナ内部でgemini-cliを使うことができるようにすることで、直接attachしながらgeminiを使うようにする。)
        -   試行の結果、明らかにhomerを使う方がよい結果になるならば、プロジェクトの主要アプローチをhomerを使ったものに変更し、各種ドキュメントを更新した後、mainにマージする。

    -   **直近 TODO:**
        1. `logs/homr_eval/20250927T230640JST_evaluator_page3_gt/metrics.json` で確認した Precision=0.11 / Recall=0.079 のギャップを解消するため、`barline_min_height_factor` / `barline_max_width_factor` / 前処理閾値を調整し、TP の増加と FP の削減を図る。
        2. 新しい GT（`data/evaluation/annotations/page_003/boxes_sorted.json`）を `tools/run_homr_tuning.py` のデフォルトに組み込み、各トライアルで Precision/Recall を記録する。
        3. 各パラメータセットについて `tools/generate_barline_overlay.py` + `tools/render_barline_boxes_overlay.py` の 2 種類のオーバーレイを生成し、目視で誤検出・未検出を確認する。
        4. 改善が得られた設定を `docs/DEVELOPMENT_LOG.md` と `logs/homr_eval/<timestamp>/` に整理し、次セッションへ引き継ぐ。

    -   **注意**
        - `homr`のセグメンテーション部分は`oemer`をベースにしているため、結果は変わらないかもしれない。
        - `homr`のREADMEによると、`homr`は内部で以下のリポジトリをベースにしたtransformerモデルを使用している。必要に応じてこちらも参考にすること。
        - `https://github.com/NetEase/Polyphonic-TrOMR`

2.  **GPUパフォーマンスの最適化:**
    -   **目標:** （1.がうまくいく場合は不要）`oemer`のCPUへのフォールバックを解消し、GPUを最大限活用して処理を高速化する。
    -   **アプローチ:**
        -   `onnxruntime-gpu` と、インストールされている `CUDA`, `cuDNN` のバージョン間の互換性を調査する。
        -   `ConvTranspose` 処理がCUDAでサポートされていない問題について、ONNXコミュニティの情報を検索し、既知の回避策（モデル変換時のオプション指定など）がないか調べる。
        - 　この作業は`perf/gpu-optimization`ブランチを使用する。
    -   **注意**
            - 基本的に1.が成功すれば不要だが、もし`homr`でも同様にGPUが使えずCPUにフォールバックするなどの問題が発生した場合はその調査を行う。

3.  **検出漏れの調査と改善:**
    -   **目標:** （1.で十分な精度が得られる場合は不要）`oemer`を用いた手法による偽陰性を減らし、検出精度をさらに向上させる。
    -   **アプローチ:**
        -   `parse_barlines` や `filter_barlines` 内のパラメータ（特に高さの閾値 `min_height_unit_ratio` など）を調整し、検出漏れした小節線が拾えるか試す。
        -   中間画像（`barline_cand`, `sym_barline_map` など）をデバッグ出力し、検出漏れした小節線がどの段階で候補から消えているかを特定する。
    -   **注意**
            - 基本的に1.が成功すれば不要だが、もし`homr`でも同様に精度の問題があればその解決のための調査を行う。

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
- homr 評価: `tools/run_homr_tuning.py` を `--images data/evaluation/images/page_3.png` と `--ground-truth page_3:data/evaluation/annotations/page_003/boxes_sorted.json` で実行し、各トライアルの `barline_min_height_factor` / `barline_max_width_factor` を記録。必ず `poetry run homr --debug` の結果と検出件数を突き合わせる。
- homr 成果物: `logs/homr_eval/<timestamp>_homr_<desc>/` に `metrics.json` / `metrics.csv` / `compare.md` / `README.md` / オーバーレイ画像 (`tools/generate_barline_overlay.py`, `tools/render_barline_boxes_overlay.py`) を保存。タイムスタンプは JST。
- oemer baseline: `docker exec pdf_score_dev_gpu bash -lc 'cd /workspace && python src/archive/oemer/run_omerer.py'` をベースに `layers.get_layer("barlines")` を JSON に書き出す処理を追加し、`logs/oemer_eval/<timestamp>_baseline/` に保存。必要に応じて `draw_teaser.py` を利用してオーバーレイを生成。
- 共通指標: GT (`data/evaluation/annotations/page_003/boxes_sorted.json`) に対する Precision / Recall / F1 と、漏れ・誤検出の目視キャプチャを `compare.md` に整理。
- ドキュメント更新: 各実験終了後に `docs/DEVELOPMENT_LOG.md` と `docs/NEXTSESSION_LOG.md` を更新し、次回の再現手順と改善ポイントを明記する。
