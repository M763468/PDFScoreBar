# Windows portable folder (Docker-free) — Issue #535

A self-contained folder that runs the PDFScoreBar engine and the correction GUI natively
on Windows 11 with an NVIDIA GPU, without Docker, WSL, a system Python or administrator
rights. **Building or running it is not permission to distribute it**: see
[Distribution gate](#distribution-gate).

## Build (maintainer)

Requirements on the build machine: Windows 10/11 x64, Git, Python ≥ 3.11 and
[uv](https://docs.astral.sh/uv/) on `PATH`, network access to PyPI, the PyTorch cu126
index and GitHub, an NVIDIA GPU, and ~25 GB free (folder 5.5 GB + uv cache).

Run the builder from a clean checkout of the frozen commit (`git checkout --detach <sha>`);
the build refuses a builder whose files differ from that commit (line endings aside).
Clone with LF line endings (`git clone -c core.autocrlf=false …`): the release tooling
and its tests compare the running files byte for byte with the commit's blobs, so a
`core.autocrlf=true` checkout fails `test_application_is_the_main_candidate_selection`
("Running release tool differs from pinned source") although the build itself tolerates it.

```bat
python tools\windows_portable\build_portable.py --output C:\pb\PDFScoreBar ^
    --asset-source C:\staged-assets --commit <40-hex sha>
```

* **Payload (#551).** The folder ships the same application as the minimal `main`
  distribution, plus only the Windows-only allowlist of [`overlay.json`](overlay.json):

  | Folder part | Content | Checked by |
  | --- | --- | --- |
  | `app\` | Exactly the files selected by `docs/MINIMAL_MAINLINE_SURFACE.json` (`tools/materialize_distribution.py:selected_files`, the selector of `tools/release_candidate.py`), read as Git blobs of the commit, plus the `DISTRIBUTION_PROVENANCE.json` that `materialize_distribution.py materialize` writes for a clean checkout | `check_tree` of the isolated tree; path + SHA-256 equality with the selection |
  | `launcher\launcher.py`, `launcher\manifest.py`, `PDFScoreBar.cmd` | The Windows entry point and its manifest checker (from `tools/windows_portable/`) | allowlist with reason, source and output SHA-256 |
  | `python\` | CPython and the locked packages, DLLs, HOMR SegNet/OCR models | lock equality, HOMR commit, exclusions |
  | `assets\` | barline CNN weights, DejaVu font and notice | `assets.json` SHA-256 |
  | `runtime\markers\` | the two HOMR profile markers | fixed names |

  Nothing else of the commit is copied: no tests, GT/evaluation data, score crops or other
  `NotLicensed` materials, experiments, developer tools, docs other than the user guides,
  the builder itself or Git metadata. `overlay.json` also lists the forbidden patterns
  checked on `app\`, the main files that are inert on Windows (`Dockerfile`,
  `.dockerignore`, `.gitignore`, `docker/distribution.py`, `docker/review_relay.py`, kept
  so `app\` equals the main distribution) and the required file whose rights are still
  pending (the MMR weight, #505).
* The lock (`requirements-cu126.txt`), the asset list (`assets.json`) and the allowlist
  are read from the commit too, and recorded by hash; they are build inputs, not shipped.
* The payload without the Windows runtime can be assembled and audited on any platform:
  `python tools/windows_portable/payload.py stage <new-dir> --commit <sha> --report <json>`.
* CPython 3.12.12 is a uv-managed, relocatable build copied into `python\`; packages are
  installed into it directly (no venv, so nothing records the build location).
* The order and pins follow the Dockerfile: torch/torchvision `2.14.0+cu126`, HOMR at the
  Dockerfile commit, the HOMR ONNX provider patch, `onnxruntime-gpu` 1.24.4 as the only
  ONNX Runtime, `opencv-python` 4.11.0.86, and the SegNet-only HOMR initialization
  (`docker/init_homr_segnet.py`: hash-checked SegNet fp16 + OCR, no transformer
  checkpoint). The build fails unless the installed distributions equal the lock minus the
  packages that the recipient installs with `setup` (triton-windows, see below), and if
  `basicsr`/`realesrgan`/`gfpgan`/`facexlib` or a HOMR transformer checkpoint is present
  (#533/#536). The x4 SR weights are the first-party `models/sr_x4` checkpoint inside the
  archived source; no Real-ESRGAN release weights are downloaded.
* `--asset-source` must provide the assets without a public URL in `assets.json` (barline
  CNN weights, and the Debian `fonts-dejavu-core` DejaVuSans-Bold.ttf whose bytes the Linux
  image uses — the upstream 2.37 TTF differs and changes label glyphs). Every asset is
  checked against its SHA-256. The font can be exported from the distribution image with
  `docker run --rm --entrypoint cat <image> /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf`.
* `runtime\build_manifest.json` (schema v2) records `source_commit` (the application source
  that jobs record, as before), `application_source_commit`, `builder_source_commit` and the
  builder file hashes, the application selection (manifest SHA-256, selector hash and
  sections, every file hash, provenance hash), the overlay records, pins, runtime versions,
  installed distributions, assets, and size + SHA-256 of every runtime file (CPython,
  packages, native DLLs, app, launcher, assets, markers). A copy of the manifest digest is
  written beside the folder (`<name>.build_manifest.sha256`).

Why cu126: torch cu130 and the CUDA 12 build of onnxruntime-gpu load two different
`cudnn64_9.dll` builds into one process and fail (Issue #506). With cu126, ONNX Runtime
uses the CUDA 12.6 / cuDNN 9.10 DLLs that torch ships. `torch.compile(reduce-overhead)`
uses `triton-windows`, which the recipient installs with `setup`; no MSVC is needed.

**Not shipped, obtained by the recipient (#553).** The `triton-windows` wheel contains
NVIDIA CUDA files (`ptxas.exe`, `cuda.h`, `cuda.lib`) that the CUDA EULA's Attachment A does
not list as Windows redistributables, and TinyCC (LGPL-2.1). The builder therefore does not
install it; `PDFScoreBar.cmd setup` downloads exactly `triton-windows==3.8.0.post29` from
PyPI with the bundled pip into `addons\site-packages` (outside `python\` and the build
manifest), and the shipped relative `python\Lib\site-packages\pdfscorebar_addons.pth`
puts it on `sys.path`. The builder also deletes `torch\lib\nvperf_host.dll` and
`torch\lib\cusolverMg64_11.dll` (NVIDIA, not listed either; no torch library loads them
for inference) and OpenCV's two FFmpeg video plugins `cv2\opencv_videoio_ffmpeg*_64.dll`
(LGPL-2.1; only `cv2.VideoCapture`/`VideoWriter` load them and neither PDFScoreBar nor HOMR
uses video), and records them in `build_exclusions`. The list lives in
[`user_setup.py`](user_setup.py) (`SETUP_SPEC`).

## Use (trial user)

Requirements: Windows 10/11 x64, NVIDIA GPU with ≥ 6 GB VRAM and a current driver, ≥ 20 GB
free on the folder's drive. Place the folder at a **short ASCII path** (≤ 40 characters,
e.g. `C:\PDFScoreBar`); the launcher refuses other locations because OpenCV/HOMR cannot
open non-ASCII paths and internal paths must stay below Windows MAX_PATH.

```bat
C:\PDFScoreBar\PDFScoreBar.cmd setup
C:\PDFScoreBar\PDFScoreBar.cmd preflight
C:\PDFScoreBar\PDFScoreBar.cmd serve
C:\PDFScoreBar\PDFScoreBar.cmd run "D:\楽譜\score.pdf" --output "D:\結果"
C:\PDFScoreBar\PDFScoreBar.cmd review "D:\結果\job-xxxxxxxxxxxx.json"
C:\PDFScoreBar\PDFScoreBar.cmd verify --full
```

* `setup` (once, needs internet): shows what is downloaded and from where, asks for
  confirmation (`--yes` to skip), downloads the pinned `triton-windows` wheel from PyPI
  into `addons\downloads`, installs it into a staging folder, checks that it imports from
  the folder and that `torch.compile` with Triton runs on the GPU, and only then swaps it
  into `addons\site-packages` and writes `addons\setup_state.json`. A failed or
  interrupted setup leaves any previous installation untouched; just run it again. A
  completed setup is not repeated (`--force` reinstalls, reusing the downloaded wheel);
  nothing is updated automatically. Without internet, `--wheel-dir <dir>` installs a wheel
  that was downloaded from PyPI beforehand. No administrator rights, no system Python and
  no files outside the folder are used; `setup` refuses to run while `serve`/`run` use
  the jobs. After setup, normal use needs no network.
* `preflight` checks the location, free space, the folder against its manifest (sizes),
  that setup was completed and its files are present, the GPU, a real ONNX Runtime CUDA
  session and that Triton is loaded from the folder's add-ons. `serve` and `run` require
  it. Jobs run with
  `PDFSCORE_REQUIRE_CUDA_ORT=1`: a CUDA session that silently runs on CPU fails the job.
* `serve` starts the browser application of #507 (`tools/browser_jobs`, unchanged) on
  `http://127.0.0.1:8010/` and opens it (`--no-browser` to skip, `--port` to change):
  choose a PDF, follow the job, open the numbered PDF, review and regenerate, and revisit
  earlier jobs. It uses the same persistent job root `jobs\` as `run`, and only one of
  `serve`/`run` can use it at a time. Stop it with Ctrl+C.
* `run` processes the PDF under `jobs\` inside the folder and copies the numbered PDF to
  `--output`, which may be any path (Japanese included), with a `<job>.json` pointer. The
  pointer names the job id, which is always resolved below the folder's current `jobs\`;
  a pointer naming anything else is refused.
* `review` opens the correction GUI (`http://127.0.0.1:8010/`). Saved corrections, the
  regenerated PDF and resume checkpoints are kept in the job; stopping the server and
  running `review` again resumes the same state.
* `verify --full` re-hashes every file (a developer/diagnostic check; normal starts only
  compare sizes). Byte-code caches are not part of the inventory. `verify` (and
  `preflight`) also check the payload contract: `app\` must equal the recorded main
  selection and its shipped manifest, and every other file must belong to the Windows
  allowlist. A file added under an inventoried root is reported as `unexpected: <path>`;
  `file outside the main application selection` appears only when the manifest itself
  was edited consistently. The add-ons installed by `setup` are checked against
  `addons\setup_state.json` (sizes; digests with `--full`); a folder whose setup has not
  been run yet still verifies clean.

All mutable state (jobs, caches, temporary files, the generated HOMR runtime overlay) stays
inside the folder. Moving the folder needs no rebuild: paths are derived at each start,
`review` re-binds the job's review package to the current location, and `serve` re-binds
every job that was moved with the folder before it starts. Saved corrections, regenerated
PDFs and checkpoints move with the jobs.

## Not covered / known limits

* Validated on the maintainer's machine (Windows 11 Pro, RTX 4060 8 GB, driver 621.14),
  including moving the folder between drives. A separate clean test machine is not part
  of the plan: other machines, GPUs/drivers, antivirus/SmartScreen behaviour and code
  signing are covered by the trial users under Issue #508.
* The opt-in trusted SR compiler cache (`PDFSCORE_SR_COMPILER_CACHE`) is Linux-only and
  refuses to run on Windows.
* Bounding boxes can differ by 1–2 px from the Linux image (different CUDA/cuDNN build);
  per-page measure counts and numbers are the agreed comparison.

## Distribution gate

Do not hand the folder to anyone outside the owner's control until Issue #508 decides
Go/No-go: device conditions (#508 Phase 0), rights and notices for every bundled component
(CPython, PyTorch/CUDA/cuDNN DLLs, onnxruntime-gpu, OpenCV, HOMR and its
models, the first-party SR weights and the vendored Real-ESRGAN/BasicSR inference code, the barline CNN, DejaVu fonts; #504/#505), the PDF intake GUI
(#507) and a formal release/promote decision. The shipped/recipient-obtained split and the
notices are recorded in `docs/licensing/DISTRIBUTION_READINESS.md` (#553).
