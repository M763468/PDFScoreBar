#!/usr/bin/env python3
"""Render all Issue #291 P1 same-ink GT pairs on canonical score images.

Investigation-only helper. It reads canonical GT and page images, writes crops/contact
sheets, and never modifies GT or runs detector inference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from itertools import combinations
from pathlib import Path
from typing import Any

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
GT_ROOT = ROOT / "data/evaluation2/annotations"
P1_X_OVERLAP = 0.25
P1_Y_OVERLAP = 0.70
P3_TYPES = {"double_barline", "end_barline", "repeat"}
P3_X_CENTER = 15.0


def _bbox(row: dict[str, Any]) -> tuple[int, int, int, int]:
    return tuple(int(round(float(v))) for v in row["barline_location"][:4])  # type: ignore[return-value]


def _overlap(a1: int, a2: int, b1: int, b2: int) -> int:
    return max(0, min(a2, b2) - max(a1, b1))


def _metrics(a: dict[str, Any], b: dict[str, Any]) -> dict[str, float]:
    ax1, ay1, ax2, ay2 = _bbox(a)
    bx1, by1, bx2, by2 = _bbox(b)
    aw, bw = max(1, ax2 - ax1), max(1, bx2 - bx1)
    ah, bh = max(1, ay2 - ay1), max(1, by2 - by1)
    return {
        "x_center_delta": abs((ax1 + ax2) / 2 - (bx1 + bx2) / 2),
        "x_overlap_over_min_width": _overlap(ax1, ax2, bx1, bx2) / min(aw, bw),
        "y_overlap_over_min_height": _overlap(ay1, ay2, by1, by2) / min(ah, bh),
    }


def _classify(rows: list[dict[str, Any]]) -> tuple[list[tuple[int, int, dict[str, float]]], list[tuple[int, int, dict[str, float]]]]:
    p1: list[tuple[int, int, dict[str, float]]] = []
    p3: list[tuple[int, int, dict[str, float]]] = []
    for (ia, a), (ib, b) in combinations(enumerate(rows), 2):
        m = _metrics(a, b)
        ta = str(a.get("barline_type") or "barline")
        tb = str(b.get("barline_type") or "barline")
        if (
            ta == tb == "barline"
            and m["x_overlap_over_min_width"] >= P1_X_OVERLAP
            and m["y_overlap_over_min_height"] >= P1_Y_OVERLAP
        ):
            p1.append((ia, ib, m))
        elif (
            ({ta, tb} & P3_TYPES)
            and m["x_center_delta"] <= P3_X_CENTER
            and m["y_overlap_over_min_height"] >= P1_Y_OVERLAP
        ):
            p3.append((ia, ib, m))
    return p1, p3


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _crop_bounds(boxes: list[tuple[int, int, int, int]], width: int, height: int) -> tuple[int, int, int, int]:
    x1 = min(b[0] for b in boxes) - 220
    y1 = min(b[1] for b in boxes) - 150
    x2 = max(b[2] for b in boxes) + 220
    y2 = max(b[3] for b in boxes) + 150
    if x2 - x1 < 640:
        d = 640 - (x2 - x1)
        x1 -= d // 2
        x2 += d - d // 2
    if y2 - y1 < 420:
        d = 420 - (y2 - y1)
        y1 -= d // 2
        y2 += d - d // 2
    return max(0, x1), max(0, y1), min(width, x2), min(height, y2)


def _tile(image: np.ndarray, width: int = 920, height: int = 620) -> np.ndarray:
    scale = min(width / image.shape[1], height / image.shape[0])
    resized = cv2.resize(image, (max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale))))
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    x = (width - resized.shape[1]) // 2
    y = (height - resized.shape[0]) // 2
    canvas[y:y + resized.shape[0], x:x + resized.shape[1]] = resized
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-root", type=Path, default=ROOT / "data/evaluation2/images")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    tiles: list[np.ndarray] = []
    p3_total = 0
    p1_ordinal = 0

    for gt_path in sorted(GT_ROOT.glob("*/page_*/boxes_sorted.json")):
        score, page = gt_path.parent.parent.name, gt_path.parent.name
        rows = json.loads(gt_path.read_text(encoding="utf-8"))
        p1_pairs, p3_pairs = _classify(rows)
        p3_total += len(p3_pairs)
        if not p1_pairs:
            continue
        image_path = args.image_root / score / f"{page}.png"
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"Canonical source page not found: {image_path}")

        for ia, ib, metrics in p1_pairs:
            p1_ordinal += 1
            a, b = rows[ia], rows[ib]
            ba, bb = _bbox(a), _bbox(b)
            canvas = image.copy()
            cv2.rectangle(canvas, (ba[0], ba[1]), (ba[2], ba[3]), (0, 0, 255), 5)
            cv2.rectangle(canvas, (bb[0], bb[1]), (bb[2], bb[3]), (255, 0, 0), 3)
            x1, y1, x2, y2 = _crop_bounds([ba, bb], image.shape[1], image.shape[0])
            crop = canvas[y1:y2, x1:x2].copy()
            header = np.full((115, crop.shape[1], 3), 255, dtype=np.uint8)
            lines = [
                f"P1 {p1_ordinal:02d} | {score}/{page} | GT idx {ia} vs {ib}",
                f"red={list(ba)} m={a.get('measure_number')} | blue={list(bb)} m={b.get('measure_number')}",
                f"dx={metrics['x_center_delta']:.2f} xOverlap/min={metrics['x_overlap_over_min_width']:.3f} yOverlap/min={metrics['y_overlap_over_min_height']:.3f}",
                "Review question: do red/blue denote the same physical ink event?",
            ]
            for line_no, text in enumerate(lines):
                cv2.putText(header, text, (12, 24 + 27 * line_no), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (20, 20, 20), 1, cv2.LINE_AA)
            annotated = np.vstack([header, crop])
            filename = f"{p1_ordinal:02d}_{score}_{page}_idx{ia}_{ib}.png"
            output_path = args.output_dir / filename
            if not cv2.imwrite(str(output_path), annotated):
                raise OSError(output_path)
            tiles.append(_tile(annotated))
            records.append({
                "ordinal": p1_ordinal,
                "score": score,
                "page": page,
                "gt_file": str(gt_path.relative_to(ROOT)),
                "image": str(image_path),
                "image_sha256": _sha256(image_path),
                "a": {"index": ia, "measure_number": a.get("measure_number"), "barline_type": a.get("barline_type"), "bbox": list(ba)},
                "b": {"index": ib, "measure_number": b.get("measure_number"), "barline_type": b.get("barline_type"), "bbox": list(bb)},
                "metrics": metrics,
                "crop": [x1, y1, x2, y2],
                "output": str(output_path),
            })

    if len(records) != 12 or len({(r['score'], r['page']) for r in records}) != 10 or p3_total != 51:
        raise RuntimeError(f"Issue #274 invariants changed: P1={len(records)}, P1 pages={len({(r['score'], r['page']) for r in records})}, P3={p3_total}")

    columns = 2
    while len(tiles) % columns:
        tiles.append(np.full_like(tiles[0], 255))
    sheet = np.vstack([np.hstack(tiles[i:i + columns]) for i in range(0, len(tiles), columns)])
    sheet_path = args.output_dir / "issue291_p1_12pair_contact_sheet.png"
    if not cv2.imwrite(str(sheet_path), sheet):
        raise OSError(sheet_path)

    manifest = {
        "schema_version": "issue291.p1_visual_review.v1",
        "p1_pair_count": len(records),
        "p1_page_count": len({(r['score'], r['page']) for r in records}),
        "p3_pair_count": p3_total,
        "contact_sheet": str(sheet_path),
        "cases": records,
    }
    manifest_path = args.output_dir / "issue291_p1_visual_review.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
