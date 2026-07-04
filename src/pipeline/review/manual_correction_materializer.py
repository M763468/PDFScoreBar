"""Materialize manual-correction review packages from pipeline run artifacts."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any


class ManualCorrectionMaterializerError(ValueError):
    """Raised when a review package cannot be built from a pipeline run."""


_BARLINES_MANIFEST_FIELDS = (
    "barlines_json",
    "resolved_barlines_json",
    "barlines_review",
    "barlines_corrected",
)


def _load_json_object(path: Path, *, description: str) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ManualCorrectionMaterializerError(f"{description} must be a JSON object: {path}")
    return payload


def _require_inside(path: Path, *, root: Path, description: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ManualCorrectionMaterializerError(
            f"{description} must stay inside current pipeline run root: {path} (run root: {root})"
        ) from exc
    return resolved


def _resolve_run_artifact(
    raw_path: Any,
    *,
    run_root: Path,
    page_id: str,
    manifest_path: Path,
    field: str,
) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise ManualCorrectionMaterializerError(
            f"{page_id}: manifest field {field} must be a non-empty artifact path "
            f"(run root: {run_root}, manifest: {manifest_path})"
        )

    raw = Path(raw_path)
    candidates = [raw] if raw.is_absolute() else [run_root / raw]
    if not raw.is_absolute() and run_root.name in raw.parts:
        run_root_index = len(raw.parts) - 1 - raw.parts[::-1].index(run_root.name)
        candidates.append(run_root.joinpath(*raw.parts[run_root_index + 1 :]))
    if not raw.is_absolute():
        candidates.append(raw)
    checked: list[str] = []
    inside_candidates: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        checked.append(str(candidate))
        try:
            resolved.relative_to(run_root)
        except ValueError:
            continue
        inside_candidates.append(resolved)
        if resolved.exists():
            return resolved

    if inside_candidates:
        raise ManualCorrectionMaterializerError(
            f"{page_id}: manifest field {field} points inside the current run but does not exist: "
            f"{raw_path} (run root: {run_root}, manifest: {manifest_path})"
        )
    raise ManualCorrectionMaterializerError(
        f"{page_id}: manifest field {field} points outside the current pipeline run: {raw_path} "
        f"(run root: {run_root}, manifest: {manifest_path}, checked: {checked})"
    )


def _page_number_from_manifest(page: dict[str, Any], *, page_id: str) -> int:
    status = page.get("status")
    if isinstance(status, dict):
        page_index = status.get("page_index")
        if isinstance(page_index, int) and page_index >= 1:
            return page_index

    match = re.search(r"(\d+)$", page_id)
    if match:
        return int(match.group(1))
    raise ManualCorrectionMaterializerError(f"{page_id}: cannot determine one-based page number")


def _select_pages(
    manifest: dict[str, Any], requested_pages: list[str] | None
) -> list[dict[str, Any]]:
    manifest_pages = manifest.get("pages")
    if not isinstance(manifest_pages, list) or not manifest_pages:
        raise ManualCorrectionMaterializerError("manifest pages must be a non-empty list")

    by_id: dict[str, dict[str, Any]] = {}
    for index, page in enumerate(manifest_pages):
        if not isinstance(page, dict):
            raise ManualCorrectionMaterializerError(f"manifest pages[{index}] must be an object")
        page_id = page.get("page_id")
        if not isinstance(page_id, str) or not page_id:
            raise ManualCorrectionMaterializerError(f"manifest pages[{index}].page_id is required")
        by_id[page_id] = page

    if requested_pages is None:
        return list(by_id.values())

    selected = []
    for page_id in requested_pages:
        if page_id not in by_id:
            raise ManualCorrectionMaterializerError(f"page not found in manifest: {page_id}")
        selected.append(by_id[page_id])
    return selected


def _copy_run_artifact(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _resolve_barlines_review_source(
    page: dict[str, Any],
    *,
    run_root: Path,
    page_id: str,
    manifest_path: Path,
) -> tuple[Path, str, str]:
    for field in _BARLINES_MANIFEST_FIELDS:
        if field in page and page[field]:
            source = _resolve_run_artifact(
                page[field],
                run_root=run_root,
                page_id=page_id,
                manifest_path=manifest_path,
                field=field,
            )
            source_kind = (
                "manifest_resolved_detector_output"
                if field == "barlines_json"
                else f"manifest_{field}"
            )
            return source, source_kind, field

    page_local = run_root / "intermediate" / page_id / "barlines_corrected.json"
    if page_local.exists():
        return (
            page_local.resolve(),
            "current_run_page_artifact",
            "intermediate/page_id/barlines_corrected.json",
        )

    raise ManualCorrectionMaterializerError(
        f"{page_id}: cannot materialize barlines_review.json from current run. "
        f"run root: {run_root}; manifest: {manifest_path}; searched manifest fields: "
        f"{', '.join(_BARLINES_MANIFEST_FIELDS)}; searched current-run page artifact: "
        f"{page_local}; follow-up PR should connect a stable page-local barlines_review.json "
        f"or manifest-resolved detector geometry artifact."
    )


def materialize_manual_correction_review_package(
    *,
    run_root: str | Path,
    review_root: str | Path,
    pages: list[str] | None = None,
    source_pipeline_command: str | None = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Create a review manual-correction package from one pipeline run.

    The materializer only consumes artifacts inside ``run_root`` and manifest
    paths resolved from that same run. It intentionally does not search global
    ``logs/`` directories or fall back to older run artifacts.
    """

    run_root_path = Path(run_root).resolve()
    review_root_path = Path(review_root).resolve()
    manifest_path = run_root_path / "manifest.json"
    if not manifest_path.exists():
        raise ManualCorrectionMaterializerError(f"manifest does not exist: {manifest_path}")
    if review_root_path.exists() and any(review_root_path.iterdir()) and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing review package: {review_root_path}")

    manifest = _load_json_object(manifest_path, description="pipeline manifest")
    selected_pages = _select_pages(manifest, pages)

    handoff_pages: list[dict[str, Any]] = []
    for page in selected_pages:
        page_id = str(page["page_id"])
        page_number = _page_number_from_manifest(page, page_id=page_id)

        image_source = _resolve_run_artifact(
            page.get("image_path"),
            run_root=run_root_path,
            page_id=page_id,
            manifest_path=manifest_path,
            field="image_path",
        )
        numbering_final = _require_inside(
            run_root_path / "outputs" / page_id / "numbering_final.json",
            root=run_root_path,
            description=f"{page_id}.numbering_final",
        )
        review_overlay = _require_inside(
            run_root_path / "outputs" / page_id / "numbering_overlay.png",
            root=run_root_path,
            description=f"{page_id}.review_overlay",
        )
        mmr_overrides = _require_inside(
            run_root_path / "intermediate" / page_id / "overrides_mmr.json",
            root=run_root_path,
            description=f"{page_id}.mmr_overrides",
        )
        barlines_source, barlines_source_kind, barlines_source_field = (
            _resolve_barlines_review_source(
                page,
                run_root=run_root_path,
                page_id=page_id,
                manifest_path=manifest_path,
            )
        )

        required = {
            "numbering_final": numbering_final,
            "review_overlay": review_overlay,
            "mmr_overrides": mmr_overrides,
            "barlines_review source": barlines_source,
        }
        missing = [f"{label}: {path}" for label, path in required.items() if not path.exists()]
        if missing:
            raise ManualCorrectionMaterializerError(
                f"{page_id}: required current-run artifact(s) missing; run root: {run_root_path}; "
                f"manifest: {manifest_path}; " + "; ".join(missing)
            )

        page_dir = review_root_path / "pages" / page_id
        _copy_run_artifact(image_source, page_dir / "source.png")
        _copy_run_artifact(numbering_final, page_dir / "numbering_final.json")
        _copy_run_artifact(review_overlay, page_dir / "review_overlay.png")
        _copy_run_artifact(mmr_overrides, page_dir / "mmr_overrides.json")
        _copy_run_artifact(barlines_source, page_dir / "barlines_review.json")

        handoff_pages.append(
            {
                "page_id": page_id,
                "page_number": page_number,
                "source_image": f"pages/{page_id}/source.png",
                "numbering_final": f"pages/{page_id}/numbering_final.json",
                "review_overlay": f"pages/{page_id}/review_overlay.png",
                "mmr_overrides": f"pages/{page_id}/mmr_overrides.json",
                "barlines_review": f"pages/{page_id}/barlines_review.json",
                "barlines_review_source": barlines_source.relative_to(run_root_path).as_posix(),
                "barlines_review_source_kind": barlines_source_kind,
                "barlines_review_source_manifest_field": barlines_source_field,
                "correction_output": "corrections",
            }
        )

    (review_root_path / "corrections").mkdir(parents=True, exist_ok=True)
    handoff = {
        "schema_version": 1,
        "kind": "manual_correction_input",
        "source_artifact_root": str(run_root_path),
        "source_manifest": "manifest.json",
        "pages": handoff_pages,
    }
    if source_pipeline_command:
        handoff["source_pipeline_command"] = source_pipeline_command

    handoff_path = review_root_path / "manual_correction_input.json"
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(
        json.dumps(handoff, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return handoff
