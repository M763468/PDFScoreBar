#!/usr/bin/env python3
"""Render retained Issue #284 final numbering on original score pages.

This review helper is read-only: it consumes a completed full68
``variant_summary.json`` plus retained ``numbering_final.json`` artifacts. It
does not rerun detection, grouping, MMR, or numbering.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

Box = tuple[int, int, int, int]
COLORS = [(0, 120, 0), (170, 70, 0), (150, 0, 150), (0, 130, 170)]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def box(value: Any) -> Box | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) < 4:
        return None
    return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]


def one_page(payload: Any, path: Path) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"Numbering payload is not an object: {path}")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], Mapping):
        raise ValueError(f"Expected one-page numbering payload: {path}")
    return pages[0]


def system_box(boxes: list[Box]) -> Box | None:
    if not boxes:
        return None
    return (
        min(item[0] for item in boxes),
        min(item[1] for item in boxes),
        max(item[2] for item in boxes),
        max(item[3] for item in boxes),
    )


def render(
    *, image_path: Path, numbering_path: Path, output_path: Path, score: str, page_name: str
) -> dict[str, Any]:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)
    page = one_page(load_json(numbering_path), numbering_path)
    canvas = image.copy()
    systems_out: list[dict[str, Any]] = []

    systems = page.get("systems", [])
    if not isinstance(systems, list):
        systems = []
    for system_index, system in enumerate(systems):
        if not isinstance(system, Mapping):
            continue
        measures = system.get("measures", [])
        if not isinstance(measures, list):
            measures = []
        color = COLORS[system_index % len(COLORS)]
        measure_boxes: list[Box] = []
        numbers: list[Any] = []
        for measure in measures:
            if not isinstance(measure, Mapping):
                continue
            numbers.append(measure.get("number"))
            bbox = box(measure.get("bbox"))
            if bbox is None:
                continue
            measure_boxes.append(bbox)
            x1, y1, x2, y2 = bbox
            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                canvas,
                str(measure.get("number")),
                (max(0, (x1 + x2) // 2 - 10), max(18, y1 - 7)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.60,
                color,
                2,
                cv2.LINE_AA,
            )
        outer = system_box(measure_boxes)
        if outer is not None:
            x1, y1, x2, y2 = outer
            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 4)
            cv2.putText(
                canvas,
                f"S{system_index} ({len(measures)} measures)",
                (x1 + 4, min(image.shape[0] - 8, y2 + 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.50,
                color,
                2,
                cv2.LINE_AA,
            )
        systems_out.append(
            {
                "system_index": system_index,
                "measure_count": len(measures),
                "numbers": numbers,
                "bbox": list(outer) if outer is not None else None,
            }
        )

    topology = [int(item["measure_count"]) for item in systems_out]
    header = np.full((76, canvas.shape[1], 3), 255, dtype=np.uint8)
    cv2.putText(
        header,
        f"Issue #284 final numbering | {score}/{page_name}",
        (12, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.60,
        (20, 20, 20),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        header,
        f"systems={len(systems_out)} topology={topology} measures={sum(topology)}",
        (12, 52),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (20, 20, 20),
        1,
        cv2.LINE_AA,
    )
    output = np.vstack([header, canvas])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), output):
        raise OSError(output_path)

    flat_numbers = [number for item in systems_out for number in item["numbers"]]
    return {
        "score": score,
        "page": page_name,
        "image": str(image_path.resolve()),
        "numbering_final": str(numbering_path.resolve()),
        "overlay": str(output_path.resolve()),
        "system_count": len(systems_out),
        "topology": topology,
        "serialized_measure_count": sum(topology),
        "first_number": flat_numbers[0] if flat_numbers else None,
        "last_number": flat_numbers[-1] if flat_numbers else None,
        "systems": systems_out,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", type=Path, required=True, help="Completed full68 variant root")
    parser.add_argument("--image-root", type=Path, default=Path("data/evaluation2/images"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--page",
        action="append",
        default=[],
        help="Optional score/page selector; repeat as needed. Default renders all 68 pages.",
    )
    args = parser.parse_args()

    variant = args.variant.resolve()
    summary_path = variant / "variant_summary.json"
    summary = load_json(summary_path)
    if not isinstance(summary, Mapping) or summary.get("status") != "completed":
        raise RuntimeError(f"Variant is not completed: {summary_path}")
    if int(summary.get("canonical_page_count") or 0) != 68:
        raise RuntimeError(f"Variant is not canonical full68: {summary_path}")

    requested = {str(value) for value in args.page}
    pages_out: list[dict[str, Any]] = []
    for score_entry in summary.get("scores", []):
        if not isinstance(score_entry, Mapping):
            continue
        score = str(score_entry.get("score"))
        artifacts = score_entry.get("page_artifacts")
        if not isinstance(artifacts, Mapping):
            continue
        for page_name, raw in artifacts.items():
            selector = f"{score}/{page_name}"
            if requested and selector not in requested:
                continue
            if not isinstance(raw, Mapping) or not raw.get("numbering_final"):
                raise ValueError(f"Missing numbering_final artifact: {selector}")
            pages_out.append(
                render(
                    image_path=args.image_root / score / f"{page_name}.png",
                    numbering_path=Path(str(raw["numbering_final"])),
                    output_path=args.output_dir / score / f"{page_name}_numbering_final.png",
                    score=score,
                    page_name=str(page_name),
                )
            )

    if requested:
        actual = {f"{item['score']}/{item['page']}" for item in pages_out}
        missing = sorted(requested - actual)
        if missing:
            raise ValueError("Requested pages not found: " + ", ".join(missing))
    if not pages_out:
        raise RuntimeError("No pages rendered")

    payload = {
        "schema_version": "issue284.full68_numbering_visual_review.v1",
        "variant": str(variant),
        "variant_git_commit": summary.get("git_commit"),
        "canonical_page_count": summary.get("canonical_page_count"),
        "rendered_page_count": len(pages_out),
        "pages": pages_out,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "issue284_full68_numbering_visual_review.json"
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
