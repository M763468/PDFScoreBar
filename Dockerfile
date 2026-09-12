# --- Build Stage ---
FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install build-time dependencies
RUN apt-get update && apt-get install -y software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y \
    python3.11 python3.11-venv python3.11-dev python3-pip \
    wget git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

WORKDIR /workspace

# Copy only dependency-defining files first for better caching
COPY pyproject.toml ./
COPY docker/patch_homr_onnx_provider.py ./docker/patch_homr_onnx_provider.py

# Create unified virtual environment and install dependencies
RUN uv venv --python 3.11 /opt/venv_pipeline
ENV PATH="/opt/venv_pipeline/bin:$PATH"

# Bypass poetry-dynamic-versioning for homr
ENV POETRY_DYNAMIC_VERSIONING_BYPASS=0.1.0

# Upgrade essential build tools in venv
RUN uv pip install --no-cache-dir --upgrade pip setuptools wheel

# Install external packages from git to avoid missing-path errors on clean checkouts
# Pinned to specific commits for reproducible builds
RUN uv pip install git+https://github.com/xinntao/Real-ESRGAN.git@a4abfb2979a7bbff3f69f58f58ae324608821e27
RUN uv pip install git+https://github.com/liebharc/homr.git@b377620a3a55bd7ff657481cec5b688dfbc9cee9
RUN /opt/venv_pipeline/bin/python docker/patch_homr_onnx_provider.py

# HOMR's supported init command materializes its CUDA/FP16 and OCR model assets.
# Do this during build so canonical GPU validation never depends on a late download.
RUN /opt/venv_pipeline/bin/python -m homr.main --init --gpu force

# Install project dependencies
RUN uv pip install -e .

# Apply basicsr patch before cloning the main venv into the isolated HOMR profile runtime.
RUN /opt/venv_pipeline/bin/python -c "from pathlib import Path; import sysconfig; p = Path(sysconfig.get_paths()['purelib']) / 'basicsr' / 'data' / 'degradations.py'; s = p.read_text(); p.write_text(s.replace('from torchvision.transforms.functional_tensor import rgb_to_grayscale', 'from torchvision.transforms.functional import rgb_to_grayscale'))"

# Keep the verified Stage E HOMR dependency stack isolated from the main OMR/CNN runtime.
ARG STAGE_E_HOMR_COMMIT=864e2882f7a41afcf8f16654728a473ae56826d6
ARG STAGE_E_PDFSCORE_COMMIT=bd6ae56f8be6c87088143cfbf0ba09dee94fe0d7
RUN cp -a /opt/venv_pipeline /opt/venv_stage_e_homr && \
    /opt/venv_stage_e_homr/bin/python -m pip uninstall -y \
      onnxruntime onnxruntime-gpu opencv-python opencv-python-headless numpy || true && \
    /opt/venv_stage_e_homr/bin/python -m pip install --no-cache-dir --no-deps \
      numpy==2.2.6 \
      opencv-python-headless==4.12.0.88 \
      onnxruntime-gpu==1.22.0
RUN git clone --filter=blob:none https://github.com/liebharc/homr.git /opt/homr_stage_e_profile && \
    git -C /opt/homr_stage_e_profile checkout --detach "${STAGE_E_HOMR_COMMIT}" && \
    git -C /opt/homr_stage_e_profile rev-parse HEAD > /opt/homr_stage_e_profile_commit.txt
RUN git clone --filter=blob:none https://github.com/M763468/PDFScoreBar.git /opt/pdfscore_stage_e_profile && \
    git -C /opt/pdfscore_stage_e_profile checkout --detach "${STAGE_E_PDFSCORE_COMMIT}" && \
    git -C /opt/pdfscore_stage_e_profile rev-parse HEAD > /opt/pdfscore_stage_e_profile_commit.txt
RUN PYTHONPATH=/opt/homr_stage_e_profile /opt/venv_stage_e_homr/bin/python - <<'PY'
import hashlib
from pathlib import Path

from homr.main import download_weights

EXPECTED = {
    "homr/segmentation/segnet_155-1240eedca553155b3c75fc9c7f643465383430a0.onnx":
        "e6a7c1e84f8d2f19f20a47e0889be2392cd487d27fa77984e4877b86534dee83",
    "homr/transformer/decoder_pytorch_model_220-c50aec7de6469480cf6f547695f48aed76d8422e-epoch-55.onnx":
        "381646983d14f17a11e4be671aaf6e4f81727b3a9edf0cf4890109a321ffce68",
    "homr/transformer/encoder_pytorch_model_220-c50aec7de6469480cf6f547695f48aed76d8422e-epoch-55.onnx":
        "22a443b2ea18da82128ae52e85436d6fb4728ab68aee24adb2ac9dfc2003a30c",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


download_weights()
root = Path("/opt/homr_stage_e_profile")
for relative, expected in EXPECTED.items():
    path = root / relative
    if not path.is_file():
        raise RuntimeError(f"Stage E HOMR model was not downloaded: {relative}")
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(
            f"Stage E HOMR model hash mismatch for {relative}: expected={expected} actual={actual}"
        )
PY

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

ARG STAGE_E_HOMR_COMMIT=864e2882f7a41afcf8f16654728a473ae56826d6
ARG STAGE_E_PDFSCORE_COMMIT=bd6ae56f8be6c87088143cfbf0ba09dee94fe0d7

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
    python3.11 python3.11-dev build-essential \
    libgl1 libgl1-mesa-glx libglib2.0-0 \
    libgtk-3-0 libxrender1 libxext6 libsm6 \
    tzdata sudo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copy the main runtime, image-owned SR assets, and the isolated verified Stage E HOMR runtime.
COPY --from=builder /opt/venv_pipeline /opt/venv_pipeline
COPY --from=builder /opt/venv_stage_e_homr /opt/venv_stage_e_homr
COPY --from=builder /opt/homr_stage_e_profile /opt/homr_stage_e_profile
COPY --from=builder /opt/pdfscore_stage_e_profile /opt/pdfscore_stage_e_profile
COPY --from=builder /opt/homr_stage_e_profile_commit.txt /opt/homr_stage_e_profile_commit.txt
COPY --from=builder /opt/pdfscore_stage_e_profile_commit.txt /opt/pdfscore_stage_e_profile_commit.txt
COPY --from=builder /opt/weights /opt/pdfscore-assets/realesrgan

# Copy source code. Canonical runtime mounts the active checkout over /workspace,
# so persistent runtime assets and the source fingerprint live under /opt instead.
COPY . /workspace

# Reuse the production artifact contract from Issue #315 for the smoke CNN. The
# manifest remains authoritative; Docker only materializes its verified bytes into
# an image-owned cache and exposes a stable validation-only path.
RUN mkdir -p /opt/pdfscore-runtime && \
    cp /workspace/docker/runtime_contract.py /opt/pdfscore-runtime/runtime_contract.py && \
    /opt/venv_pipeline/bin/python /opt/pdfscore-runtime/runtime_contract.py fingerprint /workspace \
      > /opt/pdfscore-runtime/source_fingerprint.txt && \
    CNN_MODEL_PATH=$(/opt/venv_pipeline/bin/python -m src.common.model_artifacts materialize \
      /workspace/models/barline_cnn/manifest.json --cache-root "${PDFSCOREBAR_MODEL_CACHE}") && \
    ln -s "${CNN_MODEL_PATH}" /opt/pdfscore-assets/barline_cnn_smoke.pth && \
    test -s /opt/pdfscore-assets/realesrgan/RealESRGAN_x2plus.pth && \
    test -s /opt/pdfscore-assets/realesrgan/RealESRGAN_x4plus.pth && \
    test -s /opt/pdfscore-assets/barline_cnn_smoke.pth

LABEL pdfscore.detector.homr_profile="stage_e_verified"
LABEL pdfscore.detector.homr_commit="${STAGE_E_HOMR_COMMIT}"
LABEL pdfscore.detector.pdfscore_evaluator_commit="${STAGE_E_PDFSCORE_COMMIT}"
LABEL pdfscore.runtime.asset_contract="v1"

CMD ["bash"]
