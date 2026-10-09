#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo


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
from src.homr_runtime.transforms import map_pred_to_orig as map_pred_to_orig
from src.homr_runtime.types import DEFAULT_TUNING as DEFAULT_TUNING
from src.homr_runtime.types import STEM_CONTEXT_HEURISTICS as STEM_CONTEXT_HEURISTICS
from src.homr_runtime.types import Box as Box
from src.homr_runtime.types import TransformInfo as TransformInfo
from src.homr_runtime.utils import _redirect_eprint_to_logger as _redirect_eprint_to_logger
from src.homr_runtime.utils import current_jst as current_jst
from src.homr_runtime.utils import ensure_dir as ensure_dir
from src.homr_runtime.utils import eprint as eprint
from src.homr_runtime.utils import timestamp_jst as timestamp_jst


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


def prepare_working_image(image: Path, dest_dir: Path) -> Path:
    ensure_dir(dest_dir)
    dest_path = dest_dir / image.name
    shutil.copy2(image, dest_path)
    return dest_path
