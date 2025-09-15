FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04

# PythonとOpenCVに必要な最小限のシステムライブラリをインストール
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
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
RUN pip install --no-cache-dir PyMuPDF opencv-python google-generativeai oemer

# コンテナ起動時のデフォルトコマンド
CMD ["bash"]
