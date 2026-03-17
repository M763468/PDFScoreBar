# --- Build Stage ---
FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04 as builder

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install build-time dependencies
RUN apt-get update && apt-get install -y \
    python3.11 python3.11-venv python3.11-dev python3-pip \
    wget git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

WORKDIR /workspace

# Copy only dependency-defining files first for better caching
COPY pyproject.toml ./
COPY external/homr/pyproject.toml ./external/homr/
COPY external/realesrgan/setup.py ./external/realesrgan/
COPY external/realesrgan/VERSION ./external/realesrgan/

# Create unified virtual environment and install dependencies
RUN uv venv /opt/venv_pipeline
ENV PATH="/opt/venv_pipeline/bin:$PATH"

# Upgrade essential build tools in venv
RUN uv pip install --no-cache-dir --upgrade pip setuptools wheel

# Install project dependencies (editable)
# Note: we copy the rest of external later for full functionality, 
# but we need the directory structure for editable installs.
COPY external/realesrgan/realesrgan ./external/realesrgan/realesrgan
COPY external/homr/homr ./external/homr/homr

RUN uv pip install -e .
RUN uv pip install -e ./external/realesrgan
RUN uv pip install -e ./external/homr

# Apply basicsr patch for torchvision compatibility
RUN sed -i 's/from torchvision.transforms.functional_tensor import rgb_to_grayscale/from torchvision.transforms.functional import rgb_to_grayscale/g' /opt/venv_pipeline/lib/python3.11/site-packages/basicsr/data/degradations.py

# Download model weights during build
RUN mkdir -p external/realesrgan/weights && \
    wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth -O external/realesrgan/weights/RealESRGAN_x4plus.pth

# --- Final Stage ---
FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv_pipeline/bin:$PATH"

# Install only runtime system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 libgl1 libgl1-mesa-glx libglib2.0-0 \
    libgtk-3-0 libxrender1 libxext6 libsm6 \
    tzdata sudo \
    && rm -rf /var/lib/apt/lists/*

# Use python3.11 as default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

WORKDIR /workspace

# Copy virtual environment from builder
COPY --from=builder /opt/venv_pipeline /opt/venv_pipeline

# Copy source code and external packages
COPY . /workspace

CMD ["bash"]
