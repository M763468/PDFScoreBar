# Third-party notices

This file lists the main third-party components that the PDFScoreBar runtime obtains, installs,
or modifies. PDFScoreBar's own license (AGPL-3.0-or-later, see `LICENSE` and `NOTICE`) does
**not** relicense any of them; each remains under its own license and copyright.

Source of this list: the #504 audit snapshot
(`docs/licensing/THIRD_PARTY_LICENSE_AUDIT.md` in the development repository,
<https://github.com/M763468/PDFScoreBar/blob/develop/docs/licensing/THIRD_PARTY_LICENSE_AUDIT.md>;
2026-11-07, image `sha256:5c5979a26f4b…`). Indirect dependency versions can change when the
image is rebuilt; regenerate the ledger for any image you distribute. The installed packages'
license files are in each distribution's `*.dist-info` directory inside the image. This is not
legal advice.

## Components not stored in this repository

These are fetched at Docker build time (or supplied by the operator) and are not tracked in git.

| Component | Version / origin | License | Modified by PDFScoreBar |
| --- | --- | --- | --- |
| HOMR | <https://github.com/liebharc/homr> at `457e7c6518a10ba755db2e60883419e56c4d7369` | AGPL-3.0 | **Yes** (see below) |
| Ultralytics | PyPI `ultralytics==8.3.239` (+ `ultralytics-thop`) | AGPL-3.0 (commercial license also offered by Ultralytics) | No |
| PyMuPDF (bundles MuPDF) | PyPI `PyMuPDF==1.26.4` | AGPL-3.0 or Artifex commercial license | No |
| Real-ESRGAN | <https://github.com/xinntao/Real-ESRGAN> at `a4abfb2979a7bbff3f69f58f58ae324608821e27` | BSD-3-Clause | No |
| BasicSR | PyPI `basicsr==1.4.2` | Apache-2.0 | **Yes** (see below) |
| GFPGAN, facexlib | `gfpgan==1.3.8`, `facexlib==0.3.0` | Apache-2.0 | No |
| RapidOCR (with bundled ONNX models derived from PaddleOCR) | `rapidocr-onnxruntime==1.4.4` | Apache-2.0 | No |
| ONNX Runtime GPU | `onnxruntime-gpu==1.24.4` | MIT | No |
| PyTorch, torchvision, triton | `torch==2.14.0`, `torchvision==0.29.0`, `triton==3.8.0` | BSD-style / BSD-3-Clause / MIT | No |
| OpenCV, NumPy, SciPy, scikit-learn, Pillow, matplotlib, coloredlogs | pinned in `pyproject.toml` | Apache-2.0 / BSD-3-Clause / BSD-3-Clause / BSD-3-Clause / MIT-CMU / PSF-based / MIT | No |
| certifi, tqdm, lmdb (indirect) | indirect dependencies | MPL-2.0 / MPL-2.0 AND MIT / OLDAP-2.8 | No |
| NVIDIA CUDA base image and `nvidia-*` wheels | `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04` | NVIDIA proprietary license terms | No |
| Ubuntu 22.04 packages | base image and `apt-get install` | Per-package Debian/Ubuntu licenses, including GPL/LGPL | No |

## Modifications to third-party components

| Component | What PDFScoreBar changes | Where | Since |
| --- | --- | --- | --- |
| HOMR (AGPL-3.0) | At image build time, rewrites the installed HOMR source so the ONNX Runtime CUDA provider uses `cudnn_conv_algo_search=HEURISTIC` for the encoder and decoder. | `docker/patch_homr_onnx_provider.py`, run from `Dockerfile` | 2026-06-03 (first version), last changed 2026-09-20 |
| HOMR (AGPL-3.0) | At run time, replaces selected HOMR function bindings with compatible implementations. | `src/homr_runtime/api_compat.py` | see `git log` of that file |
| BasicSR (Apache-2.0) | At image build time, replaces one import line in `basicsr/data/degradations.py` (`torchvision.transforms.functional_tensor` → `torchvision.transforms.functional`). | `Dockerfile` | 2026-04-19 |

The exact modification is the script/line itself; `git log` of the listed paths gives the full
change history.

## Third-party model weights

These weights are **not** tracked in git (only manifests and SHA-256 identities are) and are not
relicensed by PDFScoreBar.

| Weight | Origin | Status |
| --- | --- | --- |
| HOMR ONNX checkpoints | HOMR GitHub release `onnx_checkpoints`, downloaded during image build | No explicit license statement for the weights; treated as unresolved |
| OMR-DLN `YOLOv8m_Measures.pt` | Linked from <https://github.com/dmgonzalez8/OMR> (no LICENSE file upstream) | Not redistributed; the operator imports it and it is verified against `models/omr_dln/manifest.json` |
| Real-ESRGAN `RealESRGAN_x4plus.pth` / `RealESRGAN_x2plus.pth` | Real-ESRGAN GitHub releases v0.1.0 / v0.2.1 | Repository is BSD-3-Clause; weight-specific terms not separately stated |
| RapidOCR ONNX models | Inside the RapidOCR wheel | Apache-2.0 |

First-party weights (`models/mmr/mmr_classifier_best.pth`, the barline CNN release asset) are not
covered by the repository license yet; see `NOTICE`.

## Source for AGPL components

When a combined runtime is conveyed, or a modified version is made available for network
interaction, the corresponding source must be offered to those recipients/users. The
PDFScoreBar source at the exact commit, `Dockerfile`, and `docker/patch_homr_onnx_provider.py`
describe how the runtime is built from the pinned upstream sources listed above.
