"""Review-profile manual correction handoff helpers.

This module adapts the review-profile handoff contract to the current manual
correction GUI without changing the production detector/MMR/numbering path.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from src.pipeline.steps.manual_corrections import (
    merge_barline_overrides,
    merge_measure_overrides,
)

HandoffMode = Literal["base_v1", "issue229_smoke_strict"]

GUI_OUTPUT_KEYS = {
    "mmr_measure_span": "mmr_measure_spans.json",
    "measure_construction": "measure_construction_overrides.json",
    "barline_construction": "barline_construction_overrides.json",
}

STAGING_TO_CANONICAL_FILENAMES = {
    "mmr_measure_span": "mmr_measure_spans.json",
    "measure_construction": "measure_construction_overrides.json",
    "barline_construction": "barline_construction_overrides.json",
}

_REQUIRED_TOP_LEVEL_FIELDS = ("schema_version", "pages")
_REQUIRED_PAGE_FIELDS = ("page_id", "page_number", "source_image", "numbering_final")
_STRICT_PAGE_FIELDS = ("review_overlay", "mmr_overrides", "barlines_review")


class ManualCorrectionHandoffError(ValueError):
    """Raised when a manual-correction handoff is unsafe or malformed."""


def load_manual_correction_handoff(path: str | Path) -> Dict[str, Any]:
    """Load a ``review/manual_correction_input.json`` handoff file."""

    handoff_path = Path(path)
    with handoff_path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ManualCorrectionHandoffError("manual correction handoff must be a JSON object")
    return payload


def _is_missing(value: Any) -> bool:
    return value is None or value == ""


def _as_page_number(value: Any, *, page_id: str) -> int:
    try:
        page_number = int(value)
    except (TypeError, ValueError) as exc:
        raise ManualCorrectionHandoffError(f"{page_id}: page_number must be an integer") from exc
    if page_number < 1:
        raise ManualCorrectionHandoffError(f"{page_id}: page_number must be >= 1")
    return page_number


def _package_root(handoff_path: str | Path | None) -> Optional[Path]:
    if handoff_path is None:
        return None
    return Path(handoff_path).resolve().parent


def _resolve_package_path(
    raw_path: Any,
    *,
    package_root: Optional[Path],
    field: str,
    required: bool,
) -> Optional[Path]:
    if _is_missing(raw_path):
        if required:
            raise ManualCorrectionHandoffError(f"{field} is required")
        return None
    if not isinstance(raw_path, str):
        raise ManualCorrectionHandoffError(f"{field} must be a path string")

    candidate = Path(raw_path)
    if package_root is None:
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ManualCorrectionHandoffError(f"{field} must stay inside the review package")
        return candidate

    resolved = candidate if candidate.is_absolute() else package_root / candidate
    resolved = resolved.resolve()
    try:
        resolved.relative_to(package_root)
    except ValueError as exc:
        raise ManualCorrectionHandoffError(
            f"{field} must stay inside the review package: {raw_path}"
        ) from exc
    return resolved


def _validate_existing_path(
    raw_path: Any,
    *,
    package_root: Optional[Path],
    field: str,
    required: bool,
    require_exists: bool,
) -> Optional[Path]:
    resolved = _resolve_package_path(
        raw_path,
        package_root=package_root,
        field=field,
        required=required,
    )
    if (
        resolved is not None
        and package_root is not None
        and require_exists
        and not resolved.exists()
    ):
        raise ManualCorrectionHandoffError(f"{field} does not exist: {raw_path}")
    return resolved


def _relative_for_gui(path: Optional[Path], *, package_root: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    if package_root is not None:
        try:
            return path.relative_to(package_root).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def _manual_output_paths(page: Dict[str, Any], *, package_root: Optional[Path]) -> Dict[str, str]:
    configured = page.get("correction_outputs")
    if configured is not None:
        if not isinstance(configured, dict):
            raise ManualCorrectionHandoffError("correction_outputs must be an object")
        output_paths: Dict[str, str] = {}
        for key in GUI_OUTPUT_KEYS:
            if key not in configured:
                raise ManualCorrectionHandoffError(f"correction_outputs.{key} is required")
            resolved = _resolve_package_path(
                configured[key],
                package_root=package_root,
                field=f"correction_outputs.{key}",
                required=True,
            )
            assert resolved is not None
            output_paths[key] = _relative_for_gui(resolved, package_root=package_root)
        return output_paths

    output_dir = page.get("correction_output")
    if _is_missing(output_dir):
        output_dir = "corrections"
    output_root = _resolve_package_path(
        output_dir,
        package_root=package_root,
        field="correction_output",
        required=True,
    )
    assert output_root is not None
    return {
        key: _relative_for_gui(output_root / filename, package_root=package_root)
        for key, filename in GUI_OUTPUT_KEYS.items()
    }


def validate_manual_correction_handoff(
    payload: Dict[str, Any],
    *,
    handoff_path: str | Path | None = None,
    mode: HandoffMode = "base_v1",
    require_existing_artifacts: bool = False,
) -> Dict[str, Any]:
    """Validate a review manual-correction handoff.

    ``base_v1`` accepts optional MMR/barline/review-overlay evidence so older
    review-profile producers can be adapted. ``issue229_smoke_strict`` requires
    the artifacts needed by the #215/#229 GUI smoke path.
    """

    if not isinstance(payload, dict):
        raise ManualCorrectionHandoffError("manual correction handoff must be a JSON object")
    for field in _REQUIRED_TOP_LEVEL_FIELDS:
        if field not in payload:
            raise ManualCorrectionHandoffError(f"{field} is required")
    if mode not in {"base_v1", "issue229_smoke_strict"}:
        raise ManualCorrectionHandoffError(f"unsupported handoff validation mode: {mode}")

    pages = payload.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ManualCorrectionHandoffError("pages must be a non-empty list")

    package_root = _package_root(handoff_path)
    normalized = deepcopy(payload)
    normalized_pages = []

    for index, page in enumerate(pages):
        if not isinstance(page, dict):
            raise ManualCorrectionHandoffError(f"pages[{index}] must be an object")
        page_id = str(page.get("page_id") or f"pages[{index}]")
        for field in _REQUIRED_PAGE_FIELDS:
            if field not in page or _is_missing(page.get(field)):
                raise ManualCorrectionHandoffError(f"{page_id}: {field} is required")
        if mode == "issue229_smoke_strict":
            for field in _STRICT_PAGE_FIELDS:
                if field not in page or _is_missing(page.get(field)):
                    raise ManualCorrectionHandoffError(
                        f"{page_id}: {field} is required in strict mode"
                    )

        page_number = _as_page_number(page.get("page_number"), page_id=page_id)
        normalized_page = deepcopy(page)
        normalized_page["page_id"] = page_id
        normalized_page["page_number"] = page_number
        normalized_page["gui_page_index_zero_based"] = page_number - 1
        normalized_page["source_page_number_one_based"] = page_number

        for field in (
            "source_image",
            "numbering_final",
            "review_overlay",
            "mmr_overrides",
            "barlines_review",
        ):
            required = field in _REQUIRED_PAGE_FIELDS or (
                mode == "issue229_smoke_strict" and field in _STRICT_PAGE_FIELDS
            )
            resolved = _validate_existing_path(
                page.get(field),
                package_root=package_root,
                field=f"{page_id}.{field}",
                required=required,
                require_exists=require_existing_artifacts,
            )
            if resolved is not None:
                normalized_page[field] = _relative_for_gui(resolved, package_root=package_root)

        normalized_page["manual_outputs"] = _manual_output_paths(page, package_root=package_root)
        normalized_pages.append(normalized_page)

    normalized["pages"] = normalized_pages
    return normalized


def build_manual_gui_config(
    payload: Dict[str, Any],
    *,
    handoff_path: str | Path | None = None,
    mode: HandoffMode = "base_v1",
    require_existing_artifacts: bool = False,
) -> Dict[str, Any]:
    """Build the current GUI config from a review manual-correction handoff."""

    normalized = validate_manual_correction_handoff(
        payload,
        handoff_path=handoff_path,
        mode=mode,
        require_existing_artifacts=require_existing_artifacts,
    )
    pages = []
    for page in normalized["pages"]:
        gui_page = {
            "name": page["page_id"],
            "page": page["gui_page_index_zero_based"],
            "source_page_number": page["source_page_number_one_based"],
            "image": page["source_image"],
            "numbering": page["numbering_final"],
            "manual_outputs": page["manual_outputs"],
        }
        if not _is_missing(page.get("mmr_overrides")):
            gui_page["mmr"] = page["mmr_overrides"]
        if not _is_missing(page.get("barlines_review")):
            gui_page["barlines"] = page["barlines_review"]
        if not _is_missing(page.get("review_overlay")):
            gui_page["review_overlay"] = page["review_overlay"]
        pages.append(gui_page)

    return {
        "schema_version": 1,
        "source": "manual_correction_input",
        "pages": pages,
    }


def write_manual_gui_config(
    handoff_path: str | Path,
    output_path: str | Path,
    *,
    mode: HandoffMode = "base_v1",
    require_existing_artifacts: bool = False,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Load a handoff file, write a GUI config, and return the config."""

    output = Path(output_path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing GUI config: {output}")
    config = build_manual_gui_config(
        load_manual_correction_handoff(handoff_path),
        handoff_path=handoff_path,
        mode=mode,
        require_existing_artifacts=require_existing_artifacts,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return config


def _read_json_object_if_exists(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ManualCorrectionHandoffError(f"{path} must contain a JSON object")
    return payload


def _write_json_object(path: Path, payload: Dict[str, Any], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing correction file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def canonicalize_manual_correction_outputs(
    corrections_dir: str | Path,
    *,
    overwrite: bool = False,
    staging_paths: Optional[Dict[str, List[str | Path]]] = None,
) -> Dict[str, Path]:
    """Convert GUI staging correction files into pipeline canonical override files.

    The current manual GUI writes one file per correction surface. The pipeline
    consumes canonical ``measure_overrides.json`` and ``barline_overrides.json``
    payloads. This helper keeps that conversion outside the production run path
    and refuses to overwrite user-edited canonical files unless explicitly asked.
    """

    root = Path(corrections_dir)
    # We allow the corrections_dir to be missing if we are using staging_paths and none of them are in corrections_dir.
    # But wait, we still write to `root / "measure_overrides.json"`. So we should ensure root exists.
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
    elif not root.is_dir():
        raise FileNotFoundError(f"Corrections directory is not a directory: {root}")
    measure_output = root / "measure_overrides.json"
    barline_output = root / "barline_overrides.json"

    existing_outputs = [path for path in (measure_output, barline_output) if path.exists()]
    if existing_outputs and not overwrite:
        paths = ", ".join(str(path) for path in existing_outputs)
        raise FileExistsError(f"Refusing to overwrite existing correction file(s): {paths}")

    if staging_paths is None:
        mmr_measure_span = [
            _read_json_object_if_exists(root / STAGING_TO_CANONICAL_FILENAMES["mmr_measure_span"])
        ]
        measure_construction = [
            _read_json_object_if_exists(
                root / STAGING_TO_CANONICAL_FILENAMES["measure_construction"]
            )
        ]
        barline_construction = [
            _read_json_object_if_exists(
                root / STAGING_TO_CANONICAL_FILENAMES["barline_construction"]
            )
        ]
    else:
        mmr_measure_span = [
            _read_json_object_if_exists(Path(p)) for p in staging_paths.get("mmr_measure_span", [])
        ]
        measure_construction = [
            _read_json_object_if_exists(Path(p))
            for p in staging_paths.get("measure_construction", [])
        ]
        barline_construction = [
            _read_json_object_if_exists(Path(p))
            for p in staging_paths.get("barline_construction", [])
        ]

    measure_payload = merge_measure_overrides(*measure_construction, *mmr_measure_span)
    barline_payload = merge_barline_overrides(*barline_construction)

    _write_json_object(measure_output, measure_payload, overwrite=overwrite)
    _write_json_object(barline_output, barline_payload, overwrite=overwrite)
    return {
        "measure_overrides": measure_output,
        "barline_overrides": barline_output,
    }
