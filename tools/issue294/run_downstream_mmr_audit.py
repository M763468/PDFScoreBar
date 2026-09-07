#!/usr/bin/env python3
"""Audit Issue #294 candidate-native numbering with the production MMR stack."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import cv2
import torch

from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.rapidocr_provider import (
    collect_rapidocr_providers,
    create_mmr_rapidocr,
    providers_include_cuda,
)
from src.measure_numbering.serialization import score_to_dict
from src.pipeline.mmr_support_reuse import build_mmr_support_data
from tools.issue264.run_phase_c_mmr_regression import normalise_overrides

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = PROJECT_ROOT / "tools/mmr_training/models/mmr_classifier_best.pth"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _compact(payload: Any) -> list[dict[str, int]]:
    return [
        {key: int(item[key]) for key in ("page", "system", "measure", "skip")}
        for item in normalise_overrides(payload)
    ]


def _numbering_base(page: dict[str, Any], label: str) -> dict[str, Any]:
    native = page["modes"]["candidate_native_geometry"]["variants"][label]
    image_path = Path(str(page["image"]))
    staff_mask = Path(str(native["staff_mask"]))
    fixed_support = _load_json(Path(str(page["fixed_inputs"]["support_result"])))
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(image_path)
    height, width = image.shape[:2]
    score = MeasureNumberingPipeline().run_sequential(
        [
            {
                "barlines": native["final_barlines"],
                "staff_mask": str(staff_mask),
                "image_size": (width, height),
                "page_number": 1,
                "connector_mask_paths": {
                    "symbols": str(fixed_support["connector_symbols"]),
                    "brace_dot": str(fixed_support["connector_brace_dot"]),
                },
            }
        ]
    )
    return score_to_dict(score)


def run(report_path: Path, expected_path: Path, model_path: Path) -> dict[str, Any]:
    report = _load_json(report_path)
    pages = report.get("pages") if isinstance(report, dict) else None
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], dict):
        raise ValueError("Expected a one-page Issue #294 matrix report")
    page = pages[0]
    labels = ["B_b377", "C_latest"]
    bases = [_numbering_base(page, label) for label in labels]
    image = Path(str(page["image"]))
    fixed_support = _load_json(Path(str(page["fixed_inputs"]["support_result"])))
    support_mask = Path(str(fixed_support["current_homr_staff_mask"]))
    support = [build_mmr_support_data(base, support_mask) for base in bases]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("Issue #294 MMR audit requires CUDA")
    classifier = MMRClassifier(model_path, device)
    provider = create_mmr_rapidocr("cuda")
    providers = collect_rapidocr_providers(provider)
    if not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR did not activate CUDA: {providers}")
    processor = MMRProcessor(
        model_path=model_path,
        device=device,
        classifier=classifier,
        ocr_engine=MMROCREngine(ocr_engine=provider),
    )
    started = time.perf_counter()
    actual = processor.process_pages(bases, [image, image], support_data=support)
    elapsed = time.perf_counter() - started
    expected = _compact(_load_json(expected_path))
    rows = []
    for label, base, overrides in zip(labels, bases, actual):
        compact = _compact(overrides)
        systems = base["pages"][0]["systems"]
        rows.append(
            {
                "label": label,
                "system_staff_counts": [len(system["staves"]) for system in systems],
                "system_measure_counts": [len(system["measures"]) for system in systems],
                "total_measures": sum(len(system["measures"]) for system in systems),
                "expected": expected,
                "actual": compact,
                "semantic_equal": compact == expected,
            }
        )
    return {
        "schema_version": "issue294.downstream_mmr_audit.v1",
        "status": "completed",
        "matrix_report": str(report_path.resolve()),
        "expected_overrides": str(expected_path.resolve()),
        "model": str(model_path.resolve()),
        "runtime": {
            "device": str(device),
            "rapidocr_providers": providers,
            "elapsed_sec": elapsed,
        },
        "candidates": rows,
        "gates": {row["label"]: row["semantic_equal"] for row in rows},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-overrides", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = run(args.report, args.expected_overrides, args.model)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if all(payload["gates"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
