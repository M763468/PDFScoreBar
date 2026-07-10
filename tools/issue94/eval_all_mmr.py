# ruff: noqa: I001

import argparse
import json
import logging
from pathlib import Path

import torch
from src.measure_numbering.rapidocr_provider import normalize_rapidocr_provider
from src.pipeline.steps.numbering import run_mmr_batch

from tools.issue94.eval_mmr_overrides import _build_summary, _load_json, _write_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("eval_all_mmr")

DEFAULT_MODEL_PATH = Path("tools/mmr_training/models/mmr_classifier_best.pth")
DEFAULT_PAGE_INPUTS = Path("logs/issue94_mmr_current_state/page_inputs.json")
DEFAULT_OUTPUT_ROOT = Path("logs/issue94_mmr_current_state/eval")
DEFAULT_EXPECTED_ROOT = Path("tests/fixtures")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate MMR across a page-input manifest.")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--page-inputs", type=Path, default=DEFAULT_PAGE_INPUTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--expected-root", type=Path, default=DEFAULT_EXPECTED_ROOT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model_path = args.model_path
    page_inputs_path = args.page_inputs
    output_root = args.output_root
    expected_root = args.expected_root

    with page_inputs_path.open("r", encoding="utf-8") as stream:
        inputs = json.load(stream)

    pages = inputs["pages"]
    logger.info("Loaded %s pages to evaluate from %s.", len(pages), page_inputs_path)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    rapidocr_provider = "cuda" if device == "cuda" else "cpu"
    threshold = 0.5
    rescue_threshold = 0.1
    enable_rotation_tta = False

    pages_data = []
    image_paths = []
    output_paths = []

    for page in pages:
        page_id = page["page_id"]
        numbering_path = Path(page["numbering_base"])
        image_path = Path(page["image"])
        page_output_dir = output_root / page_id
        page_output_dir.mkdir(parents=True, exist_ok=True)
        output_path = page_output_dir / "mmr_overrides.json"

        pages_data.append(_load_json(numbering_path))
        image_paths.append(image_path)
        output_paths.append(output_path)

    logger.info(
        "Running run_mmr_batch on %s with rapidocr_provider=%s...",
        device,
        rapidocr_provider,
    )
    run_mmr_batch(
        pages_data=pages_data,
        image_paths=image_paths,
        output_paths=output_paths,
        model_path=model_path,
        device=torch.device(device),
        enable_rotation_tta=enable_rotation_tta,
        threshold=threshold,
        rescue_threshold=rescue_threshold,
        debug_root=None,
        rapidocr_provider=normalize_rapidocr_provider(rapidocr_provider),
    )
    logger.info("run_mmr_batch completed. Generating summaries...")

    total_base_measures = 0
    total_detected = 0
    total_expected = 0
    total_matched = 0
    total_missed = 0
    total_skip_mismatch = 0
    total_unexpected = 0
    page_summaries = []

    for page, numbering_payload, output_path in zip(
        pages,
        pages_data,
        output_paths,
        strict=True,
    ):
        page_id = page["page_id"]
        detected_payload = _load_json(output_path)
        expected_path = expected_root / f"expected_overrides_{page_id}.json"
        expected_payload = _load_json(expected_path) if expected_path.exists() else None

        summary = _build_summary(
            numbering_json=Path(page["numbering_base"]),
            image=Path(page["image"]),
            model_path=model_path,
            rapidocr_provider=rapidocr_provider,
            threshold=threshold,
            rescue_threshold=rescue_threshold,
            enable_rotation_tta=enable_rotation_tta,
            numbering_payload=numbering_payload,
            detected_payload=detected_payload,
            expected_payload=expected_payload,
        )

        counts = summary["counts"]
        total_base_measures += counts["base_measures"]
        total_detected += counts["detected_overrides"]
        total_expected += counts["expected_overrides"]
        total_matched += counts["matched"]
        total_missed += counts["missed"]
        total_skip_mismatch += counts["skip_mismatch"]
        total_unexpected += counts["unexpected"]

        page_summaries.append(
            {
                "page_id": page_id,
                "image": Path(page["image"]).name,
                "expected": counts["expected_overrides"],
                "detected": counts["detected_overrides"],
                "matched": counts["matched"],
                "missed": counts["missed"],
                "mismatch": counts["skip_mismatch"],
                "unexpected": counts["unexpected"],
            }
        )

        summary_path = output_root / page_id / "mmr_eval_summary.json"
        _write_json(summary_path, summary)

    print("\n" + "=" * 50)
    print(" MMR EVALUATION METRICS SUMMARY (REST GT)")
    print("=" * 50)
    print(f"Total Pages:         {len(pages)}")
    print(f"Total Base Measures: {total_base_measures}")
    print(f"Total Expected:      {total_expected} (Positive MMRs in GT)")
    print(f"Total Detected:      {total_detected}")
    print(f"Matched (TP):        {total_matched}")
    print(f"Missed (FN):         {total_missed}")
    print(f"Skip Mismatch:       {total_skip_mismatch}")
    print(f"Unexpected (FP):     {total_unexpected}")

    precision = total_matched / total_detected if total_detected > 0 else 0
    recall = total_matched / total_expected if total_expected > 0 else 0
    f1 = (
        2 * (precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0
    )

    print("-" * 50)
    print(f"Precision:           {precision:.4f}")
    print(f"Recall:              {recall:.4f}")
    print(f"F1-Score:            {f1:.4f}")
    print("=" * 50)

    aggregated_report = {
        "summary": {
            "total_pages": len(pages),
            "total_base_measures": total_base_measures,
            "total_expected": total_expected,
            "total_detected": total_detected,
            "matched_tp": total_matched,
            "missed_fn": total_missed,
            "skip_mismatch": total_skip_mismatch,
            "unexpected_fp": total_unexpected,
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
        },
        "pages": page_summaries,
        "provenance": {
            "page_inputs": str(page_inputs_path),
            "model_path": str(model_path),
            "expected_root": str(expected_root),
            "output_root": str(output_root),
        },
    }
    _write_json(output_root / "aggregated_eval_summary.json", aggregated_report)
    logger.info("All evaluations completed. Aggregated summary saved.")


if __name__ == "__main__":
    main()
