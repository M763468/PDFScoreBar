import json
from pathlib import Path

from tools.issue255.inspect_public_baseline_stage_e_sources import build_report


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _run(tmp_path: Path, label: str, score: str, page: str) -> dict[str, object]:
    root = tmp_path / label
    image = root / "images" / score / f"{page}.png"
    baseline = root / "hybrid" / "baseline" / "batch" / page / f"{page}_detections.json"
    sr = root / "hybrid" / "sr" / "batch" / page / f"{page}_detections.json"
    omr = root / "hybrid" / "omr_sr" / page / "predictions.json"
    hybrid = root / "hybrid" / "hybrid_results" / f"{page}_hybrid.json"
    staff = baseline.parent / f"{page}_proxy_debug_3_staff.png"
    clef = baseline.parent / f"{page}_proxy_debug_7_clefs_keys.png"
    for path in (image, baseline, sr, omr, hybrid, staff, clef):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(path.name.encode())

    import hashlib

    baseline_hash = hashlib.sha256(baseline.read_bytes()).hexdigest()
    contract = {
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
            "pdfscore_evaluator_commit": "historical-evaluator",
            "provenance_path": str(root / "provenance.json"),
        },
        "artifacts": {
            "image": {"path": str(image)},
            "fresh_baseline": {"path": str(baseline)},
            "current_sr": {"path": str(sr)},
            "current_omr": {"path": str(omr)},
            "hybrid": {"path": str(hybrid)},
        },
    }
    return {
        "label": label,
        "score": score,
        "page": page,
        "run_id": f"run_{label}",
        "contract": contract,
    }


def test_build_report_accepts_complete_fresh_public_sources(tmp_path: Path) -> None:
    batch = tmp_path / "public_batch.json"
    _write_json(
        batch,
        {
            "status": "completed",
            "variant": "public_baseline",
            "runs": [
                _run(tmp_path, "prokofiev", "score_a", "page_004"),
                _run(tmp_path, "shostakovich", "score_b", "page_014"),
            ],
        },
    )

    report = build_report(batch)

    assert report["gates"] == {
        "all_public_baselines_preserved": True,
        "all_fresh_contracts_exact": True,
        "all_stage_e_replay_inputs_complete": True,
        "next_gpu_run_required": False,
    }
    assert report["pages"]["prokofiev"]["artifacts"]["staff_masks"]
    assert report["pages"]["prokofiev"]["artifacts"]["clef_masks"]
    assert report["historical_detector_candidate_runtime_inputs"] == []
