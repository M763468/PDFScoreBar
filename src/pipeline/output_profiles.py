"""Materialize user-facing output profiles from an internal pipeline run.

The integrated pipeline currently writes an implementation-oriented run layout:

- ``pipeline.log`` / ``manifest.json`` / ``filters.json`` at the run root
- source renders under ``inputs/images``
- page intermediates under ``intermediate``
- final numbering and current overlays under ``outputs``

This module maps that internal layout into the #227 user-facing profile contract.
It deliberately keeps the materialization step separate from detector, MMR,
numbering, and overlay logic so those stages do not need to know public output
profile paths.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

from src.pipeline.utils.io import ensure_dir, load_json, write_json

OutputProfile = Literal["final", "review", "debug"]
VALID_OUTPUT_PROFILES: tuple[OutputProfile, ...] = ("final", "review", "debug")
_PROFILE_RANK: dict[OutputProfile, int] = {"final": 0, "review": 1, "debug": 2}
_PROFILE_DIRS = {"final", "review", "debug"}


@dataclass(frozen=True)
class MaterializedArtifact:
    """A source-to-public artifact mapping created by the materializer."""

    profile: str
    path: str
    source: str | None
    status: str


@dataclass(frozen=True)
class PageArtifacts:
    """Known artifact locations for one page in the internal pipeline layout."""

    page_id: str
    image_path: Path | None
    output_dir: Path
    intermediate_dir: Path


def normalize_output_profile(profile: str) -> OutputProfile:
    """Validate and normalize a public output profile name."""

    value = profile.strip().lower()
    if value not in VALID_OUTPUT_PROFILES:
        allowed = ", ".join(VALID_OUTPUT_PROFILES)
        raise ValueError(f"Unknown output profile {profile!r}. Expected one of: {allowed}.")
    return value  # type: ignore[return-value]


def effective_output_profile(profile: str = "final", *, debug: bool = False) -> OutputProfile:
    """Resolve the selected profile plus legacy/debug flag into an effective profile."""

    selected = normalize_output_profile(profile)
    if debug and _PROFILE_RANK[selected] < _PROFILE_RANK["debug"]:
        return "debug"
    return selected


def materialize_output_profile(
    source_run_dir: Path | str,
    output_dir: Path | str | None = None,
    *,
    profile: str = "final",
    debug: bool = False,
    input_pdf: Path | str | None = None,
    resolved_config_path: Path | str | None = None,
    resolved_config: dict[str, Any] | None = None,
    overwrite_existing: bool = True,
) -> Path:
    """Create #227 public output profile directories from an internal run directory.

    Args:
        source_run_dir: Existing internal pipeline run directory.
        output_dir: Public output directory. Defaults to ``source_run_dir``.
        profile: Requested public profile: ``final``, ``review``, or ``debug``.
        debug: Compatibility flag. When true, the effective profile is at least
            ``debug`` and debug artifacts are kept under ``debug/``.
        input_pdf: Optional input PDF path to record in ``run_summary.json``.
        resolved_config_path: Optional resolved config file to copy to
            ``resolved_config.yaml``.
        resolved_config: Optional resolved config mapping. Used when no config
            file path is supplied. It is written as JSON-compatible YAML.
        overwrite_existing: Whether generated profile artifacts may overwrite
            previous generated files. User correction files are never overwritten.

    Returns:
        The public output directory.
    """

    internal_root = Path(source_run_dir)
    public_root = Path(output_dir) if output_dir is not None else internal_root
    selected_profile = normalize_output_profile(profile)
    effective_profile = effective_output_profile(selected_profile, debug=debug)

    ensure_dir(public_root)

    manifest = _load_optional_json(internal_root / "manifest.json") or {}
    filters = _load_optional_json(internal_root / "filters.json") or {}
    config = _resolve_config_payload(
        manifest=manifest,
        resolved_config=resolved_config,
        profile=selected_profile,
        effective_profile=effective_profile,
    )

    artifact_index: list[MaterializedArtifact] = []
    pages = _discover_pages(internal_root, manifest)

    _materialize_resolved_config(
        public_root=public_root,
        resolved_config_path=Path(resolved_config_path) if resolved_config_path else None,
        resolved_config=config,
        artifact_index=artifact_index,
        overwrite_existing=overwrite_existing,
    )

    _materialize_final(
        internal_root=internal_root,
        public_root=public_root,
        pages=pages,
        filters=filters,
        artifact_index=artifact_index,
        overwrite_existing=overwrite_existing,
    )

    if _PROFILE_RANK[effective_profile] >= _PROFILE_RANK["review"]:
        _materialize_review(
            public_root=public_root,
            pages=pages,
            manifest=manifest,
            input_pdf=input_pdf,
            artifact_index=artifact_index,
            overwrite_existing=overwrite_existing,
        )

    if _PROFILE_RANK[effective_profile] >= _PROFILE_RANK["debug"]:
        _materialize_debug(
            internal_root=internal_root,
            public_root=public_root,
            artifact_index=artifact_index,
            overwrite_existing=overwrite_existing,
        )

    if _PROFILE_RANK[effective_profile] >= _PROFILE_RANK["review"]:
        _write_artifact_index(public_root / "artifact_index.json", artifact_index)
    if _PROFILE_RANK[effective_profile] >= _PROFILE_RANK["debug"]:
        _write_artifact_index(public_root / "debug" / "artifact_index.json", artifact_index)

    _write_run_summary(
        public_root=public_root,
        internal_root=internal_root,
        selected_profile=selected_profile,
        effective_profile=effective_profile,
        debug_requested=debug,
        input_pdf=input_pdf,
        manifest=manifest,
        filters=filters,
        pages=pages,
        artifact_index=artifact_index,
    )

    return public_root


def _resolve_config_payload(
    *,
    manifest: dict[str, Any],
    resolved_config: dict[str, Any] | None,
    profile: OutputProfile,
    effective_profile: OutputProfile,
) -> dict[str, Any]:
    if resolved_config is not None:
        return resolved_config
    manifest_config = manifest.get("config")
    if isinstance(manifest_config, dict):
        config = dict(manifest_config)
    else:
        config = {}
    config.setdefault("output_profile", {})
    if isinstance(config["output_profile"], dict):
        config["output_profile"].setdefault("selected", profile)
        config["output_profile"].setdefault("effective", effective_profile)
    return config


def _materialize_resolved_config(
    *,
    public_root: Path,
    resolved_config_path: Path | None,
    resolved_config: dict[str, Any],
    artifact_index: list[MaterializedArtifact],
    overwrite_existing: bool,
) -> None:
    destination = public_root / "resolved_config.yaml"
    if resolved_config_path is not None and resolved_config_path.exists():
        copied = _copy_file(
            resolved_config_path,
            destination,
            profile="root",
            artifact_index=artifact_index,
            overwrite_existing=overwrite_existing,
        )
        if copied:
            return
    _write_yaml_compatible(destination, resolved_config, overwrite_existing=overwrite_existing)
    artifact_index.append(
        MaterializedArtifact(
            profile="root",
            path=_relative_public_path(destination, public_root),
            source=str(resolved_config_path) if resolved_config_path else None,
            status="written",
        )
    )


def _materialize_final(
    *,
    internal_root: Path,
    public_root: Path,
    pages: list[PageArtifacts],
    filters: dict[str, Any],
    artifact_index: list[MaterializedArtifact],
    overwrite_existing: bool,
) -> None:
    final_dir = public_root / "final"
    ensure_dir(final_dir)

    aggregate_numbering = internal_root / "outputs" / "numbering_final.json"
    destination = final_dir / "score_numbering.json"
    if aggregate_numbering.exists():
        _copy_file(
            aggregate_numbering,
            destination,
            profile="final",
            artifact_index=artifact_index,
            overwrite_existing=overwrite_existing,
        )
    else:
        combined = _combine_page_numbering(pages)
        if combined is not None:
            write_json(destination, combined)
            artifact_index.append(
                MaterializedArtifact(
                    profile="final",
                    path=_relative_public_path(destination, public_root),
                    source=None,
                    status="combined_from_page_outputs",
                )
            )

    warnings = _build_user_warnings(filters)
    if warnings:
        warnings_path = final_dir / "warnings.json"
        write_json(warnings_path, {"warnings": warnings})
        artifact_index.append(
            MaterializedArtifact(
                profile="final",
                path=_relative_public_path(warnings_path, public_root),
                source=str(internal_root / "filters.json"),
                status="written",
            )
        )


def _materialize_review(
    *,
    public_root: Path,
    pages: list[PageArtifacts],
    manifest: dict[str, Any],
    input_pdf: Path | str | None,
    artifact_index: list[MaterializedArtifact],
    overwrite_existing: bool,
) -> None:
    review_root = public_root / "review"
    ensure_dir(review_root / "pages")
    corrections_path = review_root / "corrections" / "measure_overrides.json"
    _write_correction_template(corrections_path)

    manual_pages = []
    for page in pages:
        page_review = review_root / "pages" / page.page_id
        ensure_dir(page_review)

        source_image = page.image_path
        source_dest = page_review / "source.png"
        if source_image is not None:
            _copy_file(
                source_image,
                source_dest,
                profile="review",
                artifact_index=artifact_index,
                overwrite_existing=overwrite_existing,
            )

        _copy_file(
            page.output_dir / "numbering_overlay.png",
            page_review / "review_overlay.png",
            profile="review",
            artifact_index=artifact_index,
            overwrite_existing=overwrite_existing,
        )
        _copy_file(
            page.output_dir / "numbering_final.json",
            page_review / "numbering_final.json",
            profile="review",
            artifact_index=artifact_index,
            overwrite_existing=overwrite_existing,
        )
        _copy_file(
            page.intermediate_dir / "barlines_corrected.json",
            page_review / "barlines_review.json",
            profile="review",
            artifact_index=artifact_index,
            overwrite_existing=overwrite_existing,
        )
        _copy_file(
            page.intermediate_dir / "overrides_mmr.json",
            page_review / "mmr_overrides.json",
            profile="review",
            artifact_index=artifact_index,
            overwrite_existing=overwrite_existing,
        )
        template_path = page_review / "correction_template.json"
        _write_json_if_missing(template_path, {"measure_overrides": []})

        manual_pages.append(
            {
                "page_id": page.page_id,
                "source_image": _optional_public_path(source_dest, public_root),
                "review_overlay": _optional_public_path(
                    page_review / "review_overlay.png", public_root
                ),
                "numbering_final": _optional_public_path(
                    page_review / "numbering_final.json", public_root
                ),
                "barlines_review": _optional_public_path(
                    page_review / "barlines_review.json", public_root
                ),
                "mmr_overrides": _optional_public_path(
                    page_review / "mmr_overrides.json", public_root
                ),
                "correction_template": _relative_public_path(template_path, public_root),
            }
        )

    manual_input = {
        "schema": "pdfscorebar.manual_correction_input.v1",
        "input_pdf": str(input_pdf) if input_pdf is not None else _input_pdf_from_manifest(manifest),
        "correction_output": _relative_public_path(corrections_path, public_root),
        "coordinate_space": "rendered_page_image",
        "pages": manual_pages,
    }
    manual_input_path = review_root / "manual_correction_input.json"
    write_json(manual_input_path, manual_input)
    artifact_index.append(
        MaterializedArtifact(
            profile="review",
            path=_relative_public_path(manual_input_path, public_root),
            source=None,
            status="written",
        )
    )


def _materialize_debug(
    *,
    internal_root: Path,
    public_root: Path,
    artifact_index: list[MaterializedArtifact],
    overwrite_existing: bool,
) -> None:
    debug_root = public_root / "debug"
    ensure_dir(debug_root)

    for filename in ("pipeline.log", "manifest.json", "filters.json"):
        _copy_file(
            internal_root / filename,
            debug_root / filename,
            profile="debug",
            artifact_index=artifact_index,
            overwrite_existing=overwrite_existing,
        )

    _copy_tree(
        internal_root / "inputs" / "images",
        debug_root / "inputs" / "images",
        profile="debug",
        artifact_index=artifact_index,
        overwrite_existing=overwrite_existing,
    )
    _copy_tree(
        internal_root / "intermediate",
        debug_root / "intermediate",
        profile="debug",
        artifact_index=artifact_index,
        overwrite_existing=overwrite_existing,
    )
    _copy_tree(
        internal_root / "outputs",
        debug_root / "legacy_current_layout" / "outputs",
        profile="debug",
        artifact_index=artifact_index,
        overwrite_existing=overwrite_existing,
    )

    environment_path = debug_root / "environment.json"
    _write_json_if_missing(
        environment_path,
        {
            "captured": False,
            "reason": "environment capture is not implemented in the profile materializer",
        },
    )


def _discover_pages(internal_root: Path, manifest: dict[str, Any]) -> list[PageArtifacts]:
    pages: list[PageArtifacts] = []
    seen: set[str] = set()

    manifest_pages = manifest.get("pages")
    if isinstance(manifest_pages, list):
        for item in manifest_pages:
            if not isinstance(item, dict):
                continue
            page_id = str(item.get("page_id") or "").strip()
            if not page_id:
                continue
            seen.add(page_id)
            pages.append(
                PageArtifacts(
                    page_id=page_id,
                    image_path=_resolve_existing_path(item.get("image_path"), internal_root),
                    output_dir=internal_root / "outputs" / page_id,
                    intermediate_dir=internal_root / "intermediate" / page_id,
                )
            )

    outputs_root = internal_root / "outputs"
    if outputs_root.exists():
        for child in sorted(outputs_root.iterdir()):
            if not child.is_dir() or child.name in _PROFILE_DIRS or child.name in seen:
                continue
            pages.append(
                PageArtifacts(
                    page_id=child.name,
                    image_path=_resolve_image_fallback(internal_root, child.name),
                    output_dir=child,
                    intermediate_dir=internal_root / "intermediate" / child.name,
                )
            )

    return pages


def _combine_page_numbering(pages: Iterable[PageArtifacts]) -> dict[str, Any] | None:
    combined_pages = []
    for page in pages:
        path = page.output_dir / "numbering_final.json"
        payload = _load_optional_json(path)
        if not isinstance(payload, dict):
            continue
        page_payload = payload.get("pages")
        if isinstance(page_payload, list):
            combined_pages.extend(page_payload)
    if not combined_pages:
        return None
    return {"pages": combined_pages}


def _build_user_warnings(filters: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    pages = filters.get("pages")
    if not isinstance(pages, list):
        return warnings
    for page in pages:
        if not isinstance(page, dict):
            continue
        status = str(page.get("status") or page.get("state") or "").lower()
        if status and status not in {"ok", "included", "processed"}:
            warnings.append(page)
    return warnings


def _write_run_summary(
    *,
    public_root: Path,
    internal_root: Path,
    selected_profile: OutputProfile,
    effective_profile: OutputProfile,
    debug_requested: bool,
    input_pdf: Path | str | None,
    manifest: dict[str, Any],
    filters: dict[str, Any],
    pages: list[PageArtifacts],
    artifact_index: list[MaterializedArtifact],
) -> None:
    final_numbering = public_root / "final" / "score_numbering.json"
    review_input = public_root / "review" / "manual_correction_input.json"
    summary = {
        "schema": "pdfscorebar.run_summary.v1",
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source_run_dir": str(internal_root),
        "output_dir": str(public_root),
        "run_id": manifest.get("run_id") or internal_root.name,
        "input_pdf": str(input_pdf) if input_pdf is not None else _input_pdf_from_manifest(manifest),
        "profile": {
            "selected": selected_profile,
            "effective": effective_profile,
            "debug_requested": debug_requested,
        },
        "pages": [page.page_id for page in pages],
        "page_count": len(pages),
        "warnings_count": len(_build_user_warnings(filters)),
        "final_overlay": {
            "status": "not_implemented_in_issue227",
            "note": "#228 defines the stable final score-number overlay renderer.",
        },
        "artifacts": {
            "final_score_numbering": _optional_public_path(final_numbering, public_root),
            "manual_correction_input": _optional_public_path(review_input, public_root),
        },
        "artifact_count": len(artifact_index),
    }
    write_json(public_root / "run_summary.json", summary)


def _copy_file(
    source: Path,
    destination: Path,
    *,
    profile: str,
    artifact_index: list[MaterializedArtifact],
    overwrite_existing: bool,
) -> bool:
    if not source.exists() or not source.is_file():
        return False
    if destination.exists() and not overwrite_existing:
        artifact_index.append(
            MaterializedArtifact(profile=profile, path=str(destination), source=str(source), status="exists")
        )
        return False
    ensure_dir(destination.parent)
    shutil.copy2(source, destination)
    artifact_index.append(
        MaterializedArtifact(profile=profile, path=str(destination), source=str(source), status="copied")
    )
    return True


def _copy_tree(
    source: Path,
    destination: Path,
    *,
    profile: str,
    artifact_index: list[MaterializedArtifact],
    overwrite_existing: bool,
) -> bool:
    if not source.exists() or not source.is_dir():
        return False
    if destination.exists() and not overwrite_existing:
        artifact_index.append(
            MaterializedArtifact(profile=profile, path=str(destination), source=str(source), status="exists")
        )
        return False
    if destination.exists():
        shutil.rmtree(destination)
    ensure_dir(destination.parent)
    shutil.copytree(source, destination)
    artifact_index.append(
        MaterializedArtifact(profile=profile, path=str(destination), source=str(source), status="copied")
    )
    return True


def _write_artifact_index(path: Path, artifacts: list[MaterializedArtifact]) -> None:
    write_json(path, {"artifacts": [artifact.__dict__ for artifact in artifacts]})


def _write_yaml_compatible(path: Path, payload: dict[str, Any], *, overwrite_existing: bool) -> None:
    if path.exists() and not overwrite_existing:
        return
    ensure_dir(path.parent)
    # JSON is a YAML subset and avoids adding a PyYAML dependency to this materializer.
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _write_correction_template(path: Path) -> None:
    _write_json_if_missing(path, {"measure_overrides": []})


def _write_json_if_missing(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        return
    write_json(path, payload)


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    payload = load_json(path)
    return payload if isinstance(payload, dict) else None


def _resolve_existing_path(value: Any, internal_root: Path) -> Path | None:
    if value is None:
        return None
    candidate = Path(str(value))
    candidates = [candidate]
    if not candidate.is_absolute():
        candidates.extend([internal_root / candidate, internal_root.parent / candidate])
    for path in candidates:
        if path.exists():
            return path
    return None


def _resolve_image_fallback(internal_root: Path, page_id: str) -> Path | None:
    image_root = internal_root / "inputs" / "images"
    for suffix in (".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        candidate = image_root / f"{page_id}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _input_pdf_from_manifest(manifest: dict[str, Any]) -> str | None:
    config = manifest.get("config")
    if not isinstance(config, dict):
        return None
    inputs = config.get("inputs")
    if not isinstance(inputs, dict):
        return None
    pdf_path = inputs.get("pdf_path")
    return str(pdf_path) if pdf_path is not None else None


def _relative_public_path(path: Path, public_root: Path) -> str:
    try:
        return path.relative_to(public_root).as_posix()
    except ValueError:
        return str(path)


def _optional_public_path(path: Path, public_root: Path) -> str | None:
    if not path.exists():
        return None
    return _relative_public_path(path, public_root)
