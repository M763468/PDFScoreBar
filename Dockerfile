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

# Install project dependencies
RUN uv pip install -e .

# Apply basicsr patch for torchvision compatibility dynamically to avoid hardcoded python version paths
RUN /opt/venv_pipeline/bin/python -c "import basicsr; from pathlib import Path; p = Path(basicsr.__file__).parent / 'data' / 'degradations.py'; s = p.read_text(); p.write_text(s.replace('from torchvision.transforms.functional_tensor import rgb_to_grayscale', 'from torchvision.transforms.functional import rgb_to_grayscale'))"

# Download model weights during build to a safe location (not masked by volume mount)
# We place them in /opt/weights so they are always available. We will symlink them later if needed.
RUN mkdir -p /opt/weights && \
    wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth -O /opt/weights/RealESRGAN_x4plus.pth && \
    wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth -O /opt/weights/RealESRGAN_x2plus.pth

# --- Final Stage ---
FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv_pipeline/bin:$PATH"

# Install only runtime system dependencies
RUN apt-get update && apt-get install -y software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y \
    python3.11 libgl1 libgl1-mesa-glx libglib2.0-0 \
    libgtk-3-0 libxrender1 libxext6 libsm6 \
    tzdata sudo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copy virtual environment from builder
COPY --from=builder /opt/venv_pipeline /opt/venv_pipeline

# Copy source code and external packages
COPY . /workspace

CMD ["bash"]
