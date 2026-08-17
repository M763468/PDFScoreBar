#!/usr/bin/env python3
"""Issue #274: prove page-local current-HOMR predictor lifetime reuse is equivalent.

This focused gate deliberately reruns only current HOMR inference.  It does not
rerun Real-ESRGAN SR, OMR-DLN, dense probe, CNN, MMR, or the full detector.

For each selected page:
1. Reproduce the accepted current-original producer through
   HybridDetector._run_homr_in_process(..., enable_sr=False).
2. Create exactly one *shared* current HomrPredictor instance.
3. Run original-image HOMR (sr_scale=1) and the retained x4 image (sr_scale=4)
   sequentially through that same predictor instance.
4. Compare shared-original artifacts with the accepted independent-original
   producer, and shared-x4 artifacts with the retained production-B artifacts.

The experiment is intentionally page-local because current_support_worker is a
page-local worker.  The desired production change, if this gate passes, is two
neural inference passes on two semantically distinct inputs while reusing one
loaded predictor/model lifetime.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.homr_eval_scripts.core.metrics import BarlinePrediction
from src.homr_eval_scripts.core.reporting import save_homr_results
from src.pipeline.detection.current_homr_worker import _resize_mask_to_image_size
from src.pipeline.detection.hybrid import HybridDetector
from src.pipeline.utils.images import load_image
from tools.issue120.eval_full68_from_intermediates import SCORES

Box = tuple[int, int, int, int]

DEFAULT_GLOBAL_PAGES: tuple[str, ...] = (
    "page_033",  # combined x/y MMR regression blocker
    "page_042",  # Issue #244 five-override guard
    "page_035",  # known vertical split case
    "page_013",  # prior topology-divergence case
)

DEFAULT_AB_GLOB = (
    "logs/issue274_homr_unification_analysis/**/"
    "issue274_homr_x4_stage_e_ab.json"
)


def _json_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_array(array: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(str(contiguous.dtype).encode("utf-8"))
    digest.update(b"\0")
    digest.update(json.dumps(list(contiguous.shape)).encode("utf-8"))
    digest.update(b"\0")
    digest.update(contiguous.tobytes())
    return digest.hexdigest()


def _safe_git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return None


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _module_fingerprint(module: Any) -> dict[str, Any]:
    raw_path = getattr(module, "__file__", None)
    path = Path(str(raw_path)).resolve() if raw_path else None
    return {
        "path": str(path) if path else None,
        "sha256": _sha256_file(path) if path and path.is_file() else None,
    }


def _path_fingerprint(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.is_file(),
        "sha256": _sha256_file(path) if path.is_file() else None,
        "size_bytes": path.stat().st_size if path.is_file() else None,
    }


def _resolve_ab_report(explicit: Path | None) -> Path:
    if explicit is not None:
        candidate = explicit.resolve()
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(candidate)

    candidates = sorted(
        PROJECT_ROOT.glob(DEFAULT_AB_GLOB),
        key=lambda p: (p.stat().st_mtime_ns, str(p)),
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            "Could not find issue274_homr_x4_stage_e_ab.json under "
            "logs/issue274_homr_unification_analysis"
        )
    return candidates[0].resolve()


def _to_workspace(path_like: str | Path) -> Path:
    """Map retained host/workspace paths to this checkout when possible."""
    path = Path(path_like)
    if path.is_file():
        return path.resolve()

    text = str(path)
    markers = ("/workspace/", "\\workspace\\")
    for marker in markers:
        if marker in text:
            suffix = text.split(marker, 1)[1].replace("\\", "/")
            candidate = PROJECT_ROOT / suffix
            if candidate.exists():
                return candidate.resolve()

    if not path.is_absolute():
        candidate = PROJECT_ROOT / path
        if candidate.exists():
            return candidate.resolve()

    return path.resolve()


def _norm_box(values: Iterable[Any]) -> Box:
    vals = list(values)
    if len(vals) < 4:
        raise ValueError(f"Invalid bbox: {vals!r}")
    return tuple(int(round(float(value))) for value in vals[:4])  # type: ignore[return-value]


def _load_detection_records(path: Path) -> list[dict[str, Any]]:
    payload = _json_load(path)
    records: Any = payload
    if isinstance(payload, Mapping):
        records = payload.get("predictions", [])
    if not isinstance(records, list):
        raise ValueError(f"Invalid detections payload: {path}")

    out: list[dict[str, Any]] = []
    for item in records:
        if isinstance(item, Mapping):
            bbox = item.get("orig_bbox", item.get("bbox", item.get("pred_bbox")))
            if bbox is None:
                continue
            out.append(
                {
                    "orig_bbox": _norm_box(bbox),
                    "system_index": item.get("system_index"),
                    "staff_index": item.get("staff_index"),
                }
            )
        elif isinstance(item, Sequence) and len(item) >= 4:
            out.append(
                {
                    "orig_bbox": _norm_box(item),
                    "system_index": None,
                    "staff_index": None,
                }
            )
    return out


def _boxes_from_records(records: Sequence[Mapping[str, Any]]) -> list[Box]:
    return [_norm_box(row["orig_bbox"]) for row in records]


def _counter_examples(counter: Counter[Box], limit: int = 20) -> list[list[int]]:
    result: list[list[int]] = []
    for box, count in counter.items():
        for _ in range(count):
            result.append(list(box))
            if len(result) >= limit:
                return result
    return result


def _tolerant_box_match(left: Sequence[Box], right: Sequence[Box], tolerance_px: int) -> dict[str, Any]:
    pairs: list[tuple[int, int, int, int]] = []
    for li, lhs in enumerate(left):
        for ri, rhs in enumerate(right):
            deltas = [abs(lhs[i] - rhs[i]) for i in range(4)]
            max_delta = max(deltas)
            if max_delta <= tolerance_px:
                pairs.append((max_delta, sum(deltas), li, ri))
    pairs.sort()

    used_left: set[int] = set()
    used_right: set[int] = set()
    matched: list[tuple[int, int, int]] = []
    for max_delta, _, li, ri in pairs:
        if li in used_left or ri in used_right:
            continue
        used_left.add(li)
        used_right.add(ri)
        matched.append((li, ri, max_delta))

    return {
        "tolerance_px": tolerance_px,
        "matched": len(matched),
        "left_unmatched": len(left) - len(used_left),
        "right_unmatched": len(right) - len(used_right),
        "max_delta_among_matches": max((row[2] for row in matched), default=0),
        "equivalent": len(used_left) == len(left) and len(used_right) == len(right),
    }


def _compare_detection_files(left_path: Path, right_path: Path) -> dict[str, Any]:
    left_records = _load_detection_records(left_path)
    right_records = _load_detection_records(right_path)
    left = _boxes_from_records(left_records)
    right = _boxes_from_records(right_records)
    lhs = Counter(left)
    rhs = Counter(right)
    common = lhs & rhs
    left_only = lhs - rhs
    right_only = rhs - lhs

    metadata_left = Counter(
        (row["orig_bbox"], row["system_index"], row["staff_index"]) for row in left_records
    )
    metadata_right = Counter(
        (row["orig_bbox"], row["system_index"], row["staff_index"]) for row in right_records
    )
    return {
        "left": str(left_path),
        "right": str(right_path),
        "left_count": len(left),
        "right_count": len(right),
        "exact_common": sum(common.values()),
        "exact_geometry_equal": lhs == rhs,
        "exact_geometry_and_indices_equal": metadata_left == metadata_right,
        "left_only_count": sum(left_only.values()),
        "right_only_count": sum(right_only.values()),
        "left_only_sample": _counter_examples(left_only),
        "right_only_sample": _counter_examples(right_only),
        "tolerance_1px": _tolerant_box_match(left, right, 1),
        "tolerance_2px": _tolerant_box_match(left, right, 2),
    }


def _load_mask(path: Path) -> np.ndarray:
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(path)
    return mask


def _difference_bbox(diff: np.ndarray) -> list[int] | None:
    ys, xs = np.nonzero(diff)
    if len(xs) == 0:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def _compare_mask_files(left_path: Path, right_path: Path) -> dict[str, Any]:
    left = _load_mask(left_path)
    right = _load_mask(right_path)
    base: dict[str, Any] = {
        "left": str(left_path),
        "right": str(right_path),
        "left_file_sha256": _sha256_file(left_path),
        "right_file_sha256": _sha256_file(right_path),
        "left_array_sha256": _sha256_array(left),
        "right_array_sha256": _sha256_array(right),
        "left_shape": list(left.shape),
        "right_shape": list(right.shape),
        "left_nonzero": int(np.count_nonzero(left)),
        "right_nonzero": int(np.count_nonzero(right)),
    }
    if left.shape != right.shape:
        return {
            **base,
            "shape_equal": False,
            "array_exact": False,
            "binary_iou": None,
            "different_pixels": None,
            "difference_bbox": None,
        }

    left_binary = left > 0
    right_binary = right > 0
    xor = np.logical_xor(left_binary, right_binary)
    union = np.logical_or(left_binary, right_binary)
    intersection = np.logical_and(left_binary, right_binary)
    base.update(
        {
            "shape_equal": True,
            "array_exact": bool(np.array_equal(left, right)),
            "binary_exact": bool(np.array_equal(left_binary, right_binary)),
            "binary_iou": (
                float(np.count_nonzero(intersection)) / float(np.count_nonzero(union))
                if np.count_nonzero(union)
                else 1.0
            ),
            "different_pixels": int(np.count_nonzero(left != right)),
            "different_binary_pixels": int(np.count_nonzero(xor)),
            "difference_bbox": _difference_bbox(left != right),
            "row_projection_exact": bool(
                np.array_equal(
                    np.count_nonzero(left_binary, axis=1),
                    np.count_nonzero(right_binary, axis=1),
                )
            ),
            "column_projection_exact": bool(
                np.array_equal(
                    np.count_nonzero(left_binary, axis=0),
                    np.count_nonzero(right_binary, axis=0),
                )
            ),
        }
    )
    return base


def _select_rows(
    ab_report: Mapping[str, Any],
    cases: Sequence[tuple[str, str, str]],
) -> list[tuple[str, dict[str, Any]]]:
    pages = ab_report.get("hybrid_ab", {}).get("pages", [])
    if not isinstance(pages, list):
        raise ValueError("A/B report lacks hybrid_ab.pages")

    by_key = {
        (str(row.get("score")), str(row.get("page"))): dict(row)
        for row in pages
        if isinstance(row, Mapping)
    }
    selected: list[tuple[str, dict[str, Any]]] = []
    for global_page, score, page in cases:
        key = (score, page)
        if key not in by_key:
            raise KeyError(f"Focused case missing from A/B report: {global_page} -> {score}/{page}")
        selected.append((global_page, by_key[key]))
    return selected


def _find_current_request(row: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    b_path = _to_workspace(str(row["b_current_x4_path"]))
    if not b_path.is_file():
        raise FileNotFoundError(b_path)
    support_root = b_path.parents[3]
    request_path = support_root / "current_homr_request.json"
    if not request_path.is_file():
        raise FileNotFoundError(request_path)
    request = _json_load(request_path)
    if not isinstance(request, Mapping):
        raise ValueError(f"Invalid current HOMR request: {request_path}")
    return request_path, dict(request)


def _prepare_working_original(source: Path, output: Path) -> dict[str, Any]:
    image = load_image(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), image):
        raise RuntimeError(f"Failed to write working original: {output}")
    decoded = cv2.imread(str(output), cv2.IMREAD_UNCHANGED)
    if decoded is None:
        raise RuntimeError(f"Failed to decode working original: {output}")
    return {
        "path": str(output),
        "file_sha256": _sha256_file(output),
        "pixel_sha256": _sha256_array(decoded),
        "shape": list(decoded.shape),
    }


def _baseline_artifact_paths(root: Path, image: Path) -> dict[str, Path]:
    page_dir = root / "batch" / image.stem
    return {
        "working_image": page_dir / image.name,
        "detections": page_dir / f"{image.stem}_detections.json",
        "staff_mask": page_dir / f"{image.stem}_staff_mask.png",
        "notehead_mask": page_dir / f"{image.stem}_notehead_mask.png",
    }


def _shared_artifact_paths(root: Path, image: Path) -> dict[str, Path]:
    return {
        "detections": root / f"{image.stem}_detections.json",
        "staff_mask": root / f"{image.stem}_staff_mask.png",
        "notehead_mask": root / f"{image.stem}_notehead_mask.png",
    }


def _save_source_predictions(
    *,
    image: Path,
    output_dir: Path,
    predictions: Sequence[Any],
    notehead_mask: np.ndarray,
    staff_mask: np.ndarray,
    sr_scale: int,
    source_size: tuple[int, int],
) -> dict[str, Path]:
    metrics_predictions = [
        BarlinePrediction(
            pred_bbox=prediction.pred_bbox,
            orig_bbox=tuple(
                int(round(float(coord) / float(sr_scale))) for coord in prediction.orig_bbox
            ),
            system_index=prediction.system_index,
            staff_index=prediction.staff_index,
        )
        for prediction in predictions
    ]
    if sr_scale > 1:
        notehead_source = _resize_mask_to_image_size(notehead_mask, source_size)
        staff_source = _resize_mask_to_image_size(staff_mask, source_size)
    else:
        notehead_source = notehead_mask
        staff_source = staff_mask

    save_homr_results(
        image,
        output_dir,
        metrics_predictions,
        notehead_source,
        staff_source,
    )
    return _shared_artifact_paths(output_dir, image)


def _build_shared_predictor(det_cfg: Mapping[str, Any]) -> tuple[Any, Any, dict[str, Any]]:
    import torch
    import homr
    import homr.main as homr_main
    from homr.music_xml_generator import XmlGeneratorArguments
    from src.homr_eval_scripts.core import heuristics as homr_heuristics
    from src.homr_eval_scripts.core import predictor as homr_predictor
    from src.homr_eval_scripts.core.utils import DEFAULT_TUNING
    from src.pipeline.detection.connector_artifacts import install_homr_connector_artifact_capture
    from src.pipeline.detection.homr_profile_compat import (
        build_processing_config_compat,
        install_current_homr_consumer_compat,
    )

    use_gpu = torch.cuda.is_available()
    compat = install_current_homr_consumer_compat(
        homr_main,
        homr_predictor,
        homr_heuristics,
        use_gpu_inference=use_gpu,
    )
    HomrPredictor = homr_predictor.HomrPredictor
    install_homr_connector_artifact_capture(HomrPredictor)

    config = build_processing_config_compat(
        homr_main.ProcessingConfig,
        enable_debug=bool(det_cfg.get("enable_debug", False)),
        enable_cache=bool(det_cfg.get("enable_cache", True)),
        write_staff_positions=bool(det_cfg.get("write_staff_positions", False)),
        use_gpu_inference=use_gpu,
    )
    tuning = DEFAULT_TUNING.copy()
    tuning.update(
        {
            "barline_min_height_factor": det_cfg.get("barline_min_height_factor", 1.0),
            "barline_max_width_factor": det_cfg.get("barline_max_width_factor", 1.0),
        }
    )

    started = time.perf_counter()
    predictor = HomrPredictor(config, tuning, use_gpu_inference=use_gpu)
    init_s = time.perf_counter() - started
    xml_args = XmlGeneratorArguments(False, None, None)

    model_fingerprints: dict[str, Any] = {}
    try:
        import homr.segmentation.config as segmentation_config

        for name in ("segnet_path_onnx", "segnet_path_onnx_fp16"):
            raw_path = getattr(segmentation_config, name, None)
            if raw_path is not None:
                model_fingerprints[name] = _path_fingerprint(Path(str(raw_path)).resolve())
        model_fingerprints["segmentation_version"] = getattr(
            segmentation_config, "segmentation_version", None
        )
    except Exception as error:  # noqa: BLE001
        model_fingerprints["error"] = f"{type(error).__name__}: {error}"

    provenance = {
        "use_gpu_inference": use_gpu,
        "predictor_init_s": init_s,
        "homr_api_compat": compat,
        "modules": {
            "homr": _module_fingerprint(homr),
            "homr.main": _module_fingerprint(homr_main),
            "core.predictor": _module_fingerprint(homr_predictor),
            "core.heuristics": _module_fingerprint(homr_heuristics),
        },
        "models": model_fingerprints,
    }
    return predictor, xml_args, provenance


def _run_independent_original_baseline(
    *,
    det_cfg: Mapping[str, Any],
    image: Path,
    output_root: Path,
    global_page: str,
) -> tuple[dict[str, Path], float]:
    detector = HybridDetector(
        dict(det_cfg),
        [image],
        f"issue274_same_predictor_{global_page}",
        PROJECT_ROOT,
        dry_run=False,
        skip_existing=False,
        in_memory_images=None,
    )
    started = time.perf_counter()
    detector._run_homr_in_process(output_root, enable_sr=False)  # noqa: SLF001
    elapsed = time.perf_counter() - started
    paths = _baseline_artifact_paths(output_root, image)
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    return paths, elapsed


def _retained_x4_paths(row: Mapping[str, Any], image: Path) -> dict[str, Path]:
    detections = _to_workspace(str(row["b_current_x4_path"]))
    base = detections.parent
    paths = {
        "detections": detections,
        "staff_mask": base / f"{image.stem}_staff_mask.png",
        "notehead_mask": base / f"{image.stem}_notehead_mask.png",
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    return paths


def _compare_artifact_triplet(
    left: Mapping[str, Path],
    right: Mapping[str, Path],
) -> dict[str, Any]:
    return {
        "detections": _compare_detection_files(left["detections"], right["detections"]),
        "staff_mask": _compare_mask_files(left["staff_mask"], right["staff_mask"]),
        "notehead_mask": _compare_mask_files(left["notehead_mask"], right["notehead_mask"]),
    }


def _geometry_gate(compare: Mapping[str, Any]) -> bool:
    return bool(
        compare["detections"]["exact_geometry_equal"]
        and compare["staff_mask"]["binary_exact"]
    )


def _full_support_gate(compare: Mapping[str, Any]) -> bool:
    return bool(
        _geometry_gate(compare)
        and compare["notehead_mask"]["binary_exact"]
    )


def _runtime_provenance() -> dict[str, Any]:
    import torch
    import homr
    import homr.main as homr_main
    from src.homr_eval_scripts.core import predictor as homr_predictor

    return {
        "repo_head": _safe_git_head(),
        "pid": os.getpid(),
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "platform": platform.platform(),
        },
        "packages": {
            "numpy": np.__version__,
            "opencv": cv2.__version__,
            "torch": torch.__version__,
            "onnxruntime": _package_version("onnxruntime-gpu")
            or _package_version("onnxruntime"),
            "homr": _package_version("homr"),
        },
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_device": (
            torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
        ),
        "py_path": os.environ.get("PYTHONPATH"),
        "modules_before_shared_compat": {
            "homr": _module_fingerprint(homr),
            "homr.main": _module_fingerprint(homr_main),
            "core.predictor": _module_fingerprint(homr_predictor),
        },
    }


def _canonical_case(global_page: str) -> tuple[str, str, str]:
    try:
        index = int(global_page.removeprefix("page_"))
    except ValueError as error:
        raise ValueError(f"Invalid canonical page label: {global_page}") from error
    flattened = [
        (score, local_page)
        for score, local_pages in SCORES.items()
        for local_page in local_pages
    ]
    if index < 1 or index > len(flattened):
        raise ValueError(
            f"Canonical page index out of range: {global_page}; expected 1..{len(flattened)}"
        )
    score, local_page = flattened[index - 1]
    return global_page, score, local_page


def _parse_cases(raw_cases: Sequence[str] | None) -> list[tuple[str, str, str]]:
    if not raw_cases:
        return [_canonical_case(global_page) for global_page in DEFAULT_GLOBAL_PAGES]

    parsed: list[tuple[str, str, str]] = []
    for value in raw_cases:
        # Format: page_033=Score/page_002
        if "=" not in value or "/" not in value:
            raise ValueError(
                "--case must be canonical=Score/page_NNN, "
                f"for example page_033=Sibelius-Violin_Concerto-Viola/page_002: {value}"
            )
        global_page, local = value.split("=", 1)
        score, page = local.rsplit("/", 1)
        parsed.append((global_page, score, page))
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ab-report",
        type=Path,
        default=None,
        help="Existing full68 current-x4 vs pinned-x4 Stage-E A/B report. Auto-discovered by default.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(
            "logs/issue274_homr_unification_analysis/"
            "same_predictor_lifetime_01"
        ),
    )
    parser.add_argument(
        "--case",
        action="append",
        default=None,
        help="Override focused case as canonical=Score/page_NNN. Repeatable.",
    )
    args = parser.parse_args()

    output_root = (
        args.output_root.resolve()
        if args.output_root.is_absolute()
        else (PROJECT_ROOT / args.output_root).resolve()
    )
    if output_root.exists() and any(output_root.iterdir()):
        raise SystemExit(
            "Refusing to reuse a non-empty output root because HOMR cache files could "
            f"invalidate the fresh-inference gate: {output_root}"
        )
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "issue274_same_predictor_lifetime_equivalence.json"

    try:
        ab_path = _resolve_ab_report(args.ab_report)
        ab_report = _json_load(ab_path)
        if not isinstance(ab_report, Mapping):
            raise ValueError(f"Invalid A/B report: {ab_path}")
        cases = _parse_cases(args.case)
        selected = _select_rows(ab_report, cases)

        runtime = _runtime_provenance()
        page_results: list[dict[str, Any]] = []

        for global_page, row in selected:
            score = str(row["score"])
            page = str(row["page"])
            request_path, request = _find_current_request(row)
            det_cfg = request.get("detection")
            if not isinstance(det_cfg, Mapping):
                raise ValueError(f"Current-HOMR request lacks detection config: {request_path}")

            image = _to_workspace(str(request["image"]))
            sr_image = _to_workspace(str(request["sr_image"]))
            if not image.is_file():
                raise FileNotFoundError(image)
            if not sr_image.is_file():
                raise FileNotFoundError(sr_image)
            sr_scale = int(det_cfg.get("sr_scale", 2))
            if sr_scale != 4:
                raise ValueError(f"Expected retained x4 request, got sr_scale={sr_scale}")

            original_gray = cv2.imread(str(image), cv2.IMREAD_GRAYSCALE)
            if original_gray is None:
                raise RuntimeError(f"Failed to read original image: {image}")
            source_size = (int(original_gray.shape[1]), int(original_gray.shape[0]))

            page_root = output_root / "pages" / global_page / score / page
            page_root.mkdir(parents=True, exist_ok=True)

            # Baseline: invoke the actual accepted current-original producer.
            independent_root = page_root / "independent_original"
            independent_paths, independent_elapsed_s = _run_independent_original_baseline(
                det_cfg=det_cfg,
                image=image,
                output_root=independent_root,
                global_page=global_page,
            )

            # Shared candidate: exactly one predictor instance, two sequential input domains.
            shared_predictor, xml_args, shared_provenance = _build_shared_predictor(det_cfg)
            shared_id_before = id(shared_predictor)
            shared_original_dir = page_root / "shared_lifetime" / "original"
            shared_x4_dir = page_root / "shared_lifetime" / "x4"
            shared_original_dir.mkdir(parents=True, exist_ok=True)
            shared_x4_dir.mkdir(parents=True, exist_ok=True)

            shared_working = shared_original_dir / image.name
            shared_working_meta = _prepare_working_original(image, shared_working)
            baseline_working_meta = {
                "path": str(independent_paths["working_image"]),
                "file_sha256": _sha256_file(independent_paths["working_image"]),
            }
            baseline_decoded = cv2.imread(
                str(independent_paths["working_image"]),
                cv2.IMREAD_UNCHANGED,
            )
            if baseline_decoded is None:
                raise RuntimeError(
                    f"Failed to decode baseline working image: {independent_paths['working_image']}"
                )
            baseline_working_meta["pixel_sha256"] = _sha256_array(baseline_decoded)
            baseline_working_meta["shape"] = list(baseline_decoded.shape)

            try:
                original_started = time.perf_counter()
                (
                    original_predictions,
                    _,
                    _,
                    original_predictor_runtime_s,
                    original_notehead,
                    original_staff,
                    _,
                    _,
                ) = shared_predictor.predict(
                    shared_working,
                    xml_args,
                    sr_scale=1,
                    image_run_dir=shared_original_dir,
                )
                original_elapsed_s = time.perf_counter() - original_started
                shared_id_after_original = id(shared_predictor)

                shared_original_paths = _save_source_predictions(
                    image=image,
                    output_dir=shared_original_dir,
                    predictions=original_predictions,
                    notehead_mask=original_notehead,
                    staff_mask=original_staff,
                    sr_scale=1,
                    source_size=source_size,
                )

                # Copy the retained x4 file byte-for-byte to an isolated path so an
                # old sibling HOMR .npy cache cannot turn this equivalence gate into
                # a cache replay.  The persisted SR itself is not regenerated.
                shared_x4_input = shared_x4_dir / "input" / sr_image.name
                shared_x4_input.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sr_image, shared_x4_input)
                if _sha256_file(shared_x4_input) != _sha256_file(sr_image):
                    raise RuntimeError("Shared x4 input copy is not byte-identical to retained SR")

                x4_started = time.perf_counter()
                (
                    x4_predictions,
                    _,
                    _,
                    x4_predictor_runtime_s,
                    x4_notehead,
                    x4_staff,
                    _,
                    _,
                ) = shared_predictor.predict(
                    shared_x4_input,
                    xml_args,
                    sr_scale=4,
                    image_run_dir=shared_x4_dir,
                )
                x4_elapsed_s = time.perf_counter() - x4_started
                shared_id_after_x4 = id(shared_predictor)

                shared_x4_paths = _save_source_predictions(
                    image=image,
                    output_dir=shared_x4_dir,
                    predictions=x4_predictions,
                    notehead_mask=x4_notehead,
                    staff_mask=x4_staff,
                    sr_scale=4,
                    source_size=source_size,
                )
            finally:
                cleanup_started = time.perf_counter()
                shared_predictor.cleanup()
                cleanup_s = time.perf_counter() - cleanup_started

            retained_x4_paths = _retained_x4_paths(row, image)
            original_comparison = _compare_artifact_triplet(
                independent_paths,
                shared_original_paths,
            )
            x4_comparison = _compare_artifact_triplet(
                retained_x4_paths,
                shared_x4_paths,
            )

            same_shared_object = (
                shared_id_before == shared_id_after_original == shared_id_after_x4
            )
            page_result = {
                "canonical_page": global_page,
                "score": score,
                "page": page,
                "inputs": {
                    "original": _path_fingerprint(image),
                    "x4": _path_fingerprint(sr_image),
                    "shared_x4_input": _path_fingerprint(shared_x4_input),
                    "shared_x4_input_byte_exact": (
                        _sha256_file(sr_image) == _sha256_file(shared_x4_input)
                    ),
                    "source_size": list(source_size),
                    "current_homr_request": str(request_path),
                    "retained_b_detection": str(retained_x4_paths["detections"]),
                    "baseline_working_image": baseline_working_meta,
                    "shared_working_image": shared_working_meta,
                    "baseline_vs_shared_working_pixel_exact": (
                        baseline_working_meta["pixel_sha256"]
                        == shared_working_meta["pixel_sha256"]
                    ),
                },
                "shared_predictor_lifetime": {
                    "predictor_id_before_original": shared_id_before,
                    "predictor_id_after_original": shared_id_after_original,
                    "predictor_id_after_x4": shared_id_after_x4,
                    "same_object_for_both_calls": same_shared_object,
                    "call_sequence": [
                        {"input": "original", "sr_scale": 1},
                        {"input": "retained_x4", "sr_scale": 4},
                    ],
                    "provenance": shared_provenance,
                },
                "runtime_s": {
                    "independent_original_full_lifecycle": independent_elapsed_s,
                    "shared_predictor_init": shared_provenance["predictor_init_s"],
                    "shared_original_predict_call_elapsed": original_elapsed_s,
                    "shared_original_reported_predictor": original_predictor_runtime_s,
                    "shared_x4_predict_call_elapsed": x4_elapsed_s,
                    "shared_x4_reported_predictor": x4_predictor_runtime_s,
                    "shared_cleanup": cleanup_s,
                },
                "comparisons": {
                    "independent_original_vs_shared_original": original_comparison,
                    "retained_b_x4_vs_shared_after_original": x4_comparison,
                },
                "gates": {
                    "same_shared_predictor_object": same_shared_object,
                    "working_original_pixels_exact": (
                        baseline_working_meta["pixel_sha256"]
                        == shared_working_meta["pixel_sha256"]
                    ),
                    "original_geometry_equivalent": _geometry_gate(original_comparison),
                    "original_full_support_exact": _full_support_gate(original_comparison),
                    "x4_retained_geometry_equivalent": _geometry_gate(x4_comparison),
                    "x4_retained_full_support_exact": _full_support_gate(x4_comparison),
                },
            }
            page_result["gates"]["page_pass"] = all(
                (
                    page_result["gates"]["same_shared_predictor_object"],
                    page_result["gates"]["working_original_pixels_exact"],
                    page_result["gates"]["original_geometry_equivalent"],
                    page_result["gates"]["x4_retained_geometry_equivalent"],
                )
            )
            page_results.append(page_result)

            (page_root / "page_equivalence.json").write_text(
                json.dumps(page_result, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

        all_pass = all(bool(page["gates"]["page_pass"]) for page in page_results)
        report = {
            "schema_version": "issue274.same_predictor_lifetime_equivalence.v1",
            "status": "completed",
            "decision": (
                "same_predictor_lifetime_equivalent_on_focused_pages"
                if all_pass
                else "same_predictor_lifetime_not_yet_equivalent"
            ),
            "scope": {
                "focused_pages": len(page_results),
                "cases": [
                    {
                        "canonical_page": global_page,
                        "score": score,
                        "page": page,
                    }
                    for global_page, score, page in cases
                ],
                "per_page_experiment_inference_passes": 3,
                "per_page_experiment_predictor_instances": 2,
                "candidate_production_inference_passes": 2,
                "candidate_production_predictor_instances": 1,
                "sr_reexecuted": False,
                "omr_dln_reexecuted": False,
                "dense_reexecuted": False,
                "cnn_reexecuted": False,
                "mmr_reexecuted": False,
                "full68_reexecuted": False,
            },
            "architecture_under_test": {
                "keep_distinct_semantic_inputs": [
                    "original_image_current_homr_for_mmr_geometry",
                    "persisted_x4_current_homr_for_semantic_connector_mmr_support",
                ],
                "reuse_boundary": "one page-local current HomrPredictor lifetime",
                "shared_call_order": ["original sr_scale=1", "persisted x4 sr_scale=4"],
                "production_change_allowed_by_this_report": all_pass,
                "note": (
                    "This gate proves lifecycle reuse only. It does not approve merging "
                    "original/x4 semantic artifacts or changing Phase-B index/fallback behavior."
                ),
            },
            "inputs": {
                "ab_report": str(ab_path),
            },
            "runtime": runtime,
            "summary": {
                "all_pages_pass": all_pass,
                "same_object_pages": sum(
                    1 for page in page_results if page["gates"]["same_shared_predictor_object"]
                ),
                "original_geometry_equivalent_pages": sum(
                    1 for page in page_results if page["gates"]["original_geometry_equivalent"]
                ),
                "original_full_support_exact_pages": sum(
                    1 for page in page_results if page["gates"]["original_full_support_exact"]
                ),
                "x4_retained_geometry_equivalent_pages": sum(
                    1 for page in page_results if page["gates"]["x4_retained_geometry_equivalent"]
                ),
                "x4_retained_full_support_exact_pages": sum(
                    1 for page in page_results if page["gates"]["x4_retained_full_support_exact"]
                ),
            },
            "pages": page_results,
        }
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "decision": report["decision"],
                    "summary": report["summary"],
                    "output": str(report_path),
                },
                ensure_ascii=False,
            )
        )
        return 0

    except Exception as error:  # noqa: BLE001
        failure = {
            "schema_version": "issue274.same_predictor_lifetime_equivalence.v1",
            "status": "failed",
            "error_type": type(error).__name__,
            "error": str(error),
        }
        report_path.write_text(
            json.dumps(failure, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(failure, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
