#!/usr/bin/env python3
"""Temporary Issue #296 audit: was x=580 already a positive in retained Iter5?

Diagnostic-only. Delete before PR preparation.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIAG05 = ROOT / "logs/issue296/diagnostic_05_corrected_finetune/dataset_audit.json"
V5 = ROOT / "datasets/cnn_classifier_v5_rescue_iter1"
OUT = ROOT / "logs/issue296/diagnostic_09_iter5_x580"
GROUP = "Va__Prokofiev_Symphony5_page_015"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    audit = json.loads(DIAG05.read_text(encoding="utf-8"))
    crops = [Path(p) for p in audit.get("target_fp_crops", [])]
    if len(crops) != 1:
        raise SystemExit(f"expected exactly one corrected x580 crop, got {crops}")
    corrected = crops[0]
    if not corrected.is_file():
        raise FileNotFoundError(corrected)
    target_hash = sha256(corrected)

    metadata = V5 / "metadata/samples.csv"
    if not metadata.is_file():
        raise FileNotFoundError(metadata)

    rows = []
    with metadata.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("group") != GROUP:
                continue
            raw = Path(row["path"])
            path = raw if raw.is_absolute() else ROOT / raw
            if not path.is_file():
                continue
            if sha256(path) == target_hash:
                rows.append({
                    "sample_id": row.get("sample_id"),
                    "path": str(path),
                    "label": row.get("label"),
                    "source": row.get("source"),
                    "group": row.get("group"),
                    "split": row.get("split"),
                })

    payload = {
        "schema_version": "issue296.iter5_x580_contamination.v1",
        "corrected_negative_crop": str(corrected),
        "sha256": target_hash,
        "iter5_same_crop_rows_by_sha256": rows,
        "iter5_positive_match_found": any(str(r.get("label")) == "1" for r in rows),
        "iter5_train_positive_match_found": any(
            str(r.get("label")) == "1" and r.get("split") == "train" for r in rows
        ),
        "reconstruction_start": (
            "imagenet_before_iter5"
            if any(str(r.get("label")) == "1" for r in rows)
            else "iter5_not_proven_contaminated_by_this_crop"
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "iter5_x580_contamination.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"RESULT={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
