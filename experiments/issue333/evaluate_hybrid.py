#!/usr/bin/env python3
"""Fit and evaluate structured and lightweight learned Issue 333 strategies."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import joblib
import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from movement_features import build_rows


FIT = {"festival", "prokofiev1", "prokofiev5"}
VALIDATION = {"shostakovich5", "sibelius"}
NUMERIC = [
    "page_start",
    "system_index_ratio",
    "top_ratio",
    "left_ratio",
    "indent_ratio",
    "gap_page_ratio",
    "gap_median_ratio",
    "system_height_ratio",
    "system_width_ratio",
    "measure_count",
    "ocr_count",
    "max_ocr_height_to_page_median",
    "has_tempo",
    "has_ordinal",
    "has_form",
    "has_trio",
    "semantic_heading",
    "geometry_candidate",
    "structured_consensus",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matrix(rows: list[dict], scaler=None, vectorizer=None, fit=False):
    numeric = np.asarray([[row["features"][name] for name in NUMERIC] for row in rows])
    texts = [row["ocr_text"] or "<empty>" for row in rows]
    if fit:
        scaler = StandardScaler().fit(numeric)
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=1)
        text_matrix = vectorizer.fit_transform(texts)
    else:
        text_matrix = vectorizer.transform(texts)
    return hstack([csr_matrix(scaler.transform(numeric)), text_matrix]), scaler, vectorizer


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
        "recall": round(float(tp.sum() / labels.sum()), 6) if labels.sum() else None,
        "review_burden": round(float(selected.mean()), 6),
        "false_reset_locations": locations(rows, fp),
        "missed_boundary_locations": locations(rows, fn),
    }


def select_threshold(scores: np.ndarray, labels: np.ndarray, require_zero_fp: bool) -> float:
    candidates = sorted(set(float(value) for value in scores), reverse=True)
    feasible = []
    for threshold in candidates:
        selected = scores >= threshold
        tp = int((selected & labels).sum())
        fp = int((selected & ~labels).sum())
        if tp and (not require_zero_fp or fp == 0):
            feasible.append((tp, -fp, -int(selected.sum()), threshold))
    if not feasible:
        return float("inf")
    return max(feasible)[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--ocr", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    args = parser.parse_args()
    rows = build_rows(args.fixture, args.ocr, FIT | VALIDATION)
    fit_rows = [row for row in rows if row["score"] in FIT]
    val_rows = [row for row in rows if row["score"] in VALIDATION]
    x_fit, scaler, vectorizer = matrix(fit_rows, fit=True)
    x_val, _, _ = matrix(val_rows, scaler, vectorizer)
    y_fit = np.asarray([row["label"] for row in fit_rows], dtype=bool)
    y_val = np.asarray([row["label"] for row in val_rows], dtype=bool)
    trials = []
    models = {}
    for c_value in (0.1, 1.0, 10.0):
        model = LogisticRegression(
            C=c_value,
            class_weight="balanced",
            max_iter=2000,
            random_state=333,
            solver="liblinear",
        ).fit(x_fit, y_fit)
        scores = model.decision_function(x_val)
        automatic = select_threshold(scores, y_val, require_zero_fp=True)
        candidate = select_threshold(scores, y_val, require_zero_fp=False)
        trials.append(
            {
                "C": c_value,
                "automatic_threshold": automatic,
                "candidate_threshold": candidate,
                "automatic": metrics(val_rows, scores >= automatic),
                "candidate": metrics(val_rows, scores >= candidate),
            }
        )
        models[c_value] = model
    selected_trial = max(
        trials,
        key=lambda item: (
            item["automatic"]["true_positive"],
            -item["automatic"]["false_reset"],
            item["candidate"]["true_positive"],
            -item["candidate"]["predicted"],
            -item["C"],
        ),
    )
    model = models[selected_trial["C"]]
    checkpoint = {
        "model": model,
        "scaler": scaler,
        "vectorizer": vectorizer,
        "numeric_features": NUMERIC,
        "automatic_threshold": selected_trial["automatic_threshold"],
        "candidate_threshold": selected_trial["candidate_threshold"],
        "seed": 333,
    }
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(checkpoint, args.checkpoint)
    structured = np.asarray(
        [bool(row["features"]["structured_consensus"]) for row in val_rows]
    )
    report = {
        "schema_version": "issue333.model_selection_result.v1",
        "experiment_id": "phase2-hybrid-model-selection-v1",
        "source_commit": "0e55d0a8",
        "split": {"fit": sorted(FIT), "validation": sorted(VALIDATION)},
        "label_counts": {
            "fit_system_starts": len(fit_rows),
            "fit_boundaries": int(y_fit.sum()),
            "validation_system_starts": len(val_rows),
            "validation_boundaries": int(y_val.sum()),
        },
        "preprocessing": {
            "numeric_features": NUMERIC,
            "text": "OCR associated with preceding gap; char_wb TF-IDF ngram_range=(2,5)",
            "standardization": "StandardScaler fit on fit scores only",
        },
        "architecture": "StandardScaler numeric + char TF-IDF -> class-balanced logistic regression",
        "parameters": {"seed": 333, "solver": "liblinear", "max_iter": 2000},
        "runtime": {
            name: importlib.metadata.version(name)
            for name in ("scikit-learn", "scipy", "numpy", "joblib")
        },
        "command": (
            "python experiments/issue333/evaluate_hybrid.py --fixture "
            "tests/fixtures/movement_boundaries/issue333_representative.json "
            "--ocr logs/issue333/fresh/heading_ocr.json --output "
            "experiments/issue333/results/hybrid_model_selection_v1.json "
            "--checkpoint logs/issue333/phase2/models/hybrid_ranker_v1.joblib"
        ),
        "trials": trials,
        "selected": selected_trial,
        "structured_consensus_validation": metrics(val_rows, structured),
        "checkpoint": {"path": str(args.checkpoint), "sha256": digest(args.checkpoint)},
        "warning": "Decision scores and thresholds are not calibrated probabilities.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
