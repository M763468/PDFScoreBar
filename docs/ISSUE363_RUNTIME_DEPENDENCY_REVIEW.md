# Issue 363: Runtime Dependency Review

## Scope and comparison baseline

Issue #363 is evaluating the maintained production environment as one coherent runtime change.
The comparison baseline is the unchanged `pdfscore_pipeline_gpu:latest` image
`sha256:06d4918245cb1b933ad9369a9e74c7fc13d753556cb0fcdd6be65bd863b3b293`. Its effective
imports are Python 3.11.15, NumPy 1.26.4, SciPy 1.15.3, scikit-learn 1.2.0, Pillow 11.3.0, and
OpenCV 4.11.0 (with both OpenCV wheel flavors installed). The project pin for headless OpenCV is
4.10.0.84. Do not reinterpret or change the Issue #286 acceptance contract during this work.

The Dockerfile also creates the separate historical Stage-E HOMR environment with NumPy 2.2.6
and OpenCV headless 4.12.0.88. That profile is isolated and is not evidence that the production
environment has passed an upgrade.

## Deferred performance-risk item: OpenCV image morphology and connected components

The production `StaffExtractor.extract` path in `src/measure_numbering/pipeline.py` applies
`cv2.dilate`, `cv2.morphologyEx(MORPH_CLOSE)`, and `cv2.connectedComponentsWithStats` to staff
masks. Other measure-numbering code also uses morphology in `builder.py` and
`connector_evidence.py`. A new OpenCV build can change native implementation dispatch and runtime
cost for these operations; this is a specific performance risk for the staff-extraction path,
separate from whether its output remains correct.

An isolated benchmark has now been run on four retained 3600x4680 staff masks. The exact
`pyproject.toml` pins were installed into a disposable package overlay in the existing image;
the current image itself has OpenCV 4.11.0, while the project pin is 4.10.0. One candidate used
NumPy 2.4.5, SciPy 1.17.1, OpenCV 4.14.0, and scikit-learn 1.9.1. A second candidate also raised
Pillow to 12.3.0 and used OpenCV 4.13.0 to meet the pinned HOMR dependency metadata. All overlays
used Python 3.11.15, the same source tree and input bytes, three warmups, and 15 timed repetitions
per input.

The candidate preserved every extracted staff bbox across all four masks. Mean of the four
per-mask median `StaffExtractor.extract` times was 99.75 ms on exact current project pins and
93.85 ms on the candidate (-5.9%). However, the candidate's native `connectedComponentsWithStats`
time was 19.36 ms median across masks versus 13.95 ms on the current pins (+38.8%). Dilation and
morphology-close calls were faster on the candidate, so total extraction time hid a material
connected-component regression. This connected-component result is a separate OpenCV performance
gate; do not summarize the overall extraction improvement as meaning that every affected operation
is faster. The measurements and per-operation samples are in `logs/issue363/performance/`.

Stage-E OpenCV 4.12.0 / NumPy 2.2.6 results are exploratory only because both libraries differ
from the exact project baseline. Also, importing its cloned scikit-learn 1.2.0 fails with a NumPy
ABI error, so Stage-E is not a viable complete candidate environment. OpenCV 4.12, 4.13, and
4.14 were then measured with NumPy 2.2.6 and SciPy 1.15.3 fixed. Mean
`connectedComponentsWithStats` medians were 13.98 ms, 19.73 ms, and 19.71 ms respectively; all
staff bboxes remained equal. HOMR's minimum OpenCV 4.13 already has the slowdown (+41.2% against
4.12), so 4.12 is not a valid main-runtime candidate and 4.13 does not avoid the measured
regression.

A broader candidate matching the installed HOMR requirements used Python 3.11.15 / NumPy 2.4.5 /
SciPy 1.17.1 / OpenCV 4.13.0 / scikit-learn 1.9.1 / Pillow 12.3.0. All four bbox results matched
the exact project pins. Mean full-extraction time was 99.31 ms versus 99.75 ms; connected-components
time was 19.90 ms versus 13.95 ms (+42.6%). The total extraction time is effectively unchanged,
while the localized performance regression remains. Keep this OpenCV cost as an explicit unresolved
gate.

The installed HOMR VCS distribution metadata is pinned to commit
`457e7c6518a10ba755db2e60883419e56c4d7369` and requires Python >=3.11, NumPy >=2.4.2,<3,
`opencv-python-headless` >=4.13.0.92,<5, and Pillow >=12.1.1,<13. The current production pins
baseline did not satisfy the HOMR Python, NumPy, OpenCV, or Pillow requirements. The updated
candidate satisfies the Python, NumPy, and Pillow requirements but intentionally preserves the
baseline effective OpenCV behavior. A read-only `pip check` also reports that RapidOCR requires
generic `onnxruntime`; the Dockerfile intentionally removes that package after installing GPU ONNX
Runtime to avoid provider namespace collision.

There is an additional package-ownership conflict: Ultralytics requires the `opencv-python`
distribution while HOMR requires `opencv-python-headless`. Both distributions install the same
`cv2` module. The standalone project metadata pins only generic OpenCV 4.11, avoiding two competing
wheel flavors in ordinary project installs. The maintained Docker runtime installs HOMR's
headless distribution first and explicitly reinstalls generic 4.11 after project dependencies;
this is the supported environment where both dependencies coexist. A direct dependency dry run
also selected generic ONNX Runtime, which the Dockerfile later removes to preserve GPU provider
ownership. A candidate image was built under an isolated tag to test the complete runtime without
changing `latest`; its results are summarized below.

In isolated workload checks, SciPy 1.15.3 and 1.17.1 produced identical component-label arrays
with a 1.5% median-time difference; NumPy 1.26.4 and 2.4.5 produced identical staff-unit estimates
with a 1.2% median-time difference. These small timing differences are inconclusive. The built
candidate image passed 116 maintained fast/focused tests and the single-page detector-accuracy
smoke. However, the same three-page pipeline config changed measure geometry on pages 1 and 3 and
added one measure on page 3. A diagnostic image with only OpenCV returned to 4.11.0 reproduced the
baseline numbering JSON exactly, isolating that output drift to OpenCV 4.13. The candidate therefore
fails the output-preservation gate despite matching the one-page detector score. Keep maintained
pins and the shared production image at baseline until this regression and the OpenCV package
ownership conflict are resolved. Detailed results are in `logs/issue363/performance/REPORT.md`.

## Updated runtime decision

The tested versions now recorded in `pyproject.toml` are Python >=3.12, NumPy 2.5.3, SciPy 1.18.1,
scikit-learn 1.9.1, and Pillow 12.3.0. These are the newest tested versions that resolve together
for the Python runtime; NumPy 2.5.3 and SciPy 1.18.1 require Python 3.12. The maintained HOMR
profile's site-packages path was updated to Python 3.12. The effective generic OpenCV wheel is
explicitly pinned to 4.11.0.86 and installed last in the Dockerfile to preserve the version
imported by the baseline image. Headless OpenCV remains 4.10.0.84 because the tested OpenCV 4.13
runtime changed pipeline output and had a 42.6% connected-components slowdown. The shared
`pdfscore_pipeline_gpu:latest` tag was not rebuilt or changed.

The final candidate image is `pdfscore_pipeline_gpu:issue363-py312-final`, ID
`sha256:11248a0d742f8bc71d9ad0f41f766023689fd569bef4a41033d0390517773166`. It passed the official
runtime fingerprint preflight with CUDA and ONNX Runtime CUDA/TensorRT providers. The official
detector-accuracy smoke matched 85/85, with zero hard false positives, false negatives, or soft
errors. All 116 maintained fast/focused tests passed (5 deprecation warnings).

The same pages 1-3 and equivalent configs produced identical rendered input hashes, measure
counts/topology, numbers, bboxes, and next-number metadata. Comparison is in
`logs/issue363/full_eval/py312_science_comparison.json`; this run used the isolated
`issue363-py312-science` image with the same dependency versions as the final rebuild. The retained
Issue #286 68-page equal-x audit was run on that candidate runtime and unchanged `latest`. Every
page detail and selector result matched between runtimes, with the existing acceptance counts (68
pages, 16 tie pages, 36 tie groups) and wider-first result preserved. The audit files are
`logs/issue363/full_eval/py311_baseline_issue286_retained_audit.json` and
`logs/issue363/full_eval/py312_issue286_retained_audit.json`; the side-by-side gate result is in
`logs/issue363/full_eval/issue286_retained_comparison.json`. The audit tool's historical runtime
contract expected Python 3.11; its only reported candidate runtime drift was the deliberate Python
3.12 update. The NumPy, SciPy, and OpenCV distribution versions matched the updated project pins.
The pre-existing retained-versus-current replay differences were identical on both images.

The same four retained 3600x4680 masks were benchmarked with three warmups and 15 repetitions per
mask. Baseline versus Python 3.12 candidate mean per-mask median `StaffExtractor.extract` time was
99.78 ms versus 93.10 ms (-6.7%). Staff bboxes matched. `connectedComponentsWithStats` was 13.89 ms
versus 13.79 ms (-0.7%), with no material regression. Raw samples are in
`partial_candidate_baseline_staff_extractor.json` and `py312_science_staff_extractor.json`.

PyPI's current OpenCV release is 5.0.0.93, but the maintained HOMR commit requires
`opencv-python-headless<5`; OpenCV 5 is therefore outside the production compatibility range.
OpenCV 4.14 is the newest tested in-range release and retains the measured connected-components
slowdown; the full OpenCV 4.13 candidate failed output preservation. See [the OpenCV Python release history](https://pypi.org/project/opencv-python/)
and [the pinned HOMR dependency metadata](https://github.com/liebharc/homr/blob/457e7c6518a10ba755db2e60883419e56c4d7369/pyproject.toml).

This update advances the Python/scientific stack but does not fully resolve OpenCV compatibility.
`pip check` now has two findings: HOMR requires headless OpenCV >=4.13.0.92 while the preserved
4.10.0.84 distribution is installed, and RapidOCR requires generic ONNX Runtime, intentionally
omitted so GPU ONNX Runtime owns that namespace. The baseline had those plus unmet HOMR NumPy and
Pillow minimums; the update resolves the latter two. Ultralytics and HOMR still install different
wheel flavors that share `cv2`. Keep Issue #363 open until a single OpenCV arrangement meets HOMR's
declared compatibility, the output contract, and the connected-components performance gate. No
acceptance thresholds or evaluation inputs were changed.

## NumPy / SciPy compatibility notes (initial research)

As of 2026-09-29, PyPI lists NumPy 2.5.3 and SciPy 1.18.1 as current releases for Python 3.12.
Both are now built and validated in the candidate image with the updated scikit-learn. The earlier
Python 3.11 candidate used NumPy 2.4.5 and SciPy 1.17.1 and remains as an intermediate comparison.

The comparison baseline pinned scikit-learn 1.2.0. A NumPy 2 transition therefore could not
be treated as a NumPy-only bump: compiled extension ABI compatibility and the complete dependency
resolver result need review, including scikit-learn and all packages that import it. The
all-at-once OpenCV 4.13 candidate was rejected because it failed output preservation. The validated
Python/scientific updates were retained while the effective OpenCV version stays at the baseline.

## Final OpenCV decision and contour extraction check (2026-09-30)

The retained-mask CCL screen was extended from four representative masks to every retained
`*_staff_mask.png` under `logs/`: 2,476 paths, 782 byte-unique masks, and one zero-byte unreadable
historical artifact. The comparison used identical threshold, dilation, and morphology operations,
then compared full component boxes and stable top-to-bottom/left-to-right order. Contour-derived
boxes exactly matched OpenCV 4.11 connected-component boxes on all 782 readable unique masks. On
OpenCV 4.11, aggregate component extraction time was 38.23 s for CCL and 20.84 s for contours
(-45.5%); median per-mask time was 22.52 ms and 6.25 ms. The 4.13 contour result also matched the
4.11 CCL bbox hashes on all 782 masks, with aggregate contour time 20.50 s. Detailed per-mask
results are `retained_mask_ccl_opencv411_v2.json` and
`retained_mask_ccl_opencv413_v2.json`.

`StaffExtractor` now uses `findContours(RETR_CCOMP, CHAIN_APPROX_SIMPLE)` to enumerate external
components. Sorting by the leftmost foreground pixel on each component's top row reproduces the
CCL scan order for equal-y components; nested islands remain separate components and diagonal
touches remain 8-connected. Focused tests cover those cases. With Python 3.12 and effective OpenCV
4.11, the full same-input pages 1-3 run produced byte-equivalent decoded `numbering_final.json`
objects on all pages against the baseline (next numbers 87, 163, and 246). The run is
`logs/issue363/full_eval/py312_contours_opencv411/issue363_py312_contours_opencv411_pages_1_3/`.

The effective OpenCV upgrade remains rejected. A Python 3.12 / OpenCV 4.12 disposable overlay
produced next-number values 86, 162, and 245 instead of 87, 163, and 246. An OpenCV 4.13 build
with contour-based staff extraction still changed HOMR detections on pages 1 and 3 and produced
next number 247 on page 3; the 4.11 diagnostic exactly preserved the prior output. Therefore the
detector's installed generic `opencv-python` remains pinned at 4.11.0.86 and is reinstalled after
the dependency set. HOMR resolves `opencv-python-headless` 4.13.0.92 to satisfy its distribution
metadata; the Dockerfile's explicit final install order keeps the actually imported `cv2` at
4.11.0. Standalone project metadata pins only generic OpenCV 4.11. This shared-namespace
arrangement is intentional and verified by the runtime preflight and pipeline comparisons. The
one remaining `pip check` finding is RapidOCR's generic
ONNX Runtime metadata, which conflicts with the GPU runtime package intentionally owning that
namespace.

This is the final update decision for #363: upgrade Python and the compatible NumPy/SciPy/
scikit-learn/Pillow stack, update the headless wheel to meet HOMR's declared package requirement,
retain effective OpenCV 4.11 because tested 4.12/4.13 violate the existing output contract, and
replace the slow StaffExtractor CCL call with an output-equivalent faster contour scan. The
canonical `latest` image remains unchanged.

### Final candidate validation (2026-09-30)

The final isolated image is `pdfscore_pipeline_gpu:issue363-py312-reviewed`, ID
`sha256:25e7509a7bbf6d47b85c491b110d9860a51faa82a754d220bd44ab8bc44d13dd`. The canonical
`pdfscore_pipeline_gpu:latest` remains at `sha256:06d4918245cb1b933ad9369a9e74c7fc13d753556cb0fcdd6be65bd863b3b293`.
The final runtime preflight passed with Python 3.12.14, CUDA, and ONNX Runtime TensorRT/CUDA/CPU
providers. The official GPU detector smoke passed 85/85 with zero hard FP, FN, or soft errors;
the log is `logs/issue363/performance/py312_reviewed_official_smoke.log`. The focused/maintained
test set passed 118 tests with 5 warnings in 7.07 s
(`logs/issue363/performance/py312_reviewed_pytest.log`), Ruff passed for the changed Python
files, and `git diff --check` passed.

The retained Issue #286 audit was run with identical source in both the unchanged baseline image
and this candidate, allowing only the intentional runtime version drift. The 68-page, 16 tie-page,
36 tie-group counts, every page detail, selector outcomes, and existing retained-to-replay
difference sets matched exactly between runtimes. In particular, the wider-first selector had no
geometry changes. Result files are
`logs/issue363/full_eval/issue286_retained_baseline.json` and
`logs/issue363/full_eval/issue286_retained_candidate.json`; the candidate stdout is in
`issue286_retained_candidate.log`. `pip check` reports the pre-existing RapidOCR dependency on
generic ONNX Runtime, intentionally omitted so the GPU ONNX Runtime package owns that namespace.

The earlier paragraph above about keeping `opencv-python-headless` at 4.10.0.84 and the old
candidate tag/tests counts describes an intermediate candidate and is superseded by this final
decision: HOMR resolves headless OpenCV 4.14.0.94 transitively in the maintained Docker runtime,
while the generic 4.11.0.86 wheel is installed last and provides the effective `cv2` runtime
because 4.12 and 4.13 failed the output-preservation checks. The standalone project pin contains
only generic OpenCV 4.11.0.86.

## PR review follow-up (2026-09-30)

PR review found two issues, both addressed in the follow-up commit. First, the standalone
`pyproject.toml` no longer pins both OpenCV wheel flavors: it declares only output-compatible
`opencv-python==4.11.0.86`. HOMR's `opencv-python-headless` remains a transitive
requirement of the maintained Docker image, where the final generic-wheel reinstall controls the
shared `cv2` namespace. Second, `benchmark_staff_extractor.py` now instruments `findContours`,
the component extraction operation used by the current implementation, instead of the retired
connected-components call. CI's lint failure was solely formatting: Ruff check passed, while
Ruff format check listed four files. Those files are now formatted. Local full-repository
`ruff check .` and `ruff format --check .` both pass (Ruff 0.14.8); `make lint` itself could not
download its isolated Ruff tool because this environment cannot resolve PyPI. The same `develop`
commit used as PR #391's base (`1e440dfa`) is still the current `origin/develop` tip after fetching
again, so there were no newer upstream commits to add.

The Docker build after removing the conflicting standalone headless pin succeeded. Candidate image
`pdfscore_pipeline_gpu:issue363-pr-review` has ID
`sha256:227711f9c3e0a4067bf7485a8a76ec04019e10ef3f81db8c5d64e0a2d2340a02`. Its dependency
resolver selected `opencv-python-headless==4.14.0.94` for HOMR's `>=4.13,<5` requirement, then the
Dockerfile installed `opencv-python==4.11.0.86` last. Runtime inspection confirmed both
distribution versions, imported `cv2==4.11.0`, and the unchanged `latest` image ID. `pip check`
still reports only the pre-existing RapidOCR/generic ONNX Runtime metadata conflict.

The rebuilt candidate passed runtime preflight with CUDA and TensorRT/CUDA/CPU ONNX providers. The
pipeline completed the configured smoke page. The first accuracy-check invocation then exposed a
pre-existing smoke-config metadata mismatch: `configs/smoke_test.yaml` has an unused
`detection.container_name` field absent from `configs/dense_full_pipeline.yaml`, while the
validator allows only `hybrid_output_root` to differ. To avoid altering the Issue's evaluation
contract, the acceptance checker was rerun against the already-retained pipeline output using a
transient smoke-config copy with only that unused field removed. It passed: 85/85, zero hard FP,
FN, or soft errors. The full run is under
`logs/full_pipeline_runs/smoke_test_detection_20260929T171152Z/`; checker output is
`logs/issue363/performance/pr_review_candidate_accuracy.log`. The corrected benchmark tool smoke
recorded 4.81 ms median for `findContours` and 82.85 ms total `StaffExtractor.extract` time over
two repetitions on one retained 3600x4680 mask; the JSON is
`logs/issue363/performance/pr_review_staff_extractor_benchmark.json`.
