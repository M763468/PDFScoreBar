from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from src.measure_numbering.builder import SystemBuilder
from src.measure_numbering.pipeline import StaffExtractor
from src.measure_numbering.types import BBox, Barline


# These are local constants in SystemBuilder._group_by_geometry(), not attributes.
DIVISI_DIST_RATIO = 1.5
ALIGN_TOL = 10

TARGETS = {
    "page_021": "Shostakovich-Sym5-Va_page_013",
    "page_022": "Shostakovich-Sym5-Va_page_014",
    "page_045": "Va_Prokofiev_Symphony1_page_004",
}

MANIFEST = Path("logs/issue120_e2e_recovery/stage_e_full_pipeline/manifest.json")
OUT = Path("logs/issue197_system_grouping/system_grouping_decision_trace.json")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def bbox_list(b: BBox) -> list[int]:
    return [int(b.x1), int(b.y1), int(b.x2), int(b.y2)]


def parse_bbox_from_obj(obj: Any) -> list[int] | None:
    """Best-effort bbox parser for detector output variants."""
    if isinstance(obj, (list, tuple)) and len(obj) >= 4:
        try:
            vals = [int(round(float(v))) for v in obj[:4]]
        except Exception:
            return None
        x1, y1, x2, y2 = vals
        if x2 > x1 and y2 > y1:
            return [x1, y1, x2, y2]
        if x2 > 0 and y2 > 0:
            return [x1, y1, x1 + x2, y1 + y2]
        return None

    if not isinstance(obj, dict):
        return None

    for key in ("bbox", "box", "rect"):
        if key in obj:
            parsed = parse_bbox_from_obj(obj[key])
            if parsed is not None:
                return parsed

    if all(k in obj for k in ("x1", "y1", "x2", "y2")):
        try:
            x1, y1, x2, y2 = [int(round(float(obj[k]))) for k in ("x1", "y1", "x2", "y2")]
        except Exception:
            return None
        if x2 > x1 and y2 > y1:
            return [x1, y1, x2, y2]

    if all(k in obj for k in ("x", "y", "w", "h")):
        try:
            x, y, w, h = [int(round(float(obj[k]))) for k in ("x", "y", "w", "h")]
        except Exception:
            return None
        if w > 0 and h > 0:
            return [x, y, x + w, y + h]

    return None


def iter_nodes(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from iter_nodes(v)
    elif isinstance(obj, list):
        yield obj
        for v in obj:
            yield from iter_nodes(v)


def load_barlines(path: Path, image_shape_hw: tuple[int, int]) -> tuple[list[Barline], dict[str, Any]]:
    raw = load_json(path)
    img_h, img_w = image_shape_hw

    boxes: list[list[int]] = []
    for node in iter_nodes(raw):
        b = parse_bbox_from_obj(node)
        if b is None:
            continue

        x1, y1, x2, y2 = b
        if not (0 <= x1 < x2 <= img_w and 0 <= y1 < y2 <= img_h):
            continue

        w = x2 - x1
        h = y2 - y1

        # Keep permissive but vertical. This is only diagnostic.
        if h < 20:
            continue
        if w > 100:
            continue
        if h < w:
            continue

        boxes.append([x1, y1, x2, y2])

    seen = set()
    deduped: list[list[int]] = []
    for b in boxes:
        t = tuple(b)
        if t in seen:
            continue
        seen.add(t)
        deduped.append(b)

    barlines = [
        Barline(bbox=BBox(x1=x1, y1=y1, x2=x2, y2=y2), is_ghost=False)
        for x1, y1, x2, y2 in deduped
    ]

    return barlines, {
        "raw_type": type(raw).__name__,
        "candidate_box_count": len(boxes),
        "deduped_barline_count": len(barlines),
        "sample_boxes": deduped[:20],
    }


def resolve_manifest_pages() -> dict[str, dict[str, str]]:
    manifest = load_json(MANIFEST)
    resolved: dict[str, dict[str, str]] = {}

    for page in manifest.get("pages", []):
        page_id = page.get("page_id")
        if page_id in TARGETS:
            resolved[page_id] = {
                "source": TARGETS[page_id],
                "image_path": page["image_path"],
                "barlines_json": page["barlines_json"],
                "staff_mask": page["staff_mask"],
                "numbering_base": (
                    f"logs/issue120_e2e_recovery/stage_e_full_pipeline/"
                    f"intermediate/{page_id}/numbering_base.json"
                ),
            }

    missing = sorted(set(TARGETS) - set(resolved))
    if missing:
        raise RuntimeError(f"Missing target pages in manifest: {missing}")

    return resolved


def aligned_pairs(s1, s2):
    pairs = []
    for b1 in s1.barlines:
        c1 = (b1.bbox.x1 + b1.bbox.x2) / 2
        for b2 in s2.barlines:
            c2 = (b2.bbox.x1 + b2.bbox.x2) / 2
            if abs(c1 - c2) <= ALIGN_TOL:
                pairs.append((b1, b2))
                break
    return pairs


def left_connector_ink_features(image_bgr: np.ndarray, s1, s2) -> dict[str, Any]:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    gap_y1 = int(s1.bbox.y2)
    gap_y2 = int(s2.bbox.y1)
    if gap_y2 <= gap_y1:
        return {"valid": False, "reason": "non_positive_gap"}

    left = min(int(s1.bbox.x1), int(s2.bbox.x1))
    x1 = max(0, left - 100)
    x2 = min(binary.shape[1], left + 120)

    gap_roi = binary[gap_y1:gap_y2, x1:x2]
    full_roi = binary[int(s1.bbox.y1):int(s2.bbox.y2), x1:x2]

    gap_h = gap_y2 - gap_y1
    gap_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, max(5, int(gap_h * 0.65))))
    gap_open = cv2.morphologyEx(gap_roi, cv2.MORPH_OPEN, gap_kernel)

    full_h = int(s2.bbox.y2) - int(s1.bbox.y1)
    full_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, max(10, int(full_h * 0.45))))
    full_open = cv2.morphologyEx(full_roi, cv2.MORPH_OPEN, full_kernel)

    return {
        "valid": True,
        "roi_gap_xyxy": [int(x1), int(gap_y1), int(x2), int(gap_y2)],
        "gap_black_pixels": int(cv2.countNonZero(gap_roi)),
        "gap_vertical_open_pixels": int(cv2.countNonZero(gap_open)),
        "full_vertical_open_pixels": int(cv2.countNonZero(full_open)),
        "gap_black_density": float(cv2.countNonZero(gap_roi) / max(1, gap_roi.size)),
        "gap_vertical_open_density": float(cv2.countNonZero(gap_open) / max(1, gap_open.size)),
    }


def main() -> None:
    resolved = resolve_manifest_pages()

    extractor = StaffExtractor()
    builder = SystemBuilder()

    report: dict[str, Any] = {
        "constants": {
            "DIVISI_DIST_RATIO": DIVISI_DIST_RATIO,
            "ALIGN_TOL": ALIGN_TOL,
        },
        "targets": resolved,
        "pages": {},
    }

    for page_id, paths in resolved.items():
        image_path = Path(paths["image_path"])
        staff_mask_path = Path(paths["staff_mask"])
        barlines_path = Path(paths["barlines_json"])
        numbering_base_path = Path(paths["numbering_base"])

        missing = [
            str(p)
            for p in (image_path, staff_mask_path, barlines_path, numbering_base_path)
            if not p.exists()
        ]
        if missing:
            report["pages"][page_id] = {"error": "missing_inputs", "missing": missing}
            continue

        image_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image_bgr is None:
            report["pages"][page_id] = {
                "error": "failed_to_load_image",
                "image_path": str(image_path),
            }
            continue

        image_h, image_w = image_bgr.shape[:2]

        # StaffExtractor.extract currently accepts (mask_path, target_size), not image_size=...
        staves = extractor.extract(staff_mask_path, (image_w, image_h))
        barlines, barline_meta = load_barlines(barlines_path, (image_h, image_w))

        systems = builder.build_systems(staves, barlines, image=image_bgr)

        staff_to_system: dict[int, int] = {}
        for sys_idx, sys in enumerate(systems):
            for staff in sys.staves:
                staff_to_system[id(staff)] = sys_idx

        avg_height = sum(s.bbox.height for s in staves) / max(1, len(staves))
        dist_threshold = avg_height * DIVISI_DIST_RATIO

        adjacent = []
        sorted_staves = sorted(staves, key=lambda s: s.bbox.y1)
        for i in range(len(sorted_staves) - 1):
            s1 = sorted_staves[i]
            s2 = sorted_staves[i + 1]

            gap = s2.bbox.y1 - s1.bbox.y2
            pairs = aligned_pairs(s1, s2)

            try:
                aligned_connection = builder._check_aligned_connection(s1, s2, pairs, image_bgr)
            except Exception as e:
                aligned_connection = f"{type(e).__name__}: {e}"

            adjacent.append({
                "staff_pair": [i, i + 1],
                "same_system": staff_to_system.get(id(s1)) == staff_to_system.get(id(s2)),
                "system_indices": [staff_to_system.get(id(s1)), staff_to_system.get(id(s2))],
                "s1_bbox": bbox_list(s1.bbox),
                "s2_bbox": bbox_list(s2.bbox),
                "vertical_gap": int(gap),
                "avg_staff_height_global": float(avg_height),
                "gap_over_global_avg_height": float(gap / avg_height) if avg_height else None,
                "dist_threshold": float(dist_threshold),
                "passes_distance_gate": bool(gap <= dist_threshold),
                "left_delta": int(s2.bbox.x1 - s1.bbox.x1),
                "right_delta": int(s2.bbox.x2 - s1.bbox.x2),
                "width_ratio": float(s2.bbox.width / max(1, s1.bbox.width)),
                "s1_barline_count": len(s1.barlines),
                "s2_barline_count": len(s2.barlines),
                "aligned_barline_count_tol10": len(pairs),
                "aligned_barline_centers_sample": [
                    [
                        float((a.bbox.x1 + a.bbox.x2) / 2),
                        float((b.bbox.x1 + b.bbox.x2) / 2),
                    ]
                    for a, b in pairs[:12]
                ],
                "aligned_connection": aligned_connection,
                "left_connector_ink": left_connector_ink_features(image_bgr, s1, s2),
            })

        numbering_base = load_json(numbering_base_path)

        report["pages"][page_id] = {
            "source": paths["source"],
            "image_shape_hw": [int(image_h), int(image_w)],
            "barline_meta": barline_meta,
            "extracted_staff_count": len(staves),
            "built_system_count": len(systems),
            "numbering_base_system_count": len(numbering_base.get("systems", [])),
            "avg_staff_height_global": float(avg_height),
            "dist_threshold": float(dist_threshold),
            "systems": [
                {
                    "system_index": idx,
                    "staff_count": len(sys.staves),
                    "staff_bboxes": [bbox_list(s.bbox) for s in sys.staves],
                    "barline_counts": [len(s.barlines) for s in sys.staves],
                }
                for idx, sys in enumerate(systems)
            ],
            "adjacent_staff_pairs": adjacent,
        }

    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
