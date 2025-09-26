# Environments

## pdf_score_dev_gpu (existing)
- Purpose: primary development environment for the PDF Score Bar project.
- Image: built from `Dockerfile` (base `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04`).
- Persistent container: `docker start pdf_score_dev_gpu` → attach with `docker exec -it pdf_score_dev_gpu bash` (workdir `/workspace`).
- Notes: hosts project source; continue using for `oemer`/ML detector workflows.

## homr_eval_gpu (2024-06-14)
- Purpose: isolate `homr` evaluation environment with separate dependencies.
- Build image: `docker build -t homr_eval -f Dockerfile.homr .` (uses CUDA 12.1 runtime, installs Poetry).
- Container creation: `docker run --gpus all -d --name homr_eval_gpu -v /home/masaki_muramatsu/ws_PDFScoreBar:/workspace -w /workspace homr_eval tail -f /dev/null`.
- Post-create setup inside container:
  - `cd /workspace/homr && poetry config virtualenvs.in-project true`
  - `poetry install --with dev`
  - `pip uninstall onnxruntime && pip install onnxruntime-gpu==1.22.0`
  - GPU check: `python -c "import torch, onnxruntime as ort; print(torch.cuda.is_available(), ort.get_device())"`
- Host mount directories:
  - Logs: `/workspace/logs/homr_eval`
  - Models/cache: `/workspace/models/homr`
- Usage: attach with `docker exec -it homr_eval_gpu bash` and activate `/workspace/homr/.venv/bin/activate` before running `homr` commands.

