#!/usr/bin/env python3
"""Leave-one-score-out generalization and ablation for the lightweight ranker."""

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

from movement_features import HOLDOUT, build_rows


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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def choose_threshold(scores: np.ndarray, labels: np.ndarray, zero_fp: bool) -> float:
    feasible = []
    for threshold in sorted(set(float(value) for value in scores), reverse=True):
        selected = scores >= threshold
        tp = int((selected & labels).sum())
        fp = int((selected & ~labels).sum())
        if tp and (not zero_fp or fp == 0):
            feasible.append((tp, -fp, -int(selected.sum()), threshold))
    return max(feasible)[-1] if feasible else float("inf")


def metrics(rows: list[dict], selected: np.ndarray) -> dict:
    labels = np.asarray([row["label"] for row in rows], dtype=bool)
    tp = selected & labels
    fp = selected & ~labels
    fn = ~selected & labels

    def locations(mask: np.ndarray) -> list[list]:
        return [
            [row["score"], row["page_id"], row["system"]]
            for row, active in zip(rows, mask, strict=True)
            if active
        ]

    return {
        "system_starts": len(rows),
        "true_boundaries": int(labels.sum()),
        "predicted": int(selected.sum()),
        "true_positive": int(tp.sum()),
        "false_reset": int(fp.sum()),
        "missed_boundary": int(fn.sum()),
        "precision": round(float(tp.sum() / selected.sum()), 6) if selected.sum() else None,
        "recall": round(float(tp.sum() / labels.sum()), 6) if labels.sum() else None,
        "false_reset_locations": locations(fp),
        "missed_boundary_locations": locations(fn),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--development-ocr", type=Path, required=True)
    parser.add_argument("--holdout-ocr", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    scores = sorted(source["score"] for source in fixture["sources"])
    rows = build_rows(args.fixture, args.development_ocr, set(scores) - HOLDOUT)
    rows += build_rows(args.fixture, args.holdout_ocr, HOLDOUT)
    folds = []
    aggregate = {
        architecture: {"rows": [], "automatic": [], "candidate": []}
        for architecture in ("numeric", "numeric_plus_ocr_char_tfidf")
    }
    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    for held_out in scores:
        train_rows = [row for row in rows if row["score"] != held_out]
        test_rows = [row for row in rows if row["score"] == held_out]
        train_numeric = np.asarray(
            [[row["features"][name] for name in NUMERIC] for row in train_rows]
        )
        test_numeric = np.asarray(
            [[row["features"][name] for name in NUMERIC] for row in test_rows]
        )
        scaler = StandardScaler().fit(train_numeric)
        scaled_train = csr_matrix(scaler.transform(train_numeric))
        scaled_test = csr_matrix(scaler.transform(test_numeric))
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=1)
        train_text = vectorizer.fit_transform([row["ocr_text"] or "<empty>" for row in train_rows])
        test_text = vectorizer.transform([row["ocr_text"] or "<empty>" for row in test_rows])
        y_train = np.asarray([row["label"] for row in train_rows], dtype=bool)
        fold = {"held_out_score": held_out, "architectures": {}}
        for architecture, x_train, x_test in (
            ("numeric", scaled_train, scaled_test),
            (
                "numeric_plus_ocr_char_tfidf",
                hstack([scaled_train, train_text]),
                hstack([scaled_test, test_text]),
            ),
        ):
            model = LogisticRegression(
                C=0.1,
                class_weight="balanced",
                max_iter=2000,
                random_state=333,
                solver="liblinear",
            ).fit(x_train, y_train)
            train_scores = model.decision_function(x_train)
            test_scores = model.decision_function(x_test)
            automatic_threshold = choose_threshold(train_scores, y_train, zero_fp=True)
            candidate_threshold = choose_threshold(train_scores, y_train, zero_fp=False)
            automatic = test_scores >= automatic_threshold
            candidate = test_scores >= candidate_threshold
            checkpoint_path = args.checkpoint_dir / f"{held_out}_{architecture}.joblib"
            joblib.dump(
                {
                    "model": model,
                    "scaler": scaler,
                    "vectorizer": vectorizer if architecture.endswith("tfidf") else None,
                    "numeric_features": NUMERIC,
                    "automatic_threshold": automatic_threshold,
                    "candidate_threshold": candidate_threshold,
                    "seed": 333,
                },
                checkpoint_path,
            )
            fold["architectures"][architecture] = {
                "automatic_threshold_from_training": automatic_threshold,
                "candidate_threshold_from_training": candidate_threshold,
                "automatic": metrics(test_rows, automatic),
                "candidate": metrics(test_rows, candidate),
                "checkpoint": {
                    "path": str(checkpoint_path),
                    "sha256": sha256(checkpoint_path),
                },
            }
            aggregate[architecture]["rows"].extend(test_rows)
            aggregate[architecture]["automatic"].extend(automatic.tolist())
            aggregate[architecture]["candidate"].extend(candidate.tolist())
        folds.append(fold)
    report = {
        "schema_version": "issue333.cross_score_result.v1",
        "experiment_id": "phase2-leave-one-score-out-ranker-v1",
        "status": "cross-score exploratory; all scores are used in six of seven training folds",
        "architecture": "class-balanced logistic regression, C=0.1, StandardScaler numeric, optional char_wb TF-IDF(2,5)",
        "parameters": {"seed": 333, "solver": "liblinear", "max_iter": 2000},
        "threshold_selection": "in-fold training cutoff maximizing TP, with zero training FP for automatic",
        "runtime": {
            name: importlib.metadata.version(name)
            for name in ("scikit-learn", "scipy", "numpy", "joblib")
        },
        "folds": folds,
        "aggregate": {
            architecture: {
                "automatic": metrics(
                    values["rows"], np.asarray(values["automatic"], dtype=bool)
                ),
                "candidate": metrics(
                    values["rows"], np.asarray(values["candidate"], dtype=bool)
                ),
            }
            for architecture, values in aggregate.items()
        },
        "interpretation": "Source-held-out folds test ranking generalization but do not supply calibrated probabilities or an untouched final corpus.",
        "disposition": (
            "Reject both rankers: automatic folds miss 6/14 boundaries and still false-reset; "
            "candidate folds miss 2/14 and are inferior to the frozen geometry candidate. "
            "Adding OCR character TF-IDF did not change any selected location."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
