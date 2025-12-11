# Next Step Plan: Grounding DINO Evaluation

**Objective**: Evaluate the performance of the Grounding DINO model for barline detection.

**Original Plan (Summary)**:
1. Clone Grounding DINO repository.
2. Create a local Python virtual environment (`venv` or `uv`).
3. Install dependencies, including PyTorch.
4. Build the custom CUDA kernels via `pip install -e .`.
5. Download pretrained weights and run evaluation.

---\n## Progress Update (2025-12-10)

### Status: ⚠️ **ENVIRONMENT ISSUES PERSIST**

This document tracks the ongoing effort to establish a working environment for Grounding DINO.

### History of Failures

1.  **Local Venv Failures (Initial Approach)**: Multiple attempts to build the required environment locally using `pip` and `uv` failed due to a complex web of incompatibilities between Python versions, PyTorch versions, and CUDA toolkit versions. This approach was **abandoned**.

2.  **Docker Environment Pivot (Current Approach)**: To create a stable environment, we pivoted to using a dedicated Docker container based on `nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04`. The initial Docker build **succeeded**, correctly installing all Python packages and compiling the Grounding DINO custom kernels.

3.  **Execution Failure (ImportError)**: The first attempt to *run* the evaluation script inside the new container failed with the following error:
    - **Error**: `ImportError: libGL.so.1: cannot open shared object file: No such file or directory`
    - **Reason**: This error occurred when `import cv2` was called. The base NVIDIA Docker image is optimized for computation and lacks certain GUI-related shared libraries. The standard `opencv-python` package requires `libGL.so.1` for its rendering functions, but this library was not present in the container.

### Action Taken

- **Dockerfile Update**: The `Dockerfile.groundingdino` was modified to install the missing dependency. A line was added to install `libgl1-mesa-glx`, which provides `libGL.so.1`.
- **Image Rebuild**: The Docker image `groundingdino-eval` was successfully rebuilt with the updated Dockerfile.

---\n## Next Step

The environment is now believed to be fully configured and correct. The next and immediate step is to re-run the evaluation script to confirm the `ImportError` is resolved and to get the first inference results from the model.

- **Action**: Execute the evaluation script inside the newly built container.
- **Command**:
  ```bash
  docker run --gpus all --rm \
    -v $(pwd):/home/user/ws_PDFScoreBar_model_exp \
    groundingdino-eval \
    python3 experiments/models/eval_grounding_dino.py \
      --image data/evaluation/images/page_3.png \
      --gt data/evaluation/annotations/page_003/boxes_sorted.json \
      --output-dir logs/model_experiments/grounding_dino/run_001
  ```

## Run 001 (2025-12-10): Execution Notes & Outcome
- **Prep required when mounting host repo**: inside the container install runtime libs and rebuild the C++ ops on the mounted tree.
  - `apt-get install -y libglib2.0-0 build-essential`
  - `pip install numpy==1.26.4` (avoid NumPy 2.x `_ARRAY_API` failures with PyTorch)
  - `pip install --no-build-isolation --no-deps -e external/grounding_dino` (builds `groundingdino/_C` onto host volume)
- **Weights**: downloaded to `external/grounding_dino/weights/groundingdino_swint_ogc.pth`.
- **Result (run_001)**: TP=0, FP=2, FN=152, F1=0.0. Only two boxes detected on `page_3`. Outputs saved to `logs/model_experiments/grounding_dino/run_001/` (metrics, predictions, visualization).
- **Next ideas**: tune prompt/thresholds and verify the compiled ops remain available before re-running. If rebuilding the image, bake the above dependencies into `Dockerfile.groundingdino` to skip per-run setup.

## 成果 (2025-12-10)
- ホストマウント実行時の依存関係問題を解消（`libglib2.0-0` + `build-essential` + `numpy==1.26.4` + `pip install --no-build-isolation --no-deps -e external/grounding_dino` で `_C` ビルド/NumPy 2系問題を回避）。
- GroundingDINO の重みを `external/grounding_dino/weights/groundingdino_swint_ogc.pth` に取得済み。
- 初回評価 (run_001) を完了し、結果と可視化を `logs/model_experiments/grounding_dino/run_001/` に保存（TP=0, FP=2, FN=152, F1=0.0）。

## 追加トライ (2025-12-10)
- **Dockerfile update**: `Dockerfile.groundingdino` に `build-essential` 追加、`numpy==1.26.4` をビルド時にピン止めし、`pip install --no-build-isolation --no-deps -e external/grounding_dino` に変更（C++ ops をビルド時に完了させる方針）。
- **run_005**: prompt=`barline`, box/text threshold=0.05。検出18件 (すべてFP、TP=0/FN=152)。全予測が幅195〜583pxの横長ボックスで、縦線を拾えていない。
- **run_006**: prompt=`vertical barline in sheet music`（here-doc で多語プロンプトを正しく渡す）、threshold=0.05。検出22件 (すべてFP)。同様に横長ボックスのみ。
- **run_007**: 画像/GTを2x拡大して評価 (prompt=`barline`, threshold=0.05)。検出18件、TP=0/FP=18/FN=152。横長ボックスのみで変化なし。入力スケール変更では改善せず。
- 予測のアスペクト比確認: 最小幅195px、width/height 最小0.75。細い縦線を出せていないため、評価のスケールミスではなくモデルの検出失敗と判断。
- 入力画像サイズ: 593x792px。GroundingDINO の `RandomResize([800], max_size=1333)` でほぼ等倍。GT座標系とスケールは一致している。
- 多語プロンプトを渡す場合、shell 引数で潰れるため `run_eval.sh` のようなスクリプト経由で `--prompt "..."` を渡すこと。

## Next Steps
- Dockerfile.groundingdino に `libglib2.0-0` / `build-essential` / `numpy==1.26.4` / `pip install --no-build-isolation --no-deps -e external/grounding_dino` を焼き込み、ホストマウント実行でも再ビルド不要にする。
- モデルの検出が横長ボックスに偏るため、単なる閾値・プロンプト調整では改善見込みが低い。追加で試すなら (a) 画像を 2x などに拡大して解像度を上げる（GTも同じ倍率で拡大してから評価）→ **run_007 で無改善**、(b) 予測後に縦長ボックスのみ残す簡易フィルタを挟む、の順で軽く確認する。
- 実行前チェック: `_C` so が存在するか (`external/grounding_dino/groundingdino/_C*.so`) と NumPy バージョンが <2 であることを確認。多語プロンプトはスクリプト経由で渡す。
