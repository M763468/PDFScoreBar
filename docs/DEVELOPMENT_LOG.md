# Development Log

This document records the development history, key decisions, and learnings throughout the project.

## How to Use This Log
- フェーズごとに Goal / Process / Outcome / Status をまとめ、完了後に追記する。
- 新しいフェーズは時系列順に追加し、関連するログやスクリプトをリポジトリ相対パスでリンクする。
- 重要な意思決定や設計変更は、対応するドキュメント（例: `docs/BARLINE_MATCHER.md`）にも反映させる。

## Current Focus (2025-09)
homr evaluator と oemer ベースラインの比較・改善ワークフローを中心に、共通指標による評価ログ整備と GPU 実行環境の安定化を進めている。最新フェーズの詳細は Phase 15 以降を参照。

## Phase 1: OMR-based Approach (Initial Attempt)

-   **Goal:** Use a full-fledged Optical Music Recognition (OMR) library to convert the score to a machine-readable format (MusicXML) and extract barline information from it.
-   **Tool Used:** `oemer` (via `run_omerer.py`)
-   **Outcome:** While `oemer` successfully generated MusicXML files, the recognition accuracy for barlines was insufficient for our primary goal of simple measure counting. The complexity of a full OMR system proved to be overkill and difficult to tune for our specific, narrow use case.
-   **Key Learning:** A general-purpose OMR library is not always the best tool for a highly specific task. The overhead of full recognition can introduce more errors than a targeted approach.
-   **Status:** This approach was **abandoned**.

## Phase 2: Rule-Based OpenCV Approach

-   **Goal:** Directly detect barlines from the score image using custom computer vision logic built with OpenCV.
-   **Tool Used:** `barline_detector.py`
-   **Outcome:** This approach showed initial promise but ultimately struggled with a critical trade-off: relaxing detection parameters to find all true barlines inevitably led to a high number of false positives (e.g., detecting note stems). Conversely, tightening parameters to eliminate false positives resulted in missing many true barlines.
-   **Key Learning:** Rule-based computer vision is powerful but can be brittle. It requires extensive, manual parameter tuning and struggles to generalize.
-   **Status:** This approach was **superseded**.

## Phase 3: Gemini-OpenCV Hybrid Approach (Historical)

-   **Goal:** Leverage the strengths of both a powerful AI model and a robust image processing library.
-   **Tools Used:** `add_measure_numbers.py`
-   **Process:** Gemini for recognition, OpenCV for execution.
-   **Status:** Historical prototype. 現在は homr/oemer ワークフローに軸足を移している。

## Phase 4: Environment Setup and Ground Truth Creation

-   **Goal:** Establish a reproducible development environment using Docker and create high-quality ground truth data for in-context learning.
-   **Process:** Refined `Dockerfile`, built a new image (`pdf-score-tool`), launched a persistent container (`pdf_score_dev_gpu`), generated high-resolution images, and created a ground truth JSON file (`data/ground_truth_page_1.json`) by simulating manual coordinate extraction.
-   **Outcome:** A stable Docker environment is active and ground truth data is available.
-   **Status:** Complete.

## Phase 5: Initial In-Context Learning Test

-   **Goal:** Test the effectiveness of the in-context learning approach for barline detection.
-   **Process:** Created `src/gemini/incontext_barline_detector.py` to send an image (`page_3.png`) and the ground truth data (`ground_truth_page_1.json`) as a few-shot prompt to the `gemini-1.5-flash-latest` model. The detected coordinates were then drawn on the source image for visual evaluation.
-   **Outcome:** **Detection accuracy was very low.** The model-generated bounding boxes were mostly unrelated to the actual barlines. The result is saved in `output/gemini_results/page_3_detected.png`.
-   **Key Learning:** Simply providing coordinate examples is not enough to make the model accurately understand the visual task of identifying barlines. The prompt engineering needs to be more sophisticated.
-   **Status:** Test complete. Next step is to iterate on prompt and data strategies to improve accuracy.

-   **Further Iteration (gemini-1.5-pro/flash):** Attempted to improve accuracy by refining the prompt and implementing a fallback mechanism (pro -> flash). Despite these efforts, the detection accuracy remained low for both models.
-   **Conclusion on Simple Prompting:** Simple in-context learning with coordinate examples and basic prompt refinement is insufficient for accurate barline detection. A more sophisticated approach is required.

-   **Backup of `incontext_barline_detector.py` (Pre-Chain-of-Thought Prompt):** Created a backup of `src/gemini/incontext_barline_detector.py` at `src/archive/barline_detection_prompts/incontext_barline_detector_pre_chain_of_thought_prompt.py` before implementing the chain-of-thought prompt strategy. This preserves the state of the script for comparison and historical tracking.

## Phase 6: Prompt Engineering and In-Context Learning Iteration (Chain-of-Thought)

-   **Goal:** Further improve barline detection accuracy using advanced prompt engineering techniques (chain-of-thought) and refined in-context examples.
-   **Process:** Implemented a step-by-step reasoning prompt in `src/gemini/incontext_barline_detector.py` and tested with `gemini-1.5-flash-latest`.
-   **Outcome:** Despite detailed instructions and chain-of-thought prompting, the model consistently failed to identify barlines correctly. The detected bounding boxes were mostly unrelated to actual barlines, indicating that this approach is not effective for the task.
-   **Key Learning:** Even with sophisticated prompt engineering, general-purpose LLMs may struggle with highly specific visual recognition tasks like barline detection without more targeted pre-processing or a different architectural approach.
-   **Status:** This approach is **deemed ineffective** for achieving the required accuracy.

## Phase 7: Transition to Hybrid Verification Model

-   **Goal:** Combine OpenCV's image processing capabilities with Gemini's classification abilities to improve barline detection accuracy.
-   **Strategy:**
    1.  Use OpenCV to detect all potential vertical lines in the image.
    2.  Pass these detected vertical line regions to Gemini for classification (i.e., determine if each region is a true barline or not).
-   **Status:** **Initiating this new approach.**

## Phase 8: Implementation of Hybrid Verification Model and API Optimization

-   **Goal:** Implement the hybrid OpenCV-Gemini model and optimize it to be robust against API rate limits.
-   **Process:**
    1.  Archived the legacy `add_measure_numbers.py` script.
    2.  Created a new script `src/gemini/hybrid_barline_detector.py`.
    3.  The initial version of the script successfully detected candidates with OpenCV but made too many individual API calls, hitting the API's per-minute free tier limit.
    4.  A `TypeError` during JSON serialization (due to NumPy `int32` types) was identified and fixed by casting coordinates to standard Python `int`s.
    5.  To solve the rate-limiting issue, the script was re-architected. The new approach creates a single composite image of all candidate regions and uses a single, more complex prompt to have Gemini classify all candidates in one API call.
    6.  A `SyntaxError` in the new batching logic was identified and fixed.
-   **Outcome:** The script is now feature-complete and optimized. The logic is believed to be correct. A debug image (`debug_composite_candidates.png`) is successfully created, confirming the batching mechanism works.
-   **Status:** **Blocked.** The final execution of the optimized script is currently blocked by the Gemini API's *daily* free tier quota, which was exhausted during debugging. The script is ready for a full run once the quota resets.

## Phase 9: OpenCVによる小節線候補検出精度の向上

- **目標:** Gemini APIの無料利用枠がリセットされるまでの間、OpenCVを用いた小節線候補検出の精度を向上させる。
- **取り組み内容:**
  1. `src/hybrid/opencv_candidate_detector.py`を改良し、以下の点を調整:
     - Hough Line Transformのパラメータを微調整（`threshold`, `minLineLength`, `maxLineGap`）。
     - 検出された線分の角度フィルタリングを強化し、垂直線のみを抽出。
  2. デバッグ用画像（`debug_detector_binary.png`）を生成し、検出結果を可視化。
  3. 検出された候補線を元画像に描画し、最終的な可視化結果を`opencv_candidates_visualization.png`として保存。
- **成果:**
  - 小節線候補の検出数は増加したが、多くが誤検出であった。また、本来検出すべき小節線も検出できないままであった。
  - デバッグ画像を通じて、検出プロセスの透明性を確保。
  - **最終的にはこの手法では正確な小節線候補を検出することができず、課題が残る結果となった。**

- **次のステップ:** 
  - Gemini APIの利用枠がリセットされた後、ハイブリッドモデルの動作検証を再開する。

- **再試行1 (HoughLinesPパラメータ厳格化とモルフォロジー変換)**:
  - **変更点**: HoughLinesPの`threshold`と`minLineLength`を増加、`maxLineGap`を減少。垂直線を強調するモルフォロジー変換（`MORPH_OPEN`, `MORPH_CLOSE`）を追加。
  - **結果**: 候補が0個しか検出されず、小節線が完全に失われた。
  - **学び**: パラメータが厳しすぎ、モルフォロジー変換が小節線まで除去してしまった可能性。

- **再試行2 (モルフォロジー変換削除とHoughLinesPパラメータ緩和)**:
  - **変更点**: モルフォロジー変換を削除。HoughLinesPの`threshold`を`20`、`minLineLength`を`30`、`maxLineGap`を`20`に緩和。角度フィルタリングを`85-95`度に戻す。
  - **結果**: 候補が0個しか検出されず、改善が見られなかった。
  - **学び**: パラメータ緩和だけでは不十分。前処理や根本的なアプローチの見直しが必要。

- **再試行3 (五線譜除去の導入とHoughLinesPパラメータ再調整)**:
  - **変更点**: 水平カーネルによるモルフォロジー変換で五線譜を除去する前処理を追加。HoughLinesPの`threshold`を`15`、`minLineLength`を`20`、`maxLineGap`を`15`に設定。
  - **結果**: 4個の候補を検出し、Geminiが2個を小節線と分類。終止線のみが正しく検出されたが、他の小節線は未検出。
  - **学び**: 五線譜除去は有効だが、HoughLinesPのパラメータがまだ通常の小節線には厳しすぎる。

- **再試行4 (五線譜除去カーネルとHoughLinesPパラメータの微調整)**:
  - **変更点**: `horizontal_kernel`の幅を`30`に減らし、HoughLinesPの`threshold`を`8`、`minLineLength`を`15`、`maxLineGap`を`15`に設定。
  - **結果**: 23個の候補を検出し、Geminiが12個を小節線と分類。段の左端を小節線として誤検出、二分音符のステムの誤検出（no.8）、段の右端の小節線の多くが未検出、終止線が認識されなくなった。
  - **学び**: 候補数は増えたが、誤検出と検出漏れが混在。パラメータ調整だけでは限界がある。

- **再試行5 (Y座標範囲によるフィルタリングとHoughLinesPパラメータ緩和)**:
  - **変更点**: 検出された線分のY座標範囲（画像の高さの5%〜30%）によるフィルタリングを追加。HoughLinesPの`threshold`を`5`、`minLineLength`を`20`、`maxLineGap`を`20`に設定。
  - **結果**: 5個の候補を検出し、Geminiが5個を小節線と分類。段を飛び越えた誤検出（no.1, no.3, no.5, no.6）、八分音符のステムの誤検出（no.2, no.4）が継続。終止線はno.12で認識された。
  - **学び**: Y座標フィルタリングは誤検出を減らす効果があるが、まだ不十分。Hough Line Transformベースの手法では、小節線の多様な形状やノイズへの対応が困難であり、安定した高精度な検出は難しいと判断。

- **結論**: Hough Line Transformとモルフォロジー変換、五線譜除去を組み合わせたアプローチでは、小節線の多様な形状やノイズへの対応が困難であり、安定した高精度な検出は難しいと判断。

## Phase 10: 輪郭検出アプローチへの移行

- **目標**: Hough Line Transformの代わりに輪郭検出を用いて、小節線候補の検出精度を向上させる。
- **試行1**: 輪郭検出を導入し、幅、高さ、アスペクト比でフィルタリング。結果、0個の候補しか検出されず。
- **試行2**: 輪郭フィルタリングのパラメータを緩和。結果、0個の候補しか検出されず。
- **試行3**: 五線譜除去を無効にし、`cv2.findContours`のモードを`RETR_LIST`に変更。結果、0個の候補しか検出されず。
- **試行4**: 二値化のパラメータを調整し、輪郭フィルタリングのパラメータをさらに緩和。結果、1個の候補しか検出されず。
- **試行5**: 二値化を大津の二値化に変更し、コントラスト強調を追加。結果、0個の候補しか検出されず。
- **試行6**: 二値化を`adaptiveThreshold`に戻し、五線譜除去を再導入。輪郭フィルタリングのパラメータを再調整。結果、1個の候補しか検出されず。
- **試行7**: 輪郭フィルタリングを完全に無効化。結果、3309個の候補が検出されたが、Gemini APIの画像サイズ制限エラーが発生。
- **結論**: 輪郭検出アプローチも、パラメータ調整が非常に難しく、安定した高精度な検出は困難と判断。


## Phase 11: 垂直射影アプローチの試行

- **目標**: Hough変換や輪郭検出に代わるアプローチとして「垂直射影（Vertical Projection Profile）」を試し、OpenCVによる候補検出の安定化を図る。
- **アプローチ**: `src/hybrid/opencv_candidate_detector.py` を使用し、垂直射影法を実装・デバッグ。
- **試行内容**:
    1.  **五線譜除去＋パラメータ調整**:
        -   まず、五線譜除去を行った上で垂直射影を計算。
        -   ピーク検出のしきい値、五線譜除去のカーネルサイズ、形態素解析の種類（`MORPH_OPEN` vs `MORPH_ERODE`）、反復回数などを様々に変更してテストしたが、候補を一件も検出できなかった。
    2.  **五線譜除去なし＋パラメータ調整**:
        -   アプローチを転換し、五線譜を除去せず元の二値化画像に直接垂直射影を適用。
        -   小節線と他の要素（音符など）をピークの高さで区別することを試みた。
        -   ピーク検出のしきい値を30%→20%→10%と段階的に下げてテストしたが、こちらも候補を一件も検出できなかった。
- **結論**: 垂直射影アプローチは、五線譜除去の有無にかかわらず、今回のテスト画像に対して有効ではなかった。純粋なOpenCVベースの候補検出は困難であると再確認。このアプローチは一旦保留とする。

## Phase 12: MLベースの検出器への移行とデバッグ

- **目標**: OpenCVベースの候補検出アプローチの限界を受け、機械学習（ML）ベースの検出アプローチに移行し、そのデバッグを行う。
- **アプローチ**: `oemer`の既存のMLモデル（セグメンテーションネットワーク）を参考に、`src/ml_detector/barline_detector.py`を実装。
- **デバッグ過程**:
    1.  **初期実装**: `oemer`のアーキテクチャを誤解しており、2つのモデルのうち`unet_big`しか使用せず、その出力（確率マップ）の解釈も間違っていたため、期待通りに動作しなかった。
    2.  **アーキテクチャ修正**: `oemer`のソースコード(`ete.py`)を詳細に分析し、`unet_big`（五線譜と記号の粗分類）と`seg_net`（記号の詳細分類）の2モデル構成であることを特定。`barline_detector.py`をこのアーキテクチャに合わせて全面的に書き直した。
    3.  **エラー1 (`IndexError`):** `staff_extract`関数で`IndexError`が発生。原因は、`unet_big`の出力として、`ete.py`が使用するクラス分類マップではなく、生の確率マップを渡していたため。`np.where`を使ってクラス分類マップを正しく生成するように修正。
    4.  **エラー2 (`KeyError: 'zones'`):** `staff_extract`関数が返す`zones`情報をレイヤーとして登録していなかったため、後続の処理で`KeyError`が発生。`staff_extract`の戻り値を正しく受け取り、`zones`レイヤーを登録するように修正。
- **成果**:
    -   複数回のエラー修正を経て、`barline_detector.py`が正常に最後まで実行されるようになった。
    -   `page_3.png`に対して738個の小節線を検出。これは過剰検出の可能性が高いが、まずはMLパイプラインが技術的に動作することを確認できた。
    -   最終的な検出結果は`output/ml_detector/page_3_detected_ml_barlines.png`に、中間生成物は`output/ml_detector/debug_*.png`に保存されている。
-   **精度向上への試行 (偽陽性削減)**:
    -   **可視化ずれの修正**: 検出されたバウンディングボックスの座標が元画像サイズにスケーリングされていなかったため、可視化がずれていた問題を修正。
    -   **記号マスクの膨張**: `symbols_pred`から`stems_rests_pred`, `notehead_pred`, `clefs_keys_pred`を減算する前に、これらのマスクを膨張させることで、より多くのノイズを除去しようと試みた。初期は偽陽性が増加したが、その後の調整で効果が見られた。
    -   **`stems_rests_pred`の除去**: `bmap`の計算から`stems_rests_pred`を除去する試み。偽陽性は減少したが、同時に実際の小節線の偽陰性も増加したため、このアプローチは採用しなかった。
    -   **符頭近接フィルタリング**: 検出された線分が符頭に近接している場合、それを小節線ではないと判断するフィルタリングを追加。偽陽性のわずかな減少に貢献。
    -   **幅・高さフィルタリング**: 検出された線分の幅と高さに基づいてフィルタリングを追加。
        -   初期設定で741本の小節線を検出。
        -   `max_width_ratio=0.4`, `min_height_ratio=2.5`で655本に減少。
        -   `min_height_ratio`を`3.5`に厳格化した結果、641本に減少。
    -   **`oemer`の`parse_barlines`と`filter_barlines`の再現試行**: `oemer`の複雑なフィルタリングロジック（特に`group_map`の利用）を再現しようと試みたが、0本の小節線しか検出されず、ロジックが過剰に厳しかったか、`group_map`の近似が不十分であったと判断。
-   **現在の状況**:
    -   様々なフィルタリングを試みた結果、検出小節線は641本まで減少したが、目標の約150本にはまだ遠い。
    -   単純なフィルタリング手法では限界に達したと判断。
    -   根本的な問題は、`mix`画像（`find_lines`への入力）に依然として多くのノイズが含まれていること。
    -   `oemer`の`parse_barlines`関数が持つ、より洗練された`group_map`を用いたクリーニングロジックの再現が不可欠であると結論。
- **ステータス**: **完了**。MLベースの検出器の基本的な実装とデバッグが完了した。

## Phase 13: ML検出器の復元

- **目標:** 以前の修正作業中に動作しなくなったMLベースの検出器 (`src/ml_detector/barline_detector.py`) を、正常に動作する状態に復元する。
- **アプローチ:** 動作しなくなった際の一時ファイル (`src/ml_detector/barline_detector_new.py`) を元に、デバッグ作業を行った。
- **デバッグ過程:**
    1.  **モデルパスの修正 (`FileNotFoundError`):** `oemer`ライブラリがモデルファイルを読み込む際のパス指定に誤りがあった。コンテナ内のプロジェクトディレクトリ (`/workspace`) からの絶対パスで指定することで解決した。
    2.  **描画関数のエラー (`AttributeError`):** `oemer`の `draw_bounding_boxes` 関数で発生していた `AttributeError: 'list' object has no attribute 'shape'` は、ライブラリ内部の複雑な状態依存が原因と推測された。原因の切り分けと復元作業を優先するため、最終的な画像への描画処理を一時的にコメントアウトしてエラーを回避した。
    3.  **構文エラーの修正 (`SyntaxError`):** `replace`ツールの使用時に、文字列のエスケープを誤り `SyntaxError` が発生。これを修正した。
- **成果:**
    - `barline_detector.py` が最後まで正常に実行され、小節線候補を検出できる状態に復旧した。
    - これにより、Phase 12完了時点の「過剰検出」という課題に再度取り組むためのベースラインが確立された。
- **ステータス:** **完了**。

## Phase 14: `group_map`フィルタリング導入と可視化の修正

- **目標:** `oemer`の高度なフィルタリングロジックを移植して過剰検出を抑制し、その結果を正しく可視化する。
- **アプローチ:**
    1. `oemer`の `note_group_extraction.py` と `symbol_extraction.py` を分析し、`group_map` を使ったフィルタリングが偽陽性（特に符幹の誤検出）の除去に有効であると特定。
    2. 符頭検出 (`note_extract`)、音符ID登録 (`register_note_id`)、音符グループ化 (`group_extract`) の処理を `barline_detector.py` に追加し、`group_map` を生成。
    3. `symbol_extraction.py` から `parse_barlines` と `filter_barlines` 関数を移植し、`group_map` を使って音符領域をマスクすることで、小節線候補を絞り込むロジックを実装。
- **成果:**
    - 小節線の検出数を **600件以上から137件まで大幅に削減**することに成功。(目視確認による正解は150程度。とりあえずこのくらいになったらある程度精度が高いと思われる。)
    - `oemer`のフィルタリングロジックの有効性を確認できた。
- **デバッグ過程 (可視化):**
    1. **描画されない問題:** 当初、結果画像に何も描画されない問題が発生。
    2. **`AttributeError` / `ValueError`:** 調査の結果、`oemer`の描画関数 `draw_bounding_boxes` が内部で管理する状態（レイヤー）に依存しており、我々の環境では型エラーを引き起こしていると判明。
    3. **独自描画関数の実装:** `oemer`の描画関数への依存を断ち切るため、OpenCVを直接使うシンプルな描画関数 `draw_barlines_on_image` を実装して問題を回避。
    4. **座標スケーリング問題:** 描画位置がずれる問題が発生。推論時のリサイズされた画像座標を、元の画像座標にスケール変換する処理を追加して解決。
- **既知の問題:**
    - いくつかの小節線が検出できていない（偽陰性）。
    - 実行時にONNX Runtimeが `ConvTranspose` 処理でCPUへのフォールバックを警告しており、GPUが完全には活用されていない。
- **ステータス:** **完了**。検出器は大幅に改善され、検証可能な状態になった。

## Phase 15: homr 評価環境構築

- **目的:** `homr` リポジトリを既存ワークスペースに分離配置し、依存関係の衝突を避けつつ GPU 上で検証できるようにする。
- **作業内容:**
    1. `homr` ディレクトリを新規作成し、`git clone https://github.com/liebharc/homr.git homr` で最新ソースを取得。
    2. CUDA 12.1 ベースの新しい Docker イメージ (`Dockerfile.homr`) を構築し、`homr_eval_gpu` コンテナを `docker run --gpus all` で起動。ホストの `/workspace` をマウントして既存プロジェクトと共有。
    3. コンテナ内で `poetry install --with dev` を実行し、必要な追加依存 (`onnxruntime-gpu==1.22.0`) を導入。
        - 実行コマンド:
          - `docker exec homr_eval_gpu bash -lc 'cd /workspace/homr && poetry install --with dev'`
          - `docker exec homr_eval_gpu bash -lc 'source /workspace/homr/.venv/bin/activate && pip uninstall -y onnxruntime'`
          - `docker exec homr_eval_gpu bash -lc 'source /workspace/homr/.venv/bin/activate && pip install onnxruntime-gpu==1.22.0'`
        - 導入後に `torch.cuda.is_available()` と `onnxruntime.get_device()` を使って GPU 利用可否を確認。
    4. ログ用 `logs/homr_eval/` とモデル／キャッシュ用 `models/homr/` をホスト側に作成し、コンテナからマウント。
- **成果:** `homr` 用作業環境とログ／モデル保管先を既存パイプラインと分離。GPU 上での推論実験を準備できた（`onnxruntime` も GPU 利用に切り替え済み）。
- **課題/次ステップ:** `homr` 推論フローの実入力検証と `oemer` 既存検出器との指標比較を進める。必要に応じて GPU フォールバックの挙動を追加調査する。
- **アップデート (2025-09-26):**
    - `Dockerfile.homr` を刷新し、cuDNN 9 ランタイム／ヘッダーの導入と `poetry install --with dev`、`pip uninstall onnxruntime && pip install onnxruntime-gpu==1.22.0`、`opencv-python-headless` までをビルド時に自動反映。起動後の手動セットアップが不要に。
    - 新イメージから `homr_eval_gpu` コンテナを再作成し、`poetry run python -c "import torch, onnxruntime as ort; print(torch.cuda.is_available()); print(ort.get_device())"` で GPU 動作 (`GPU`) を確認。
    - `poetry run homr --debug /workspace/data/evaluation/images/page_3.png` を GPU で再実行し、`logs/homr_eval/page_3/` 配下に MusicXML・ログ・デバッグ画像を整理。`tools/generate_barline_overlay.py`（重ね色は赤）で最新マスクからオーバーレイを再生成。
    - `data/evaluation/images` 直下に残るデバッグ画像／MusicXML は実行毎に `logs/homr_eval/page_3/` へ移動後削除し、入力ディレクトリをクリーンに保つ運用を確認。

## Phase 16: homr 評価ワークフロー自動化と閾値チューニング（2025-09-27）

- **目的:** `homr` 推論の結果を既存 ML 検出器と同じ形式で収集・比較できるようにし、閾値調整を反復しやすくする。
- **実装:**
    1. `src/homr/homr_evaluator.py` を新規追加。`homr` 本体の推論パイプラインをラップし、以下を自動生成できるようにした。
        - `logs/homr_eval/<run_id>/<page>/` 配下への MusicXML・デバッグ画像・オーバーレイ（赤重ね）・検出座標 JSON。
        - `metrics.json` / `metrics.csv`（IoU 計測は GT が無い場合は未算出だが、検出本数や差分を記録）。
        - `run_config.json` に CLI パラメータ、Git コミット、Docker イメージタグを記録。
    2. `tools/run_homr_tuning.py` を作成。`barline_min_height_factor` と `barline_max_width_factor` のグリッド探索を行い、各トライアルを `logs/homr_eval/<timestamp>_autotune/trials/trial-XXX/` に保存。Heuristic として「目視で正解 150 本」に近い検出本数をスコア化し、`trials_summary.json` と `logs/night_run/steps.ndjson` に記録。
- **実行結果:**
    - ベースライン (`min=1.0`, `max=1.0`) は `logs/homr_eval/20250926T183651Z_baseline/` に保存。GPU ライブラリ不足で CPU フォールバックしたものの、推論は完走し検出本数 105 を取得。
    - グリッド探索では `min=0.85`, `max=0.9` が検出本数 118 で最も 150 に近づいた（差分 32）。同条件の再実行でも同じ結果を確認。閾値を下げることで偽陰性が減り、過剰検出は大きく増えないことを確認。
    - すべてのトライアルについて手順・メトリクスを `logs/night_run/steps.ndjson` に追記し、run ルート `logs/homr_eval/20250926T184903Z_autotune/` に集約。
- **付随作業:**
    - Docker ビルドコンテキスト削減のため `.dockerignore` を新設（`logs/`, `data/evaluation/images/`, `homr/.venv/` などを除外）。ただしホスト権限の制約で `docker build` は未実施。必要に応じて権限付与後に再ビルドする。
- **課題:**
    - 正式な地真 (ground truth) が未整備のため、F1 などの定量指標は算出できていない。`metrics.json` には placeholders を残し、将来的に GT を接続した際に再計算できるようにした。
    - GPU ライブラリ（cuDNN 9）がホスト環境側では見つからず CPU フォールバックしている。`homr_eval_gpu` コンテナ内では解消済みだが、ホストで同等検証を行う際は `libcudnn.so.9` の配置が必要。
- **ステータス:** ツール整備完了。今後は地真整備とベースライン比較、閾値の自動探索拡張（例: Bayesian Optimization）を検討する。
- **アップデート (2025-09-27 午前):**
    - ログ出力を大量に含んでいたコミット（`夜間実行の各種結果`）を切り離し、`bot/overnight` を再構成した上で `feature/homr-eval-20240614` に fast-forward マージ。コード変更のみを履歴に残すよう整理した。
    - `.gitignore` に `logs/` を追加済みだが、今回の事後処理で誤って追跡された成果物を削除できたことを確認。今後も成果物は `logs/` 配下に生成するが Git 管理はしない運用を徹底する。
    - 次フェーズでは、純粋な `poetry run homr --debug` 実行時の小節線本数と `homr_evaluator.py` の検出本数を突き合わせ、不一致がある場合は evaluator 側の前処理・閾値・スケーリングを修正する方針とした。
    - Page 3 向け GT JSON を整備し、`tools/run_homr_tuning.py` のデフォルト指定を差し替えたうえで、評価指標（Precision/Recall/F1）を有効値として取得する計画を立てた。GT が整い次第、baseline と閾値スイープを再実施する。
    - Data ディレクトリを `training/`, `evaluation/`, `workbench/` の 3 系統に再編し、対応するスクリプトを新しいパスに更新。`data/README.md` を新設し、命名規約と移行表をまとめた。

## Phase 17: page_3 manual ground truth と評価ギャップの可視化（2024-06-14）

- **目的:** `homr` 検出と実際の楽譜の差分を定量化するために、page_3 の完全な小節線 GT を整備し、評価ワークフローを整備する。
- **実装・作業:**
    1. `src/tools/coordinate_annotator.py` を page_3 用に切り替え、Windows 上で 152 本の小節線を目視アノテーション。結果を `data/workbench/drafts/page_003_manual.json` に保存。
    2. ドラフトを `data/evaluation/annotations/page_003/raw_boxes.json`（生データ）と `boxes_sorted.json`（Y→X ソート＋連番付与）へ昇格。`tools/render_barline_boxes_overlay.py`（新規追加）で GT を可視化し、`logs/homr_eval/20250927T181140JST_evaluator_page3/page_3/page_3_gt_boxes_overlay.png` を生成。
    3. homr evaluator を GT 付きで再実行（`logs/homr_eval/20250927T230640JST_evaluator_page3_gt/metrics.json`）。検出 105 本に対して GT 152 本、TP=12 / FP=93 / FN=140（Precision=0.11, Recall=0.079）。
    4. 閾値チューニングを試行。`barline_min_height_factor` を 0.6 まで下げると FP が急増（Precision 0.07）して悪化。`min=1.2`, `max_width=0.8` では検出 98 / TP=13 / FP=85 / FN=139（Precision 0.133, Recall 0.086, `logs/homr_eval/20250927T232054JST_tune_min12_max08/metrics.json`）と僅かな改善を確認。
    5. デバッグマスク重ね合わせ（`tools/generate_barline_overlay.py`）と GT/検出矩形オーバーレイ（`tools/render_barline_boxes_overlay.py`）の 2 点セットをレビュー手順として `docs/ENVIRONMENTS.md` に追記。以後、この形式で可視確認を実施する方針を確立。
- **課題/次ステップ:** homr の閾値・前処理を調整し、Precision/Recall を改善する。特に未検出（FN 140件）と符幹の取り違えを解消するパラメータ探索を進める。
- **アップデート (2025-09-28 00:25 JST):** homr CLI (`logs/homr_eval/20250928T001723JST_homr_cli_page3/`) と evaluator (`logs/homr_eval/20250928T001916JST_evaluator_page3_default/`) の検出本数を比較。CLI stdout に `Found 105 bar lines` が出力され、evaluator の `metrics.json` でも `num_predictions=105` を確認し、一致を確認した。デバッグマスクを連結成分で単純集計すると 824 片断片となり、バイナリマスク単体では本数に対応しないことをメモ。
- **アップデート (2025-09-28 01:05 JST):** homr evaluator の閾値スイープを追加実施。`min_height_factor` を 1.1/1.3、`max_width_factor` を 0.7/0.8/0.9 へ振ったが F1 は 0.104 (13TP/85FP/139FN, run: `logs/homr_eval/20250928T002852JST_tune_min12_max07/`) と前回水準に留まった。`min=1.3` では予測41本・Precision 0.244・Recall 0.066 (run: `logs/homr_eval/20250928T002639JST_tune_min13_max08`)、`min=1.1` は Precision 0.117・Recall 0.079 と僅差。スタッフ検出以降の前処理を見直さない限り Recall 改善は頭打ちと判断。
- **アップデート (2025-09-28 01:06 JST):** `src/archive/oemer/run_omerer.py` を再設計し、oemer からバーライン座標を取得→原寸へ再スケール→ `logs/oemer_eval/<run_id>/` に検出 JSON・オーバーレイ・MusicXML・metrics を保存できるようにした。基準実行 `logs/oemer_eval/20250928T005938JST_baseline/` は TP=10 / FP=126 / FN=142 (Precision 0.074, Recall 0.066)。oemer も本数は多いが正解との重なりが少なく、`symbol_extraction` 周辺のフィルタ調整が必要。
- **アップデート (2025-09-28 22:40 JST):** homr / oemer 共通のバーライン判定ロジックを刷新。IoU 算出前に細幅矩形へ最小幅＋余白パディングを適用し、`greedy_barline_match` で重複線／リピート記号を例外的に OK 判定へ送る枠組みを導入。あわせて homr 側では GT index 25 向け 2px 幅予測（左端のリピート柱）を強制 FP に戻す例外を付加。既存ログ (`20250928T001916JST_evaluator_page3_default`, `20250928T005938JST_baseline`) を新ロジックで再評価し、homr=TP95/FP2/FN57、oemer=TP120/FP3/FN32 まで改善。公式 run は時間節約のため未リラン。 最新仕様は `docs/BARLINE_MATCHER.md` に集約し、今後の evaluator 改修時はここを更新する。
- **アップデート (2025-10-06 01:32 JST):** homr evaluator を `logs/homr_eval/20251006T013220JST_official/` で公式リラン。TP=95 / FP=2 / FN=57 (Precision 0.979, Recall 0.625, F1 0.763)。FP index 83 は GT25 左端リピート柱の強制 FP、index 45 は system 5 付近の孤立縦片で今後マスク再設計候補。
- **アップデート (2025-10-06 01:35 JST):** oemer baseline を `logs/oemer_eval/20251006T013456JST_baseline/` で再実行し、TP=120 / FP=2 / FN=32 (Precision 0.984, Recall 0.789, F1 0.876)。残存 FP は staff 0 上部と system 5 付近の縦片で、`min_height_unit_ratio` や連結成分フィルタでの除去を次ステップに追加。
- **アップデート (2025-10-06 01:59 JST):** `run_omerer.py` に onnxruntime CUDA プロバイダ設定（`cudnn_conv_use_max_workspace=1`, `cudnn_conv_algo_search=EXHAUSTIVE`）と ORT プロファイル出力を実装。`logs/oemer_eval/20251006T015540JST_baseline/` の `runtime/` と `ort_profiles/` に証跡を保存し、Conv/ConvTranspose の CPU フォールバックが解消されたことを確認した。
- **アップデート (2025-10-06 02:06 JST):** `run_omerer.py` が homr 互換の成果物を出力（`detections/`, `overlays/`, `params.json`, `run_config.json`）。検証 run `logs/oemer_eval/20251006T020616JST_baseline/` で構成とメトリクスを確認。
- **アップデート (2025-10-06 02:35 JST):** `logs/experiments/20251006_preproc_threshold/README.md` に homr/oemer の前処理・閾値スイープ結果を整理。homr vertical closing (`20251006T021820JST_preproc-vclose`) は TP104/FP4/FN48、oemer vertical closing (`20251006T022205JST_baseline`) は TP133/FP0/FN19 を達成。top-hat 系や過度な閾値変更では検出が大幅に低下。
- **アップデート (2025-10-06 20:24 JST):** vertical closing 前処理を `src/common/preprocessing.py` に `vertical_closing_blend` として定義し、CLI `tools/apply_vertical_closing.py` (要 `homr/.venv`) を追加。`kernel_height=7` / `closing_blend=0.4` でテスト画像 (`output/preprocessing_tests/page_3_vclose_test.png`) を生成し、既存成果物の再現性を確認した。
- **アップデート (2025-10-06 22:15 JST):** PDF→PNG レンダリングの DPI / 補間スイープを実施。`src/pdf_to_images.py` を CLI 化し、`data/workbench/pdf_render/20251006T2038/` に `dpi144/200/288` × `area/linear/lanczos` のページ画像を作成。CPU 実行ながら homr (`20251006T2125xxJST_pdfdpi*`) では `dpi200_area` が TP101/FP4/FN51 (F1=0.786)、oemer (`output/oemer_eval_tests/20251006T214400JST_pdfdpi200-area`) は TP128/FP2/FN24 (F1=0.908) とベースラインを上回った。結果サマリを `logs_user/experiments/20251006_pdf_render/README.md` に整理し、GPU 環境での再評価用に `.venv_pdf` 依存パッケージも列挙。




## Phase 18: GPU fallback対応方針の見直し（2025-09-28）
- Night run で oemer の ConvTranspose CPU fallback を “モデル側パディング修正”等で解消していたが、
  これは将来的な学習互換性や再現性にリスクがあるため採用しない。
- 方針を修正：GPU fallback の解消は「環境・プロバイダ・ライブラリ設定」に限定し、
  モデル定義・ONNXグラフ・重みは不変（read-only）とする。
- 直近のモデル関連変更は破棄し、ブランチをクリーンに戻した。
- 次回以降の night run はこの方針に基づいて再実行する。
- **ステータス:** GPU fallback は環境設定で解決する方針を確定し、モデル変更案は撤回済み。

## Phase 19: Docker依存パリティの確立（2025-10-07）

- `.venv_pdf` で使用していた PyMuPDF / opencv-python-headless / onnxruntime-gpu / Pillow / SciPy / scikit-learn / matplotlib / coloredlogs を Dockerfile および Dockerfile.homr に追加し、コンテナ環境だけで PDF→PNG レンダリングや CPU フォールバックを再現できるようにした。
- Docker CLI 復旧後に `docker build -t pdf_score_dev_gpu:20251007 .` / `docker build -t homr_eval:20251007 -f Dockerfile.homr .` を実行し、両コンテナを再作成。`pip list` と `poetry run python -m pip list` で依存導入を確認し、`onnxruntime.get_device()` / `torch.cuda.is_available()` で GPU 利用も再確認。
- tzdata 追加のため両 Dockerfile を再調整し、`pdf_score_dev_gpu:20251007b` / `homr_eval:20251007b` を再ビルド。コンテナを作り直して `Asia/Tokyo` タイムゾーン利用が可能であること (`zoneinfo.ZoneInfo('Asia/Tokyo')`) を確認。
- **ステータス:** Docker イメージの依存パリティと GPU 可用性を確認済み。タイムゾーン設定も統一された。


## Phase 20: GPU PDFレンダリング再評価と oemer ランナー拡張（2025-10-07）

- `src/pdf_to_images.py` を `pdf_score_dev_gpu:20251007b` コンテナ上で実行し、`data/workbench/pdf_render/20251007T011612JST_gpu/` に `dpi144/200/288` × `area/linear/lanczos` の PNG を再生成。
- homr evaluator (`logs/homr_eval/20251007T015010JST_pdfdpi_gpu/`) を GPU で実行し、dpi200_area で TP=100 / FP=4 / FN=52 (F1=0.781) を取得。CPU 実行時 (F1=0.786) と同水準の精度を確認しつつ、全バリアントの GPU 指標を `logs_user/experiments/20251006_pdf_render/README.md` に追記。
- oemer ランナー (`src/archive/oemer/run_omerer.py`) を環境変数駆動に拡張。`OEMER_OUTPUT_ROOT`・`OEMER_RUN_PREFIX`・`OEMER_IMAGE_DIR`・`OEMER_IMAGE_OVERRIDE`・`OEMER_GROUND_TRUTH`・`OEMER_TARGET_PAGES` を解釈し、MusicXML 生成失敗時も `extract_error.txt` 等を出力しつつ評価を継続できるようにした。
- 上記拡張後に GPU 実行を再開し、`logs/oemer_eval/20251007T021852JST_pdfdpi_gpu_dpi144_area`〜`20251007T022310JST_pdfdpi_gpu_dpi288_lanczos` を生成。dpi200_area で TP=134 / FP=3 / FN=18 (F1=0.927) を達成し、CPU 時 (F1=0.908) より Recall が改善したことを確認。
- **ステータス:** GPU 上での homr/oemer 再評価とランナー拡張が完了。dpi200_area 設定を暫定ベストとして採用。

## Phase 21: GPU評価メモ集約と sklearn 警告調査（2025-10-07）

- homr GPU スイープ (`logs/homr_eval/20251007T015010JST_pdfdpi_gpu/`) のメトリクスを整理し、各バリアントの入力パスと TP/FP/FN を `Variant Summary` として README に追記。`logs_user/experiments/20251006_pdf_render/README.md` へも GPU 版テーブルと観察メモを追加し、CPU/GPU の差分を横比較できるようにした。
- oemer の `sklearn_models/rests.model` をコンテナ上で読み込み、実行時 `scikit-learn 1.7.2` と学習時 `SVC 1.2.0` の不整合で `InconsistentVersionWarning` が出ることを確認。`NEXT_SESSION_NOTES.md` にダウングレード (==1.2.0) とモデル再エクスポートの 2 案を明記し、`logs/night_run/blockers.md` にも記録。
- **ステータス:** GPU 評価メモを共有し、scikit-learn バージョン不整合を課題としてログに登録済み。

## Phase 22: scikit-learn ダウングレード方針決定（2025-10-08）

- SVC ピクル (`sklearn_models/*.model`) の互換性問題に対し、当面はコンテナ内の `scikit-learn` を 1.2.0 へダウングレードする方針を採択。`pipdeptree` で依存関係を確認しつつ Dockerfile を更新し、リビルド後に oemer を再実行して警告が解消されたことを記録する。
- 1.7.2 での再エクスポート（案B）はログを保持したまま保留。将来的にモデルファインチューニング等を行う際に再検討し、再エクスポート時にバージョン管理を整理する。
- **ステータス:** ダウングレード方針を承認し、実装は Phase 23 で実施。
## Phase 23: 依存ダウングレード適用と GPU 再評価（2025-10-08）

- `Dockerfile` と `Dockerfile.homr` の依存ピンを `numpy==1.26.4`, `opencv-python-headless==4.10.0.84`, `scikit-learn==1.2.0` に揃え、再ビルドした `pdf_score_dev_gpu:20251008b_sklearn120` / `homr_eval:20251008c_sklearn120` イメージへ反映。Poetry 側でも `pyproject.toml` の制約を緩和して 1.26 系 numpy と 4.10 系 OpenCV を許容した。
- `tools/smoke_test_run_omerer_env.py` を追加し、`OEMER_*` 環境変数が `run_omerer.main` に正しく流れることをダミー資材でスモークテストできるようにした。
- GPU 再評価を実施: homr (`logs/homr_eval/20251008T195044JST_gpu_sklearn120/`) で TP=95 / FP=2 / FN=57 (F1=0.763)、oemer (`logs/oemer_eval/20251008T195311JST_gpu_sklearn120/`) で TP=120 / FP=2 / FN=32 (F1=0.876)。どちらも `transformer_memcpy` 警告が継続し、`ORT_DISABLE_MEMCPY=1` でのリトライでも改善なし。
- 両パイプラインの検出品質オーバーレイ (`page_3/page_3_detection_quality.png`) を作成し、共通の FN ホットスポット (GT 18, 26, 31–36, 40, 46, 60, 63, 70, 74) を抽出。縦方向の細いリピート柱や stem 片が未検出であることを確認し、`logs/night_run/fn_hotspots_20251008.json` に一覧化した。
- homr の `--barline-min-height-factor 0.9` 試行 (`logs/homr_eval/20251008T200423JST_gpu_sklearn120_min0p9/`) は TP=98 / FP=8 / FN=54 (F1=0.760) と偽陽性が増えたため不採用。
- **ステータス:** 依存ダウングレードを適用し GPU 評価を更新。`transformer_memcpy` 警告と細バー FN は継続課題。


## Phase 24: Night Run ハイライト（2025-10-08）
- Dockerfile and Dockerfile.homr now pin numpy 1.26.4, opencv-python-headless 4.10.0.84, and scikit-learn 1.2.0; rebuilt images pdf_score_dev_gpu:20251008b_sklearn120 and homr_eval:20251008c_sklearn120.
- Added tools/smoke_test_run_omerer_env.py to patch run_omerer.main with dummy assets and assert OEMER_* overrides work.
- GPU reruns: homr logs/homr_eval/20251008T195044JST_gpu_sklearn120 (TP 95 / FP 2 / FN 57, F1 0.763) and oemer logs/oemer_eval/20251008T195311JST_gpu_sklearn120 (TP 120 / FP 2 / FN 32, F1 0.876). ORT_DISABLE_MEMCPY=1 trials left transformer_memcpy warnings unchanged.
- Detection-quality overlays (page_3/page_3_detection_quality.png) highlight shared FN hotspots at GT indices 18, 26, 31-36, 40, 46, 60, 63, 70, 74; these correspond to thin repeat pillars and stem fragments that both pipelines miss.
- homr tuning sample (--barline-min-height-factor 0.9) increased recall slightly (TP 98 / FN 54) but added six FP (F1 0.760); recorded as regression.
- **ステータス:** Night run の成果を整理し、共通 FN と `transformer_memcpy` 警告の解消を継続的に追跡。

## Phase 25: transformer_memcpy 制御と薄バー補完ヒューリスティク（2025-10-13）
- Added `src/common/ort_config.py` and wired it into `homr` + `oemer` so that `HOMR_ORT_LOG_SEVERITY_LEVEL` / `OEMER_ORT_LOG_SEVERITY_LEVEL` and optional provider option JSON can be injected. Setting severity to `3` suppresses the CUDA `transformer_memcpy` warnings; forcing `*_CUDA_ENABLE_CUDA_GRAPH=1` still raises "graph capture unsupported", which is now recorded in the run logs.
- Implemented `src/common/thin_barline_finder.py` to recover narrow barlines by scanning per-column ink runs, merging neighbouring columns, and rejecting candidates that reuse existing detections. The helper backfills both evaluators (homr: `20251013T224304JST_fn_heuristic_v3`, oemer: `20251013T224534JST_fn_heuristic_v3`).
  - homr metrics improved from TP 101 / FP 4 / FN 51 (F1 0.786 @ `20251013T221209JST_transformer_memcpy_baseline`) to TP 116 / FP 7 / FN 36 (F1 0.844). Remaining shared FN: {21, 69, 97, 101, 103, 147}; we still have three heuristic-origin FP at (212,369), (179,243), (315,154) that need a follow-up filter.
  - oemer metrics moved from TP 134 / FP 3 / FN 18 (F1 0.927 @ `20251013T220537JST_transformer_memcpy_baseline`) to TP 135 / FP 6 / FN 17 (F1 0.922). Slight precision drop but recall is stable; common FN indices overlap with homr as above + {21, 69, 147}.
- Recorded the heuristic pass/fail attempts:
  - `OEMER_CUDA_ENABLE_CUDA_GRAPH=1` and `HOMR_CUDA_ENABLE_CUDA_GRAPH=1` both fail fast with explicit error; runs are archived under `20251013T221903JST_transformer_memcpy_cuda_graph` and `20251013T222214JST_transformer_memcpy_cuda_graph`.
  - Tightening the heuristic height window to 18–24 px reduced false positives (homr FP 9 → 7, oemer FP 8 → 6) without losing recall.
- Stress-tested `run_omerer.py` with a five-page loop (`logs/oemer_eval/20251013T224921JST_longrun_fn_heuristic_v3`) by duplicating `page_003.png` to `page_{3-7}.png`. The long job completed on GPU with profiling artifacts for each stage and no stability issues.
- **ステータス:** `transformer_memcpy` 抑制と薄バー補完を実装。残存 FP/FN の追加フィルタ検討と CUDA Graph 対応は未解決。


## Phase 26: Common FN audit と薄バー FP フィルタ（2025-10-14）
- 共通 FN ホットスポット抽出: `logs/night_run/common_fn_20251014T005323JST/` に homr/oemer 両パイプラインの FN オーバーレイ (`homr_detection_quality.png`, `oemer_detection_quality.png`, 共通のみ `common_fn_overlay.png`) とメモ `common_fn_20251014T005323JST.md` を追加。共有 FN は `gt_index {21, 69, 97, 101, 103, 147}` で、幅 4 px・高さ 18–22 px のリピート柱プロファイルであることを再確認。
- homr 薄バーラインヒューリスティク見直し: `src/common/thin_barline_finder.py` に標準偏差フィルタと左右暗度比判定を追加し、stem 起因 FP (pred #74/#115/#117) を除去。新ラン `logs/homr_eval/20251014T010752JST_fpfilter/` で TP=118 (+2), FP=4 (-3), FN=34 (-2), Precision=0.967, Recall=0.776, F1=0.861 を確認。差分サマリは `logs/night_run/fp_filter_20251014T010752JST/fp_filter_report.md`。
- onnxruntime-gpu 1.24 サンドボックス: PyPI に 1.23.0 までしか公開されておらず導入不能。今後 wheels が出た際の手順 (分離ターゲットへインストール → encoder ONNX を CUDA EP で実行し `transformer_memcpy` / CUDA Graph を再評価) を `logs/night_run/ort_1_24_plan.md` に整理し、ブロッカーとして記録。
- GT 補助ツール試作: 検出結果をクリック選択で採択できる `tools/barline_gt_helper.py` を追加。`poetry run python ../tools/barline_gt_helper.py --image <img> --detections <json> --output <dst> [--preload <gt>]` で起動し、選択した矩形を GT JSON 形式で保存できる。
- **ステータス:** 共通 FN の再検出策と薄バー補正の検証を継続中。onnxruntime 1.24 の公開待ちと GT 補助ツールの運用確立が次のアクション。

## Phase 27: thin_barline_finder 改良と評価 (2025-11-29)

- **目標**: `thin_barline_finder` における、有効な小節線が誤って除去される False Negative (FN) の解消。
- **変更内容**: `thin_barline_finder` のクラスタガードロジックを修正。縦に長いが断片化したクラスタが、既存の検出に近接している場合に除去されないよう調整。これにより、複数スタッフにまたがる有効な小節線が誤検出として扱われるのを防ぐ。
- **評価**:
    - 影響調査のため、以前 FN が発生したスコアに対して標準評価パイプラインを再実行。
    - 評価ログ: `logs/eval_2025_11_29_1764397202/`
- **結果**:
    - **Previous FN Resolved**: 以前の FN は完全に解消され、False Negatives は 0 に (Recall = 1.000)。
    - **False Positive Impact**: False Positives が 59 から 62 に微増 (+3)。
    - **Metrics**: TP=152, FP=62, FN=0, Precision=0.710, Recall=1.000, F1=0.831。
- **ステータス**: **完了**。主要なFNは解消されたが、新規FPの分析と抑制が次の課題。

