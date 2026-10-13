#!/usr/bin/env python3
"""Prepare original 3div./4div. scan inputs and verify fresh pipeline outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "tests/fixtures/system_grouping/issue218_real_score.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def prepare(source_pdf: Path, output_root: Path, contract_path: Path = CONTRACT) -> Path:
    import fitz
    import yaml

    contract = json.loads(contract_path.read_text())
    if sha256(source_pdf) != contract["source"]["sha256"]:
        raise ValueError("Source PDF does not match the retained Issue #218 contract")
    inputs = output_root / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    with fitz.open(source_pdf) as document:
        for case in contract["cases"]:
            image = inputs / f"{case['page_id']}.png"
            if image.exists():
                if sha256(image) != case["image_sha256"]:
                    raise ValueError(f"Refusing to replace a different input: {image}")
                continue
            if contract.get("renderer") == "src.pdf_to_images":
                from src.pdf_to_images import render_pdf

                render_pdf(
                    source_pdf,
                    inputs,
                    dpi=contract["dpi"],
                    pages=[case["pdf_page_1based"] - 1],
                    overwrite=False,
                    prefix="page",
                    fmt="png",
                    keep_alpha=False,
                    target_width=None,
                    target_height=None,
                    interpolation="area",
                )
            else:
                page = document[contract["source"]["pdf_page_1based"] - 1]
                page.get_pixmap(
                    dpi=contract["dpi"], clip=fitz.Rect(case["crop_pdf_points"]), alpha=False
                ).save(image)
            if sha256(image) != case["image_sha256"]:
                raise ValueError(f"Rendered input identity differs: {image}")

    artifact_root = output_root.relative_to(ROOT)
    config = yaml.safe_load((ROOT / "configs/dense_full_pipeline.yaml").read_text())
    config["run"] = {"run_id": "real_scores", "output_root": str(artifact_root / "runs")}
    config["inputs"]["pdf_to_images"]["output_dir"] = str(artifact_root / "inputs")
    config["inputs"]["pdf_to_images"]["image_glob"] = "page_[0-9][0-9][0-9].png"
    config["detection"]["hybrid_output_root"] = str(
        artifact_root / "runs/real_scores/hybrid_output"
    )
    config["steps"]["overlay"] = True
    config_path = output_root / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    return config_path


def inspect_page(page: dict, case: dict) -> dict:
    systems = page.get("systems", [])
    errors = []
    counts = [len(system["staves"]) for system in systems]
    if counts != case["expected_system_staff_counts"]:
        errors.append(
            f"system staff counts: {counts}; expected {case['expected_system_staff_counts']}"
        )
    if page.get("empty_systems"):
        errors.append(f"unexpected empty systems: {page['empty_systems']}")
    centers = case["expected_staff_center_y"]
    membership = []
    for system in systems:
        slots = []
        for staff in system["staves"]:
            matches = [
                index for index, y in enumerate(centers) if staff["bbox"][1] <= y < staff["bbox"][3]
            ]
            slots.append(matches)
        membership.append(slots)
        for measure in system["measures"]:
            if measure["bbox"][1] != min(staff["bbox"][1] for staff in system["staves"]) or measure[
                "bbox"
            ][3] != max(staff["bbox"][3] for staff in system["staves"]):
                errors.append("measure does not span all grouped staves")
    expected_membership = []
    offset = 0
    for count in case["expected_system_staff_counts"]:
        expected_membership.append([[index] for index in range(offset, offset + count)])
        offset += count
    if membership != expected_membership:
        errors.append(f"staff membership: {membership}; expected {expected_membership}")
    measure_counts = [len(system["measures"]) for system in systems]
    if (
        "expected_measures_per_system" in case
        and measure_counts != case["expected_measures_per_system"]
    ):
        errors.append(
            f"measure counts: {measure_counts}; expected {case['expected_measures_per_system']}"
        )
    return {
        "system_staff_counts": counts,
        "membership": membership,
        "measure_counts": measure_counts,
        "measure_numbers": [[m["number"] for m in s["measures"]] for s in systems],
        "errors": errors,
    }


def verify(
    run_dir: Path, detector_run_dir: Path | None = None, contract_path: Path = CONTRACT
) -> dict:
    import yaml

    from src.common.connector_artifacts import connector_mask_paths_for_numbering

    contract = json.loads(contract_path.read_text())
    manifest = json.loads((run_dir / "manifest.json").read_text())
    config = manifest["config"]
    reference = yaml.safe_load((ROOT / "configs/dense_full_pipeline.yaml").read_text())

    def detection(c):
        return {k: v for k, v in c["detection"].items() if k != "hybrid_output_root"}

    if detection(config) != detection(reference):
        raise ValueError("Detector settings differ from the production contract")
    if config["numbering"].get("force_single_system", False):
        raise ValueError("Geometric grouping is required")
    detector_manifest = manifest
    if detector_run_dir is not None:
        detector_manifest = json.loads((detector_run_dir / "manifest.json").read_text())
    if detector_manifest["config"]["steps"].get("detection") is not True:
        raise ValueError("An actual fresh detection run is required as source evidence")
    if config["steps"].get("detection") is not True and detector_run_dir is None:
        raise ValueError("Retained-output replay requires --detector-run-dir")
    if detection(detector_manifest["config"]) != detection(reference):
        raise ValueError("Source detector settings differ from the production contract")
    if any("override" in key and value for key, value in config["inputs"].items()):
        raise ValueError("Manual overrides are not valid detection evidence")
    pages = manifest["pages"]
    if [page["page_id"] for page in pages] != [case["page_id"] for case in contract["cases"]]:
        raise ValueError("Run input set/order differs from the original contract")
    if [page["page_id"] for page in detector_manifest["pages"]] != [
        page["page_id"] for page in pages
    ]:
        raise ValueError("Source detector input set differs from the replay")
    results = []
    numbers = []
    for page, case, source_page in zip(pages, contract["cases"], detector_manifest["pages"]):
        if sha256(resolve(page["image_path"])) != case["image_sha256"]:
            raise ValueError(f"Input identity differs: {case['page_id']}")
        for field in ("image_path", "barlines_json", "staff_mask"):
            if sha256(resolve(page[field])) != sha256(resolve(source_page[field])):
                raise ValueError(f"Retained detector artifact differs: {case['page_id']} {field}")
        connector_paths = connector_mask_paths_for_numbering(resolve(page["staff_mask"]))
        source_connector_paths = connector_mask_paths_for_numbering(
            resolve(source_page["staff_mask"])
        )
        if not connector_paths or not source_connector_paths:
            raise ValueError(f"Model-produced connector masks are required: {case['page_id']}")
        connector_hashes = {key: sha256(path) for key, path in connector_paths.items()}
        if connector_hashes != {key: sha256(path) for key, path in source_connector_paths.items()}:
            raise ValueError(f"Retained connector masks differ: {case['page_id']}")
        base = json.loads(
            (run_dir / "intermediate" / case["page_id"] / "numbering_base.json").read_text()
        )
        final = json.loads(
            (run_dir / "outputs" / case["page_id"] / "numbering_final.json").read_text()
        )
        result = {
            "name": case["name"],
            "page_id": case["page_id"],
            "connector_mask_sha256": connector_hashes,
        }
        result["base"] = inspect_page(base["pages"][0], case)
        result["final"] = inspect_page(final["pages"][0], case)
        numbers.extend(number for group in result["final"]["measure_numbers"] for number in group)
        results.append(result)
    errors = [
        f"{result['name']} {phase}: {error}"
        for result in results
        for phase in ("base", "final")
        for error in result[phase]["errors"]
    ]
    if "expected_final_numbers" in contract and numbers != contract["expected_final_numbers"]:
        errors.append(
            f"final shared measure progression: {numbers}; expected {contract['expected_final_numbers']}"
        )
    return {
        "status": "failed" if errors else "passed",
        "contract": str(contract_path),
        "source": contract["source"],
        "run_dir": str(run_dir),
        "detector_source_run": str(detector_run_dir or run_dir),
        "cases": results,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--contract", type=Path, default=CONTRACT)
    prep.add_argument("--source-pdf", type=Path, required=True)
    prep.add_argument("--output-root", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("--contract", type=Path, default=CONTRACT)
    check.add_argument("--run-dir", type=Path, required=True)
    check.add_argument("--report", type=Path, required=True)
    check.add_argument("--detector-run-dir", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        print(prepare(resolve(args.source_pdf), resolve(args.output_root), resolve(args.contract)))
        return 0
    report = verify(
        resolve(args.run_dir),
        resolve(args.detector_run_dir) if args.detector_run_dir else None,
        resolve(args.contract),
    )
    resolve(args.report).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
