import hashlib
import json
from pathlib import Path

import pytest

from tools.issue255.run_public_baseline_stage_e_reconstruction import (
    _find_historical_mask,
    _fresh_contract_matches,
    _load_public_sources,
    _resolve_repo_artifact,
)


def _write(path: Path, content: bytes | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content if content is not None else path.name.encode())
    return path


def _record(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "exists": True,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _public_run(
    root: Path,
    *,
    label: str,
    score: str,
    page: str,
) -> dict[str, object]:
    image = _write(root / "data/evaluation2/images" / score / f"{page}.png")
    baseline = _write(
        root / "logs/hybrid" / label / "baseline/batch" / page / f"{page}_detections.json"
    )
    sr = _write(root / "logs/hybrid" / label / "sr/batch" / page / f"{page}_detections.json")
    omr = _write(root / "logs/hybrid" / label / "omr_sr" / page / "predictions.json")
    hybrid = _write(root / "logs/hybrid" / label / "hybrid_results" / f"{page}_hybrid.json")
    final = _write(root / "logs/probe" / label / "pipeline2_no_peak_filtered_cnn.json")
    _write(baseline.parent / f"{page}_proxy_debug_3_staff.png")
    _write(baseline.parent / f"{page}_proxy_debug_7_clefs_keys.png")

    baseline_hash = hashlib.sha256(baseline.read_bytes()).hexdigest()
    return {
        "label": label,
        "score": score,
        "page": page,
        "run_id": f"run_{label}",
        "contract": {
            "status": "completed",
            "variant": "public_baseline",
            "detector_input_contract": {
                "mode": "fresh_upstream",
                "fresh_upstream_authoritative": True,
                "override_keys": [],
            },
            "baseline_profile_handoff": {
                "status": "completed",
                "freshly_generated": True,
                "historical_artifact_used_as_runtime_input": False,
                "detection_sha256": baseline_hash,
                "homr_commit": "historical-homr",
            },
            "artifacts": {
                "image": _record(image),
                "fresh_baseline": _record(baseline),
                "current_sr": _record(sr),
                "current_omr": _record(omr),
                "hybrid": _record(hybrid),
                "cnn_accepted": _record(final),
            },
        },
    }


def test_fresh_contract_matches_required_fields_with_extra_metadata() -> None:
    assert _fresh_contract_matches(
        {
            "mode": "fresh_upstream",
            "fresh_upstream_authoritative": True,
            "override_keys": [],
            "schema_version": "pipeline.detector_input_contract.v1",
            "hybrid_detection_may_execute": True,
        }
    )


def test_fresh_contract_rejects_wrong_required_field() -> None:
    assert not _fresh_contract_matches(
        {
            "mode": "fresh_upstream",
            "fresh_upstream_authoritative": False,
            "override_keys": [],
            "schema_version": "pipeline.detector_input_contract.v1",
        }
    )


def test_resolve_repo_artifact_remaps_host_checkout_path(tmp_path: Path) -> None:
    root = tmp_path / "PDFScoreBar"
    expected = _write(root / "logs/example.json")
    host_path = Path("/home/user/ws/PDFScoreBar/logs/example.json")

    assert _resolve_repo_artifact(host_path, root) == expected.resolve()


def test_find_historical_mask_prefers_baseline_proxy_debug(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    sr = tmp_path / "sr"
    preferred = _write(baseline / "page_004_proxy_debug_3_staff.png")
    _write(sr / "page_004_staff_mask.png")

    actual = _find_historical_mask(
        (baseline, sr),
        (
            "{stem}_proxy_debug_3_staff.png",
            "{stem}_staff_mask.png",
        ),
        stem="page_004",
        name="staff mask",
    )

    assert actual == preferred.resolve()


def test_load_public_sources_validates_two_fresh_pages(tmp_path: Path) -> None:
    pages = [
        {
            "label": "prokofiev",
            "score": "score_a",
            "page": "page_004",
        },
        {
            "label": "shostakovich",
            "score": "score_b",
            "page": "page_014",
        },
    ]
    batch = tmp_path / "public_batch.json"
    batch.write_text(
        json.dumps(
            {
                "status": "completed",
                "variant": "public_baseline",
                "runs": [
                    _public_run(
                        tmp_path,
                        label="prokofiev",
                        score="score_a",
                        page="page_004",
                    ),
                    _public_run(
                        tmp_path,
                        label="shostakovich",
                        score="score_b",
                        page="page_014",
                    ),
                ],
            }
        ),
        encoding="utf-8",
    )

    sources = _load_public_sources(batch, pages)

    assert set(sources) == {"prokofiev", "shostakovich"}
    assert sources["prokofiev"]["staff_mask"].name.endswith("_proxy_debug_3_staff.png")
    assert sources["prokofiev"]["clef_mask"].name.endswith("_proxy_debug_7_clefs_keys.png")
    assert sources["prokofiev"]["fresh_contract"]["override_keys"] == []


def test_load_public_sources_rejects_historical_runtime_input(
    tmp_path: Path,
) -> None:
    page = {
        "label": "prokofiev",
        "score": "score_a",
        "page": "page_004",
    }
    run = _public_run(
        tmp_path,
        label="prokofiev",
        score="score_a",
        page="page_004",
    )
    run["contract"]["baseline_profile_handoff"]["historical_artifact_used_as_runtime_input"] = True
    batch = tmp_path / "public_batch.json"
    batch.write_text(
        json.dumps(
            {
                "status": "completed",
                "variant": "public_baseline",
                "runs": [run],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Historical runtime input detected"):
        _load_public_sources(batch, [page])
