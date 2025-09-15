# Development Log

This document records the development history, key decisions, and learnings throughout the project.

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

## Phase 3: Gemini-OpenCV Hybrid Approach (Current)

-   **Goal:** Leverage the strengths of both a powerful AI model and a robust image processing library.
-   **Tools Used:** `add_measure_numbers.py`
-   **Process:** Gemini for recognition, OpenCV for execution.
-   **Status:** This is the **current, active approach** for the project.

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