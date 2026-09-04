#!/usr/bin/env python3
"""Compare Issue #294 baseline candidates at PDFScoreBar's operational boundary.

Current-x4 HOMR/OMR support and the production CNN are fixed for every variant.
The matrix runs both a frozen-A geometry replay for causal diagnosis and a
candidate-native staff/clef replay for the actual operational gate.  Each
variant passes through hybrid consensus, dense candidate reconstruction, CNN
scoring and MeasureNumberingPipeline.  MusicXML and direct GT are not gates.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import cv2
import yaml

from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.pipeline.detection.current_support_worker import run as run_current_support
from src.pipeline.detector_routes.dense_full_pipeline import reconstruct_dense_full_pipeline_route
from src.pipeline.steps.barlines import normalize_barlines
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch
from src.pipeline.steps.hybrid_consensus import apply_hybrid_consensus_filter, load_json_boxes

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_PYTHON = Path("/opt/venv_pipeline/bin/python")
PRODUCTION_CONFIG = PROJECT_ROOT / "configs/dense_full_pipeline.yaml"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _one(paths: list[Path], description: str) -> Path:
    unique = {str(path.resolve()): path.resolve() for path in paths if path.is_file()}
    if len(unique) != 1:
        raise RuntimeError(f"Expected one {description}, found {len(unique)}: {sorted(unique)}")
    return next(iter(unique.values()))


def _control_geometry(a_detection: Path, stem: str) -> dict[str, Path]:
    page_root = a_detection.parent
    return {
        "staff": _one(
            list(page_root.glob(f"{stem}*_debug_3_staff.png")),
            "historical control staff mask",
        ),
        "clef": _one(
            list(page_root.glob(f"{stem}*_debug_7_clefs_keys.png")),
            "historical control clef mask",
        ),
    }


def _candidate_paths(page: dict[str, Any]) -> tuple[Path, Path]:
    a = page.get("A_pinned")
    b = page.get("B_maintained")
    if not isinstance(a, dict) or not isinstance(b, dict):
        raise ValueError("A/B page payload missing")
    a_artifacts = a.get("artifacts")
    b_worker = b.get("worker")
    if not isinstance(a_artifacts, dict) or not isinstance(b_worker, dict):
        raise ValueError("A/B artifact payload missing")
    b_artifacts = b_worker.get("artifacts")
    if not isinstance(b_artifacts, dict):
        raise ValueError("B worker artifacts missing")
    return (
        Path(str(a_artifacts["detections"])).resolve(),
        Path(str(b_artifacts["detections"])).resolve(),
    )


def _load_production_detection() -> dict[str, Any]:
    payload = yaml.safe_load(PRODUCTION_CONFIG.read_text(encoding="utf-8"))
    detection = payload.get("detection") if isinstance(payload, dict) else None
    if not isinstance(detection, dict):
        raise ValueError(f"Missing detection config: {PRODUCTION_CONFIG}")
    return dict(detection)


def _generate_fixed_support(image: Path, output_root: Path) -> dict[str, Any]:
    request_path = output_root / "request.json"
    result_path = output_root / "result.json"
    request_path.parent.mkdir(parents=True, exist_ok=False)
    request = {
        "schema_version": "issue294.downstream_fixed_support_request.v1",
        "detection": _load_production_detection(),
        "image": str(image),
        "output_root": str(output_root / "artifacts"),
    }
    request_path.write_text(json.dumps(request, indent=2, ensure_ascii=False) + "\n")
    run_current_support(request_path, result_path)
    result = load_json(result_path)
    if not isinstance(result, dict) or result.get("status") != "completed":
        raise ValueError(f"Incomplete fixed support: {result_path}")
    for key in (
        "current_sr_detection",
        "current_omr",
        "current_homr_staff_mask",
        "connector_symbols",
        "connector_brace_dot",
    ):
        path = Path(str(result.get(key, "")))
        if not path.is_file():
            raise FileNotFoundError(f"Fixed support {key}: {path}")
    if result.get("connector_complete") is not True:
        raise RuntimeError("Fixed support connector contract failed")
    return result


def _run_detector_material(
    *,
    label: str,
    image: Path,
    homr_source: Path,
    homr_commit: str,
    output_root: Path,
) -> dict[str, Any]:
    result_path = output_root.parent / f"{label}_result.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(homr_source), str(PROJECT_ROOT)])
    command = [
        str(PIPELINE_PYTHON),
        str(PROJECT_ROOT / "tools/issue294/run_latest_homr_detector_original.py"),
        "--image",
        str(image),
        "--homr-source",
        str(homr_source),
        "--homr-commit",
        homr_commit,
        "--output-root",
        str(output_root),
        "--result",
        str(result_path),
    ]
    process = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    (output_root.parent / f"{label}.log").write_text(process.stdout or "", encoding="utf-8")
    if process.returncode != 0:
        raise RuntimeError(
            f"{label} detector-material run failed ({process.returncode}):\n{process.stdout}"
        )
    result = load_json(result_path)
    if not isinstance(result, dict) or result.get("status") != "completed":
        raise ValueError(f"Incomplete detector-material candidate: {result_path}")
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError(f"Detector-material artifacts missing: {result_path}")
    for key in ("detections", "staff_mask", "clef_mask"):
        path = Path(str(artifacts.get(key, "")))
        if not path.is_file():
            raise FileNotFoundError(f"{label} {key}: {path}")
    return result


def _score_signature(score: Any) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    for page in score.pages:
        systems: list[dict[str, Any]] = []
        for system in page.systems:
            measures = list(system.measures)
            systems.append(
                {
                    "staff_count": len(system.staves),
                    "measure_count": len(measures),
                    "measure_numbers": [measure.number for measure in measures],
                    "measure_bboxes": [
                        [measure.bbox.x1, measure.bbox.y1, measure.bbox.x2, measure.bbox.y2]
                        for measure in measures
                    ],
                }
            )
        pages.append(
            {
                "page_number": page.page_number,
                "system_count": len(page.systems),
                "systems": systems,
                "total_measures": sum(item["measure_count"] for item in systems),
            }
        )
    return {"pages": pages, "total_measures": sum(page["total_measures"] for page in pages)}


def _run_downstream_variant(
    *,
    label: str,
    image: Path,
    baseline_detection: Path,
    support: dict[str, Any],
    staff_mask: Path,
    clef_mask: Path,
    output_root: Path,
    detection_config: dict[str, Any],
) -> dict[str, Any]:
    variant_root = output_root / label
    variant_root.mkdir(parents=True, exist_ok=False)
    baseline_boxes = [list(box) for box in load_json_boxes(baseline_detection)]
    current_boxes = [
        list(box) for box in load_json_boxes(Path(str(support["current_sr_detection"])))
    ]
    omr_boxes = [list(box) for box in load_json_boxes(Path(str(support["current_omr"])))]
    hybrid = [
        list(box)
        for box in apply_hybrid_consensus_filter(
            baseline_boxes=baseline_boxes,
            sr_boxes=current_boxes,
            omr_boxes=omr_boxes,
        )
    ]
    hybrid_path = variant_root / "hybrid.json"
    hybrid_path.write_text(json.dumps(hybrid, indent=2) + "\n")

    inventory = variant_root / "inventory.json"
    exclude = variant_root / "exclude.json"
    inventory.write_text(
        json.dumps(
            {
                "schema_version": "issue294.downstream_matrix_inventory.v1",
                "historical_detector_artifact_runtime_input": False,
                "records": [
                    {
                        "score": image.parent.name,
                        "page": image.stem,
                        "image": str(image),
                        "hybrid_predictions": str(hybrid_path),
                        "staff_mask": str(staff_mask),
                        "clef_mask": str(clef_mask),
                        "run_dir": str(staff_mask.parent),
                    }
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    exclude.write_text('{"excluded_pages": []}\n')

    dense = reconstruct_dense_full_pipeline_route(
        inventory=inventory,
        exclude=exclude,
        route_root=variant_root / "dense_route",
        expected_pages=1,
    )
    cnn_model = Path(str(detection_config["cnn_model_path"])).resolve()
    if not cnn_model.is_file():
        raise FileNotFoundError(cnn_model)
    run_cnn_scoring_batch(
        probe_output_root=dense.probe_rescue_root,
        images=[image],
        model_path=cnn_model,
        threshold=float(detection_config.get("cnn_threshold", 0.1)),
        score_name=(
            str(detection_config["probe_score_name"])
            if detection_config.get("probe_score_name")
            else None
        ),
        crop_recenter_on_bbox_ink=bool(detection_config.get("crop_recenter_on_bbox_ink", False)),
        crop_recenter_max_shift_unit_ratio=float(
            detection_config.get("crop_recenter_max_shift_unit_ratio", 0.35)
        ),
        input_image_scale=1.0,
        bands_from=dense.filtered_root,
        staff_vov_threshold=float(detection_config.get("staff_vov_threshold", 0.5)),
        apply_nms_enabled=False,
        in_memory_images=None,
    )
    cnn_path = _one(
        list(dense.probe_rescue_root.rglob("pipeline2_no_peak_filtered_cnn.json")),
        f"{label} CNN-filtered barline output",
    )
    final_barlines = normalize_barlines(load_json(cnn_path))

    image_data = cv2.imread(str(image))
    if image_data is None:
        raise FileNotFoundError(image)
    height, width = image_data.shape[:2]
    numbering = MeasureNumberingPipeline().run_sequential(
        [
            {
                "barlines": final_barlines,
                "staff_mask": str(staff_mask),
                "image_size": (width, height),
                "page_number": 1,
                "connector_mask_paths": {
                    "symbols": str(support["connector_symbols"]),
                    "brace_dot": str(support["connector_brace_dot"]),
                },
            }
        ]
    )
    return {
        "label": label,
        "baseline_detection": str(baseline_detection),
        "staff_mask": str(staff_mask),
        "clef_mask": str(clef_mask),
        "baseline_count": len(baseline_boxes),
        "hybrid_path": str(hybrid_path),
        "hybrid_count": len(hybrid),
        "final_cnn_barlines": str(cnn_path),
        "final_barline_count": len(final_barlines),
        "final_barlines": final_barlines,
        "numbering": _score_signature(numbering),
    }


def _comparison(control: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    control_pages = control["numbering"]["pages"]
    candidate_pages = candidate["numbering"]["pages"]
    control_topology = [
        [system["staff_count"], system["measure_count"]]
        for page in control_pages
        for system in page["systems"]
    ]
    candidate_topology = [
        [system["staff_count"], system["measure_count"]]
        for page in candidate_pages
        for system in page["systems"]
    ]
    control_numbers = [
        number
        for page in control_pages
        for system in page["systems"]
        for number in system["measure_numbers"]
    ]
    candidate_numbers = [
        number
        for page in candidate_pages
        for system in page["systems"]
        for number in system["measure_numbers"]
    ]
    operational = {
        "final_barline_count_equal": candidate["final_barline_count"]
        == control["final_barline_count"],
        "total_measures_equal": candidate["numbering"]["total_measures"]
        == control["numbering"]["total_measures"],
        "system_measure_topology_equal": candidate_topology == control_topology,
        "numbering_equal": candidate_numbers == control_numbers,
        "final_barline_boxes_exact": candidate["final_barlines"] == control["final_barlines"],
    }
    operational["count_topology_numbering_pass"] = all(
        operational[key]
        for key in (
            "final_barline_count_equal",
            "total_measures_equal",
            "system_measure_topology_equal",
            "numbering_equal",
        )
    )
    return operational


def _material_artifacts(payload: dict[str, Any]) -> dict[str, Path]:
    artifacts = payload["artifacts"]
    assert isinstance(artifacts, dict)
    return {
        key: Path(str(artifacts[key])).resolve()
        for key in ("detections", "staff_mask", "clef_mask")
    }


def _run_mode(
    *,
    mode: str,
    image: Path,
    detections: dict[str, Path],
    geometry: dict[str, dict[str, Path]],
    support: dict[str, Any],
    output_root: Path,
    detection_config: dict[str, Any],
) -> dict[str, Any]:
    variants = {
        label: _run_downstream_variant(
            label=label,
            image=image,
            baseline_detection=detections[label],
            support=support,
            staff_mask=geometry[label]["staff"],
            clef_mask=geometry[label]["clef"],
            output_root=output_root / mode,
            detection_config=detection_config,
        )
        for label in ("A_pinned", "B_b377", "C_latest")
    }
    return {
        "variants": variants,
        "comparisons_to_A": {
            label: _comparison(variants["A_pinned"], variants[label])
            for label in ("B_b377", "C_latest")
        },
    }


def run(
    summary_path: Path,
    b_homr_source: Path,
    b_homr_commit: str,
    c_homr_source: Path,
    c_homr_commit: str,
    output_root: Path,
) -> dict[str, Any]:
    summary_path = summary_path.resolve()
    output_root = output_root.resolve()
    if not summary_path.is_file():
        raise FileNotFoundError(summary_path)
    if output_root.exists():
        raise FileExistsError(output_root)
    summary = load_json(summary_path)
    pages_raw = summary.get("pages") if isinstance(summary, dict) else None
    if not isinstance(pages_raw, list) or not pages_raw:
        raise ValueError("Same-original summary has no pages")
    output_root.mkdir(parents=True, exist_ok=False)
    detection_config = _load_production_detection()

    page_reports: list[dict[str, Any]] = []
    for index, page in enumerate(pages_raw, start=1):
        if not isinstance(page, dict):
            raise ValueError("Invalid page payload")
        image = Path(str(page["image"])).resolve()
        a_detection, b_detection = _candidate_paths(page)
        for path in (image, a_detection, b_detection):
            if not path.is_file():
                raise FileNotFoundError(path)
        a_geometry = _control_geometry(a_detection, image.stem)
        page_root = output_root / f"{index:02d}_{image.stem}"
        page_root.mkdir(parents=True, exist_ok=False)

        support = _generate_fixed_support(image, page_root / "fixed_support")
        b_material = _run_detector_material(
            label="B_b377_material",
            image=image,
            homr_source=b_homr_source,
            homr_commit=b_homr_commit,
            output_root=page_root / "B_b377_material",
        )
        c_material = _run_detector_material(
            label="C_latest_material",
            image=image,
            homr_source=c_homr_source,
            homr_commit=c_homr_commit,
            output_root=page_root / "C_latest_material",
        )
        b_artifacts = _material_artifacts(b_material)
        c_artifacts = _material_artifacts(c_material)
        b_detector_boxes = [list(box) for box in load_json_boxes(b_artifacts["detections"])]
        b_full_boxes = [list(box) for box in load_json_boxes(b_detection)]

        detections = {
            "A_pinned": a_detection,
            "B_b377": b_detection,
            "C_latest": c_artifacts["detections"],
        }
        frozen_geometry = {label: a_geometry for label in ("A_pinned", "B_b377", "C_latest")}
        native_geometry = {
            "A_pinned": a_geometry,
            "B_b377": {"staff": b_artifacts["staff_mask"], "clef": b_artifacts["clef_mask"]},
            "C_latest": {"staff": c_artifacts["staff_mask"], "clef": c_artifacts["clef_mask"]},
        }
        modes = {
            "frozen_A_geometry": _run_mode(
                mode="frozen_A_geometry",
                image=image,
                detections=detections,
                geometry=frozen_geometry,
                support=support,
                output_root=page_root / "downstream",
                detection_config=detection_config,
            ),
            "candidate_native_geometry": _run_mode(
                mode="candidate_native_geometry",
                image=image,
                detections=detections,
                geometry=native_geometry,
                support=support,
                output_root=page_root / "downstream",
                detection_config=detection_config,
            ),
        }
        page_report = {
            "image": str(image),
            "fixed_inputs": {
                "support_result": str(page_root / "fixed_support/result.json"),
                "cnn_model": str(Path(str(detection_config["cnn_model_path"])).resolve()),
                "cnn_threshold": float(detection_config.get("cnn_threshold", 0.1)),
            },
            "B_material": b_material,
            "C_material": c_material,
            "B_full_vs_detector_material": {
                "full_count": len(b_full_boxes),
                "detector_material_count": len(b_detector_boxes),
                "boxes_exact": b_full_boxes == b_detector_boxes,
            },
            "modes": modes,
        }
        (page_root / "report.json").write_text(
            json.dumps(page_report, indent=2, ensure_ascii=False) + "\n"
        )
        page_reports.append(page_report)

    report = {
        "schema_version": "issue294.production_downstream_candidate_matrix.v2",
        "status": "completed",
        "same_original_summary": str(summary_path),
        "B_homr": {"source": str(b_homr_source.resolve()), "commit": b_homr_commit},
        "C_homr": {"source": str(c_homr_source.resolve()), "commit": c_homr_commit},
        "scope": {
            "primary_gate": "candidate_native_geometry final barline/count/topology/numbering",
            "causal_diagnostic": "frozen_A_geometry",
            "musicxml": "not_a_gate",
            "ground_truth": "optional_not_required",
            "fixed_current_x4_and_omr_support": True,
            "transformer_executed_for_detector_material_runs": False,
        },
        "pages": page_reports,
        "gates": {
            label: all(
                page["modes"]["candidate_native_geometry"]["comparisons_to_A"][label][
                    "count_topology_numbering_pass"
                ]
                for page in page_reports
            )
            for label in ("B_b377", "C_latest")
        },
        "diagnostics": {
            "B_detector_material_matches_full_B_all_pages": all(
                page["B_full_vs_detector_material"]["boxes_exact"] for page in page_reports
            )
        },
    }
    report_path = output_root / "report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--b-homr-source", type=Path, required=True)
    parser.add_argument("--b-homr-commit", required=True)
    parser.add_argument("--c-homr-source", type=Path, required=True)
    parser.add_argument("--c-homr-commit", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(
            args.summary,
            args.b_homr_source,
            args.b_homr_commit,
            args.c_homr_source,
            args.c_homr_commit,
            args.output_root,
        )
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": "completed",
                "report": str(args.output_root.resolve() / "report.json"),
                "gates": report["gates"],
                "diagnostics": report["diagnostics"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
