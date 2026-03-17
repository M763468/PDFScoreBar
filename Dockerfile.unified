FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install essential packages and Python 3.11 and uv
RUN apt-get update && apt-get install -y \
    python3.11 python3.11-venv python3.11-dev python3-pip \
    wget git curl build-essential \
    libgl1 libgl1-mesa-glx libglib2.0-0 \
    libgtk-3-0 libxrender1 libxext6 libsm6 \
    tzdata sudo \
    && rm -rf /var/lib/apt/lists/*

# Use python3.11 as default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Install uv
RUN pip install uv

# Set working directory inside the container
WORKDIR /workspace

# Copy project source code (Usually overriden by docker-compose/mounts during dev, but good for standalone build)
COPY . /workspace

# Create unified virtual environment
RUN uv venv /opt/venv_pipeline

# Activate the venv for subsequent commands
ENV PATH="/opt/venv_pipeline/bin:$PATH"

# Ensure pip, setuptools, wheel are up to date
RUN /opt/venv_pipeline/bin/python -m ensurepip --upgrade && \
    /opt/venv_pipeline/bin/python -m pip install --no-cache-dir --upgrade pip setuptools wheel

# Install dependencies from pyproject.toml
RUN uv pip install -e .

# Install external local editable packages
RUN uv pip install -e ./external/realesrgan
RUN uv pip install -e ./external/homr

# Apply basicsr patch for torchvision compatibility (from Real-ESRGAN)
RUN sed -i 's/from torchvision.transforms.functional_tensor import rgb_to_grayscale/from torchvision.transforms.functional import rgb_to_grayscale/g' /opt/venv_pipeline/lib/python3.11/site-packages/basicsr/data/degradations.py

# Ensure realesrgan model weights exist
RUN test -f external/realesrgan/weights/RealESRGAN_x4plus.pth || \
    wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth -P external/realesrgan/weights

CMD ["bash"]
