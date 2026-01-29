#!/usr/bin/env python3
"""
Analyze directory-based image classification for Phase 5b2 review.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-root", type=Path, required=True)
    args = parser.parse_args()

    index_path = args.review_root / "image_index.json"
    classified_root = args.review_root / "classified"
    if not index_path.exists():
        raise FileNotFoundError(f"Missing image_index.json: {index_path}")
    if not classified_root.exists():
        raise FileNotFoundError(f"Missing classified/ directory: {classified_root}")

    index = json.loads(index_path.read_text())
    file_to_meta = {row["filename"]: row for row in index}

    label_map = {}
    labels = [p.name for p in classified_root.iterdir() if p.is_dir()]
    for label in labels:
        for img in (classified_root / label).glob("*.png"):
            label_map[img.name] = label

    per_page = defaultdict(Counter)
    overall = Counter()

    for filename, meta in file_to_meta.items():
        label = label_map.get(filename, "unclassified")
        overall[label] += 1
        per_page[meta["page"]][label] += 1

    summary_md = ["# Review Label Summary", ""]
    summary_md.append("## Overall")
    for label, count in sorted(overall.items()):
        summary_md.append(f"- {label}: {count}")
    summary_md.append("")
    for page, counts in per_page.items():
        summary_md.append(f"## {page}")
        for label, count in sorted(counts.items()):
            summary_md.append(f"- {label}: {count}")
        summary_md.append("")

    summary_path = classified_root / "summary.md"
    summary_path.write_text("\n".join(summary_md))

    csv_path = classified_root / "summary.csv"
    all_labels = sorted(set(list(overall.keys()) + ["unclassified"]))
    with csv_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["page"] + all_labels)
        writer.writerow(["overall"] + [overall.get(label, 0) for label in all_labels])
        for page, counts in sorted(per_page.items()):
            writer.writerow([page] + [counts.get(label, 0) for label in all_labels])

    print(f"Wrote {summary_path}")
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
