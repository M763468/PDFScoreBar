"""Stable connector-semantic artifact contract shared by detection and numbering."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

CONNECTOR_SYMBOLS_SUFFIX = "_connector_symbols.png"
CONNECTOR_BRACE_DOT_SUFFIX = "_connector_brace_dot.png"


def connector_mask_paths_for_staff_mask(
    staff_mask_path: Path | str,
) -> dict[str, Path] | None:
    """Resolve stable connector masks stored beside a HOMR staff mask."""

    staff_path = Path(staff_mask_path)
    suffix = "_staff_mask.png"
    if not staff_path.name.endswith(suffix):
        return None

    stem = staff_path.name[: -len(suffix)]
    paths = {
        "symbols": staff_path.with_name(f"{stem}{CONNECTOR_SYMBOLS_SUFFIX}"),
        "brace_dot": staff_path.with_name(f"{stem}{CONNECTOR_BRACE_DOT_SUFFIX}"),
    }
    if not all(path.is_file() for path in paths.values()):
        return None
    return paths


def write_connector_masks(
    image_run_dir: Path,
    stem: str,
    masks: Mapping[str, np.ndarray],
) -> dict[str, Path] | None:
    """Persist captured HOMR semantic masks with stable production filenames."""

    required = {"symbols", "brace_dot"}
    if not required.issubset(masks):
        return None

    image_run_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "symbols": image_run_dir / f"{stem}{CONNECTOR_SYMBOLS_SUFFIX}",
        "brace_dot": image_run_dir / f"{stem}{CONNECTOR_BRACE_DOT_SUFFIX}",
    }
    for key, path in paths.items():
        mask = _as_binary_u8(masks[key])
        if not cv2.imwrite(str(path), mask):
            raise RuntimeError(f"Failed to write connector mask: {path}")
    return paths


def describe_connector_artifacts(staff_mask_path: Path | str) -> dict[str, Any]:
    """Describe the connector source used by numbering for manifest provenance."""

    paths = connector_mask_paths_for_staff_mask(staff_mask_path)
    if paths is None:
        return {
            "source": "page_image_ink",
            "coordinate_space": "page_image",
            "include_absent_pairs": False,
            "masks": {},
        }

    mask_descriptions: dict[str, Any] = {}
    for key, path in paths.items():
        mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            raise RuntimeError(f"Failed to read connector mask: {path}")
        mask_descriptions[key] = {
            "path": str(path),
            "sha256": _sha256(path),
            "shape": [int(mask.shape[0]), int(mask.shape[1])],
        }

    return {
        "source": "proxy_symbol_layers",
        "coordinate_space": "homr_segmentation_mask",
        "include_absent_pairs": True,
        "masks": mask_descriptions,
    }


def _as_binary_u8(mask: np.ndarray) -> np.ndarray:
    array = np.asarray(mask)
    if array.ndim != 2:
        raise ValueError(f"Connector mask must be 2-D, got shape {array.shape}")
    return (array > 0).astype(np.uint8) * 255


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
