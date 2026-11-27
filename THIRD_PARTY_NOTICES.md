# Third-party notices

This file lists the main third-party components that the PDFScoreBar runtime obtains, installs,
or modifies. PDFScoreBar's own license (AGPL-3.0-or-later, see `LICENSE` and `NOTICE`) does
**not** relicense any of them; each remains under its own license and copyright.

Source of this list: the #504 audit, section 0
(`docs/licensing/THIRD_PARTY_LICENSE_AUDIT.md` and `docs/licensing/PYTHON_IMAGE_LICENSE_LEDGER.md`
in the development repository,
<https://github.com/M763468/PDFScoreBar/blob/develop/docs/licensing/THIRD_PARTY_LICENSE_AUDIT.md>;
2026-11-13, image `sha256:71cbccf6d7f7…`, 99 Python distributions), updated for Issue #533
§0.10–0.11 (removal of BasicSR/Real-ESRGAN/GFPGAN/facexlib and HOMR transformer weights, leaving
76 Python distributions in the maintained Docker runtime) and Issue #553
(`docs/licensing/DISTRIBUTION_READINESS.md`). Indirect dependency versions
can change when the image is rebuilt; regenerate the ledger for any image you distribute and
review every component before conveying it. The installed packages'
license files are in each distribution's `*.dist-info` directory inside the image. This is not
legal advice.

## Third-party code stored in this repository

| Path | Upstream | License | Modified by PDFScoreBar |
| --- | --- | --- | --- |
| `src/third_party/realesrgan_sr/rrdbnet.py` | BasicSR 1.4.2 `basicsr/archs/rrdbnet_arch.py` and three helpers from `basicsr/archs/arch_util.py` (<https://github.com/XPixelGroup/BasicSR>) | Apache-2.0 (`src/third_party/realesrgan_sr/LICENSE-BasicSR.txt`) | **Yes** (registry/import graph removed; see file header) |
| `src/third_party/realesrgan_sr/upsampler.py` | Real-ESRGAN `realesrgan/utils.py` at `a4abfb2979a7bbff3f69f58f58ae324608821e27` (<https://github.com/xinntao/Real-ESRGAN>) | BSD-3-Clause (`src/third_party/realesrgan_sr/LICENSE-Real-ESRGAN.txt`) | **Yes** (URL download, DNI and I/O helpers removed; see file header) |

No BasicSR `ops`/StyleGAN2 file (NVIDIA Source Code License-NC), GFPGAN or facexlib code is
included or installed (Issue #533).

## Components not stored in this repository

These are fetched at Docker build time (or supplied by the operator) and are not tracked in git.

| Component | Version / origin | License | Modified by PDFScoreBar |
| --- | --- | --- | --- |
| HOMR | <https://github.com/liebharc/homr> at `457e7c6518a10ba755db2e60883419e56c4d7369` | AGPL-3.0 | **Yes** (see below) |
| PyMuPDF (bundles MuPDF) | PyPI `PyMuPDF==1.26.4` | AGPL-3.0 or Artifex commercial license | No |
| pypdfium2 (bundles PDFium and its dependencies) | PyPI `pypdfium2==5.15.1` (pinned in `pyproject.toml`) | BSD-3-Clause / Apache-2.0 plus bundled dependency licenses under `licenses/` | No |
| RapidOCR (with bundled ONNX models derived from PaddleOCR) | `rapidocr==3.10.0`, `rapidocr-onnxruntime==1.4.4` | Apache-2.0 | No |
| ONNX Runtime GPU | `onnxruntime-gpu==1.24.4` | MIT | No |
| PyTorch, torchvision, triton | `torch==2.14.0`, `torchvision==0.29.0`, `triton==3.8.0` | BSD-style / BSD-3-Clause / MIT | No |
| OpenCV, NumPy, SciPy, scikit-learn, Pillow, matplotlib, coloredlogs, psutil | pinned in `pyproject.toml` | Apache-2.0 / BSD-3-Clause / BSD-3-Clause / BSD-3-Clause / MIT-CMU / PSF-based / MIT / BSD-3-Clause | No |
| setuptools (build/runtime dependency) | `setuptools==84.2.1` (bundles `autocommand 2.2.2` pure-Python) | MIT (with vendored MIT / Apache-2.0 / BSD-2-Clause / BSD-3-Clause / MPL-2.0 / LGPL-3.0) | No |
| certifi, tqdm (indirect) | indirect dependencies | MPL-2.0 / MPL-2.0 AND MIT | No |
| Other Python distributions | see `PYTHON_IMAGE_LICENSE_LEDGER.md` (76 distributions in the current Docker runtime after #533) | per distribution | No |
| NVIDIA CUDA base image and `nvidia-*` / `cuda-*` wheels | `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04`; Python-side NVIDIA wheels | NVIDIA proprietary license terms (`nvidia-nvtx`: Apache-2.0); `cuda-toolkit` wheel: license not identified | No |
| Ubuntu 22.04 packages | base image and `apt-get install` | Per-package Debian/Ubuntu licenses, including GPL/LGPL | No |

## Modifications to third-party components

| Component | What PDFScoreBar changes | Where | Since |
| --- | --- | --- | --- |
| HOMR (AGPL-3.0) | At image build time, rewrites the installed HOMR source so the ONNX Runtime CUDA provider uses `cudnn_conv_algo_search=HEURISTIC` for the encoder and decoder. | `docker/patch_homr_onnx_provider.py`, run from `Dockerfile` | 2026-06-03 (first version), last changed 2026-09-20 |
| HOMR (AGPL-3.0) | At run time, replaces selected HOMR function bindings with compatible implementations. | `src/homr_runtime/api_compat.py` | see `git log` of that file |

The exact modification is the script/line itself; `git log` of the listed paths gives the full
change history.

## Third-party model weights

These weights are **not** tracked in git (only manifests and SHA-256 identities are) and are not
relicensed by PDFScoreBar.

| Weight | Origin | Status |
| --- | --- | --- |
| HOMR SegNet 308 (FP16 ONNX) | HOMR GitHub release `onnx_checkpoints`, downloaded and SHA-256-checked during image build (`docker/init_homr_segnet.py`) | Upstream `LICENSE_FAQ.md` states the weights are released under AGPL-3.0 and that SegNet is trained on DeepScoresV2 (<https://zenodo.org/records/4012193>, CC BY 4.0). Attribution: DeepScoresV2 by Tuggener et al. Whether dataset terms carry over to weights is not resolved by that statement. The HOMR transformer checkpoints are not downloaded or used (Issue #533) |
| RapidOCR ONNX models | Inside the RapidOCR wheel | Apache-2.0 |

First-party weights and their third-party inputs (Issues #505, #533, #550, #553):

| Weight | Initialization | Training data | Status |
| --- | --- | --- | --- |
| `models/sr_x4/pdfscorebar_sr_x4_issue533_s1r.pth` (x4 super-resolution) | random | procedurally generated synthetic scores only (Issue #533) | first-party, covered by `AGPL-3.0-or-later` |
| `models/mmr/mmr_classifier_best.pth` (multi-measure-rest classifier) | torchvision ResNet18 `IMAGENET1K_V1` (`resnet18-f37072fd.pth`; torchvision is BSD-3-Clause) | crops of score pages used for evaluation (not distributed; see `NOTICE`) | **owner's rights licensed under `AGPL-3.0-or-later`** (third-party rights in initialization weights and training data are not relicensed) |
| barline CNN release asset `issue296-d27-v1` (GitHub release tag `model-barline-cnn-issue296-d27-v1`, `cnn_classifier_epoch_9.pth`, SHA-256 `f41a9b57…`) | torchvision EfficientNet-B0 `IMAGENET1K_V1` (`efficientnet_b0_rwightman-7f5810bc.pth`, ported from timm; its author states that the ImageNet terms should be assumed to apply to those weights) | candidate crops of score pages used for evaluation (not distributed), and DeepScoresV2 crops | **owner's rights licensed under `AGPL-3.0-or-later`** (see `models/barline_cnn/manifest.json` and release notes; third-party rights in initialization weights and training data are not relicensed) |

Attribution: the barline CNN was trained in part on DeepScoresV2 (L. Tuggener, I. Elezi, Y.
Satyawan, J. Schmidhuber, M. Pelillo, T. Stadelmann, 2020; <https://doi.org/10.5281/zenodo.4012193>),
licensed under CC BY 4.0 (<https://creativecommons.org/licenses/by/4.0/>). The Real-ESRGAN
release weights are no longer used.

The Windows portable folder ships prebuilt third-party binaries (CPython, PyTorch with NVIDIA
CUDA/cuDNN DLLs, ONNX Runtime, PyMuPDF, OpenCV and others; `triton-windows` is downloaded
by the recipient at first-run setup). Its notices, license texts, build-scoped trial terms,
and source offers are generated as a separate compliance bundle for that exact build
(`tools/licensing/portable_compliance.py`, Issue #553), independent of this `main` source
distribution.

OMR-DLN and Ultralytics are no longer used by the runtime (removed in #522 / PR #523).

## Source for AGPL components

When a combined runtime is conveyed, or a modified version is made available for network
interaction, the corresponding source must be offered to those recipients/users. The
PDFScoreBar source at the exact commit, `Dockerfile`, `docker/patch_homr_onnx_provider.py`,
`docker/init_homr_segnet.py`, and `src/homr_runtime/api_compat.py`
describe how the runtime is built from the pinned upstream sources listed above.
