#!/usr/bin/env python3
"""Native score-level evaluation for Issue #332 classifier checkpoints."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import time
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np
import torch
from PIL import Image

from tools.mmr_training.issue332.geometry_training import (
    _read_source_page,
    crop_measure,
    resolve_image_path,
    sha256_file,
)
from tools.mmr_training.issue332_geometry_benchmark import (
    ProductionMMRClassifierMirror,
    _load_manifest,
)


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _metrics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    labels = np.asarray([int(row["label"]) for row in rows], dtype=np.int64)
    predictions = np.asarray([int(row["prediction"]) for row in rows], dtype=np.int64)
    tp = int(np.sum((labels == 1) & (predictions == 1)))
    tn = int(np.sum((labels == 0) & (predictions == 0)))
    fp = int(np.sum((labels == 0) & (predictions == 1)))
    fn = int(np.sum((labels == 1) & (predictions == 0)))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "accuracy": (tp + tn) / len(rows) if rows else 0.0,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "samples": len(rows),
        "positives": int(np.sum(labels == 1)),
        "negatives": int(np.sum(labels == 0)),
    }


def summarize_native_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Return pooled and score-level metrics for native prediction rows."""
    by_score: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_score.setdefault(str(row["score_id"]), []).append(row)
    return {
        "pooled": _metrics(rows),
        "by_score": {score: _metrics(by_score[score]) for score in sorted(by_score)},
    }


def evaluate_model(
    *,
    model_path: Path,
    model_name: str,
    samples: Sequence[dict[str, Any]],
    manifest_path: Path,
    device: torch.device,
) -> dict[str, Any]:
    started = time.perf_counter()
    classifier = ProductionMMRClassifierMirror(model_path, device)
    rows: list[dict[str, Any]] = []
    with torch.inference_mode():
        for sample in samples:
            image_path = resolve_image_path(manifest_path, sample["image_path"])
            image = _read_source_page(str(image_path))
            if image is None:
                raise FileNotFoundError(f"could not load source image: {image_path}")
            crop = crop_measure(image, sample["bbox"], margin_px=20)
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            tensor = classifier.transform(Image.fromarray(rgb)).unsqueeze(0).to(device)
            probability = float(torch.sigmoid(classifier.model(tensor)).item())
            prediction = int(probability >= 0.5)
            rows.append(
                {
                    "sample_id": sample["sample_id"],
                    "score_id": sample["score_id"],
                    "page_id": sample["page_id"],
                    "image_path": str(image_path),
                    "bbox": list(sample["bbox"]),
                    "label": int(sample["label"]),
                    "probability": probability,
                    "prediction": prediction,
                    "correct": prediction == int(sample["label"]),
                }
            )

    summary = summarize_native_rows(rows)
    return {
        "model_name": model_name,
        "model_path": str(model_path.resolve()),
        "model_sha256": sha256_file(model_path),
        "elapsed_seconds": time.perf_counter() - started,
        "summary": summary,
        "misclassified_samples": [row for row in rows if not row["correct"]],
        "rows": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--model",
        action="append",
        required=True,
        metavar="NAME=PATH",
        help="Checkpoint to evaluate; may be repeated.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--device",
        default="cuda" if torch.cuda.is_available() else "cpu",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    model_specs: list[tuple[str, Path]] = []
    for raw in args.model:
        if "=" not in raw:
            raise ValueError(f"--model must be NAME=PATH, got {raw!r}")
        name, raw_path = raw.split("=", 1)
        model_specs.append((name, Path(raw_path)))

    samples = _load_manifest(args.manifest)
    scores = sorted({sample["score_id"] for sample in samples})
    if len(scores) != 5:
        raise ValueError(f"expected canonical five scores, got {scores}")
    device = torch.device(args.device)
    started = time.perf_counter()
    models_result = {
        name: evaluate_model(
            model_path=path,
            model_name=name,
            samples=samples,
            manifest_path=args.manifest,
            device=device,
        )
        for name, path in model_specs
    }
    result = {
        "provenance": {
            "issue": 332,
            "git_head": _git_head(),
            "manifest_path": str(args.manifest.resolve()),
            "manifest_sha256": sha256_file(args.manifest),
            "device": str(device),
            "torch_version": torch.__version__,
            "opencv_version": cv2.__version__,
            "python_version": platform.python_version(),
            "evaluation": "native crop, direct 224x224 production transform, threshold 0.5",
        },
        "scores": scores,
        "samples": len(samples),
        "elapsed_seconds": time.perf_counter() - started,
        "models": models_result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({name: value["summary"] for name, value in models_result.items()}, indent=2))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
