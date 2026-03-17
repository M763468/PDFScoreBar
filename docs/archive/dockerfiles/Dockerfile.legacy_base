FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# PythonとOpenCVに必要な最小限のシステムライブラリをインストール
RUN apt update && apt install -y \
    sudo \
    git \
    python3 \
    python3-pip \
    tzdata \
    libgl1-mesa-glx \
    libgtk-3-0 \
    libglib2.0-0 \
    libxrender1 \
    libxext6 \
    libsm6 \
    && rm -rf /var/lib/apt/lists/*

# python3をpythonコマンドとして使えるように設定
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 1

# コンテナ内の作業ディレクトリを設定
WORKDIR /workspace

# 必要なPythonライブラリをインストール
RUN pip install --no-cache-dir \
    numpy==1.26.4 \
    PyMuPDF==1.26.4 \
    opencv-python-headless==4.10.0.84 \
    onnxruntime-gpu==1.22.0 \
    pillow==11.3.0 \
    scipy==1.15.3 \
    scikit-learn==1.2.0 \
    matplotlib==3.10.6 \
    coloredlogs==15.0.1 \
    google-generativeai \
    oemer

# コンテナ起動時のデフォルトコマンド
CMD ["bash"]
