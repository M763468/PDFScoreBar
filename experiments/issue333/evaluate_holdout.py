#!/usr/bin/env python3
"""One-shot evaluation of frozen Issue 333 strategies on source holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
from scipy.sparse import csr_matrix, hstack

from movement_features import HOLDOUT, build_rows


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def locations(rows: list[dict], mask: np.ndarray) -> list[list]:
    return [
        [row["score"], row["page_id"], row["system"]]
        for row, selected in zip(rows, mask, strict=True)
        if selected
    ]


def metrics(rows: list[dict], selected: np.ndarray) -> dict:
    labels = np.asarray([row["label"] for row in rows], dtype=bool)
    tp = selected & labels
    fp = selected & ~labels
    fn = ~selected & labels
    return {
        "system_starts": len(rows),
        "true_boundaries": int(labels.sum()),
        "predicted": int(selected.sum()),
        "true_positive": int(tp.sum()),
        "false_reset": int(fp.sum()),
        "missed_boundary": int(fn.sum()),
        "precision": round(float(tp.sum() / selected.sum()), 6) if selected.sum() else None,
        "recall": round(float(tp.sum() / labels.sum()), 6),
        "review_burden": round(float(selected.mean()), 6),
        "false_reset_locations": locations(rows, fp),
        "missed_boundary_locations": locations(rows, fn),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--ocr", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    frozen = joblib.load(args.checkpoint)
    rows = build_rows(args.fixture, args.ocr, HOLDOUT)
    numeric = np.asarray(
        [
            [row["features"][name] for name in frozen["numeric_features"]]
            for row in rows
        ]
    )
    texts = [row["ocr_text"] or "<empty>" for row in rows]
    matrix = hstack(
        [
            csr_matrix(frozen["scaler"].transform(numeric)),
            frozen["vectorizer"].transform(texts),
        ]
    )
    scores = frozen["model"].decision_function(matrix)
    strategies = {
        "frozen_ranker_automatic": scores >= frozen["automatic_threshold"],
        "frozen_ranker_candidate": scores >= frozen["candidate_threshold"],
        "structured_consensus": np.asarray(
            [bool(row["features"]["structured_consensus"]) for row in rows]
        ),
        "geometry_candidate": np.asarray(
            [bool(row["features"]["geometry_candidate"]) for row in rows]
        ),
    }
    per_score = {}
    for score in sorted(HOLDOUT):
        indices = [index for index, row in enumerate(rows) if row["score"] == score]
        score_rows = [rows[index] for index in indices]
        per_score[score] = {
            name: metrics(score_rows, selected[indices])
            for name, selected in strategies.items()
        }
    report = {
        "schema_version": "issue333.holdout_result.v1",
        "experiment_id": "phase2-frozen-hybrid-holdout-v1",
        "source_commit": "5dec308a",
        "holdout_scores": sorted(HOLDOUT),
        "checkpoint": {
            "path": str(args.checkpoint),
            "sha256": sha256(args.checkpoint),
            "architecture": "numeric+OCR-char-TFIDF class-balanced logistic regression",
            "seed": frozen["seed"],
            "automatic_threshold": frozen["automatic_threshold"],
            "candidate_threshold": frozen["candidate_threshold"],
        },
        "ocr": {"path": str(args.ocr), "sha256": sha256(args.ocr)},
        "metrics": {name: metrics(rows, selected) for name, selected in strategies.items()},
        "per_score": per_score,
        "scores": [
            {
                "score": row["score"],
                "page_id": row["page_id"],
                "system": row["system"],
                "label": row["label"],
                "decision_score": round(float(score), 8),
                "features": row["features"],
                "ocr_text": row["ocr_text"],
            }
            for row, score in zip(rows, scores, strict=True)
        ],
        "interpretation": (
            "The frozen ranker did not generalize: it missed every Beethoven boundary and "
            "four of five holdout boundaries overall. Exact lexical consensus was less brittle "
            "but missed OCR variants 'prestoxd' and 'meuuetto'. Geometry retained all five "
            "boundaries with one first-musical-system false proposal."
        ),
        "disposition": {
            "frozen_ranker": "rejected for automatic resolution and candidate generation",
            "structured_consensus": "rejected as sole candidate generator",
            "geometry": "retain as high-recall review candidate baseline",
        },
        "warning": "Decision scores are uncalibrated and are not production confidence.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
