#!/usr/bin/env python3
"""Run the oemer pipeline and emit barline detections/metrics for evaluation."""

from __future__ import annotations

import importlib.util
import functools
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import cv2

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover (Python <3.9)
    from backports.zoneinfo import ZoneInfo  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

OEMER_SRC = REPO_ROOT / "src/archive/oemer/oemer_src"
if str(OEMER_SRC) not in sys.path:
    sys.path.insert(0, str(OEMER_SRC))

from oemer import layers  # type: ignore
from oemer.ete import clear_data, extract, teaser  # type: ignore
from oemer import symbol_extraction as oemer_symbol_extraction  # type: ignore

from common.barline_evaluation import (
    BarlineMatch,
    BarlineSoftMatch,
    greedy_barline_match,
)
from common.thin_barline_finder import detect_thin_vertical_runs

JST = ZoneInfo("Asia/Tokyo")
DEFAULT_IOU = 0.5


@dataclass
class ImageMetrics:
    image: str
    num_predictions: int
    num_ground_truth: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    matches: List[BarlineMatch] = field(default_factory=list)
    soft_matches: List[BarlineSoftMatch] = field(default_factory=list)


@dataclass
class AggregateMetrics:
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float


@dataclass
class BarlinePrediction:
    orig_bbox: Tuple[int, int, int, int]


DEFAULT_IMAGE_DIR = REPO_ROOT / "data/evaluation/images"
DEFAULT_GROUND_TRUTH = REPO_ROOT / "data/evaluation/annotations/page_003/boxes_sorted.json"
DEFAULT_TARGET_PAGES = [3]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "logs/oemer_eval"
DEFAULT_RUN_PREFIX = "baseline"


def resolve_repo_path(value: Optional[str], *, default: Path) -> Path:
    if not value:
        return default
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate


def timestamp_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%SJST")


def run_id(prefix: str) -> str:
    return datetime.now(JST).strftime("%Y%m%dT%H%M%S%Z_" + prefix)


def load_ground_truth(path: Path) -> List[Tuple[int, int, int, int]]:
    records = json.loads(path.read_text())
    boxes: List[Tuple[int, int, int, int]] = []
    for record in records:
        loc = record.get("barline_location")
        if not loc or len(loc) != 4:
            continue
        boxes.append(tuple(int(v) for v in loc))
    return boxes


def extract_barline_boxes() -> List[Tuple[int, int, int, int]]:
    barlines = layers.get_layer("barlines")
    boxes: List[Tuple[int, int, int, int]] = []
    for barline in barlines:
        bbox = getattr(barline, "bbox", None)
        if bbox is None:
            continue
        boxes.append(tuple(int(v) for v in bbox))
    boxes.sort(key=lambda item: (item[1], item[0]))
    return boxes


def save_overlay(
    image_path: Path,
    boxes: Sequence[Tuple[int, int, int, int]],
    output_path: Path,
    *,
    matches: Optional[Sequence[BarlineMatch]] = None,
    soft_matches: Optional[Sequence[BarlineSoftMatch]] = None,
    false_positive_indices: Optional[Sequence[int]] = None,
) -> None:
    base = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if base is None:
        raise RuntimeError(f"Failed to load base image: {source_path}")
    overlay = base.copy()

    matched_pred_indices = {m.pred_index for m in matches} if matches else set()
    soft_lookup = {sm.pred_index: sm for sm in soft_matches} if soft_matches else {}
    fp_indices = set(false_positive_indices or [])

    for idx, (x1, y1, x2, y2) in enumerate(boxes):
        if idx in matched_pred_indices:
            color = (0, 255, 0)
            label = f"TP#{idx}"
        elif idx in soft_lookup:
            reason = soft_lookup[idx].reason
            marker = "dup" if reason == "duplicate" else "rep"
            color = (255, 165, 0)
            label = f"OK#{idx}:{marker}"
        elif fp_indices:
            color = (0, 0, 255)
            label = f"FP#{idx}"
        else:
            color = (0, 0, 255)
            label = f"P#{idx}"
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            overlay,
            label,
            (x1, max(12, y1 - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
            cv2.LINE_AA,
        )

    blended = cv2.addWeighted(overlay, 0.65, base, 0.35, 0.0)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), blended):
        raise RuntimeError(f"Failed to write overlay: {output_path}")


def compute_metrics(
    predictions: Sequence[BarlinePrediction],
    ground_truth: Sequence[Tuple[int, int, int, int]],
    threshold: float,
) -> Tuple[ImageMetrics, BarlineMatchResult]:
    boxes = [pred.orig_bbox for pred in predictions]
    match_result = greedy_barline_match(boxes, ground_truth, iou_threshold=threshold)
    tp = len(match_result.matches)
    fp = len(match_result.false_positive_indices)
    fn = len(match_result.false_negative_indices)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return ImageMetrics(
        image="",
        num_predictions=len(boxes),
        num_ground_truth=len(ground_truth),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        matches=match_result.matches,
        soft_matches=match_result.soft_matches,
    ), match_result


def aggregate_metrics(per_image: Sequence[ImageMetrics]) -> AggregateMetrics:
    tp = sum(metric.true_positives for metric in per_image)
    fp = sum(metric.false_positives for metric in per_image)
    fn = sum(metric.false_negatives for metric in per_image)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return AggregateMetrics(tp, fp, fn, precision, recall, f1)


def main() -> None:
    output_root = resolve_repo_path(os.environ.get("OEMER_OUTPUT_ROOT"), default=DEFAULT_OUTPUT_ROOT)
    run_prefix = os.environ.get("OEMER_RUN_PREFIX", DEFAULT_RUN_PREFIX)
    force_run_id = os.environ.get("OEMER_FORCE_RUN_ID")

    image_dir = resolve_repo_path(os.environ.get("OEMER_IMAGE_DIR"), default=DEFAULT_IMAGE_DIR)
    gt_path = resolve_repo_path(os.environ.get("OEMER_GROUND_TRUTH"), default=DEFAULT_GROUND_TRUTH)

    target_pages_env = os.environ.get("OEMER_TARGET_PAGES")
    if target_pages_env:
        parsed_pages = []
        for token in target_pages_env.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                parsed_pages.append(int(token))
            except ValueError as exc:
                raise ValueError(f"Invalid OEMER_TARGET_PAGES entry: {token}") from exc
        if not parsed_pages:
            raise ValueError("OEMER_TARGET_PAGES was provided but no valid page indices were parsed")
        target_pages = sorted(set(parsed_pages))
    else:
        target_pages = list(DEFAULT_TARGET_PAGES)

    run_id_value = force_run_id or run_id(run_prefix)
    run_root = output_root / run_id_value
    run_root.mkdir(parents=True, exist_ok=True)

    provider_dump_dir = run_root / "runtime"
    profile_dir = run_root / "ort_profiles"
    detections_dir = run_root / "detections"
    overlays_dir = run_root / "overlays"
    provider_dump_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)
    detections_dir.mkdir(parents=True, exist_ok=True)
    overlays_dir.mkdir(parents=True, exist_ok=True)

    prev_env = {}
    env_updates = {
        "OEMER_ORT_PROFILE_DIR": str(profile_dir),
        "OEMER_PROVIDER_DUMP_DIR": str(provider_dump_dir),
    }
    optional_defaults = {
        "OEMER_LOG_PROVIDERS": "1",
        "OEMER_CUDNN_MAX_WORKSPACE": "1",
        "OEMER_CUDNN_CONV_ALGO_SEARCH": "EXHAUSTIVE",
    }

    def set_env(key: str, value: str, *, overwrite: bool = True) -> None:
        if key not in prev_env:
            prev_env[key] = os.environ.get(key)
        if overwrite or key not in os.environ:
            os.environ[key] = value

    set_env("OEMER_ORT_PROFILE_DIR", str(profile_dir))
    set_env("OEMER_PROVIDER_DUMP_DIR", str(provider_dump_dir))
    set_env("OEMER_LOG_PROVIDERS", "1", overwrite=False)
    set_env("OEMER_CUDNN_MAX_WORKSPACE", "1", overwrite=False)
    set_env("OEMER_CUDNN_CONV_ALGO_SEARCH", "EXHAUSTIVE", overwrite=False)

    tracked_keys = set(env_updates.keys()) | set(optional_defaults.keys())
    runtime_env = {
        "OEMER_OUTPUT_ROOT": str(output_root),
        "OEMER_RUN_PREFIX": run_prefix,
        "OEMER_IMAGE_DIR": str(image_dir),
        "OEMER_GROUND_TRUTH": str(gt_path),
        "OEMER_TARGET_PAGES": ",".join(str(p) for p in target_pages),
    }
    if force_run_id:
        runtime_env["OEMER_FORCE_RUN_ID"] = force_run_id
    for key in sorted(tracked_keys):
        runtime_env[key] = os.environ.get(key)
    override_keys = ["OEMER_IMAGE_OVERRIDE"] + [f"OEMER_IMAGE_OVERRIDE_PAGE_{page}" for page in target_pages]
    for key in override_keys:
        value = os.environ.get(key)
        if value:
            runtime_env[key] = value

    original_symbol_extract = None
    min_barline_ratio_env = os.environ.get("OEMER_MIN_BARLINE_UNIT_RATIO")
    if min_barline_ratio_env:
        runtime_env["OEMER_MIN_BARLINE_UNIT_RATIO"] = min_barline_ratio_env
    if min_barline_ratio_env:
        try:
            min_barline_ratio = float(min_barline_ratio_env)
            original_symbol_extract = oemer_symbol_extraction.extract
            oemer_symbol_extraction.extract = functools.partial(
                original_symbol_extract,
                min_barline_h_unit_ratio=min_barline_ratio,
            )
        except ValueError:
            original_symbol_extract = None

    processed_images = []

    try:
        gt_boxes = load_ground_truth(gt_path)
        per_image_metrics: List[ImageMetrics] = []

        for page in target_pages:
            override_path = os.environ.get(f"OEMER_IMAGE_OVERRIDE_PAGE_{page}") or os.environ.get("OEMER_IMAGE_OVERRIDE")
            source_path = Path(override_path) if override_path else image_dir / f"page_{page}.png"
            if not source_path.exists():
                raise FileNotFoundError(f"Image not found: {source_path}")

            canonical_name = f"page_{page}"
            stem = source_path.stem
            if stem.startswith('page_'):
                suffix = stem.split('page_', 1)[1]
                if suffix.isdigit() and len(suffix) == 3:
                    canonical_name = f"page_{suffix}"
                else:
                    canonical_name = stem
            page_dir = run_root / canonical_name
            page_dir.mkdir(parents=True, exist_ok=True)
            processed_images.append(str(source_path))

            clear_data()
            args = type("Args", (), {
                "img_path": str(source_path),
                "output_path": str(page_dir / f"{canonical_name}.musicxml"),
                "use_tf": False,
                "save_cache": False,
                "without_deskew": False,
            })()

            extract_error = None
            musicxml_path = Path(args.output_path)
            try:
                extract_result = extract(args)
                if extract_result:
                    musicxml_path = Path(extract_result)
            except Exception as exc:
                extract_error = exc
                (page_dir / "extract_error.txt").write_text(f"{type(exc).__name__}: {exc}\n")
            else:
                try:
                    teaser_image = teaser()
                    teaser_path = page_dir / f"{canonical_name}_teaser.png"
                    teaser_image.save(teaser_path)
                except Exception as teaser_exc:
                    (page_dir / "teaser_error.txt").write_text(f"{type(teaser_exc).__name__}: {teaser_exc}\n")

            try:
                boxes = extract_barline_boxes()
            except Exception as box_exc:
                boxes = []
                (page_dir / "barline_extract_error.txt").write_text(f"{type(box_exc).__name__}: {box_exc}\n")

            base_image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
            if base_image is None:
                raise RuntimeError(f"Failed to load base image: {source_path}")

            scale_x = scale_y = 1.0
            try:
                processed_image = layers.get_layer("original_image")
                proc_h, proc_w = processed_image.shape[:2]
                if proc_w and proc_h:
                    base_h, base_w = base_image.shape[:2]
                    scale_x = base_w / float(proc_w)
                    scale_y = base_h / float(proc_h)
                else:
                    processed_image = None
            except Exception:
                processed_image = None

            scaled_boxes = [
                (
                    int(round(x1 * scale_x)),
                    int(round(y1 * scale_y)),
                    int(round(x2 * scale_x)),
                    int(round(y2 * scale_y)),
                )
                for (x1, y1, x2, y2) in boxes
            ]

            predictions = [BarlinePrediction(orig_bbox=box) for box in scaled_boxes]

            def _centre(box: Tuple[int, int, int, int]) -> Tuple[float, float]:
                x1, y1, x2, y2 = box
                return (x1 + x2) / 2.0, (y1 + y2) / 2.0

            extra_boxes = detect_thin_vertical_runs(source_path, [p.orig_bbox for p in predictions])
            for extra in extra_boxes:
                box_tuple = (int(extra[0]), int(extra[1]), int(extra[2]), int(extra[3]))
                cx_extra, cy_extra = _centre(box_tuple)
                replaced = False
                for idx, pred in enumerate(predictions):
                    cx_existing, cy_existing = _centre(pred.orig_bbox)
                    if abs(cx_existing - cx_extra) <= 2:
                        if abs(cy_existing - cy_extra) > 4:
                            predictions[idx] = BarlinePrediction(orig_bbox=box_tuple)
                            scaled_boxes[idx] = box_tuple
                            boxes[idx] = box_tuple
                        replaced = True
                        break
                if not replaced:
                    predictions.append(BarlinePrediction(orig_bbox=box_tuple))
                    scaled_boxes.append(box_tuple)
                    boxes.append(box_tuple)

            meta = {
                "detector": "oemer",
                "image": str(source_path),
                "timestamp": timestamp_jst(),
                "scale": {"x": scale_x, "y": scale_y},
            }
            if extra_boxes:
                meta["heuristic_barlines"] = len(extra_boxes)
            if extract_error:
                meta["extract_error"] = f"{type(extract_error).__name__}: {extract_error}"
            if override_path:
                meta["image_override"] = override_path

            detection_payload = {
                "predictions": [
                    {
                        "barline_location": list(scaled),
                        "source_bbox": list(raw),
                    }
                    for scaled, raw in zip(scaled_boxes, boxes)
                ],
                "meta": meta,
            }
            detection_path = page_dir / f"{canonical_name}_detections.json"
            detection_json = json.dumps(detection_payload, indent=2, ensure_ascii=False)
            detection_path.write_text(detection_json)
            (detections_dir / f"{canonical_name}.json").write_text(detection_json)

            metric, match_result = compute_metrics(predictions, gt_boxes, DEFAULT_IOU)
            metric.image = canonical_name
            per_image_metrics.append(metric)

            overlay_path = page_dir / f"{canonical_name}_overlay.png"
            save_overlay(
                source_path,
                scaled_boxes,
                overlay_path,
                matches=match_result.matches,
                soft_matches=match_result.soft_matches,
                false_positive_indices=match_result.false_positive_indices,
            )
            shutil.copyfile(overlay_path, overlays_dir / f"{canonical_name}.png")

            if musicxml_path.exists() and musicxml_path.parent != page_dir:
                target_path = page_dir / musicxml_path.name
                target_path.write_bytes(musicxml_path.read_bytes())

        aggregate = aggregate_metrics(per_image_metrics)
        payload = {
            "run_id": run_root.name,
            "timestamp": timestamp_jst(),
            "images": [
                {
                    **asdict(metric),
                    "matches": [asdict(match) for match in metric.matches],
                    "soft_matches": [asdict(sm) for sm in metric.soft_matches],
                }
                for metric in per_image_metrics
            ],
            "aggregate": asdict(aggregate),
            "extra": {
                "detector": "oemer",
                "ground_truth": {metric.image: str(gt_path) for metric in per_image_metrics},
                "iou_threshold": DEFAULT_IOU,
            },
        }
        (run_root / "metrics.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))

        csv_lines = [
            "image,num_predictions,num_ground_truth,true_positives,false_positives,false_negatives,precision,recall,f1",
        ]
        for metric in per_image_metrics:
            csv_lines.append(
                f"{metric.image},{metric.num_predictions},{metric.num_ground_truth},{metric.true_positives},{metric.false_positives},{metric.false_negatives},{metric.precision:.6f},{metric.recall:.6f},{metric.f1:.6f}"
            )
        csv_lines.append(
            f"aggregate,-,-,{aggregate.true_positives},{aggregate.false_positives},{aggregate.false_negatives},{aggregate.precision:.6f},{aggregate.recall:.6f},{aggregate.f1:.6f}"
        )
        (run_root / "metrics.csv").write_text("\n".join(csv_lines) + "\n")

        summary = [
            "# oemer Evaluation Run",
            f"- Run ID: {run_root.name}",
            f"- Timestamp: {timestamp_jst()}",
            f"- Images processed: {len(per_image_metrics)}",
            f"- Ground truth: {gt_path}",
            "",
            "Outputs are stored per image under this directory.",
        ]
        (run_root / "README.md").write_text("\n".join(summary) + "\n")

        params = {
            "images": processed_images,
            "ground_truth": str(gt_path),
            "target_pages": target_pages,
            "iou_threshold": DEFAULT_IOU,
            "provider_dump_dir": str(provider_dump_dir),
            "profile_dir": str(profile_dir),
            "output_root": str(output_root),
            "run_prefix": run_prefix,
            "force_run_id": force_run_id,
            "runtime_env": runtime_env,
        }
        (run_root / "params.json").write_text(json.dumps(params, indent=2, ensure_ascii=False))

        git_commit = git_branch = git_status = None
        try:
            git_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except subprocess.CalledProcessError:
            pass
        try:
            git_branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except subprocess.CalledProcessError:
            pass
        try:
            git_status = subprocess.run(
                ["git", "status", "-sb"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except subprocess.CalledProcessError:
            pass

        run_config = {
            "run_id": run_root.name,
            "timestamp": timestamp_jst(),
            "command": "python src/archive/oemer/run_omerer.py",
            "images": processed_images,
            "ground_truth": str(gt_path),
            "target_pages": target_pages,
            "provider_dump_dir": str(provider_dump_dir),
            "ort_profile_dir": str(profile_dir),
            "output_root": str(output_root),
            "run_prefix": run_prefix,
            "force_run_id": force_run_id,
            "runtime_env": runtime_env,
            "git": {
                "commit": git_commit,
                "branch": git_branch,
                "status": git_status,
            },
        }
        (run_root / "run_config.json").write_text(json.dumps(run_config, indent=2, ensure_ascii=False))

        print(f"oemer evaluation artifacts written to {run_root}")
    finally:
        if original_symbol_extract is not None:
            oemer_symbol_extraction.extract = original_symbol_extract
        for key, value in prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    main()
