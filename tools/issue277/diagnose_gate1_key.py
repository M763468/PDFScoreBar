"""Validation-only trace for a retained accepted-geometry MMR key."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import torch

from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
from src.measure_numbering.rapidocr_provider import create_mmr_rapidocr


def main() -> None:
    image = cv2.imread("/source/data/evaluation2/images/Sibelius-Violin_Concerto-Viola/page_004.png")
    support = json.loads(Path("/prod/reuse/intermediate/page_035/mmr_support.json").read_text())
    system = support["views"]["primary"]["pages"][0]["systems"][9]
    bbox = system["measures"][4]["bbox"]
    model = Path("/source/tools/mmr_training/models/mmr_classifier_best.pth")
    ocr = create_mmr_rapidocr("cuda")
    processor = MMRProcessor(
        model,
        torch.device("cuda"),
        classifier=MMRClassifier(model, torch.device("cuda")),
        ocr_engine=MMROCREngine(ocr_engine=ocr),
    )
    height, width = image.shape[:2]
    x1, y1, x2, y2 = bbox
    crop = image[max(0, y1 - 20) : min(height, y2 + 20), max(0, x1 - 20) : min(width, x2 + 20)]
    probability = processor.classifier.predict(crop)
    baseline = processor._detect_number_with_evidence_once(
        image, system, x1, y1, x2, y2, probability, width, height
    )
    policy = processor._detect_number_with_evidence(
        image, system, x1, y1, x2, y2, probability, width, height
    )
    print(json.dumps({"bbox": bbox, "prob": probability, "baseline": baseline, "policy": policy}, default=str))


if __name__ == "__main__":
    main()
