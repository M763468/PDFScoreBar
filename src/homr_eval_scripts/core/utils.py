#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo


import homr.simple_logging

REPO_ROOT = Path(__file__).resolve().parents[2]
if __name__ != "__main__":
    REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
_HOMR_CANDIDATES = (REPO_ROOT / "homr", REPO_ROOT / "external" / "homr")
HOMR_REPO = next((p for p in _HOMR_CANDIDATES if (p / "homr").exists()), _HOMR_CANDIDATES[1])
JST = ZoneInfo("Asia/Tokyo")

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

logger = logging.getLogger("homr_evaluator")


LEFT_MARGIN_FORCE_FP_GT_INDICES: Set[int] = set()
LEFT_MARGIN_FORCE_FP_MAX_WIDTH = 2
STEM_CONTEXT_HEURISTICS = {
    "enabled": True,
    "notehead_proximity_threshold_px": 5,
    "min_overlap_px": 5,
    "max_height_px": 24,
    "max_width_px": 4,
    "staff_crossing_enabled": False,
    "min_staff_crossings": 3,
    "cluster_resolution_dry_run": False,
    "cluster_gap_threshold_px": 15,
    "tight_duplicate_dry_run": False,
    "measure_grid_export": True,
}
Box = Tuple[int, int, int, int]
DEFAULT_TUNING = {
    "barline_min_height_factor": 1.0,
    "barline_max_width_factor": 1.0,
    "enable_end_barline_recovery": False,
    "end_barline_max_x_dist_px": 10,
    "end_barline_min_height_px": 30,
}


def _redirect_eprint_to_logger(*args, **kwargs):
    logger.info(" ".join(map(str, args)))


@dataclass
class TransformInfo:
    original_shape: Tuple[int, int]  # width, height
    crop_box: Tuple[int, int, int, int]  # x, y, w, h
    resize_shape: Tuple[int, int]
    seg_shape: Tuple[int, int]
    resize_scale: Tuple[float, float]
    seg_scale: Tuple[float, float]

    @property
    def total_scale(self) -> Tuple[float, float]:
        return (
            self.resize_scale[0] * self.seg_scale[0],
            self.resize_scale[1] * self.seg_scale[1],
        )


def load_ground_truth_mapping(args: argparse.Namespace) -> Dict[str, Path]:
    mapping: Dict[str, Path] = {}
    for item in args.ground_truth:
        if ":" not in item:
            raise ValueError(
                f"Invalid ground truth mapping '{item}'. Expected format <stem>:<path>."
            )
        stem, path_str = item.split(":", maxsplit=1)
        path = Path(path_str).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Ground truth file not found: {path}")
        mapping[stem] = path
    return mapping


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def git_info() -> Dict[str, Optional[str]]:
    def run_git(cmd: Sequence[str]) -> Optional[str]:
        try:
            result = subprocess.run(
                cmd,
                cwd=REPO_ROOT,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None
        return result.stdout.strip()

    return {
        "commit": run_git(["git", "rev-parse", "HEAD"]),
        "branch": run_git(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "status": run_git(["git", "status", "-sb"]),
    }


def current_jst() -> datetime:
    return datetime.now(JST)


def timestamp_jst() -> str:
    return current_jst().strftime("%Y-%m-%dT%H:%M:%S") + "JST"


def choose_run_id(args: argparse.Namespace) -> str:
    if args.force_run_id:
        return args.force_run_id
    base = current_jst().strftime("%Y%m%dT%H%M%S") + "JST"
    if args.run_tag:
        return f"{base}_{args.run_tag}"
    return base


def sanitise_images(images: Iterable[str]) -> List[Path]:
    resolved = []
    for item in images:
        path = Path(item).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Image path not found: {path}")
        resolved.append(path)
    return resolved


def map_pred_to_orig(
    box: Tuple[int, int, int, int], transform: TransformInfo
) -> Tuple[int, int, int, int]:
    crop_x, crop_y, *_ = transform.crop_box
    scale_x, scale_y = transform.total_scale
    inv_scale_x = 1.0 / scale_x if scale_x != 0 else 0.0
    inv_scale_y = 1.0 / scale_y if scale_y != 0 else 0.0
    orig_w, orig_h = transform.original_shape

    x1, y1, x2, y2 = box
    x1_orig = int(round(x1 * inv_scale_x + crop_x))
    y1_orig = int(round(y1 * inv_scale_y + crop_y))
    x2_orig = int(round(x2 * inv_scale_x + crop_x))
    y2_orig = int(round(y2 * inv_scale_y + crop_y))

    x1_clamped = max(0, min(orig_w - 1, x1_orig))
    y1_clamped = max(0, min(orig_h - 1, y1_orig))
    x2_clamped = max(0, min(orig_w - 1, x2_orig))
    y2_clamped = max(0, min(orig_h - 1, y2_orig))

    if x2_clamped < x1_clamped:
        x2_clamped = x1_clamped
    if y2_clamped < y1_clamped:
        y2_clamped = y1_clamped

    return (x1_clamped, y1_clamped, x2_clamped, y2_clamped)


def prepare_working_image(image: Path, dest_dir: Path) -> Path:
    ensure_dir(dest_dir)
    dest_path = dest_dir / image.name
    shutil.copy2(image, dest_path)
    return dest_path


homr.simple_logging.eprint = _redirect_eprint_to_logger
eprint = _redirect_eprint_to_logger
