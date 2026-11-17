# Windows portable folder (Docker-free) — Issue #535

A self-contained folder that runs the PDFScoreBar engine and the correction GUI natively
on Windows 11 with an NVIDIA GPU, without Docker, WSL, a system Python or administrator
rights. **Building or running it is not permission to distribute it**: see
[Distribution gate](#distribution-gate).

## Build (maintainer)

Requirements on the build machine: Windows 10/11 x64, Git, Python ≥ 3.11 and
[uv](https://docs.astral.sh/uv/) on `PATH`, network access to PyPI, the PyTorch cu126
index and GitHub, an NVIDIA GPU (HOMR's `--init --gpu force` materializes its CUDA model
assets), and ~25 GB free (folder 5.5 GB + uv cache).

```bat
python tools\windows_portable\build_portable.py --output C:\pb\PDFScoreBar ^
    --asset-source C:\staged-assets --commit <sha>
```

* The source is `git archive <sha>`; the lock (`requirements-cu126.txt`), the asset list
  (`assets.json`) and the launcher are taken from that archived commit.
* CPython 3.12.12 is a uv-managed, relocatable build copied into `python\`; packages are
  installed into it directly (no venv, so nothing records the build location).
* The order and pins follow the Dockerfile: torch/torchvision `2.14.0+cu126`, Real-ESRGAN
  and HOMR at the Dockerfile commits, the HOMR ONNX provider patch, `onnxruntime-gpu`
  1.24.4 as the only ONNX Runtime, `opencv-python` 4.11.0.86, the basicsr patch,
  `homr --init`. The build fails unless the installed distributions equal the lock.
* `--asset-source` must provide the assets without a public URL in `assets.json` (barline
  CNN weights, and the Debian `fonts-dejavu-core` DejaVuSans-Bold.ttf whose bytes the Linux
  image uses — the upstream 2.37 TTF differs and changes label glyphs). Every asset is
  checked against its SHA-256. The font can be exported from the distribution image with
  `docker run --rm --entrypoint cat <image> /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf`.
* `runtime\build_manifest.json` records the source commit, pins, runtime versions,
  installed distributions, assets, and size + SHA-256 of every runtime file (CPython,
  packages, native DLLs, app, assets, markers). A copy of the manifest digest is written
  beside the folder (`<name>.build_manifest.sha256`).

Why cu126: torch cu130 and the CUDA 12 build of onnxruntime-gpu load two different
`cudnn64_9.dll` builds into one process and fail (Issue #506). With cu126, ONNX Runtime
uses the CUDA 12.6 / cuDNN 9.10 DLLs that torch ships. `torch.compile(reduce-overhead)`
uses the bundled `triton-windows`; no MSVC is needed.

## Use (trial user)

Requirements: Windows 10/11 x64, NVIDIA GPU with ≥ 6 GB VRAM and a current driver, ≥ 20 GB
free on the folder's drive. Place the folder at a **short ASCII path** (≤ 40 characters,
e.g. `C:\PDFScoreBar`); the launcher refuses other locations because OpenCV/HOMR cannot
open non-ASCII paths and internal paths must stay below Windows MAX_PATH.

```bat
C:\PDFScoreBar\PDFScoreBar.cmd preflight
C:\PDFScoreBar\PDFScoreBar.cmd run "D:\楽譜\score.pdf" --output "D:\結果"
C:\PDFScoreBar\PDFScoreBar.cmd review "D:\結果\job-xxxxxxxxxxxx.json"
C:\PDFScoreBar\PDFScoreBar.cmd verify --full
```

* `preflight` checks the location, free space, the folder against its manifest (sizes),
  the GPU, a real ONNX Runtime CUDA session and Triton. Jobs run with
  `PDFSCORE_REQUIRE_CUDA_ORT=1`: a CUDA session that silently runs on CPU fails the job.
* `run` processes the PDF under `jobs\` inside the folder and copies the numbered PDF to
  `--output`, which may be any path (Japanese included), with a `<job>.json` pointer.
* `review` opens the correction GUI (`http://127.0.0.1:8010/`). Saved corrections, the
  regenerated PDF and resume checkpoints are kept in the job; stopping the server and
  running `review` again resumes the same state.
* `verify --full` re-hashes every file. Byte-code caches are not part of the inventory.

All mutable state (jobs, caches, temporary files, the generated HOMR runtime overlay) stays
inside the folder. Moving the folder needs no rebuild: paths are derived at each start.

## Not covered / known limits

* Validated on one machine (Windows 11 Pro, RTX 4060 8 GB, driver 621.14). A clean
  machine, other GPUs/drivers, antivirus/SmartScreen behaviour and code signing are not
  validated (see the PR for the exact record).
* The opt-in trusted SR compiler cache (`PDFSCORE_SR_COMPILER_CACHE`) is Linux-only and
  refuses to run on Windows.
* Bounding boxes can differ by 1–2 px from the Linux image (different CUDA/cuDNN build);
  per-page measure counts and numbers are the agreed comparison.

## Distribution gate

Do not hand the folder to anyone outside the owner's control until Issue #508 decides
Go/No-go: device conditions (#508 Phase 0), rights and notices for every bundled component
(CPython, PyTorch/CUDA/cuDNN DLLs, onnxruntime-gpu, triton-windows, OpenCV, HOMR and its
models, Real-ESRGAN weights, the barline CNN, DejaVu fonts; #504/#505), the PDF intake GUI
(#507) and a formal release/promote decision.
