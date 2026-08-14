"""Fresh Phase-A connector-semantic replay for Issue #264 Phase C.

The frozen detector replay retains the accepted Proxy/SR staff geometry and detector
barlines, but Phase A also requires current-runtime HOMR connector semantics in
source-page coordinates.  The canonical detector run's retained current-support
artifacts predate the Phase-A coordinate fix, so Phase C must not silently reuse
those stale x4 masks.

This helper reruns only current HOMR on the already-retained canonical x4 SR image.
It does not rerun detector inference, CNN scoring, Real-ESRGAN, or OMR-DLN.  The
fresh semantic artifacts are written under the Phase-C run directory beside a
mirrored copy of the canonical Proxy/SR staff mask, so normal production numbering
resolution can discover them without mutating the accepted detector artifacts.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

from src.common.connector_artifacts import describe_connector_artifacts
from src.pipeline.core.config import load_yaml
from src.pipeline.detection.current_homr_worker import run as run_current_homr


def _completed_current_homr_result(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        return None
    if payload.get("historical_detector_artifact_runtime_input") is not False:
        return None
    if payload.get("connector_complete") is not True:
        return None
    return payload


def ensure_phase_a_semantic_support(
    *,
    score: str,
    page_name: str,
    source_image: Path,
    canonical_staff_mask: Path,
    replay_root: Path,
    detection_config: dict[str, Any],
    resume: bool,
) -> tuple[Path, dict[str, Any]]:
    """Return a Proxy/SR staff path backed by fresh current-HOMR semantics."""

    canonical_sr_image = canonical_staff_mask.parent / f"{page_name}.png"
    if not canonical_staff_mask.is_file():
        raise FileNotFoundError(canonical_staff_mask)
    if not canonical_sr_image.is_file():
        raise FileNotFoundError(
            f"Retained canonical x4 SR image is missing for {score}/{page_name}: "
            f"{canonical_sr_image}"
        )

    score_root = replay_root / score
    mirrored_staff = (
        score_root
        / "sr"
        / "batch"
        / page_name
        / canonical_staff_mask.name
    )
    mirrored_staff.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(canonical_staff_mask, mirrored_staff)

    support_page_root = (
        score_root / "current_support" / score / page_name / "artifacts"
    )
    homr_root = support_page_root / "current_homr"
    request_path = support_page_root / "current_homr_request.json"
    result_path = support_page_root / "current_homr_result.json"

    result_payload = _completed_current_homr_result(result_path) if resume else None
    reused = result_payload is not None
    if result_payload is None:
        request = {
            "schema_version": "issue264.phase_c_phase_a_current_homr_request.v1",
            "detection": dict(detection_config),
            "image": str(source_image),
            "sr_image": str(canonical_sr_image),
            "output_root": str(homr_root),
        }
        request_path.parent.mkdir(parents=True, exist_ok=True)
        request_path.write_text(
            json.dumps(request, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        run_current_homr(request_path, result_path)
        result_payload = _completed_current_homr_result(result_path)
        if result_payload is None:
            raise RuntimeError(f"Incomplete Phase-A current-HOMR replay: {result_path}")

    connector_description = describe_connector_artifacts(mirrored_staff)
    if connector_description.get("source") != "proxy_symbol_layers":
        raise RuntimeError(
            "Fresh Phase-A connector semantics were not resolved for "
            f"{score}/{page_name}: {connector_description}"
        )

    return mirrored_staff, {
        "score": score,
        "page_name": page_name,
        "source_image": str(source_image),
        "canonical_proxy_staff_mask": str(canonical_staff_mask),
        "canonical_x4_sr_image": str(canonical_sr_image),
        "mirrored_proxy_staff_mask": str(mirrored_staff),
        "current_homr_result": str(result_path),
        "current_homr_staff_mask": result_payload.get("staff_mask"),
        "connector_complete": result_payload.get("connector_complete") is True,
        "historical_detector_artifact_runtime_input": result_payload.get(
            "historical_detector_artifact_runtime_input"
        ),
        "reused": reused,
        "connector_artifacts": connector_description,
    }


def install_phase_a_support_replay(
    runner: Any,
    *,
    run_dir: Path,
    resume: bool,
) -> dict[str, dict[str, Any]]:
    """Patch the Phase-C runner's canonical path resolver for this process only."""

    config = load_yaml(runner.CANONICAL_CONFIG)
    detection_config = config.get("detection") or {}
    if not isinstance(detection_config, dict):
        raise ValueError("Canonical detection configuration must be a mapping")

    original_resolver: Callable[[str, str, str], tuple[Path, Path, Path]] = (
        runner._canonical_paths
    )
    replay_root = run_dir / "phase_a_hybrid_replay"
    provenance: dict[str, dict[str, Any]] = {}

    def resolve(score: str, page_name: str, image_stem: str) -> tuple[Path, Path, Path]:
        image, barlines, canonical_staff = original_resolver(score, page_name, image_stem)
        mirrored_staff, detail = ensure_phase_a_semantic_support(
            score=score,
            page_name=page_name,
            source_image=image,
            canonical_staff_mask=canonical_staff,
            replay_root=replay_root,
            detection_config=detection_config,
            resume=resume,
        )
        provenance[image_stem] = detail
        return image, barlines, mirrored_staff

    runner._canonical_paths = resolve
    return provenance


def augment_report(
    report_path: Path,
    *,
    support_provenance: dict[str, dict[str, Any]],
) -> None:
    """Add replay and Phase-B fallback provenance without changing score semantics."""

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    pages = payload.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Phase C report lacks pages")

    fallback_pages: list[str] = []
    support_pages: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        score = str(page.get("score", ""))
        score_page = str(page.get("score_page", ""))
        image_stem = f"{score}_{score_page}"
        support = support_provenance.get(image_stem)
        if support is not None:
            page["phase_a_semantic_support"] = support
            support_pages.append(support)

        page_id = str(page.get("page_id", ""))
        run_dir = report_path.parent
        intermediate = run_dir / "intermediate" / page_id
        candidate_path = intermediate / "numbering_mmr_geometry_candidate.json"
        if candidate_path.is_file():
            fallback_pages.append(page_id)
            base_path = intermediate / "numbering_base.json"
            effective_path = intermediate / "numbering_mmr_geometry.json"
            from tools.issue264.run_phase_c_mmr_regression import physical_counts
            from src.pipeline.utils.io import load_json

            page["mmr_layout_decision"] = {
                "numbering_geometry_source": "phase_a_base_fallback",
                "fallback_reason": "index_layout_mismatch",
                "base_layout_signature": physical_counts(load_json(base_path)),
                "candidate_layout_signature": physical_counts(load_json(candidate_path)),
                "effective_layout_signature": physical_counts(load_json(effective_path)),
                "rejected_candidate_numbering_path": str(candidate_path),
            }
        else:
            page["mmr_layout_decision"] = {
                "numbering_geometry_source": "fresh_current_homr",
                "fallback_reason": None,
            }

    payload.setdefault("evaluation_inputs", {})["phase_a_semantic_support"] = {
        "producer": "src.pipeline.detection.current_homr_worker",
        "runtime_input": "retained canonical x4 SR images",
        "detector_reexecuted": False,
        "real_esrgan_reexecuted": False,
        "omr_dln_reexecuted": False,
        "historical_detector_artifact_runtime_input": False,
        "pages": len(support_pages),
    }
    payload["phase_b_layout_fallback"] = {
        "count": len(fallback_pages),
        "pages": fallback_pages,
    }
    gates = payload.setdefault("gates", {})
    gates["phase_a_fresh_current_homr_semantics_68"] = (
        len(support_pages) == 68
        and all(item.get("connector_complete") is True for item in support_pages)
        and all(
            item.get("historical_detector_artifact_runtime_input") is False
            for item in support_pages
        )
    )
    payload["status"] = "passed" if all(bool(value) for value in gates.values()) else "failed"
    report_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
