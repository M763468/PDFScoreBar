"""Stable connector-semantic artifact contract shared by detection and numbering."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

CONNECTOR_SYMBOLS_SUFFIX = "_connector_symbols.png"
CONNECTOR_BRACE_DOT_SUFFIX = "_connector_brace_dot.png"
NON_SCORE_PAGE_MARKER_SUFFIX = "_non_score_page.json"
NON_SCORE_PAGE_MARKER_SCHEMA = "pipeline.non_score_page.v1"
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

    A discovered ``current_support`` subtree is a declared semantic contract. If
    that subtree lacks a complete pair for this page, fail instead of silently
    changing connector evidence to the page-image fallback.
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
        if _declared_non_score_page(support_root, stem):
            # Current x4 support classified this page as a cover/blank page from
            # HOMR's segmentation evidence (#532). It has no staves, so there is no
            # connector semantics to read; this is not a missing-artifact fallback.
            return None
        raise RuntimeError(
            f"Current support exists but connector semantic pair is missing for {stem} "
            f"under {support_root}"
        )

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


def non_score_page_marker_path(image_run_dir: Path | str, stem: str) -> Path:
    """Path of the marker that declares one HOMR page a non-score page (#532)."""

    return Path(image_run_dir) / f"{stem}{NON_SCORE_PAGE_MARKER_SUFFIX}"


def invalidate_non_score_page_marker(image_run_dir: Path | str, stem: str) -> None:
    non_score_page_marker_path(image_run_dir, stem).unlink(missing_ok=True)


def write_non_score_page_marker(
    image_run_dir: Path | str,
    stem: str,
    *,
    image: Path | str,
    reason: str,
    evidence: Mapping[str, Any],
    thresholds: Mapping[str, Any],
) -> Path:
    """Atomically publish the non-score-page declaration beside the HOMR outputs.

    The marker replaces the connector pair for this page only. Its presence must
    never be inferred from a missing pair; only the current HOMR worker writes it,
    after classifying the recorded segmentation evidence.
    """

    path = non_score_page_marker_path(image_run_dir, stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": NON_SCORE_PAGE_MARKER_SCHEMA,
        "page_content": "non_score_page",
        "stem": stem,
        "image": str(image),
        "homr_reason": reason,
        "evidence": dict(evidence),
        "thresholds": dict(thresholds),
    }
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return path


def read_non_score_page_marker(path: Path | str, *, stem: str) -> dict[str, Any]:
    """Load and validate a non-score-page marker; raise when it is not usable."""

    marker_path = Path(path)
    payload = json.loads(marker_path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, Mapping)
        or payload.get("schema_version") != NON_SCORE_PAGE_MARKER_SCHEMA
        or payload.get("page_content") != "non_score_page"
        or payload.get("stem") != stem
        or not isinstance(payload.get("evidence"), Mapping)
    ):
        raise ValueError(f"Invalid non-score-page marker for {stem}: {marker_path}")
    return dict(payload)


def _declared_non_score_page(support_root: Path, stem: str) -> bool:
    markers = {
        str(path.resolve()): path
        for path in support_root.rglob(f"{stem}{NON_SCORE_PAGE_MARKER_SUFFIX}")
        if path.is_file()
    }
    if len(markers) > 1:
        raise RuntimeError(f"Ambiguous non-score-page markers for {stem} under {support_root}")
    if not markers:
        return False
    marker = next(iter(markers.values()))
    read_non_score_page_marker(marker, stem=stem)
    partial = [
        str(path) for path in connector_mask_paths(marker.parent, stem).values() if path.is_file()
    ]
    if partial:
        raise RuntimeError(
            f"Non-score-page marker for {stem} conflicts with connector artifacts: {partial}"
        )
    return True


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
