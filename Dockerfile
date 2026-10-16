# --- Build Stage ---
FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install build-time dependencies
RUN apt-get update && apt-get install -y software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y \
    python3.12 python3.12-venv python3.12-dev python3-pip \
    wget git curl build-essential \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

WORKDIR /workspace

# Copy only dependency-defining files first for better caching
COPY pyproject.toml ./
COPY docker/patch_homr_onnx_provider.py ./docker/patch_homr_onnx_provider.py

# Create unified virtual environment and install dependencies
RUN uv venv --python 3.12 /opt/venv_pipeline
ENV PATH="/opt/venv_pipeline/bin:$PATH"

# Bypass poetry-dynamic-versioning for homr
ENV POETRY_DYNAMIC_VERSIONING_BYPASS=0.1.0

# Upgrade essential build tools in venv
RUN uv pip install --no-cache-dir --upgrade pip setuptools wheel

# Install external packages from git to avoid missing-path errors on clean checkouts
# Pinned to specific commits for reproducible builds
ARG MAINTAINED_HOMR_COMMIT=457e7c6518a10ba755db2e60883419e56c4d7369
RUN uv pip install git+https://github.com/xinntao/Real-ESRGAN.git@a4abfb2979a7bbff3f69f58f58ae324608821e27
RUN uv pip install git+https://github.com/liebharc/homr.git@${MAINTAINED_HOMR_COMMIT}
# Fail the image build if pip's installed distribution does not retain the same
# immutable VCS revision as the Docker build argument.
RUN MAINTAINED_HOMR_COMMIT="${MAINTAINED_HOMR_COMMIT}" /opt/venv_pipeline/bin/python - <<'PY'
import importlib.metadata
import json
import os

expected = os.environ["MAINTAINED_HOMR_COMMIT"]
distribution = importlib.metadata.distribution("homr")
raw = distribution.read_text("direct_url.json")
if not raw:
    raise RuntimeError("homr direct_url.json is missing")
payload = json.loads(raw)
actual = payload.get("vcs_info", {}).get("commit_id")
if actual != expected:
    raise RuntimeError(f"homr direct_url commit mismatch: expected={expected} actual={actual}")
PY
RUN /opt/venv_pipeline/bin/python docker/patch_homr_onnx_provider.py

# HOMR's supported init command needs ONNX Runtime at this stage; the project
# dependency install below pins the same maintained runtime contract explicitly.
RUN uv pip install onnxruntime-gpu==1.24.4

# Install project dependencies
RUN uv pip install -e .

# HOMR installs its declared headless OpenCV distribution before project
# dependencies. Keep the standalone project dependency on generic OpenCV only;
# these wheel flavors share cv2, so reinstall the output-compatible production
# wheel last in the supported Docker runtime.
RUN uv pip install --no-cache-dir --force-reinstall --no-deps opencv-python==4.11.0.86

# Maintained HOMR declares both generic and GPU ONNX Runtime distributions.  The
# generic distribution wins the import namespace if left installed, hiding the
# CUDA execution provider required by the production contract.  Keep the pinned
# GPU distribution as the sole owner of that namespace.
RUN uv pip uninstall -y onnxruntime && \
    uv pip install --no-cache-dir --force-reinstall --no-deps onnxruntime-gpu==1.24.4

# HOMR's supported init command materializes its CUDA/FP16 and OCR model assets.
# Do this during build so canonical GPU validation never depends on a late download.
RUN /opt/venv_pipeline/bin/python -m homr.main --init --gpu force

# Apply the basicsr torchvision compatibility patch.
RUN /opt/venv_pipeline/bin/python -c "from pathlib import Path; import sysconfig; p = Path(sysconfig.get_paths()['purelib']) / 'basicsr' / 'data' / 'degradations.py'; s = p.read_text(); p.write_text(s.replace('from torchvision.transforms.functional_tensor import rgb_to_grayscale', 'from torchvision.transforms.functional import rgb_to_grayscale'))"

# Real-ESRGAN weights are image-owned runtime assets. Keep them outside /workspace
# so the canonical source bind mount cannot hide them. The selected release bytes are
# verified before they become part of the image; a silent replacement fails the build.
RUN mkdir -p /opt/weights && \
    wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth -O /opt/weights/RealESRGAN_x4plus.pth && \
    wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth -O /opt/weights/RealESRGAN_x2plus.pth && \
    echo "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1  /opt/weights/RealESRGAN_x4plus.pth" | sha256sum -c - && \
    echo "49fafd45f8fd7aa8d31ab2a22d14d91b536c34494a5cfe31eb5d89c2fa266abb  /opt/weights/RealESRGAN_x2plus.pth" | sha256sum -c -

# --- Final Stage ---
FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04

ARG MAINTAINED_HOMR_COMMIT=457e7c6518a10ba755db2e60883419e56c4d7369

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv_pipeline/bin:$PATH"
ENV PDFSCORE_REALESRGAN_WEIGHTS_DIR=/opt/pdfscore-assets/realesrgan
ENV PDFSCOREBAR_MODEL_CACHE=/opt/pdfscore-assets/model-cache

# Install runtime system dependencies. torch.compile/Inductor needs a native
# compiler in the final image because compilation occurs in the SR process.
RUN apt-get update && apt-get install -y software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y \
    python3.12 python3.12-dev build-essential \
    libgl1 libgl1-mesa-glx libglib2.0-0 \
    libgtk-3-0 libxrender1 libxext6 libsm6 \
    tzdata sudo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copy the maintained production runtime and image-owned SR assets.
COPY --from=builder /opt/venv_pipeline /opt/venv_pipeline
RUN echo "${MAINTAINED_HOMR_COMMIT}" > /opt/homr_maintained_profile_commit.txt && \
    echo "workspace-runtime" > /opt/pdfscore_maintained_profile_commit.txt && \
    test "$(cat /opt/homr_maintained_profile_commit.txt)" = "${MAINTAINED_HOMR_COMMIT}"
COPY --from=builder /opt/weights /opt/pdfscore-assets/realesrgan

# Copy source code. Canonical runtime mounts the active checkout over /workspace,
# so persistent runtime assets and the source fingerprint live under /opt instead.
COPY . /workspace

# Source provenance must not invalidate the expensive runtime dependency layers.
ARG PDFSCORE_SOURCE_FINGERPRINT
ARG PDFSCORE_SOURCE_COMMIT
ARG PDFSCORE_SOURCE_BRANCH

# Reuse the production artifact contract from Issue #315 for the smoke CNN. The
# manifest remains authoritative; Docker only materializes its verified bytes into
# an image-owned cache and exposes a stable validation-only path.
RUN mkdir -p /opt/pdfscore-runtime && \
    cp /workspace/docker/runtime_contract.py /opt/pdfscore-runtime/runtime_contract.py && \
    ACTUAL_SOURCE_FINGERPRINT=$(/opt/venv_pipeline/bin/python \
      /opt/pdfscore-runtime/runtime_contract.py fingerprint /workspace) && \
    printf '%s\n' "${ACTUAL_SOURCE_FINGERPRINT}" \
      > /opt/pdfscore-runtime/source_fingerprint.txt && \
    if [ -n "${PDFSCORE_SOURCE_FINGERPRINT}" ] && \
       [ "${ACTUAL_SOURCE_FINGERPRINT}" != "${PDFSCORE_SOURCE_FINGERPRINT}" ]; then \
      echo "Docker build source fingerprint changed during build context transfer" >&2; \
      echo "expected=${PDFSCORE_SOURCE_FINGERPRINT} actual=${ACTUAL_SOURCE_FINGERPRINT}" >&2; \
      exit 1; \
    fi && \
    CNN_MODEL_PATH=$(/opt/venv_pipeline/bin/python -m src.common.model_artifacts materialize \
      /workspace/models/barline_cnn/manifest.json --cache-root "${PDFSCOREBAR_MODEL_CACHE}") && \
    ln -s "${CNN_MODEL_PATH}" /opt/pdfscore-assets/barline_cnn_smoke.pth && \
    test -s /opt/pdfscore-assets/realesrgan/RealESRGAN_x2plus.pth && \
    test -s /opt/pdfscore-assets/realesrgan/RealESRGAN_x4plus.pth && \
    test -s /opt/pdfscore-assets/barline_cnn_smoke.pth

LABEL pdfscore.detector.homr_profile="maintained_original"
LABEL pdfscore.detector.homr_commit="${MAINTAINED_HOMR_COMMIT}"
LABEL pdfscore.detector.pdfscore_evaluator_commit="workspace-runtime"
LABEL pdfscore.runtime.asset_contract="v1"
LABEL pdfscore.runtime.source_fingerprint="${PDFSCORE_SOURCE_FINGERPRINT}"
LABEL pdfscore.runtime.source_commit="${PDFSCORE_SOURCE_COMMIT}"
LABEL pdfscore.runtime.source_branch="${PDFSCORE_SOURCE_BRANCH}"

CMD ["bash"]
