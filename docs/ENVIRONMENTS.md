# Environment & Tooling Guide

> [!NOTE]
> **Status (Mar 2026)**: The environments have been consolidated into a single unified Docker container `pdfscore_pipeline_gpu`. Older fragmented environments are now considered legacy.

## Unified Pipeline Environment (Recommended)
- **Container Name**: `pdfscore_pipeline_gpu`
- **Image**: Built from `Dockerfile` (formerly `Dockerfile.unified`).
- **Base**: `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04`
- **Package Manager**: `uv`
- **Python Path**: `/opt/venv_pipeline/bin/python`
- **Purpose**: A single environment that supports all pipeline steps:
  - PDF to Image conversion
  - Homr (OMR) detection
  - Real-ESRGAN (Super-Resolution)
  - OMR-DLN detection
  - CNN barline classification
  - MMR (Measure Number Recognition)
  - Measure numbering integration

### Usage (Makefile - Recommended)
The project provides a `Makefile` to simplify common operations:

- **Build the image**: `make docker-build` (handles cleanup and logging to `artifacts/docker_build.log`)
- **Run smoke test**: `make run-smoke`
- **Run custom pipeline**: `make run-pipeline CONFIG=configs/my_config.yaml`
- **Cleanup space**: `make docker-clean` (removes container and image)

### Manual Usage (Host)
Start the container:
```bash
docker run --gpus all -d --name pdfscore_pipeline_gpu -v "$(pwd):/workspace" -w /workspace pdfscore_pipeline_gpu tail -f /dev/null
```

Run the full pipeline:
```bash
docker exec -it pdfscore_pipeline_gpu bash -c "export PYTHONPATH=. ; /opt/venv_pipeline/bin/python src/pipeline/main.py --config configs/evaluation2_e2e_verification_full.yaml"
```

## GUI Helper Environment
- **Tool Location**: `tools/gui_helper/`
- **Execution**: Runs directly on the Host (WSL/Linux), **no Docker required**.
- **Dependencies**: Minimal. Requires `flask` and `Pillow`.
- **Display**: Served via HTTP (`localhost:5000`), allowing usage in any browser (no X11 forwarding needed).

## CNN Classifier Training & Dataset
- **Purpose**: Build datasets and train the CNN classifier for barline filtering.
- **Environment**: Compatible with both the host `.venv_cnn_classifier` and the unified `pdfscore_pipeline_gpu` container.
- **Dataset Root**: Default is `/mnt/d/datasets/cnn_classifier_v1` (configurable via `CNN_DATASET_ROOT`).

### Dataset Building
To extract crops from images based on GT and predictions:
```bash
# In container:
/opt/venv_pipeline/bin/python tools/cnn_classifier/build_cnn_dataset.py
```

### Training
To train the model:
```bash
# In container:
/opt/venv_pipeline/bin/python experiments/cnn_classifier/train.py
```
*Note: Training logs are stored in `logs/cnn_barline_classification/training`.*

## PDF Rendering (Host / uv)
- **Purpose**: Quick PDF to image conversion on host.
- **Virtualenv**: `.venv_pdf`
- **Usage**:
  ```bash
  .venv_pdf/bin/python src/pdf_to_images.py --pdf <path> --output-dir <dir>
  ```

## Data Directory Layout
- `data/training/`: Training PDFs, images, and annotations (`boxes_sorted.json`).
- `data/evaluation/`: Evaluation PDFs, images, and annotations.
- `data/workbench/`: Temporary captures and drafts.
- `datasets/`: Processed datasets for training (e.g., `cnn_classifier_v7_base`).

---
## Legacy Environments (Archived)
The following Dockerfiles and environments are preserved in `docs/archive/dockerfiles/` for historical reference but are no longer actively maintained:
- `pdf_score_dev_gpu` (Original `Dockerfile`)
- `homr_eval_gpu` (`Dockerfile.homr`)
- `sr_eval_gpu` (`Dockerfile.sr_eval`)
- `groundingdino` (`Dockerfile.groundingdino`)

For any new development, use the **Unified Pipeline Environment**.
