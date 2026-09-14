#!/usr/bin/env python3
"""Render Issue #277 candidate-space diagnostics for human visual inspection.

This is visualization-only. It does not run OCR or change any selection rule. It loads
the retained native maintained-B page image plus the candidate-space artifact and
renders, for every traced key:

* a page-context crop with measure/staff/bar/group overlays;
* each original digit-group OCR crop;
* the corresponding horizontal-suppressed isolated bitmap;
* compact contact sheets grouped by failure mode.

The goal is to inspect what the algorithm is actually looking at before changing
candidate-generation or selection heuristics.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import probe_bar_digit_candidate_space as trace_probe
import probe_native_geometry_robustness as base

FONT = cv2.FONT_HERSHEY_SIMPLEX


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_name(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", key)


def _clip_bbox(bbox: list[int], width: int, height: int) -> list[int]:
    x1, y1, x2, y2 = (int(v) for v in bbox)
    return [
        max(0, min(width - 1, x1)),
        max(0, min(height - 1, y1)),
        max(1, min(width, x2)),
        max(1, min(height, y2)),
    ]


def _put_label(
    image: np.ndarray,
    text: str,
    origin: tuple[int, int],
    color: tuple[int, int, int],
    scale: float = 0.55,
) -> None:
    x, y = origin
    (tw, th), baseline = cv2.getTextSize(text, FONT, scale, 1)
    x = max(0, min(image.shape[1] - tw - 4, x))
    y = max(th + baseline + 4, min(image.shape[0] - 2, y))
    cv2.rectangle(
        image,
        (x, y - th - baseline - 4),
        (x + tw + 4, y + 2),
        (255, 255, 255),
        -1,
    )
    cv2.putText(image, text, (x + 2, y - baseline - 1), FONT, scale, color, 1, cv2.LINE_AA)


def _draw_rect(
    image: np.ndarray,
    bbox: list[int],
    color: tuple[int, int, int],
    thickness: int = 2,
) -> None:
    x1, y1, x2, y2 = (int(v) for v in bbox)
    cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)


def _offset_bbox(bbox: list[int], origin: tuple[int, int]) -> list[int]:
    ox, oy = origin
    x1, y1, x2, y2 = (int(v) for v in bbox)
    return [x1 - ox, y1 - oy, x2 - ox, y2 - oy]


def _panel_header(panel: np.ndarray, lines: list[str]) -> np.ndarray:
    header_h = max(48, 24 + 22 * len(lines))
    header = np.full((header_h, panel.shape[1], 3), 255, dtype=np.uint8)
    for index, line in enumerate(lines):
        cv2.putText(
            header,
            line,
            (8, 22 + index * 22),
            FONT,
            0.55,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
    return np.vstack([header, panel])


def _fit(image: np.ndarray, max_width: int, max_height: int) -> np.ndarray:
    if image is None or image.size == 0:
        return np.full((80, 160, 3), 255, dtype=np.uint8)
    height, width = image.shape[:2]
    scale = min(max_width / max(1, width), max_height / max(1, height), 1.0)
    if scale < 1.0:
        image = cv2.resize(
            image,
            (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
            interpolation=cv2.INTER_AREA,
        )
    return image


def _pad_to(image: np.ndarray, width: int, height: int) -> np.ndarray:
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    h, w = image.shape[:2]
    x = max(0, (width - w) // 2)
    y = max(0, (height - h) // 2)
    canvas[y : y + h, x : x + w] = image[: min(h, height), : min(w, width)]
    return canvas


def _ocr_summary(result: Mapping[str, Any]) -> str:
    skip = result.get("skip")
    debug = str(result.get("debug") or "")
    raw = result.get("raw") or []
    texts = []
    for item in raw:
        if isinstance(item, Mapping) and "text" in item:
            texts.append(str(item["text"]))
    raw_text = "|".join(texts[:4]) if texts else "-"
    return f"skip={skip} raw={raw_text} {debug}"[:150]


def _render_event(
    image: np.ndarray,
    system: Mapping[str, Any],
    event: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    height, width = image.shape[:2]
    measure_bbox = [int(v) for v in event["measure_bbox"]]
    staves = system.get("staves", [])
    staff_heights = [
        max(1, int(stave["bbox"][3]) - int(stave["bbox"][1])) for stave in staves
    ]
    typical_staff = int(np.median(staff_heights)) if staff_heights else 120
    margin_x = max(80, int(round(1.2 * typical_staff)))
    margin_y = max(100, int(round(1.5 * typical_staff)))
    context_bbox = _clip_bbox(
        [
            measure_bbox[0] - margin_x,
            min([int(s["bbox"][1]) for s in staves], default=measure_bbox[1]) - margin_y,
            measure_bbox[2] + margin_x,
            max([int(s["bbox"][3]) for s in staves], default=measure_bbox[3]) + margin_y,
        ],
        width,
        height,
    )
    cx1, cy1, cx2, cy2 = context_bbox
    context = image[cy1:cy2, cx1:cx2].copy()

    # High-contrast diagnostic colors: measure=yellow, staves=cyan,
    # cluster 0 bars/groups=red/magenta, cluster 1=green/blue.
    _draw_rect(context, _offset_bbox(measure_bbox, (cx1, cy1)), (0, 215, 255), 3)
    _put_label(
        context,
        "measure",
        tuple(_offset_bbox(measure_bbox, (cx1, cy1))[:2]),
        (0, 120, 160),
    )
    for staff_index, stave in enumerate(staves):
        staff_bbox = [int(v) for v in stave["bbox"]]
        local = _offset_bbox(staff_bbox, (cx1, cy1))
        _draw_rect(context, local, (255, 200, 0), 1)
        _put_label(context, f"staff {staff_index}", (local[0], local[1]), (160, 80, 0), 0.45)

    cluster_colors = [
        ((0, 0, 255), (255, 0, 255)),
        ((0, 160, 0), (255, 80, 0)),
        ((0, 120, 255), (180, 0, 180)),
    ]
    crop_records = []
    for cluster in event.get("clusters", []):
        cluster_index = int(cluster.get("cluster_index", 0))
        bar_color, group_color = cluster_colors[cluster_index % len(cluster_colors)]
        for bar_index, bar_entry in enumerate(cluster.get("bars", [])):
            bar = bar_entry["bar"]
            local_bar = _offset_bbox([int(v) for v in bar["bbox"]], (cx1, cy1))
            _draw_rect(context, local_bar, bar_color, 3)
            _put_label(
                context,
                f"C{cluster_index} S{bar_entry['staff']} bar",
                (local_bar[0], local_bar[1]),
                bar_color,
                0.48,
            )
            for group_index, trace in enumerate(bar_entry.get("groups", [])):
                group_bbox = [int(v) for v in trace["group"]["bbox"]]
                local_group = _offset_bbox(group_bbox, (cx1, cy1))
                _draw_rect(context, local_group, group_color, 2)
                original = trace["original"]
                isolated = trace["isolated"]
                _put_label(
                    context,
                    f"G{group_index} o={original.get('skip')} i={isolated.get('skip')}",
                    (local_group[0], max(12, local_group[1] - 3)),
                    group_color,
                    0.43,
                )

                original_bbox = [int(v) for v in trace["original_bbox"]]
                original_crop = image[
                    original_bbox[1] : original_bbox[3],
                    original_bbox[0] : original_bbox[2],
                ].copy()
                isolated_crop, _isolated_bbox, _isolated_debug = trace_probe._isolated_group_image(
                    image, bar, trace["group"]
                )
                crop_records.append(
                    {
                        "cluster": cluster_index,
                        "staff": int(bar_entry["staff"]),
                        "group": group_index,
                        "original": original_crop,
                        "isolated": isolated_crop,
                        "original_text": _ocr_summary(original),
                        "isolated_text": _ocr_summary(isolated),
                    }
                )

    key = str(event["key"])
    context = _panel_header(
        context,
        [
            f"{key} expected_skip={event.get('expected_skip')} policy={event['selected_policy'].get('skip')}",
            f"reason={event['selected_policy'].get('selection_reason')} original={event.get('original_candidate_skips')} isolated={event.get('isolated_candidate_skips')}",
            "measure=yellow staff=cyan; C0=red/magenta C1=green/blue",
        ],
    )
    context_path = output_dir / f"{_safe_name(key)}__context.png"
    cv2.imwrite(str(context_path), context)

    tiles = []
    tile_w, tile_h = 360, 230
    for record in crop_records:
        for kind in ("original", "isolated"):
            crop = record[kind]
            if crop is None or crop.size == 0:
                crop = np.full((60, 120, 3), 255, dtype=np.uint8)
            crop = _fit(crop, tile_w - 16, 135)
            tile = np.full((tile_h, tile_w, 3), 255, dtype=np.uint8)
            tile[: crop.shape[0], : crop.shape[1]] = crop
            label = (
                f"C{record['cluster']} S{record['staff']} G{record['group']} {kind}"
            )
            cv2.putText(tile, label, (6, 160), FONT, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
            text = record[f"{kind}_text"]
            for line_index in range(0, min(len(text), 144), 48):
                cv2.putText(
                    tile,
                    text[line_index : line_index + 48],
                    (6, 182 + (line_index // 48) * 18),
                    FONT,
                    0.42,
                    (0, 0, 0),
                    1,
                    cv2.LINE_AA,
                )
            tiles.append(tile)

    if tiles:
        cols = 3
        rows = (len(tiles) + cols - 1) // cols
        sheet = np.full((rows * tile_h, cols * tile_w, 3), 245, dtype=np.uint8)
        for index, tile in enumerate(tiles):
            row, col = divmod(index, cols)
            sheet[
                row * tile_h : (row + 1) * tile_h,
                col * tile_w : (col + 1) * tile_w,
            ] = tile
        crops_path = output_dir / f"{_safe_name(key)}__candidates.png"
        cv2.imwrite(str(crops_path), sheet)
    else:
        crops_path = None

    return {
        "key": key,
        "expected_skip": event.get("expected_skip"),
        "policy_skip": event["selected_policy"].get("skip"),
        "policy_reason": event["selected_policy"].get("selection_reason"),
        "expected_seen_original": bool(event.get("expected_seen_original")),
        "expected_seen_isolated": bool(event.get("expected_seen_isolated")),
        "context": str(context_path),
        "candidates": None if crops_path is None else str(crops_path),
    }


def _category(item: Mapping[str, Any]) -> str:
    expected = item.get("expected_skip")
    policy = item.get("policy_skip")
    seen = bool(item.get("expected_seen_original") or item.get("expected_seen_isolated"))
    if expected is None:
        return "false_positive_risk" if policy is not None else "negative_control"
    if policy == expected:
        return "correct_control"
    if seen:
        return "selection_error_expected_exists"
    return "candidate_generation_missing"


def _make_contact_sheet(
    records: list[dict[str, Any]],
    category: str,
    output_dir: Path,
) -> Path | None:
    category_records = [item for item in records if _category(item) == category]
    if not category_records:
        return None
    thumb_w, thumb_h = 760, 500
    cols = 2
    rows = (len(category_records) + cols - 1) // cols
    canvas = np.full((rows * thumb_h, cols * thumb_w, 3), 245, dtype=np.uint8)
    for index, item in enumerate(category_records):
        image = cv2.imread(item["context"])
        if image is None:
            continue
        fitted = _fit(image, thumb_w - 20, thumb_h - 20)
        tile = _pad_to(fitted, thumb_w, thumb_h)
        row, col = divmod(index, cols)
        canvas[
            row * thumb_h : (row + 1) * thumb_h,
            col * thumb_w : (col + 1) * thumb_w,
        ] = tile
    path = output_dir / f"CONTACT__{category}.png"
    cv2.imwrite(str(path), canvas)
    return path


def run(args: argparse.Namespace) -> dict[str, Any]:
    issue294_root = args.issue294_root.resolve()
    artifact_path = args.candidate_space_artifact.resolve()
    output_dir = args.output_dir.resolve()
    if not artifact_path.is_file():
        raise FileNotFoundError(artifact_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    artifact = _load(artifact_path)
    events = artifact.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("candidate-space artifact lacks events")

    manifest_path = (
        args.manifest.resolve()
        if args.manifest is not None
        else (issue294_root / base.DEFAULT_MANIFEST_REL).resolve()
    )
    manifest = base._load_json(manifest_path)
    matrix_pages = base._load_matrix_pages(manifest, issue294_root)
    specs = {str(spec.page_id): spec for spec in base.build_page_specs()}

    events_by_page: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        events_by_page[str(event["page_id"])].append(event)

    records = []
    for page_id in sorted(events_by_page):
        spec = specs[page_id]
        matrix_page = matrix_pages[(str(spec.score), str(spec.page_name))]
        _page_data, image_path, support, _mapping_mode = base._build_candidate_page(
            spec, matrix_page, issue294_root
        )
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        systems = support["views"]["primary"]["pages"][0]["systems"]
        for event in events_by_page[page_id]:
            system = systems[int(event["system"])]
            records.append(_render_event(image, system, event, output_dir))

    categories = [
        "selection_error_expected_exists",
        "candidate_generation_missing",
        "false_positive_risk",
        "negative_control",
        "correct_control",
    ]
    sheets = {}
    for category in categories:
        path = _make_contact_sheet(records, category, output_dir)
        if path is not None:
            sheets[category] = str(path)

    manifest_out = {
        "schema_version": "issue277.visual_candidate_diagnostics.v1",
        "status": "completed",
        "source_artifact": str(artifact_path),
        "output_dir": str(output_dir),
        "records": [{**item, "category": _category(item)} for item in records],
        "contact_sheets": sheets,
    }
    manifest_file = output_dir / "manifest.json"
    manifest_file.write_text(
        json.dumps(manifest_out, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--issue294-root",
        type=Path,
        default=base.DEFAULT_ISSUE294_ROOT,
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--candidate-space-artifact", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    try:
        result = run(args)
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "output_dir": result["output_dir"],
                    "record_count": len(result["records"]),
                    "contact_sheets": result["contact_sheets"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:  # pragma: no cover - diagnostic CLI
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
