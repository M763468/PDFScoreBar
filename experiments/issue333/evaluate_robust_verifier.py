#!/usr/bin/env python3
"""Post-holdout OCR-error robustness experiment for Issue 333."""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import json
import re
from pathlib import Path

import numpy as np

from movement_features import HOLDOUT, build_rows


VOCABULARY = {
    "adagio",
    "allegro",
    "andante",
    "finale",
    "gavotte",
    "grave",
    "largo",
    "larghetto",
    "lento",
    "menuett",
    "menuetto",
    "minuet",
    "moderato",
    "presto",
    "prestissimo",
    "scherzo",
    "vivace",
    "vivacissimo",
}
WORD = re.compile(r"[a-z]{5,}")
FUZZY_MIN_RATIO = 0.8


def is_fuzzy_semantic(text: str) -> tuple[bool, dict | None]:
    best = None
    for token in WORD.findall(text.lower()):
        for expected in VOCABULARY:
            ratio = SequenceMatcher(None, token, expected).ratio()
            candidate = (ratio, token, expected)
            if best is None or candidate > best:
                best = candidate
    if best is None:
        return False, None
    ratio, token, expected = best
    return ratio >= FUZZY_MIN_RATIO, {
        "observed": token,
        "expected": expected,
        "similarity": round(ratio, 6),
    }


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
        "recall": round(float(tp.sum() / labels.sum()), 6),
        "review_burden": round(float(selected.mean()), 6),
        "false_reset_locations": locations(fp),
        "missed_boundary_locations": locations(fn),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--development-ocr", type=Path, required=True)
    parser.add_argument("--holdout-ocr", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    all_scores = {source["score"] for source in fixture["sources"]}
    development = build_rows(args.fixture, args.development_ocr, all_scores - HOLDOUT)
    holdout = build_rows(args.fixture, args.holdout_ocr, HOLDOUT)
    rows = development + holdout
    first_pages = {
        source["score"]: source["first_musical_source_page"]
        for source in fixture["sources"]
    }
    fuzzy_matches = [is_fuzzy_semantic(row["ocr_text"]) for row in rows]
    geometry = np.asarray([bool(row["features"]["geometry_candidate"]) for row in rows])
    exact = np.asarray([bool(row["features"]["semantic_heading"]) for row in rows])
    fuzzy = np.asarray([active for active, _ in fuzzy_matches])
    initial = np.asarray(
        [
            row["source_page"] == first_pages[row["score"]] and row["system"] == 0
            for row in rows
        ]
    )
    strategies = {
        "geometry_candidate": geometry,
        "exact_semantic_consensus": geometry & exact,
        "fuzzy_semantic_consensus": geometry & (exact | fuzzy),
        "fuzzy_consensus_excluding_initial_document_system": geometry & (exact | fuzzy) & ~initial,
    }
    subsets = {
        "development": np.asarray([row["score"] not in HOLDOUT for row in rows]),
        "holdout": np.asarray([row["score"] in HOLDOUT for row in rows]),
        "all": np.ones(len(rows), dtype=bool),
    }
    report = {
        "schema_version": "issue333.experiment_result.v1",
        "experiment_id": "phase2-post-holdout-robust-verifier-v1",
        "status": "exploratory_post_holdout; cannot supersede the locked holdout result",
        "hypothesis": "Fuzzy musical-heading matching repairs OCR variants while a universal initial-system invariant removes the Toy first-movement false proposal.",
        "parameters": {
            "vocabulary": sorted(VOCABULARY),
            "fuzzy_similarity": "difflib.SequenceMatcher ratio",
            "fuzzy_min_ratio": FUZZY_MIN_RATIO,
            "candidate_gate": "frozen Phase 1 geometry rule",
            "initial_invariant": "the first musical system in a complete document never needs a reset",
        },
        "metrics": {
            split: {
                name: metrics(
                    [row for row, active in zip(rows, subset, strict=True) if active],
                    selected[subset],
                )
                for name, selected in strategies.items()
            }
            for split, subset in subsets.items()
        },
        "fuzzy_evidence": [
            {
                "score": row["score"],
                "page_id": row["page_id"],
                "system": row["system"],
                "label": row["label"],
                "geometry_candidate": bool(geometry[index]),
                "match": match,
                "ocr_text": row["ocr_text"],
            }
            for index, (row, (_, match)) in enumerate(zip(rows, fuzzy_matches, strict=True))
            if match is not None and geometry[index]
        ],
        "interpretation": "This error-aware rule is informative but was designed after inspecting holdout failures and is not independent production evidence.",
        "disposition": "Do not enable automatic reset; retain geometry candidates for review and use fuzzy text only as additional evidence.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
