# Issue #506: Windows-native PoC evidence (Docker-free portable feasibility)

Dated experiment record (2026-11-13/14 JST) for
[Issue #506](https://github.com/M763468/PDFScoreBar/issues/506). It is **not** a maintained
runtime contract and **not** a distribution decision. Current source/tests and the Linux/Docker
distribution (#410) remain authoritative. The PoC branch `exp/issue506-windows-native-poc`
([PR #531](https://github.com/M763468/PDFScoreBar/pull/531), draft, not for merge) holds the
patches, scripts (`tools/issue506/`), and the small evidence files under
[`issue506_evidence/`](issue506_evidence/). Large outputs, runtimes, and models stay local.

## Conclusion

| Question | Answer (scope of this record only) |
| --- | --- |
| Can the existing engine and review application run natively on Windows without Docker/WSL2? | **Yes, on one machine with PoC patches.** Automatic processing, numbered PDF, review save → corrected PDF regeneration, server-restart resume, and resume-in-new-session ran natively. |
| Does unmodified `develop` run on Windows? | **No.** It fails at input validation, and eleven further Windows blockers follow, plus three not reached (see Blockers). |
| Is the Windows runtime equivalent to the Docker runtime? | **Not identical.** On evaluation2 (25 successful pages) 22 pages are exactly equal; 3 pages keep identical barline counts, measure numbers, MMR and numbering metadata but 1–2 px bbox differences. Final PDF row-label glyphs differ by 1–2 px. A different runtime (torch cu126 / cuDNN 9.10 / triton-windows) would need its own accepted regression gate before production use. |
| Is a distributable portable build proven? | **No.** A relocated portable *folder* ran on the same machine with the originals hidden. Clean machines, other GPUs, AV, signing, normal user paths and Japanese output paths are not proven (Japanese output paths fail). |
| Third-party distribution | **No-go** until #504/#505 rights, #508 Phase 0 device conditions, and the gates below pass. |

## Provenance

| Item | Identity |
| --- | --- |
| Base source | `develop` `82853c5b` (PR #526 merge). `develop` was later `04c16674`; the PoC was **not** rerun on that HEAD. |
| PoC commits | `8496451e` (patches), `5698cf73` (binary-mode input read), `046f1cb3` (tooling), `25310280` (font path from `PDFSCORE_LABEL_FONT`). Source diff `82853c5b..25310280 -- src docker configs` sha256 `37559aac8f6bfbee13aa38317a6df41eea043f709789a0361a6adfe0c1bc274b`. evaluation2 native runs used `5698cf73`; the relocated portable runs used `25310280`. |
| Machine | Windows 11 Pro 10.0.26200 (ja-JP, ANSI cp932), RTX 4060 8 GB WDDM, driver 621.14, no admin rights used, `LongPathsEnabled=0`, no MSVC. |
| Native runtime | uv-managed CPython 3.12.12, venv `venv_cu126`: torch 2.14.0+cu126 (cuDNN 9.10.2), torchvision 0.29.0+cu126, onnxruntime-gpu 1.24.4, triton-windows 3.8.0.post29, HOMR `457e7c65…` with the Docker ONNX provider patch. Freeze: [`freeze_venv_cu126.txt`](issue506_evidence/freeze_venv_cu126.txt) (sha256 `4f11e4cd…2c00`). |
| Docker baseline | Fresh `docker/distribution.py build` from `82853c5b` in WSL (LF clone): image `sha256:32ad8bea78caa215fe9c85ef10c6bc5f3e46eb80e7d2812ce3d2d78042271391`, 17.7 GB, `preflight` rc=0. Freeze: [`freeze_docker_82853c5b.txt`](issue506_evidence/freeze_docker_82853c5b.txt). Differences: [`freeze_diff_docker_vs_native.txt`](issue506_evidence/freeze_diff_docker_vs_native.txt) (torch CUDA build, Linux nvidia wheels, triton vs triton-windows). |
| Inputs | evaluation2 PDFs, [`input_SHA256SUMS`](issue506_evidence/input_SHA256SUMS). Config `configs/dense_full_pipeline.yaml` unchanged. |
| Models / font | [`asset_SHA256SUMS`](issue506_evidence/asset_SHA256SUMS): Real-ESRGAN x2/x4 and CNN match the Dockerfile/manifest hashes; DejaVuSans-Bold copied byte-identically from the Docker image (`fonts-dejavu-core`). |
| Runtime isolation | All uv/Python/torch/triton/HF caches inside the PoC root; `UV_LINK_MODE=copy`, `UV_PYTHON_INSTALL_BIN=0`, `UV_PYTHON_INSTALL_REGISTRY=0` (`tools/issue506/env.sh`). |

Commands: runtime `tools/issue506/install_runtime.sh venv_cu126 cu126` then
`uv pip install "triton-windows<3.9"`; native jobs `tools/issue506/run_native.sh` /
`run_eval2_native.sh`; Docker jobs `tools/issue506/wsl_docker_run.sh` / `wsl_eval2_docker.sh`
(`python3 docker/distribution.py --image pdfscore_issue506_develop_82853c5b run …`);
comparison `tools/issue506/compare_semantic.py <docker_job> <native_job>` (exact, 0 px
tolerance) and `compare_pdf_render.py`; review `tools/issue506/review_scenario.py`;
portable `tools/issue506/portable/run_job.cmd`.

## Results

### Runtime separation from Docker

| Element | Result |
| --- | --- |
| PyTorch CUDA | Works only with download.pytorch.org wheels (PyPI Windows torch is CPU-only). torch 2.14.0 has cu126 and cu130 Windows wheels, no cu128. |
| ORT CUDA EP | The Windows onnxruntime-gpu 1.24.4 wheel targets CUDA 12.x/cuDNN 9. Without those DLLs, sessions silently become CPU while `get_available_providers()` still lists CUDA, so the current preflight cannot detect it. |
| torch cu130 + ORT cu12 in one process | Fails: two different `cudnn64_9.dll` builds conflict (WinError 127 either import order). The numbering step uses MMR (torch) and RapidOCR (ORT CUDA) in one process. |
| torch cu126 + ORT | Works: ORT reuses torch's CUDA 12.6/cuDNN 9.10 once `torch` is imported. |
| `torch.compile(mode="reduce-overhead")` | Fails without Triton; works with community `triton-windows` 3.8.0.post29 (no MSVC needed). |
| uv hardlink mode | In-place HOMR/BasicSR patches also modify uv's cache through hardlinks; `UV_LINK_MODE=copy` is required. |
| Real per-session providers | ORT audit shim over the relocated 6-page run: 77 sessions in 13 processes; **all 41 CUDA-requesting sessions are active on `CUDAExecutionProvider`**, including current HOMR (x4) segnet/encoder/decoder and MMR RapidOCR; CPU-only RapidOCR/HOMR-OCR sessions were requested as CPU. One audit line was unparsable. [`portable_ort_audit_summary.txt`](issue506_evidence/portable_ort_audit_summary.txt). Production code still lacks a fail-fast for current HOMR (x4) and MMR RapidOCR CPU fallback. |

### Docker vs native, evaluation2 (all pages, one job per PDF)

| PDF | Pages | Docker | Native | Semantic comparison |
| --- | --- | --- | --- | --- |
| Shostakovich Festival Overture | 9 | succeeded, 774 s | succeeded, 1433 s | all 9 pages exactly equal |
| Shostakovich Sym. 5 | 25 | **failed** page_001 | **failed** page_001 | same failure: `Current x4 support requires a complete connector semantic pair` |
| Sibelius Violin Concerto | 10 | succeeded, 841 s | succeeded, 1276 s | 8 equal; page_004 one barline box and measure bboxes ±2 px; page_007 measure bbox ±1 px |
| Prokofiev Sym. 1 | 6 | succeeded, 592 s | succeeded, 747 s | 5 equal; page_005 measure bbox ±2 px |
| Prokofiev Sym. 5 | 23 | **failed** page_006 | **failed** page_006 | same failure as Sym. 5 |

Across the 25 successful pages, barline counts (1,635), measure counts (1,464), measure
numbers, MMR overrides, numbering metadata, page geometry and rendered source pages are equal.
Differences are limited to the bboxes above (exact gate: **3 pages fail**). The two job
failures are identical on both runtimes, so they are a pre-existing `82853c5b` behavior, not a
Windows effect; they are outside #506 and need their own Issue. Native timings were measured
with other disk/CPU work running and are not a performance comparison. Native-vs-native
repetition was exactly equal including final PDF pixels. Details:
[`compare/`](issue506_evidence/compare/), [`eval2_failures.txt`](issue506_evidence/eval2_failures.txt).

Final PDF rendering: the Docker image renders row labels with DejaVu Sans Bold; on Windows every
font candidate fails and Pillow silently falls back to `load_default()` (tiny labels). With the
bundled font, labels match in position and size, but glyph edges differ by 1–2 px because the
Docker Pillow uses raqm layout and the Windows wheel uses basic layout (FreeType 2.14.3 on both).
[`label_ink_bbox_docker_vs_native.txt`](issue506_evidence/label_ink_bbox_docker_vs_native.txt).

### Review, correction, resume

`review_scenario.py` ran the same API sequence on the Docker review server (Docker Desktop
relay) and the native server (PoC `fcntl` shim) for Prokofiev Sym. 1: save one MMR correction
(system 1, measure 2, span 3) → apply → resume in a new session from the produced checkpoint
with the original PDF upload.

| Check | Docker | Native |
| --- | --- | --- |
| Apply | succeeded, 8.4 s | succeeded, 11.3 s |
| `corrections_identity` | `f1a04a43…` | `f1a04a43…` (equal) |
| Resume in new session | session created, 1 recorded correction | same |
| Corrected numbering, 6 pages | — | measure numbers and numbering metadata equal on all pages; `applied_measure_overrides.json` equal; page_005 keeps the same ±2 px bbox |

[`review_scenario_docker.json`](issue506_evidence/review_scenario_docker.json),
[`review_scenario_native.json`](issue506_evidence/review_scenario_native.json),
[`review_scenario_corrected_compare.txt`](issue506_evidence/review_scenario_corrected_compare.txt).
The earlier GUI session (browser) also exercised save → apply → server restart resume natively.
The native result depends on the PoC lock shim; lock semantics (concurrency, crash, checkpoint
atomicity) are **not** verified.

### Portable folder relocation

`S:\pb` contains a copy of the CPython, the venv, `git archive` of `25310280` as `app`, assets,
the shim, and `run_job.cmd`. `tools/issue506/portable/materialize.py` rewrites `pyvenv.cfg`,
the HOMR profile runtime paths and markers for the current location and records
[`portable_identity.json`](issue506_evidence/portable_identity.json). With the original
`venv_cu126` and `python` directories renamed away:

- Prokofiev Sym. 1, 6 pages: succeeded in 961 s with a cold compile cache. Exactly equal to the
  in-place native run; versus Docker the same page_005 ±2 px.
- `source_commit` is recorded as `unknown` because the folder has no Git checkout; a real build
  must embed the commit.
- Japanese input path (`日本語入力\楽譜.pdf`) with ASCII output: succeeded.
- Japanese **output** path (`日本語出力`): **failed** at `Failed to write image` (PDF to page
  image). OpenCV on Windows passes UTF-8 bytes to the ANSI (cp932) API: `cv2.imwrite` returned
  True while writing a mojibake file name into the parent directory.

This proves relocation on the same machine only. Unverified: clean machine (MSVC runtime,
driver), other GPUs/VRAM, AV/SmartScreen, code signing, `LongPathsEnabled`, normal user-profile
paths (MAX_PATH below), update procedure.

## Windows blockers found in `develop` (PoC workaround → required production treatment)

1. Input validation treats `S:\…` as a URI scheme → allow drive-qualified paths without
   weakening URL, UNC, or traversal rejection.
2. `engine_input_safety._read_bounded_file` opens in text mode (no `O_BINARY`): reads stop at the
   first `0x1A` and translate CRLF. All five evaluation2 PDFs read 489–1,662 bytes; page count and
   sha256 metadata were wrong (processing used a separately binary-staged copy).
3. `perf_trace` imports POSIX `resource`.
4. MAX_PATH: internal paths repeat the job id three times (~243 characters below the output
   root). Even `S:\workspace\i506` overflowed; the PoC shortened `hybrid_output_root` and used
   roots like `S:\i5`. Normal `C:\Users\<name>\…` roots will fail.
5. `source_concurrency` reads `/proc/meminfo` and calls `os.killpg`.
6. `profile_sources_batch_sr` calls `os.getuid`.
7. The maintained HOMR profile hardcodes `/opt/venv_pipeline` and `/workspace`.
8. `prepare_local_review` relocates only `old_root + "/"`: on Windows it relocated 0 of 23 paths
   and still reported success. Needs bounded relocation with expected count and existence checks.
9. Review application imports `fcntl` and uses `os.O_NOFOLLOW`; the PoC shim is not a production
   lock.
10. Label font candidates are Linux paths with a silent fallback.
11. Non-ASCII output paths fail in OpenCV (above).
12. ORT CUDA fallback is silent for current HOMR (x4) and only a warning for MMR RapidOCR.
13. Not reached: `sr_compiler_cache` (`fcntl`, uid/mode), `docker/review_relay` (`/proc/net/route`),
    `python_env` (`/opt/venv_pipeline`).

## Distribution options and cost (rough)

| Option | Removes Docker/WSL2 for the user? | Status |
| --- | --- | --- |
| (A) exe launcher over Docker | No | Not pursued |
| (B) portable folder + bundled Python/libs/models + launcher | Yes (NVIDIA driver only) | Native runtime and same-machine relocation shown; distributable build unproven |
| (C) PyInstaller/Nuitka | Yes | Not tried; torch/Inductor/Triton code generation, HOMR in-package models and `-m` worker subprocesses make it costlier than (B) |
| (D) current Docker | No | Existing |
| (E) temporary cloud GPU runs | User side yes | Not tried; reuses the Linux contract |

Measured (B) footprint: 5.82 GB uncompressed (28,701 files; torch 4.0 GB), 3.43 GB with gzip -6.
Docker image: 17.7 GB. Rough effort: Windows-support PR 3–5 person-days + portable build and
Windows runtime contract 2–3 + clean-machine validation 1–2 = **about 6–10 person-days**,
excluding device procurement and ongoing maintenance of a second CUDA/runtime combination.

## Gates before any Windows distribution (handover)

- Windows-support PR with the safety conditions above and tests (relocation counts, real locks,
  path validation, binary I/O, path length, non-ASCII output).
- A Windows runtime contract checked by machine: torch/cuDNN/ORT/triton-windows identity, model
  and font hashes, resolved profile/markers, per-worker real-session CUDA providers with
  fail-fast on CPU fallback, uv copy mode, embedded source commit.
- An agreed regression gate for the cu126/triton-windows runtime (this record: evaluation2 exact
  gate fails on 3 pages by ≤2 px; numbering-level semantics equal).
- Clean-machine, other GPU, AV, Japanese path, and path-length acceptance; #508 Phase 0 device
  facts.
- #504/#505: rights for triton-windows, CUDA/cuDNN redistributable DLLs, onnxruntime-gpu,
  python-build-standalone CPython, DejaVu fonts, and existing models.
