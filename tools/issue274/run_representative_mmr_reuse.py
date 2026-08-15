"""Run the Issue #274 12-page production MMR gate from retained artifacts only."""

from __future__ import annotations

import argparse
from pathlib import Path

import torch

from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
from src.measure_numbering.rapidocr_provider import (
    collect_rapidocr_providers,
    create_mmr_rapidocr,
    providers_include_cuda,
)
from src.pipeline.mmr_support_reuse import build_mmr_support
from src.pipeline.utils.io import load_json, write_json
from tools.issue264.run_phase_c_mmr_regression import build_page_specs, normalise_overrides
from tools.issue274.validate_mmr_support_mapping import _visible_path

PAGES = [
    "page_013",
    "page_045",
    "page_066",
    "page_067",
    "page_032",
    "page_035",
    "page_040",
    "page_041",
    "page_043",
    "page_046",
    "page_042",
    "page_033",
]


def _compact(payload: dict) -> list[dict]:
    return [
        {key: item[key] for key in ("page", "system", "measure", "skip")}
        for item in normalise_overrides(payload)
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retained-root", type=Path, required=True)
    parser.add_argument("--feasibility", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("Representative Issue #274 gate requires CUDA")
    feasibility = load_json(args.feasibility)
    feasibility_by_id = {item["page_id"]: item for item in feasibility["pages"]}
    specs = {item.page_id: item for item in build_page_specs()}
    classifier = MMRClassifier(args.model, device)
    provider = create_mmr_rapidocr("cuda")
    processor = MMRProcessor(
        model_path=args.model,
        device=device,
        classifier=classifier,
        ocr_engine=MMROCREngine(ocr_engine=provider),
    )
    pages_data, images, support_data, expected = [], [], [], []
    for page_id in PAGES:
        entry = feasibility_by_id[page_id]
        base = args.retained_root / "intermediate" / page_id / "numbering_base.json"
        sidecar = args.output.parent / "intermediate" / page_id / "mmr_support.json"
        support_data.append(
            build_mmr_support(
                numbering_base_path=base,
                current_homr_staff_mask=_visible_path(entry["shared_staff_mask"], Path.cwd()),
                output_path=sidecar,
            )
        )
        pages_data.append(load_json(base))
        images.append(specs[page_id].image)
        expected.append(
            load_json(args.retained_root / "intermediate" / page_id / "overrides_mmr.json")
        )
    actual = processor.process_pages(pages_data, images, support_data=support_data)
    page_results = [
        {
            "page_id": page_id,
            "expected": _compact(want),
            "actual": _compact(got),
            "equal": _compact(want) == _compact(got),
        }
        for page_id, want, got in zip(PAGES, expected, actual)
    ]
    report = {
        "schema_version": "issue274.production_reuse_representative.v1",
        "scope": {
            "pages": PAGES,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "original_image_homr_execution": 0,
            "second_numbering_rebuild": 0,
        },
        "rapidocr": {
            "providers": collect_rapidocr_providers(provider),
            "cuda_confirmed": providers_include_cuda(collect_rapidocr_providers(provider)),
        },
        "summary": {
            "page_count": len(PAGES),
            "exact_pages": sum(x["equal"] for x in page_results),
            "changed_pages": [x["page_id"] for x in page_results if not x["equal"]],
            **processor.support_stats,
        },
        "pages": page_results,
    }
    write_json(args.output, report)
    if report["summary"]["exact_pages"] != len(PAGES):
        raise SystemExit("Representative MMR mismatch; see report")


if __name__ == "__main__":
    main()
