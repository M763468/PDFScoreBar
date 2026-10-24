"""Experimental, sidecar-bound numbering layer for an already annotated score.

Fixed acceptance: preserve CropBox/MediaBox, all original dark pixels (<250 at
144 DPI), all original annotations, and place every row label at >=8 pt. Never
erase or classify user ink. This is a focused experiment, not a public import API.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import fitz
import numpy as np
from PIL import Image

from src.pipeline.review.final_output import _first_page_payload, _row_label_records
from tools.issue441.mobile_export_probe import note_signature
from tools.issue441.phase0_probe import sha

ZOOM = 2
WHITE_FLOOR = 250
MARKER = "issue441.experimental.row_numbers.v1"


def records_from_run(handoff, run):
    data = json.loads(Path(handoff).read_text())
    result = []
    for page in data["pages"]:
        numbering = Path(run) / "outputs" / page["page_id"] / "numbering_final.json"
        payload = _first_page_payload(json.loads(numbering.read_text()), numbering)
        with Image.open(Path(handoff).parent / page["source_image"]) as image:
            size = image.size
        result.append(
            {
                "source_pixels": size,
                "rows": _row_label_records(
                    page_id=page["page_id"], page_number=page["page_number"], page_payload=payload
                ),
            }
        )
    return result


def pix_array(page):
    pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)


def find_placement(page, pixels, text, staff, previous_top, occupied):
    font = fitz.Font("hebo")
    unit = staff.height
    gap = max(1, unit * 0.04)
    note_boxes = [a.rect for a in page.annots() or []]
    preferred_size = min(10.0, max(8.0, unit * 0.20))
    sizes = list(dict.fromkeys([preferred_size, 8.0]))
    for size in sizes:
        width = font.text_length(text, fontsize=size)
        height = (font.ascender - font.descender) * size
        min_y = max(gap, (previous_top + staff.y0) / 2 if previous_top is not None else gap)
        max_y = min(page.rect.height - height - gap, staff.y0 + unit * 0.25)
        min_x = gap
        max_x = min(page.rect.width - width - gap, staff.x0 + unit)
        preferred_x = max(min_x, min(max_x, staff.x0 - width - gap))
        preferred_y = staff.y0 - height - gap
        step = max(size / 4, unit * 0.08)
        xs = [preferred_x] + list(np.arange(min_x, max_x + 0.001, step))
        ys = sorted(np.arange(min_y, max_y + 0.001, step), key=lambda y: abs(y - preferred_y))
        for y in ys:
            for x in xs:
                rect = fitz.Rect(x, y, x + width, y + height)
                padded = rect + (-gap, -gap, gap, gap)
                if not page.rect.contains(padded):
                    continue
                if any(padded.intersects(box) for box in note_boxes + occupied):
                    continue
                x0, y0 = math.floor(padded.x0 * ZOOM), math.floor(padded.y0 * ZOOM)
                x1, y1 = math.ceil(padded.x1 * ZOOM), math.ceil(padded.y1 * ZOOM)
                region = pixels[y0:y1, x0:x1]
                if region.size and np.min(region) >= WHITE_FLOOR:
                    return rect, float(size), float(y + font.ascender * size), padded
    raise ValueError(f"No safe >=8pt placement for {text} near staff top {staff.y0:.2f}")


def remove_owned_layer(doc, sidecar):
    for index, saved in enumerate(sidecar["pages"]):
        page = doc[index]
        expected = saved["source_contents"] + [s["xref"] for s in saved["number_streams"]]
        if page.get_contents() != expected:
            raise ValueError("Page contents changed since layer was recorded")
        for stream in saved["number_streams"]:
            xref = stream["xref"]
            if hashlib.sha256(doc.xref_stream(xref)).hexdigest() != stream["sha256"]:
                raise ValueError("Number stream changed since recording")
            if doc.xref_get_key(xref, "PDFScoreBarNumbers")[1] != MARKER:
                raise ValueError("Number stream marker changed")
        refs = " ".join(f"{x} 0 R" for x in saved["source_contents"])
        doc.xref_set_key(page.xref, "Contents", f"[{refs}]")


def write_number_layer(input_pdf, original_pdf, numbering, output, *, previous_sidecar=None):
    input_pdf, original_pdf, output = map(Path, (input_pdf, original_pdf, output))
    if output.exists():
        raise FileExistsError(output)
    old = json.loads(Path(previous_sidecar).read_text()) if previous_sidecar else None
    if old and (
        old["output_sha256"] != sha(input_pdf) or old["source_sha256"] != sha(original_pdf)
    ):
        raise ValueError("Layer provenance does not match PDF")
    report = {
        "source_sha256": sha(original_pdf),
        "input_sha256": sha(input_pdf),
        "pages": [],
        "contract": {"zoom": ZOOM, "white_floor": WHITE_FLOOR, "min_font_points": 8},
    }
    with fitz.open(input_pdf) as doc, fitz.open(original_pdf) as source:
        if old:
            remove_owned_layer(doc, old)
        if len(doc) != len(source) or len(doc) != len(numbering):
            raise ValueError("Page count mismatch")
        for index, page in enumerate(doc):
            reference = source[index]
            if (
                page.mediabox != reference.mediabox
                or page.cropbox != reference.cropbox
                or page.rotation != reference.rotation
            ):
                raise ValueError("Page geometry changed")
            if note_signature(doc, page) != note_signature(source, reference):
                raise ValueError("Original annotations changed")
            # Erasing our previous layer must recover the original annotated page
            # exactly before another numbering state is added.
            pixels = pix_array(page)
            if not np.array_equal(pixels, pix_array(reference)):
                raise ValueError("Layer removal did not recover original annotated PDF")
            contents = page.get_contents()
            current = {"source_contents": contents, "number_streams": [], "labels": []}
            occupied = []
            previous_top = None
            width, height = numbering[index]["source_pixels"]
            sx, sy = page.mediabox.width / width, page.mediabox.height / height
            for row in numbering[index]["rows"]:
                x0, y0, x1, y1 = row["top_staff_bbox"]
                staff = fitz.Rect(
                    x0 * sx - page.cropbox.x0,
                    y0 * sy - page.cropbox.y0,
                    x1 * sx - page.cropbox.x0,
                    y1 * sy - page.cropbox.y0,
                )
                text = str(row["row_start_measure_number"])
                rect, size, baseline, padded = find_placement(
                    page, pixels, text, staff, previous_top, occupied
                )
                before = page.get_contents()
                page.insert_text(
                    (rect.x0, baseline), text, fontsize=size, fontname="hebo", color=(0, 0, 0)
                )
                added = [x for x in page.get_contents() if x not in before]
                if len(added) != 1:
                    raise ValueError("Number insertion did not create one independent stream")
                xref = added[0]
                doc.xref_set_key(xref, "PDFScoreBarNumbers", f"({MARKER})")
                current["number_streams"].append(
                    {"xref": xref, "sha256": hashlib.sha256(doc.xref_stream(xref)).hexdigest()}
                )
                current["labels"].append(
                    {
                        "row_id": row["row_id"],
                        "number": int(text),
                        "rect": list(rect),
                        "font_size": size,
                    }
                )
                occupied.append(padded)
                previous_top = staff.y0
            report["pages"].append(current)
        doc.save(output)
    with fitz.open(output) as actual, fitz.open(original_pdf) as source:
        for index, page in enumerate(actual):
            reference = source[index]
            assert note_signature(actual, page) == note_signature(source, reference)
            original_pixels, new_pixels = pix_array(reference), pix_array(page)
            dark = np.min(original_pixels, axis=2) < WHITE_FLOOR
            assert np.array_equal(original_pixels[dark], new_pixels[dark]), (
                "Original dark pixels changed"
            )
            assert page.get_text().split() == [
                str(x["number"]) for x in report["pages"][index]["labels"]
            ]
            assert page.cropbox == reference.cropbox and page.mediabox == reference.mediabox
            # The original embedded background bytes are retained, not JPEG-reencoded.
            a, b = page.get_images()[0][0], reference.get_images()[0][0]
            assert actual.extract_image(a)["image"] == source.extract_image(b)["image"]
    report["output_sha256"] = sha(output)
    report["label_count"] = sum(len(p["labels"]) for p in report["pages"])
    report["all_original_dark_pixels_and_annotations_unchanged"] = True
    report["previous_layer_removed_to_exact_original"] = bool(old)
    sidecar = output.with_suffix(".layer.json")
    sidecar.write_text(json.dumps(report, indent=2) + "\n")
    return sidecar, report
