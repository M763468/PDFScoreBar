import argparse
import datetime as dt
import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.serialization import score_to_dict
from src.measure_numbering.types import Score
from src.pipeline.core.config import get_nested, load_yaml
from src.pipeline.mmr_support_reuse import build_mmr_support_data
from src.pipeline.review.final_output import materialize_corrected_final_outputs
from src.pipeline.review.manual_correction_handoff import (
    canonicalize_manual_correction_outputs,
    load_manual_correction_handoff,
    validate_manual_correction_handoff,
)
from src.pipeline.steps.barlines import apply_barline_overrides, normalize_barlines
from src.pipeline.steps.manual_corrections import (
    merge_barline_overrides,
    merge_measure_overrides,
    normalise_barline_overrides,
    normalise_measure_overrides,
)
from src.pipeline.steps.numbering import (
    final_numbering_metadata,
    load_movement_boundary_payload,
    movement_boundaries_for_page,
    run_mmr_batch,
)
from src.pipeline.utils.images import load_image
from src.pipeline.utils.io import ensure_dir, load_json, write_json

logger = logging.getLogger(__name__)


def _resolve_source_manifest_path(payload: dict[str, Any], package_root: Path) -> Path:
    source_manifest = payload.get("source_manifest")
    source_artifact_root = payload.get("source_artifact_root")

    if source_manifest:
        manifest_path = Path(str(source_manifest))
        if not manifest_path.is_absolute():
            if source_artifact_root:
                manifest_path = Path(str(source_artifact_root)) / manifest_path
            else:
                manifest_path = package_root / manifest_path
        return manifest_path.resolve()

    return (package_root.parent / "manifest.json").resolve()


def _unique_existing_paths(paths: List[str | Path]) -> List[Path]:
    unique: List[Path] = []
    seen: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path)
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _read_json_object_if_exists(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _input_override_path(
    source_config: Dict[str, Any],
    key: str,
    *,
    base_dir: Path | None,
) -> Optional[Path]:
    inputs = source_config.get("inputs")
    if not isinstance(inputs, dict):
        return None
    raw_path = inputs.get(key)
    if not raw_path:
        return None
    path = Path(str(raw_path))
    candidates = [path]
    if not path.is_absolute() and base_dir is not None:
        candidates.append(base_dir / path)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _read_existing_override_inputs(
    *,
    source_config: Dict[str, Any],
    config_base_dir: Path | None,
) -> Dict[str, Any]:
    """Read existing override payloads before canonical files may be overwritten."""

    existing_measure_path = _input_override_path(
        source_config, "measure_overrides", base_dir=config_base_dir
    )
    existing_barline_path = _input_override_path(
        source_config, "barline_overrides", base_dir=config_base_dir
    )

    return {
        "existing_measure_path": existing_measure_path,
        "existing_measure_payload": (
            _read_json_object_if_exists(existing_measure_path) if existing_measure_path else None
        ),
        "existing_barline_path": existing_barline_path,
        "existing_barline_payload": (
            _read_json_object_if_exists(existing_barline_path) if existing_barline_path else None
        ),
    }


def _mmr_suppression_override_payload(
    staging_paths: Dict[str, List[str | Path]],
) -> Optional[Dict[str, Any]]:
    """Encode MMR suppress operations as neutral user overrides.

    The final numbering phase merges freshly generated MMR overrides first and
    user overrides second. A same-key user override with ``skip=0`` therefore
    cancels the automatic MMR skip without disabling MMR for unrelated pages.
    """

    overrides: List[Dict[str, Any]] = []
    seen: set[tuple[int, int, int]] = set()
    for path in _unique_existing_paths(staging_paths.get("mmr_measure_span", [])):
        payload = _read_json_object_if_exists(path)
        if not payload:
            continue
        items = payload.get("items", [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or item.get("op") != "suppress":
                continue
            try:
                key = (int(item["page"]), int(item["system"]), int(item["measure"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid MMR suppress correction item: {item}") from exc
            if key in seen:
                continue
            seen.add(key)
            page, system, measure = key
            overrides.append(
                {
                    "page": page,
                    "system": system,
                    "measure": measure,
                    "skip": 0,
                    "comment": "manual MMR suppression",
                    "source": "manual:mmr_measure_span_suppress",
                }
            )
    if not overrides:
        return None
    return {"measure_overrides": overrides, "overrides": deepcopy(overrides)}


def _merge_existing_override_inputs(
    *,
    canonical_paths: Dict[str, Path],
    existing_override_inputs: Dict[str, Any],
    staging_paths: Dict[str, List[str | Path]],
) -> Dict[str, Any]:
    existing_measure_path = existing_override_inputs.get("existing_measure_path")
    existing_barline_path = existing_override_inputs.get("existing_barline_path")
    existing_measure_payload = existing_override_inputs.get("existing_measure_payload")
    existing_barline_payload = existing_override_inputs.get("existing_barline_payload")

    current_measure_payload = _read_json_object_if_exists(canonical_paths["measure_overrides"])
    current_barline_payload = _read_json_object_if_exists(canonical_paths["barline_overrides"])
    suppression_payload = _mmr_suppression_override_payload(staging_paths)

    measure_payloads: List[Optional[Dict[str, Any]]] = []
    measure_payloads.append(existing_measure_payload)
    measure_payloads.append(current_measure_payload)
    measure_payloads.append(suppression_payload)

    barline_payloads: List[Optional[Dict[str, Any]]] = []
    barline_payloads.append(existing_barline_payload)
    barline_payloads.append(current_barline_payload)

    measure_payload = merge_measure_overrides(*measure_payloads)
    barline_payload = merge_barline_overrides(*barline_payloads)

    canonical_paths["measure_overrides"].write_text(
        json.dumps(measure_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    canonical_paths["barline_overrides"].write_text(
        json.dumps(barline_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return {
        "existing_measure_overrides": str(existing_measure_path) if existing_measure_path else None,
        "existing_barline_overrides": str(existing_barline_path) if existing_barline_path else None,
        "mmr_suppressions_encoded": bool(suppression_payload),
    }


def _write_apply_summary(summary: dict[str, Any], new_run_dir: Path, corrections_dir: Path) -> None:
    summary_path = new_run_dir / "review" / "correction_summary.json"
    ensure_dir(summary_path.parent)
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    back_summary_path = corrections_dir / "apply_summary.json"
    back_summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )



def _resolve_package_artifact(package_root: Path, raw_path: Any, *, role: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError(f"{role} must be a non-empty package-relative path")
    path = Path(raw_path)
    if path.is_absolute():
        raise ValueError(f"{role} must stay inside the review package: {raw_path}")
    resolved = (package_root / path).resolve()
    try:
        resolved.relative_to(package_root)
    except ValueError as exc:
        raise ValueError(f"{role} must stay inside the review package: {raw_path}") from exc
    if not resolved.exists():
        raise FileNotFoundError(f"{role} does not exist: {resolved}")
    return resolved


def _resolve_retained_artifact(raw_path: Any, *, source_root: Path, role: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError(f"{role} must be a non-empty path")
    raw = Path(raw_path)
    candidates = [raw] if raw.is_absolute() else [raw, source_root / raw, source_root.parent / raw]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(
        f"{role} does not exist in retained source context: {raw_path} "
        f"(source_root={source_root})"
    )


def _first_numbering_page(payload: Dict[str, Any], *, role: str) -> Dict[str, Any]:
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], dict):
        raise ValueError(f"{role} must contain exactly one page payload")
    return pages[0]


def _measure_bbox(payload: Dict[str, Any], system_index: int, measure_index: int) -> List[int]:
    page = _first_numbering_page(payload, role="numbering payload")
    systems = page.get("systems")
    if not isinstance(systems, list) or not (0 <= system_index < len(systems)):
        raise ValueError(f"system index is outside numbering payload: {system_index}")
    measures = systems[system_index].get("measures")
    if not isinstance(measures, list) or not (0 <= measure_index < len(measures)):
        raise ValueError(
            f"measure index is outside numbering payload: system={system_index} "
            f"measure={measure_index}"
        )
    bbox = measures[measure_index].get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError(
            f"measure bbox is invalid: system={system_index} measure={measure_index}"
        )
    return [int(value) for value in bbox]


def _bbox_overlap_score(left: List[int], right: List[int]) -> float:
    ix = max(0, min(left[2], right[2]) - max(left[0], right[0]))
    iy = max(0, min(left[3], right[3]) - max(left[1], right[1]))
    if ix <= 0 or iy <= 0:
        return 0.0
    left_area = max(1, (left[2] - left[0]) * (left[3] - left[1]))
    right_area = max(1, (right[2] - right[0]) * (right[3] - right[1]))
    return (ix * iy) / min(left_area, right_area)


def _remap_measure_key(
    source_payload: Dict[str, Any],
    corrected_payload: Dict[str, Any],
    key: tuple[int, int, int],
    *,
    strict: bool,
) -> tuple[int, int, int] | None:
    page_index, system_index, measure_index = key
    source_bbox = _measure_bbox(source_payload, system_index, measure_index)
    corrected_page = _first_numbering_page(corrected_payload, role="corrected numbering payload")
    systems = corrected_page.get("systems")
    if not isinstance(systems, list) or not (0 <= system_index < len(systems)):
        if strict:
            raise ValueError(
                f"Cannot remap correction key {key}: corrected system no longer exists"
            )
        return None
    measures = systems[system_index].get("measures")
    if not isinstance(measures, list) or not measures:
        if strict:
            raise ValueError(
                f"Cannot remap correction key {key}: corrected system has no measures"
            )
        return None

    ranked: List[tuple[float, int]] = []
    for new_index, measure in enumerate(measures):
        bbox = measure.get("bbox") if isinstance(measure, dict) else None
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        score = _bbox_overlap_score(source_bbox, [int(value) for value in bbox])
        if score > 0:
            ranked.append((score, new_index))
    ranked.sort(reverse=True)

    if not ranked:
        if strict:
            raise ValueError(f"Cannot remap correction key {key}: no overlapping corrected measure")
        return None

    best_score, best_index = ranked[0]
    if len(ranked) > 1:
        second_score = ranked[1][0]
        if second_score >= 0.8 and second_score >= best_score * 0.95:
            if strict:
                raise ValueError(
                    f"Cannot safely remap correction key {key}: one reviewed measure "
                    "maps to multiple corrected measures; review the MMR correction again"
                )
            return None

    return (page_index, system_index, best_index)


def _barline_neighborhood_keys(
    numbering_payload: Dict[str, Any],
    barline_overrides: List[Dict[str, Any]],
    *,
    page_index: int,
    radius: int = 0,
) -> set[tuple[int, int, int]]:
    page = _first_numbering_page(numbering_payload, role="barline-neighborhood numbering")
    systems = page.get("systems")
    if not isinstance(systems, list):
        return set()

    keys: set[tuple[int, int, int]] = set()
    for override in barline_overrides:
        if int(override.get("page", -1)) != page_index:
            continue
        raw_bbox = override.get("bbox")
        if not isinstance(raw_bbox, list) or len(raw_bbox) != 4:
            continue
        bbox = [int(value) for value in raw_bbox]
        bar_x = (bbox[0] + bbox[2]) / 2.0

        for system_index, system in enumerate(systems):
            measures = system.get("measures") if isinstance(system, dict) else None
            if not isinstance(measures, list) or not measures:
                continue

            candidates: List[tuple[float, int]] = []
            for measure_index, measure in enumerate(measures):
                measure_bbox = measure.get("bbox") if isinstance(measure, dict) else None
                if not isinstance(measure_bbox, list) or len(measure_bbox) != 4:
                    continue
                mb = [int(value) for value in measure_bbox]
                vertical_overlap = max(0, min(bbox[3], mb[3]) - max(bbox[1], mb[1]))
                if vertical_overlap <= 0:
                    continue
                if mb[0] <= bar_x <= mb[2]:
                    distance = 0.0
                else:
                    distance = min(abs(bar_x - mb[0]), abs(bar_x - mb[2]))
                candidates.append((distance, measure_index))

            if not candidates:
                continue
            min_distance = min(distance for distance, _ in candidates)
            nearest = [
                measure_index
                for distance, measure_index in candidates
                if abs(distance - min_distance) < 1e-6
            ]
            for measure_index in nearest:
                lo = max(0, measure_index - radius)
                hi = min(len(measures) - 1, measure_index + radius)
                for target_index in range(lo, hi + 1):
                    keys.add((page_index, system_index, target_index))
    return keys


def _read_staging_payloads(paths: List[str | Path]) -> List[Dict[str, Any]]:
    payloads: List[Dict[str, Any]] = []
    for path in _unique_existing_paths(paths):
        payload = _read_json_object_if_exists(path)
        if payload:
            payloads.append(payload)
    return payloads


def _current_staging_pages(
    staging_paths: Dict[str, List[str | Path]],
) -> set[int]:
    pages: set[int] = set()
    for paths in staging_paths.values():
        for payload in _read_staging_payloads(paths):
            items = payload.get("items")
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict) or "page" not in item:
                    continue
                try:
                    pages.add(int(item["page"]))
                except (TypeError, ValueError):
                    continue
    return pages


def _current_barline_overrides(
    staging_paths: Dict[str, List[str | Path]],
) -> List[Dict[str, Any]]:
    payloads = _read_staging_payloads(staging_paths.get("barline_construction", []))
    return normalise_barline_overrides(merge_barline_overrides(*payloads))


def _manifest_pages_by_id(manifest: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    pages = manifest.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Source manifest must contain a pages list for retained-artifact rerun")
    result: Dict[str, Dict[str, Any]] = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = page.get("page_id")
        if isinstance(page_id, str) and page_id:
            result[page_id] = page
    return result


def _source_numbering_base(
    *,
    source_root: Path,
    package_root: Path,
    page: Dict[str, Any],
) -> Dict[str, Any]:
    page_id = str(page["page_id"])
    retained = source_root / "intermediate" / page_id / "numbering_base.json"
    if retained.is_file():
        payload = load_json(retained)
        if isinstance(payload, dict):
            return payload
    fallback = _resolve_package_artifact(
        package_root,
        page.get("numbering_final"),
        role=f"{page_id}.numbering_final",
    )
    payload = load_json(fallback)
    if not isinstance(payload, dict):
        raise ValueError(f"{page_id}: numbering artifact must be a JSON object")
    return payload


def _rebuild_phase_a_numbering(
    *,
    page_id: str,
    page_number: int,
    source_image: Path,
    staff_mask: Path,
    reviewed_barlines: List[List[int]],
    current_barline_overrides: List[Dict[str, Any]],
    page_index: int,
    force_single_system: bool,
) -> tuple[Dict[str, Any], List[List[int]], Dict[str, int]]:
    corrected_barlines, stats = apply_barline_overrides(
        list(reviewed_barlines),
        current_barline_overrides,
        page_index=page_index,
    )
    image = load_image(source_image)
    height, width = image.shape[:2]
    pipeline = MeasureNumberingPipeline()
    page_obj = pipeline.process_page(
        corrected_barlines,
        staff_mask,
        (width, height),
        page_number=page_number,
        assume_one_staff_per_system=force_single_system,
        image=image,
    )
    score = Score()
    score.pages.append(page_obj)
    pipeline.numberer.number_score(score, start_number=1)
    payload = score_to_dict(score)
    return payload, corrected_barlines, stats


def _remap_user_measure_overrides(
    overrides: List[Dict[str, Any]],
    *,
    page_index: int,
    source_base: Dict[str, Any],
    corrected_base: Dict[str, Any],
    barline_changed: bool,
) -> List[Dict[str, Any]]:
    page_overrides: List[Dict[str, Any]] = []
    for override in overrides:
        if int(override.get("page", -1)) != page_index:
            continue
        item = deepcopy(override)
        if not barline_changed or item.get("force_measure"):
            page_overrides.append(item)
            continue
        key = (
            page_index,
            int(item.get("system", -1)),
            int(item.get("measure", -1)),
        )
        mapped = _remap_measure_key(source_base, corrected_base, key, strict=True)
        assert mapped is not None
        item["system"] = mapped[1]
        item["measure"] = mapped[2]
        page_overrides.append(item)
    return page_overrides


def _reuse_auto_mmr_overrides(
    source_payload: Dict[str, Any],
    *,
    page_index: int,
    source_base: Dict[str, Any],
    corrected_base: Dict[str, Any],
    barline_changed: bool,
    affected_source_keys: set[tuple[int, int, int]],
    affected_corrected_keys: set[tuple[int, int, int]],
    manual_corrected_keys: set[tuple[int, int, int]],
) -> List[Dict[str, Any]]:
    reused: Dict[tuple[int, int, int], Dict[str, Any]] = {}
    for override in normalise_measure_overrides(source_payload):
        if int(override.get("page", -1)) != page_index:
            continue
        key = (
            page_index,
            int(override.get("system", -1)),
            int(override.get("measure", -1)),
        )
        if key in affected_source_keys:
            continue

        mapped = key
        if barline_changed:
            remapped = _remap_measure_key(source_base, corrected_base, key, strict=False)
            if remapped is None:
                raise ValueError(
                    f"Cannot safely reuse reviewed MMR result outside the corrected barline "
                    f"neighborhood: {key}"
                )
            mapped = remapped

        if mapped in affected_corrected_keys or mapped in manual_corrected_keys:
            continue
        item = deepcopy(override)
        item["page"], item["system"], item["measure"] = mapped
        reused[mapped] = item
    return list(reused.values())


def _current_homr_staff_mask(
    manifest_page: Dict[str, Any],
    *,
    source_root: Path,
    page_id: str,
) -> Path:
    support = manifest_page.get("mmr_support")
    if isinstance(support, dict):
        raw = support.get("current_homr_staff_mask")
        if raw:
            return _resolve_retained_artifact(
                raw,
                source_root=source_root,
                role=f"{page_id}.current_homr_staff_mask",
            )

    support_path = source_root / "intermediate" / page_id / "mmr_support.json"
    if support_path.is_file():
        payload = load_json(support_path)
        if isinstance(payload, dict):
            provenance = payload.get("provenance")
            if isinstance(provenance, dict) and provenance.get("current_homr_staff_mask"):
                return _resolve_retained_artifact(
                    provenance["current_homr_staff_mask"],
                    source_root=source_root,
                    role=f"{page_id}.current_homr_staff_mask",
                )

    raise FileNotFoundError(
        f"{page_id}: retained dense MMR support does not expose current-HOMR staff mask"
    )


def _final_numbering_from_retained_geometry(
    *,
    page_id: str,
    page_number: int,
    page_index: int,
    source_image: Path,
    staff_mask: Path,
    barlines: List[List[int]],
    force_single_system: bool,
    start_number: int,
    overrides: List[Dict[str, Any]],
    page_boundaries: List[Dict[str, Any]],
) -> tuple[Dict[str, Any], int]:
    image = load_image(source_image)
    height, width = image.shape[:2]
    pipeline = MeasureNumberingPipeline()
    page_obj = pipeline.process_page(
        barlines,
        staff_mask,
        (width, height),
        page_number=page_number,
        assume_one_staff_per_system=force_single_system,
        image=image,
    )
    score = Score()
    score.pages.append(page_obj)

    local_overrides = []
    for override in overrides:
        if int(override.get("page", -1)) != page_index:
            continue
        item = deepcopy(override)
        item["page"] = 0
        local_overrides.append(item)

    boundary_resets = {
        (0, int(boundary["system"])): int(boundary["reset_number"])
        for boundary in page_boundaries
    }
    next_number = pipeline.numberer.number_score(
        score,
        start_number=start_number,
        overrides=local_overrides,
        boundary_resets=boundary_resets,
    )
    payload = score_to_dict(score)
    payload["numbering_metadata"] = final_numbering_metadata(
        page_index=page_index,
        start_number=start_number,
        next_number=next_number,
        boundaries=page_boundaries,
    )
    return payload, next_number


def _run_retained_artifact_correction(
    *,
    normalized_handoff: Dict[str, Any],
    package_root: Path,
    source_manifest: Dict[str, Any],
    source_root: Path,
    source_config: Dict[str, Any],
    canonical_paths: Dict[str, Path],
    staging_paths: Dict[str, List[str | Path]],
    new_run_dir: Path,
) -> Dict[str, Any]:
    manifest_pages = _manifest_pages_by_id(source_manifest)
    current_barlines = _current_barline_overrides(staging_paths)
    current_correction_pages = _current_staging_pages(staging_paths)
    canonical_measure_payload = _read_json_object_if_exists(canonical_paths["measure_overrides"]) or {}
    user_measure_overrides = normalise_measure_overrides(canonical_measure_payload)
    force_single_system = bool(
        get_nested(source_config, "numbering", "force_single_system", default=False)
    )
    mmr_enabled = bool(get_nested(source_config, "steps", "mmr_overrides", default=False))
    dense_mmr = (
        str(get_nested(source_config, "detection", "detector_route", default="standard"))
        == "dense_full_pipeline"
    )

    states: List[Dict[str, Any]] = []
    execution_user_overrides: List[Dict[str, Any]] = []
    barline_stats: Dict[str, Dict[str, int]] = {}

    for page in normalized_handoff.get("pages", []):
        page_id = str(page["page_id"])
        page_number = int(page["page_number"])
        page_index = page_number - 1
        manifest_page = manifest_pages.get(page_id)
        if manifest_page is None:
            raise ValueError(f"{page_id}: page is missing from source manifest")

        source_image = _resolve_package_artifact(
            package_root,
            page.get("source_image"),
            role=f"{page_id}.source_image",
        )
        source_final_path = _resolve_package_artifact(
            package_root,
            page.get("numbering_final"),
            role=f"{page_id}.numbering_final",
        )
        source_final = load_json(source_final_path)
        if not isinstance(source_final, dict):
            raise ValueError(f"{page_id}: numbering_final must be a JSON object")

        source_base = _source_numbering_base(
            source_root=source_root,
            package_root=package_root,
            page=page,
        )
        staff_mask = _resolve_retained_artifact(
            manifest_page.get("staff_mask"),
            source_root=source_root,
            role=f"{page_id}.staff_mask",
        )
        barlines_path = _resolve_package_artifact(
            package_root,
            page.get("barlines_review"),
            role=f"{page_id}.barlines_review",
        )
        reviewed_barlines = normalize_barlines(load_json(barlines_path))
        page_current_barlines = [
            item for item in current_barlines if int(item.get("page", -1)) == page_index
        ]
        barline_changed = bool(page_current_barlines)

        if barline_changed:
            corrected_base, corrected_barlines, stats = _rebuild_phase_a_numbering(
                page_id=page_id,
                page_number=page_number,
                source_image=source_image,
                staff_mask=staff_mask,
                reviewed_barlines=reviewed_barlines,
                current_barline_overrides=page_current_barlines,
                page_index=page_index,
                force_single_system=force_single_system,
            )
        else:
            corrected_base = deepcopy(source_base)
            corrected_barlines = list(reviewed_barlines)
            stats = {
                "removed": 0,
                "added": 0,
                "remove_requests": 0,
                "unmatched_remove": 0,
            }

        page_intermediate = new_run_dir / "intermediate" / page_id
        ensure_dir(page_intermediate)
        write_json(page_intermediate / "numbering_base.json", corrected_base)
        if barline_changed:
            write_json(page_intermediate / "barlines_corrected.json", corrected_barlines)
        barline_stats[page_id] = stats

        page_execution_user = _remap_user_measure_overrides(
            user_measure_overrides,
            page_index=page_index,
            source_base=source_base,
            corrected_base=corrected_base,
            barline_changed=barline_changed,
        )
        if barline_changed and any(item.get("force_measure") for item in page_execution_user):
            raise ValueError(
                f"{page_id}: combining a barline topology correction with force_measure "
                "cannot be remapped safely; review the measure-construction correction again"
            )
        execution_user_overrides.extend(page_execution_user)

        manual_keys = {
            (
                page_index,
                int(item.get("system", -1)),
                int(item.get("measure", -1)),
            )
            for item in page_execution_user
            if not item.get("force_measure")
            and ("skip" in item or item.get("set_number") is not None)
        }

        affected_source = _barline_neighborhood_keys(
            source_base,
            page_current_barlines,
            page_index=page_index,
        )
        affected_corrected = _barline_neighborhood_keys(
            corrected_base,
            page_current_barlines,
            page_index=page_index,
        )
        mmr_targets = (affected_corrected - manual_keys) if mmr_enabled else set()

        source_mmr_payload: Dict[str, Any] = {"measure_overrides": []}
        if page.get("mmr_overrides"):
            source_mmr_path = _resolve_package_artifact(
                package_root,
                page.get("mmr_overrides"),
                role=f"{page_id}.mmr_overrides",
            )
            payload = load_json(source_mmr_path)
            if isinstance(payload, dict):
                source_mmr_payload = payload

        reused_auto = _reuse_auto_mmr_overrides(
            source_mmr_payload,
            page_index=page_index,
            source_base=source_base,
            corrected_base=corrected_base,
            barline_changed=barline_changed,
            affected_source_keys=affected_source,
            affected_corrected_keys=affected_corrected,
            manual_corrected_keys=manual_keys,
        )

        states.append(
            {
                "page": page,
                "page_id": page_id,
                "page_number": page_number,
                "page_index": page_index,
                "manifest_page": manifest_page,
                "source_image": source_image,
                "source_final": source_final,
                "source_base": source_base,
                "corrected_base": corrected_base,
                "staff_mask": staff_mask,
                "corrected_barlines": corrected_barlines,
                "barline_changed": barline_changed,
                "reused_auto": reused_auto,
                "manual_keys": manual_keys,
                "mmr_targets": mmr_targets,
                "page_intermediate": page_intermediate,
            }
        )

    applied_measure_path = new_run_dir / "review" / "applied_measure_overrides.json"
    write_json(
        applied_measure_path,
        {
            "measure_overrides": execution_user_overrides,
            "overrides": deepcopy(execution_user_overrides),
        },
    )

    mmr_states = [state for state in states if state["mmr_targets"]]
    all_targets: set[tuple[int, int, int]] = set()
    for state in mmr_states:
        all_targets.update(state["mmr_targets"])

    if mmr_states:
        model_path_raw = get_nested(source_config, "mmr", "model_path")
        if not model_path_raw:
            raise ValueError("mmr.model_path is required for selective correction rerun")
        model_path = Path(str(model_path_raw))
        enable_rotation_tta = bool(
            get_nested(source_config, "mmr", "enable_rotation_tta", default=False)
        )
        threshold = float(get_nested(source_config, "mmr", "threshold", default=0.5))
        rescue_threshold = float(
            get_nested(source_config, "mmr", "rescue_threshold", default=0.1)
        )
        rapidocr_provider = str(
            get_nested(source_config, "mmr", "rapidocr_provider", default="auto")
        )

        support_data: List[Dict[str, Any] | None] = []
        output_paths: List[Path] = []
        for state in mmr_states:
            support = None
            if dense_mmr:
                current_mask = _current_homr_staff_mask(
                    state["manifest_page"],
                    source_root=source_root,
                    page_id=state["page_id"],
                )
                support = build_mmr_support_data(state["corrected_base"], current_mask)
                write_json(state["page_intermediate"] / "mmr_support.json", support)
            support_data.append(support)
            output_paths.append(state["page_intermediate"] / "overrides_mmr_selective.json")

        import torch

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        run_mmr_batch(
            pages_data=[state["corrected_base"] for state in mmr_states],
            image_paths=[state["source_image"] for state in mmr_states],
            output_paths=output_paths,
            model_path=model_path,
            device=device,
            enable_rotation_tta=enable_rotation_tta,
            threshold=threshold,
            rescue_threshold=rescue_threshold,
            rapidocr_provider=rapidocr_provider,
            support_data=support_data,
            target_measure_keys=all_targets,
        )

    selective_count = 0
    reused_count = 0
    for state in states:
        auto_by_key: Dict[tuple[int, int, int], Dict[str, Any]] = {}
        for item in state["reused_auto"]:
            key = (
                int(item.get("page", -1)),
                int(item.get("system", -1)),
                int(item.get("measure", -1)),
            )
            auto_by_key[key] = item
        reused_count += len(auto_by_key)

        selective_path = state["page_intermediate"] / "overrides_mmr_selective.json"
        if selective_path.is_file():
            selective_payload = load_json(selective_path)
            if isinstance(selective_payload, dict):
                for item in normalise_measure_overrides(selective_payload):
                    key = (
                        int(item.get("page", -1)),
                        int(item.get("system", -1)),
                        int(item.get("measure", -1)),
                    )
                    auto_by_key[key] = item
                    selective_count += 1

        state["auto_mmr"] = list(auto_by_key.values())
        write_json(
            state["page_intermediate"] / "overrides_mmr.json",
            {
                "measure_overrides": state["auto_mmr"],
                "overrides": deepcopy(state["auto_mmr"]),
            },
        )

    movement_boundaries = load_movement_boundary_payload(
        get_nested(source_config, "inputs", "movement_boundaries")
    )
    current_number = 1
    reused_final_pages: List[str] = []
    rebuilt_final_pages: List[str] = []

    for state in states:
        page_id = state["page_id"]
        page_index = state["page_index"]
        page_outputs = new_run_dir / "outputs" / page_id
        ensure_dir(page_outputs)
        final_path = page_outputs / "numbering_final.json"
        source_metadata = state["source_final"].get("numbering_metadata")
        source_start = (
            source_metadata.get("start_number")
            if isinstance(source_metadata, dict)
            else None
        )
        source_next = (
            source_metadata.get("next_number")
            if isinstance(source_metadata, dict)
            else None
        )

        page_has_new_correction = page_index in current_correction_pages
        can_reuse_final = (
            not page_has_new_correction
            and not state["barline_changed"]
            and source_start == current_number
            and isinstance(source_next, int)
        )
        if can_reuse_final:
            write_json(final_path, state["source_final"])
            current_number = source_next
            reused_final_pages.append(page_id)
            continue

        page_overrides = list(state["auto_mmr"]) + [
            item
            for item in execution_user_overrides
            if int(item.get("page", -1)) == page_index
        ]
        page_boundaries = movement_boundaries_for_page(movement_boundaries, page_index)
        final_payload, current_number = _final_numbering_from_retained_geometry(
            page_id=page_id,
            page_number=state["page_number"],
            page_index=page_index,
            source_image=state["source_image"],
            staff_mask=state["staff_mask"],
            barlines=state["corrected_barlines"],
            force_single_system=force_single_system,
            start_number=current_number,
            overrides=page_overrides,
            page_boundaries=page_boundaries,
        )
        write_json(final_path, final_payload)
        rebuilt_final_pages.append(page_id)

    return {
        "rerun_mode": "retained_artifacts_selective",
        "upstream_inference_rerun": False,
        "barline_override_stats": barline_stats,
        "mmr_target_measure_keys": [list(key) for key in sorted(all_targets)],
        "mmr_target_count": len(all_targets),
        "mmr_selective_override_count": selective_count,
        "mmr_reused_override_count": reused_count,
        "applied_measure_overrides": str(applied_measure_path),
        "reused_final_pages": reused_final_pages,
        "rebuilt_final_pages": rebuilt_final_pages,
    }


def apply_corrections_and_rerun(
    handoff_path: str | Path,
    config_path: Optional[str | Path] = None,
    output_root: Optional[str | Path] = None,
    run_id: Optional[str] = None,
    overwrite: bool = False,
    dry_run: bool = False,
    generate_final_pdf: bool = False,
    output_name: Optional[str] = None,
) -> Path:
    """Apply manual corrections and trigger a corrected pipeline rerun."""
    handoff_path = Path(handoff_path).resolve()
    package_root = handoff_path.parent

    # 1. Load & validate handoff
    raw_payload = load_manual_correction_handoff(handoff_path)
    normalized = validate_manual_correction_handoff(
        raw_payload, handoff_path=handoff_path, mode="base_v1"
    )

    # Collect custom staging paths from normalized handoff
    staging_paths: Dict[str, List[str | Path]] = {
        "mmr_measure_span": [],
        "measure_construction": [],
        "barline_construction": [],
    }
    for page in normalized.get("pages", []):
        manual_outputs = page.get("manual_outputs", {})
        for key in staging_paths:
            if key in manual_outputs and manual_outputs[key]:
                staging_paths[key].append(package_root / manual_outputs[key])

    # 2. Resolve the reviewed source run. The retained source manifest is required
    # for a real correction rerun even when an explicit config is supplied, because
    # the correction path reuses reviewed detector/MMR artifacts rather than
    # regenerating them.
    manifest_path = _resolve_source_manifest_path(normalized, package_root)
    source_manifest: Dict[str, Any] | None = None
    if manifest_path.exists():
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw_manifest, dict):
            raise ValueError("manifest.json must be a JSON object.")
        source_manifest = raw_manifest

    source_config: Dict[str, Any] = {}
    config_base_dir: Path | None = None
    if config_path:
        source_config_path = Path(config_path).resolve()
        config_base_dir = source_config_path.parent
        if source_config_path.suffix in (".yaml", ".yml"):
            source_config = load_yaml(source_config_path)
        else:
            source_config = json.loads(source_config_path.read_text(encoding="utf-8"))
        if not isinstance(source_config, dict):
            raise ValueError("Source configuration must be a dictionary/mapping.")
    else:
        if source_manifest is None:
            raise FileNotFoundError(f"Source manifest not found: {manifest_path}")
        config_base_dir = manifest_path.parent
        if "config" not in source_manifest:
            raise ValueError("manifest.json does not contain a 'config' key.")
        source_config = source_manifest["config"]
        if not isinstance(source_config, dict):
            raise ValueError("Source configuration must be a dictionary/mapping.")

    if not output_root and source_manifest is not None:
        output_root = manifest_path.parent.parent

    existing_override_inputs = _read_existing_override_inputs(
        source_config=source_config,
        config_base_dir=config_base_dir,
    )

    # 3. Canonicalize outputs
    corrections_dir = package_root / "corrections"
    canonical_paths = canonicalize_manual_correction_outputs(
        corrections_dir,
        overwrite=overwrite,
        staging_paths=staging_paths,
    )

    carried_forward = _merge_existing_override_inputs(
        canonical_paths=canonical_paths,
        existing_override_inputs=existing_override_inputs,
        staging_paths=staging_paths,
    )

    # 4. Create rerun config
    rerun_config = deepcopy(source_config)

    if not isinstance(rerun_config.get("inputs"), dict):
        rerun_config["inputs"] = {}

    rerun_config["inputs"]["measure_overrides"] = str(canonical_paths["measure_overrides"])
    rerun_config["inputs"]["barline_overrides"] = str(canonical_paths["barline_overrides"])

    if not isinstance(rerun_config.get("steps"), dict):
        rerun_config["steps"] = {}
    # The corrected run is retained-artifact based. These flags describe the
    # execution contract and also prevent this config from being mistaken for a
    # fresh detector rerun if inspected later.
    rerun_config["steps"]["pdf_to_images"] = False
    rerun_config["steps"]["detection"] = False
    rerun_config["steps"]["apply_measure_overrides"] = True
    rerun_config["steps"]["apply_barline_overrides"] = True
    rerun_config["correction_rerun"] = {
        "mode": "retained_artifacts_selective",
        "source_manifest": str(manifest_path),
        "upstream_inference_rerun": False,
    }

    if not isinstance(rerun_config.get("outputs"), dict):
        rerun_config["outputs"] = {}
    if not isinstance(rerun_config["outputs"].get("review"), dict):
        rerun_config["outputs"]["review"] = {}

    # Avoid infinite recursion of review package generation
    rerun_config["outputs"]["review"]["manual_correction_package"] = False

    # 5. Setup new run dir
    run_id_value = run_id or f"corrected_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if output_root:
        out_root = Path(output_root)
    else:
        # Default to the same root as the original run
        out_root = package_root.parent.parent

    new_run_dir = out_root / run_id_value
    ensure_dir(new_run_dir)

    new_config_path = new_run_dir / "corrected_pipeline_config.json"
    new_config_path.write_text(
        json.dumps(rerun_config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    summary = {
        "source_handoff": str(handoff_path),
        "measure_overrides": str(canonical_paths["measure_overrides"]),
        "barline_overrides": str(canonical_paths["barline_overrides"]),
        **carried_forward,
        "rerun_mmr_overrides_enabled": bool(rerun_config["steps"].get("mmr_overrides", False)),
        "run_id": run_id_value,
        "output_dir": str(new_run_dir),
        "generate_final_pdf": generate_final_pdf,
        "final_pdf": None,
        "corrected_final_summary": None,
    }

    _write_apply_summary(summary, new_run_dir, corrections_dir)

    if dry_run:
        logger.info(f"Dry run. Would execute pipeline with config: {new_config_path}")
        return new_run_dir

    # 6. Execute only the downstream correction boundary against retained
    # reviewed artifacts. Do not regenerate PDF images, detector/HOMR/SR/OMR-DLN,
    # probe candidates, or CNN scores.
    if source_manifest is None:
        raise FileNotFoundError(
            f"Source manifest is required for retained-artifact correction rerun: {manifest_path}"
        )
    logger.info(f"Executing retained-artifact corrected rerun: {run_id_value}")
    selective_summary = _run_retained_artifact_correction(
        normalized_handoff=normalized,
        package_root=package_root,
        source_manifest=source_manifest,
        source_root=manifest_path.parent,
        source_config=source_config,
        canonical_paths=canonical_paths,
        staging_paths=staging_paths,
        new_run_dir=new_run_dir,
    )
    summary.update(selective_summary)
    _write_apply_summary(summary, new_run_dir, corrections_dir)

    if generate_final_pdf:
        final_summary = materialize_corrected_final_outputs(
            handoff_path=handoff_path,
            corrected_run_dir=new_run_dir,
            final_root=new_run_dir / "final",
            review_root=new_run_dir / "review",
            output_name=output_name,
        )
        summary["final_pdf"] = final_summary.get("final_pdf")
        summary["corrected_final_summary"] = final_summary.get("summary_path")
        _write_apply_summary(summary, new_run_dir, corrections_dir)

    return new_run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply manual corrections and rerun the pipeline.")
    parser.add_argument("handoff", type=Path, help="Path to review/manual_correction_input.json")
    parser.add_argument("--config", type=Path, help="Path to original pipeline config (yaml/json).")
    parser.add_argument("--output-root", type=Path, help="Root directory for the corrected run.")
    parser.add_argument("--run-id", type=str, help="Run ID for the corrected run.")
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing canonical override files."
    )
    parser.add_argument("--dry-run", action="store_true", help="Dry run.")
    parser.add_argument(
        "--generate-final-pdf",
        action="store_true",
        help="After the corrected rerun, generate final/<output-name>_score_numbered.pdf.",
    )
    parser.add_argument(
        "--output-name",
        type=str,
        help="Optional output name used for final/<output-name>_score_numbered.pdf.",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    apply_corrections_and_rerun(
        handoff_path=args.handoff,
        config_path=args.config,
        output_root=args.output_root,
        run_id=args.run_id,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        generate_final_pdf=args.generate_final_pdf,
        output_name=args.output_name,
    )


if __name__ == "__main__":
    main()
