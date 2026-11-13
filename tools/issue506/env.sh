# Source this to keep every tool cache inside the PoC root (no global state).
export POC=/s/workspace/ws_PDFScoreBar/issue506_poc
export POCW='S:\workspace\ws_PDFScoreBar\issue506_poc'
export UV_CACHE_DIR="$POCW\cache\uv"
export UV_PYTHON_INSTALL_DIR="$POCW\python"
export UV_PYTHON_PREFERENCE=only-managed
export UV_NO_CONFIG=1
export PIP_CACHE_DIR="$POCW\cache\pip"
export TORCHINDUCTOR_CACHE_DIR="$POCW\cache\inductor"
export TRITON_CACHE_DIR="$POCW\cache\triton"
export HF_HOME="$POCW\cache\hf"
export TORCH_HOME="$POCW\cache\torch"
export PDFSCOREBAR_MODEL_CACHE="$POCW\assets\model-cache"
export PDFSCORE_REALESRGAN_WEIGHTS_DIR="$POCW\assets\realesrgan"
export TEMP="$POCW\tmp" TMP="$POCW\tmp"
export POETRY_DYNAMIC_VERSIONING_BYPASS=0.1.0
export PYTHONUTF8=1
export VENV="$POCW\venv"
export PY="$POC/venv/Scripts/python.exe"
export UV_PYTHON_INSTALL_BIN=0
export UV_PYTHON_INSTALL_REGISTRY=0
export UV_LINK_MODE=copy
