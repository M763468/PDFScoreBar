"""Stable connector-semantic artifact contract shared by detection and numbering."""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

CONNECTOR_SYMBOLS_SUFFIX = "_connector_symbols.png"
CONNECTOR_BRACE_DOT_SUFFIX = "_connector_brace_dot.png"
_STAFF_MASK_SUFFIXES = (
    "_proxy_debug_3_staff.png",
    "_debug_3_staff.png",
    "_staff_mask.png",
)


def connector_mask_paths(image_run_dir: Path | str, stem: str) -> dict[str, Path]:
    """Return stable connector-mask paths for one HOMR page output."""

    root = Path(image_run_dir)
    return {
        "symbols": root / f"{stem}{CONNECTOR_SYMBOLS_SUFFIX}",
        "brace_dot": root / f"{stem}{CONNECTOR_BRACE_DOT_SUFFIX}",
    }


def connector_mask_paths_for_staff_mask(
    staff_mask_path: Path | str,
) -> dict[str, Path] | None:
    """Resolve stable connector masks stored beside a HOMR staff mask.

    This is the strict producer-side sibling contract. Do not broaden it: the
    skip-existing completeness guard relies on this function requiring the
    semantic pair to be published beside the corresponding stable staff mask.
    """

    staff_path = Path(staff_mask_path)
    stem = _staff_mask_stem(staff_path.name)
    if stem is None:
        return None

    paths = connector_mask_paths(staff_path.parent, stem)
    if not all(path.is_file() for path in paths.values()):
        return None
    return paths


def connector_mask_paths_for_numbering(
    staff_mask_path: Path | str,
) -> dict[str, Path] | None:
    """Resolve connector semantics for a numbering consumer.

    Numbering may intentionally use a Proxy/SR debug staff mask for stable staff
    geometry while the current-HOMR semantic connector masks live under the same
    hybrid run's ``current_support`` tree. Keep those two roles independent:
    first accept a complete sibling pair, then look only in the nearest hybrid
    run's ``current_support`` subtree for the same page stem.
    """

    staff_path = Path(staff_mask_path)
    sibling_paths = connector_mask_paths_for_staff_mask(staff_path)
    if sibling_paths is not None:
        return sibling_paths

    stem = _staff_mask_stem(staff_path.name)
    if stem is None:
        return None

    for ancestor in staff_path.parents:
        support_root = ancestor / "current_support"
        if not support_root.is_dir():
            continue

        candidates: list[dict[str, Path]] = []
        for symbols_path in support_root.rglob(f"{stem}{CONNECTOR_SYMBOLS_SUFFIX}"):
            paths = connector_mask_paths(symbols_path.parent, stem)
            if all(path.is_file() for path in paths.values()):
                candidates.append(paths)

        unique = {
            (str(paths["symbols"].resolve()), str(paths["brace_dot"].resolve())): paths
            for paths in candidates
        }
        if len(unique) > 1:
            raise RuntimeError(
                f"Ambiguous connector semantic pairs for {stem} under {support_root}"
            )
        if unique:
            return next(iter(unique.values()))
        return None

    return None


def connector_masks_complete(
    image_run_dir: Path | str,
    stems: Sequence[str],
) -> bool:
    """Return whether every requested HOMR page has a complete semantic pair."""

    root = Path(image_run_dir)
    for stem in stems:
        staff_path = root / "batch" / stem / f"{stem}_staff_mask.png"
        if not staff_path.is_file() or connector_mask_paths_for_staff_mask(staff_path) is None:
            return False
    return True


def invalidate_connector_masks(image_run_dir: Path | str, stem: str) -> None:
    """Remove a previously published pair so stale semantics cannot be reused."""

    for path in connector_mask_paths(image_run_dir, stem).values():
        path.unlink(missing_ok=True)


def write_connector_masks(
    image_run_dir: Path,
    stem: str,
    masks: Mapping[str, np.ndarray],
) -> dict[str, Path] | None:
    """Persist captured HOMR semantic masks with stable production filenames."""

    image_run_dir.mkdir(parents=True, exist_ok=True)
    paths = connector_mask_paths(image_run_dir, stem)
    invalidate_connector_masks(image_run_dir, stem)

    required = {"symbols", "brace_dot"}
    if not required.issubset(masks):
        return None

    temporary_paths: dict[str, Path] = {}
    try:
        for key, path in paths.items():
            mask = _as_binary_u8(masks[key])
            temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp.png")
            temporary_paths[key] = temporary_path
            if not cv2.imwrite(str(temporary_path), mask):
                raise RuntimeError(f"Failed to write connector mask: {temporary_path}")

        for key, path in paths.items():
            os.replace(temporary_paths[key], path)
    except Exception:
        for temporary_path in temporary_paths.values():
            temporary_path.unlink(missing_ok=True)
        invalidate_connector_masks(image_run_dir, stem)
        raise

    return paths


def describe_connector_artifacts(staff_mask_path: Path | str) -> dict[str, Any]:
    """Describe the connector source actually available to numbering."""

    paths = connector_mask_paths_for_numbering(staff_mask_path)
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


def _staff_mask_stem(filename: str) -> str | None:
    for suffix in _STAFF_MASK_SUFFIXES:
        if filename.endswith(suffix):
            return filename[: -len(suffix)]
    return None


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
