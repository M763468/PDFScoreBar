#!/usr/bin/env bash
# Reproduce the Dockerfile dependency steps in an isolated Windows venv.
# Usage: install_runtime.sh <venv-name> <torch-cuda-tag e.g. cu130|cu126> [--ort-cuda-extras]
set -euo pipefail
. "$(dirname "$0")/env.sh"
NAME=$1; TAG=$2; EXTRAS=${3:-}
V="$POCW/$NAME"; P="$POC/$NAME/Scripts/python.exe"
R='S:\workspace\ws_PDFScoreBar\PDFScoreBar'
C="$POC/scripts/constraints_$TAG.txt"
printf 'torch==2.14.0+%s\ntorchvision==0.29.0+%s\n' "$TAG" "$TAG" > "$C"
uv venv --python 3.12 "$V"
X=(--python "$V" --extra-index-url "https://download.pytorch.org/whl/$TAG" --index-strategy unsafe-best-match -c "$C")
uv pip install "${X[@]}" --upgrade pip setuptools wheel
uv pip install "${X[@]}" "torch==2.14.0+$TAG" "torchvision==0.29.0+$TAG"
uv pip install "${X[@]}" git+https://github.com/xinntao/Real-ESRGAN.git@a4abfb2979a7bbff3f69f58f58ae324608821e27
uv pip install "${X[@]}" git+https://github.com/liebharc/homr.git@457e7c6518a10ba755db2e60883419e56c4d7369
"$P" -c "import importlib.metadata as m,json;c=json.loads(m.distribution('homr').read_text('direct_url.json'))['vcs_info']['commit_id'];assert c=='457e7c6518a10ba755db2e60883419e56c4d7369',c;print('homr',c)"
"$P" "$R\docker\patch_homr_onnx_provider.py"
uv pip install "${X[@]}" onnxruntime-gpu==1.24.4
uv pip install "${X[@]}" -r "$POC/scripts/project_deps.txt"
uv pip install "${X[@]}" --force-reinstall --no-deps opencv-python==4.11.0.86
uv pip uninstall --python "$V" onnxruntime || true
uv pip install "${X[@]}" --force-reinstall --no-deps onnxruntime-gpu==1.24.4
if [ "$EXTRAS" = "--ort-cuda-extras" ]; then uv pip install "${X[@]}" "onnxruntime-gpu[cuda,cudnn]==1.24.4"; fi
"$P" -m homr.main --init --gpu force 2>&1 | grep -v "^Downloaded" | tail -3
"$P" - <<'PY'
from pathlib import Path; import sysconfig
p = Path(sysconfig.get_paths()['purelib']) / 'basicsr' / 'data' / 'degradations.py'
s = p.read_text(); n = s.replace('from torchvision.transforms.functional_tensor import rgb_to_grayscale', 'from torchvision.transforms.functional import rgb_to_grayscale')
p.write_text(n); print('basicsr patched', s != n)
PY
uv pip freeze --python "$V" > "$POC/logs/freeze_$NAME.txt"
echo DONE
