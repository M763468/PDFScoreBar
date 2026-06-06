#!/usr/bin/env python3
"""Evaluate MMR override detection from existing numbering artifacts.

This script intentionally does not run the detector or the full pipeline. It takes an
existing base numbering JSON plus the corresponding page image, runs only the MMR
processor, and writes a compact summary that can be used to classify Issue #94
failures.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import torch

from src.measure_numbering.rapidocr_provider import normalize_rapidocr_provider
from src.pipeline.steps.numbering import run_mmr_batch

logger = logging.getLogger(__name__)
OverrideKey = Tuple[int, int, int]


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _normalise_overrides(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        if "measure_overrides" in payload:
            return list(payload.get("measure_overrides") or [])
        if "overrides" in payload:
            return list(payload.get("overrides") or [])
    if isinstance(payload, list):
        return payload
    return []


def _override_key(override: Dict[str, Any]) -> OverrideKey:
    return (int(override["page"]), int(override["system"]), int(override["measure"]))


def _override_skip(override: Dict[str, Any]) -> int:
    return int(override.get("skip", 0))


def _index_overrides(overrides: Iterable[Dict[str, Any]]) -> Dict[OverrideKey, Dict[str, Any]]:
    indexed: Dict[OverrideKey, Dict[str, Any]] = {}
    for override in overrides:
        try:
            indexed[_override_key(override)] = override
        except KeyError:
            logger.warning("Skipping malformed override without page/system/measure: %s", override)
    return indexed


def _measure_count(numbering_payload: Dict[str, Any]) -> int:
    total = 0
    for page in numbering_payload.get("pages", []):
        for system in page.get("systems", []):
            total += len(system.get("measures", []))
    return total


def _build_summary(
    *,
    numbering_json: Path,
    image: Path,
    model_path: Path,
    rapidocr_provider: str,
    threshold: float,
    rescue_threshold: float,
    enable_rotation_tta: bool,
    numbering_payload: Dict[str, Any],
    detected_payload: Dict[str, Any],
    expected_payload: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    detected = _normalise_overrides(detected_payload)
    detected_by_key = _index_overrides(detected)
    expected = _normalise_overrides(expected_payload) if expected_payload is not None else []
    expected_by_key = _index_overrides(expected)

    matched = []
    skip_mismatch = []
    missed = []

    for key, expected_override in expected_by_key.items():
        detected_override = detected_by_key.get(key)
        if detected_override is None:
            missed.append(
                {
                    "key": list(key),
                    "expected_skip": _override_skip(expected_override),
                    "classification_hint": "ocr_missing_or_cnn_rejected_or_candidate_missing",
                }
            )
            continue
        expected_skip = _override_skip(expected_override)
        detected_skip = _override_skip(detected_override)
        if expected_skip == detected_skip:
            matched.append({"key": list(key), "skip": detected_skip})
        else:
            skip_mismatch.append(
                {
                    "key": list(key),
                    "expected_skip": expected_skip,
                    "detected_skip": detected_skip,
                    "classification_hint": "ocr_wrong_or_wrong_target",
                    "detected_comment": detected_override.get("comment"),
                }
            )

    unexpected = []
    if expected_by_key:
        for key, detected_override in detected_by_key.items():
            if key not in expected_by_key:
                unexpected.append(
                    {
                        "key": list(key),
                        "detected_skip": _override_skip(detected_override),
                        "classification_hint": "unexpected_detection_or_expected_fixture_incomplete",
                        "detected_comment": detected_override.get("comment"),
                    }
                )

    return {
        "inputs": {
            "numbering_json": str(numbering_json),
            "image": str(image),
            "model_path": str(model_path),
        },
        "parameters": {
            "rapidocr_provider": rapidocr_provider,
            "threshold": threshold,
            "rescue_threshold": rescue_threshold,
            "enable_rotation_tta": enable_rotation_tta,
        },
        "counts": {
            "base_measures": _measure_count(numbering_payload),
            "detected_overrides": len(detected),
            "expected_overrides": len(expected),
            "matched": len(matched),
            "missed": len(missed),
            "skip_mismatch": len(skip_mismatch),
            "unexpected": len(unexpected),
        },
        "matched": matched,
        "missed": missed,
        "skip_mismatch": skip_mismatch,
        "unexpected": unexpected,
        "detected_overrides": detected,
        "notes": [
            "candidate_missing requires inspecting the base numbering measure list and image overlay.",
            "cnn_rejected vs ocr_missing requires MMR debug logs or a temporary classifier/OCR trace.",
            "numbering_not_applied should be checked by rerunning final numbering with the emitted overrides.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run only MMR override detection from existing base numbering JSON."
    )
    parser.add_argument("--numbering-json", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-overrides", type=Path)
    parser.add_argument(
        "--device",
        default="cuda" if torch.cuda.is_available() else "cpu",
        choices=("cpu", "cuda"),
    )
    parser.add_argument(
        "--rapidocr-provider",
        default="auto",
        choices=("auto", "cpu", "cuda"),
        help="RapidOCR provider preference used through the MMR provider-selection helper.",
    )
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--rescue-threshold", type=float, default=0.1)
    parser.add_argument("--enable-rotation-tta", action="store_true")
    parser.add_argument("--no-debug", action="store_true")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    args = parse_args()

    provider_mode = normalize_rapidocr_provider(args.rapidocr_provider)
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("--device cuda was requested, but torch.cuda.is_available() is false.")

    numbering_payload = _load_json(args.numbering_json)
    expected_payload = _load_json(args.expected_overrides) if args.expected_overrides else None

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "mmr_overrides.json"
    debug_root = None if args.no_debug else args.output_dir / "mmr_debug"

    run_mmr_batch(
        pages_data=[numbering_payload],
        image_paths=[args.image],
        output_paths=[output_path],
        model_path=args.model_path,
        device=torch.device(args.device),
        enable_rotation_tta=args.enable_rotation_tta,
        threshold=args.threshold,
        rescue_threshold=args.rescue_threshold,
        debug_root=debug_root,
        rapidocr_provider=provider_mode,
    )

    detected_payload = _load_json(output_path)
    summary = _build_summary(
        numbering_json=args.numbering_json,
        image=args.image,
        model_path=args.model_path,
        rapidocr_provider=provider_mode,
        threshold=args.threshold,
        rescue_threshold=args.rescue_threshold,
        enable_rotation_tta=args.enable_rotation_tta,
        numbering_payload=numbering_payload,
        detected_payload=detected_payload,
        expected_payload=expected_payload,
    )
    _write_json(args.output_dir / "mmr_eval_summary.json", summary)
    logger.info("Wrote %s", output_path)
    logger.info("Wrote %s", args.output_dir / "mmr_eval_summary.json")


if __name__ == "__main__":
    main()
