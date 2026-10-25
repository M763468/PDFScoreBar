"""Sidecar-bound numbering layer for an already annotated review score.

Fixed acceptance: preserve CropBox/MediaBox, all original dark pixels (<250 at
144 DPI), all original annotations, and place every row label at >=8 pt. Never
erase or classify user ink. Input correspondence belongs to the resume adapter.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections import Counter
from pathlib import Path

import fitz
import numpy as np
from PIL import Image

from src.pipeline.review.final_output import (
    _first_page_payload,
    _resolve_package_path,
    _row_label_records,
)

ZOOM = 2
WHITE_FLOOR = 250
MARKER = "issue441.experimental.row_numbers.v1"
FONT_POINTS = 9.0


class NumberLayerValidationError(ValueError):
    """A saved candidate failed validation and must not be published."""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def note_signature(doc, page):
    """Private in-memory fingerprint; never publish note text or metadata."""
    result = []
    for note in page.annots() or []:
        pix = note.get_pixmap(alpha=True)
        fields = {k: doc.xref_get_key(note.xref, k) for k in sorted(doc.xref_get_keys(note.xref))}
        result.append(
            (
                fields,
                list(note.rect),
                note.vertices,
                pix.width,
                pix.height,
                hashlib.sha256(pix.samples).hexdigest(),
            )
        )
    return result


def records_from_run(handoff, run):
    data = json.loads(Path(handoff).read_text())
    result = []
    for page in data["pages"]:
        numbering = Path(run) / "outputs" / page["page_id"] / "numbering_final.json"
        payload = _first_page_payload(json.loads(numbering.read_text()), numbering)
        package_root = Path(handoff).resolve().parent
        source_image = _resolve_package_path(
            package_root, page["source_image"], description="number layer source image"
        )
        with Image.open(source_image) as image:
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


def digit_ink_bounds(text, size):
    """Glyph bounds relative to the insertion origin, in PDF page coordinates."""
    font = fitz.Font("hebo")
    cursor = 0.0
    result = None
    for char in text:
        glyph = font.glyph_bbox(ord(char))
        box = fitz.Rect(
            (cursor + glyph.x0) * size,
            -glyph.y1 * size,
            (cursor + glyph.x1) * size,
            -glyph.y0 * size,
        )
        result = box if result is None else result | box
        cursor += font.glyph_advance(ord(char))
    if result is None or result.is_empty:
        raise ValueError("Number has no visible glyph bounds")
    return result


def distance_to_staff_start(rect, staff):
    dx = max(rect.x0 - staff.x0, staff.x0 - rect.x1, 0)
    dy = max(rect.y0 - staff.y0, staff.y0 - rect.y1, 0)
    return math.hypot(dx, dy)


def find_placement(page, pixels, text, staff, previous_top, occupied, font_points=FONT_POINTS):
    unit = staff.height
    gap = max(0.75, min(1.5, unit * 0.025))
    note_boxes = [a.rect for a in page.annots() or []]
    ink = digit_ink_bounds(text, font_points)
    width, height = ink.width, ink.height
    min_y = max(gap, (previous_top + staff.y0) / 2 if previous_top is not None else gap)
    max_y = min(page.rect.height - height - gap, staff.y0 + unit * 0.25)
    min_x = gap
    max_x = min(page.rect.width - width - gap, staff.x0 + unit)
    preferred_x = max(min_x, min(max_x, staff.x0 - width - gap))
    preferred_y = staff.y0 - height - gap
    step = max(font_points / 5, unit * 0.04)
    xs = sorted(set([preferred_x, min_x] + list(np.arange(min_x, max_x + 0.001, step))))
    ys = sorted(
        set([min(max_y, max(min_y, preferred_y))] + list(np.arange(min_y, max_y + 0.001, step)))
    )
    candidates = [fitz.Rect(x, y, x + width, y + height) for y in ys for x in xs]
    candidates.sort(
        key=lambda r: (
            distance_to_staff_start(r, staff),
            abs(r.y1 - (staff.y0 - gap)),
            abs(r.x1 - (staff.x0 - gap)),
        )
    )
    for rect in candidates:
        # Keep the label above or to the left of the staff, never inside it.
        if rect.x1 > staff.x0 - gap and rect.y1 > staff.y0 - gap:
            continue
        padded = rect + (-gap, -gap, gap, gap)
        if not page.rect.contains(padded):
            continue
        if any(padded.intersects(box) for box in note_boxes + occupied):
            continue
        x0, y0 = math.floor(padded.x0 * ZOOM), math.floor(padded.y0 * ZOOM)
        x1, y1 = math.ceil(padded.x1 * ZOOM), math.ceil(padded.y1 * ZOOM)
        region = pixels[y0:y1, x0:x1]
        if region.size and np.min(region) >= WHITE_FLOOR:
            return rect, font_points, rect.y0 - ink.y0, padded, rect.x0 - ink.x0
    raise ValueError(
        f"No safe uniform {font_points:g}pt placement for {text} near staff top {staff.y0:.2f}"
    )


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


def _validate_saved_output(candidate, original_pdf, report):
    with fitz.open(candidate) as actual, fitz.open(original_pdf) as source:
        if len(actual) != len(source):
            raise NumberLayerValidationError("Saved page count changed")
        for index, page in enumerate(actual):
            reference = source[index]
            if (
                page.cropbox != reference.cropbox
                or page.mediabox != reference.mediabox
                or page.rotation != reference.rotation
            ):
                raise NumberLayerValidationError("Saved page geometry changed")
            if note_signature(actual, page) != note_signature(source, reference):
                raise NumberLayerValidationError("Saved annotations changed")
            original_pixels, new_pixels = pix_array(reference), pix_array(page)
            dark = np.min(original_pixels, axis=2) < WHITE_FLOOR
            if not np.array_equal(original_pixels[dark], new_pixels[dark]):
                raise NumberLayerValidationError("Original dark pixels changed")
            if report["pages"][index]["labels"]:
                _number_font_signature(actual, page)
            for label in report["pages"][index]["labels"]:
                rect = label["rect"]
                if not all(math.isfinite(value) for value in rect) or not page.rect.contains(
                    fitz.Rect(rect)
                ):
                    raise NumberLayerValidationError(
                        "Saved number ink bounds escape the visible CropBox"
                    )
            expected_text = Counter(reference.get_text().split())
            expected_text.update(str(x["number"]) for x in report["pages"][index]["labels"])
            if Counter(page.get_text().split()) != expected_text:
                raise NumberLayerValidationError("Saved number sequence changed")
            for stream in report["pages"][index]["number_streams"]:
                if (
                    hashlib.sha256(actual.xref_stream(stream["xref"])).hexdigest()
                    != stream["sha256"]
                ):
                    raise NumberLayerValidationError("Saved number stream changed")
            actual_images = [actual.extract_image(x[0])["image"] for x in page.get_images()]
            source_images = [source.extract_image(x[0])["image"] for x in reference.get_images()]
            if actual_images != source_images:
                raise NumberLayerValidationError("Original background bytes changed")


def _publish_validated_pair(candidate, staged_sidecar, output):
    """PDF is the commit point: its validated sidecar must already be present.

    Hard links publish without replacing another writer's result. A process kill
    between the two links can leave a sidecar alone, never an unchecked PDF.
    Such an orphan is not a successful result and a retry refuses to overwrite it.
    """
    sidecar = output.with_suffix(".layer.json")
    linked_sidecar = False
    try:
        os.link(staged_sidecar, sidecar)
        linked_sidecar = True
        os.link(candidate, output)
    except BaseException:
        if linked_sidecar:
            sidecar.unlink()
        raise


def write_number_layer(
    input_pdf, original_pdf, numbering, output, *, previous_sidecar=None, font_points=FONT_POINTS
):
    input_pdf, original_pdf, output = map(Path, (input_pdf, original_pdf, output))
    sidecar = output.with_suffix(".layer.json")
    if output.exists() or output.is_symlink() or sidecar.exists() or sidecar.is_symlink():
        raise FileExistsError(output)
    if not math.isfinite(font_points) or font_points < 8:
        raise ValueError("Document-wide font size must be finite and at least 8pt")
    old = json.loads(Path(previous_sidecar).read_text()) if previous_sidecar else None
    if old and (
        old["output_sha256"] != sha(input_pdf) or old["source_sha256"] != sha(original_pdf)
    ):
        raise ValueError("Layer provenance does not match PDF")
    report = {
        "source_sha256": sha(original_pdf),
        "input_sha256": sha(input_pdf),
        "pages": [],
        "contract": {
            "zoom": ZOOM,
            "white_floor": WHITE_FLOOR,
            "min_font_points": 8,
            "font_points": font_points,
            "bbox_kind": "digit_ink",
            "placement_ranking": "nearest_staff_start",
        },
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
            if page.rotation or page.mediabox.top_left != fitz.Point(0, 0):
                raise ValueError(
                    "Rotated or nonzero-origin pages need an explicit coordinate mapping"
                )
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
                rect, size, baseline, padded, origin_x = find_placement(
                    page, pixels, text, staff, previous_top, occupied, font_points
                )
                before = page.get_contents()
                page.insert_text(
                    (origin_x, baseline), text, fontsize=size, fontname="hebo", color=(0, 0, 0)
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
                        "staff_start": [staff.x0, staff.y0],
                        "distance_to_staff_start_points": distance_to_staff_start(rect, staff),
                    }
                )
                occupied.append(padded)
                previous_top = staff.y0
            report["pages"].append(current)
        # No final path exists until the saved candidate and its sidecar pass.
        with tempfile.TemporaryDirectory(prefix=f".{output.stem}-", dir=output.parent) as temporary:
            candidate = Path(temporary) / "candidate.pdf"
            staged_sidecar = Path(temporary) / "candidate.layer.json"
            doc.save(candidate)
            _validate_saved_output(candidate, original_pdf, report)
            report["output_sha256"] = sha(candidate)
            report["label_count"] = sum(len(p["labels"]) for p in report["pages"])
            report["all_original_dark_pixels_and_annotations_unchanged"] = True
            report["previous_layer_removed_to_exact_original"] = bool(old)
            report["publication"] = "validated_sidecar_first_pdf_last_commit"
            staged_sidecar.write_text(json.dumps(report, indent=2) + "\n")
            saved = json.loads(staged_sidecar.read_text())
            if saved != report or saved["output_sha256"] != sha(candidate):
                raise NumberLayerValidationError("Staged PDF and sidecar do not match")
            _publish_validated_pair(candidate, staged_sidecar, output)
    return sidecar, report


def _full_pixels(page, *, annotations):
    crop = page.cropbox
    try:
        page.set_cropbox(page.mediabox)
        pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), alpha=False, annots=annotations)
        return pix.width, pix.height, pix.samples
    finally:
        page.set_cropbox(crop)


def _number_font_signature(doc, page):
    fonts = [font for font in page.get_fonts() if font[4] == "hebo"]
    if len(fonts) != 1:
        raise NumberLayerValidationError("Numbering font resource is ambiguous")
    xref = fonts[0][0]
    keys = set(doc.xref_get_keys(xref))
    if keys != {"Type", "Subtype", "BaseFont", "Encoding"}:
        raise NumberLayerValidationError("Unsupported numbering font dictionary")
    signature = {key: doc.xref_get_key(xref, key) for key in sorted(keys)}
    expected = {
        "Type": ("name", "/Font"),
        "Subtype": ("name", "/Type1"),
        "BaseFont": ("name", "/Helvetica-Bold"),
        "Encoding": ("name", "/WinAnsiEncoding"),
    }
    if signature != expected:
        raise NumberLayerValidationError("Numbering font does not match the measured digit metrics")
    return signature


def strip_returned_layer(input_pdf, trusted_pdf, trusted_sidecar, original_pdf, output):
    """Remove only streams proven against an attested pre-export result.

    Whole-file identity and xrefs may change during an annotation-only export.
    The complete ordered content, owned stream digests/markers, image bytes and
    full-page non-annotation pixels must still match the retained result.
    New annotations are never compared to the old annotations or removed.
    """
    input_pdf, trusted_pdf, trusted_sidecar, original_pdf, output = map(
        Path, (input_pdf, trusted_pdf, trusted_sidecar, original_pdf, output)
    )
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    layer = json.loads(trusted_sidecar.read_text())
    if layer["output_sha256"] != sha(trusted_pdf):
        raise NumberLayerValidationError("Trusted PDF and numbering sidecar disagree")
    removed = 0
    with (
        fitz.open(input_pdf) as incoming,
        fitz.open(trusted_pdf) as trusted,
        fitz.open(original_pdf) as original,
    ):
        if not (len(incoming) == len(trusted) == len(original) == len(layer["pages"])):
            raise NumberLayerValidationError("Returned PDF page count changed")
        for index, page in enumerate(incoming):
            reference = trusted[index]
            saved = layer["pages"][index]
            baseline_refs = saved["source_contents"]
            owned = saved["number_streams"]
            expected = baseline_refs + [item["xref"] for item in owned]
            refs = page.get_contents()
            if (
                reference.get_contents() != expected
                or len(refs) != len(expected)
                or len(set(expected)) != len(expected)
                or page.mediabox != reference.mediabox
                or page.rotation != reference.rotation
                or page.rotation
            ):
                raise NumberLayerValidationError("Returned content layout or geometry changed")
            if [incoming.xref_stream(x) for x in refs] != [
                trusted.xref_stream(x) for x in expected
            ]:
                raise NumberLayerValidationError("Returned page content changed")
            for xref, item in zip(refs[len(baseline_refs) :], owned):
                if (
                    hashlib.sha256(incoming.xref_stream(xref)).hexdigest() != item["sha256"]
                    or incoming.xref_get_key(xref, "PDFScoreBarNumbers")[1] != MARKER
                    or trusted.xref_get_key(item["xref"], "PDFScoreBarNumbers")[1] != MARKER
                ):
                    raise NumberLayerValidationError(
                        "Returned number ownership could not be verified"
                    )
            if _number_font_signature(incoming, page) != _number_font_signature(trusted, reference):
                raise NumberLayerValidationError("Returned numbering font changed")
            images = [incoming.extract_image(x[0])["image"] for x in page.get_images()]
            old_images = [trusted.extract_image(x[0])["image"] for x in reference.get_images()]
            if images != old_images or _full_pixels(page, annotations=False) != _full_pixels(
                reference, annotations=False
            ):
                raise NumberLayerValidationError("Returned background or resources changed")
            keep = " ".join(f"{xref} 0 R" for xref in refs[: len(baseline_refs)])
            incoming.xref_set_key(page.xref, "Contents", f"[{keep}]")
            page = incoming.reload_page(page)
            if page.mediabox != original[index].mediabox or _full_pixels(
                page, annotations=False
            ) != _full_pixels(original[index], annotations=False):
                raise NumberLayerValidationError(
                    "Removing owned numbers did not recover source background"
                )
            removed += len(owned)
        if not removed:
            raise NumberLayerValidationError("No attested numbering layer to remove")
        with tempfile.TemporaryDirectory(prefix=".returned-layer-", dir=output.parent) as temporary:
            candidate = Path(temporary) / "clean.pdf"
            incoming.save(candidate)
            with fitz.open(candidate) as saved:
                for index, page in enumerate(saved):
                    reference = incoming[index]
                    if (
                        page.cropbox != reference.cropbox
                        or page.mediabox != reference.mediabox
                        or page.rotation != reference.rotation
                        or note_signature(saved, page) != note_signature(incoming, reference)
                        or _full_pixels(page, annotations=True)
                        != _full_pixels(reference, annotations=True)
                    ):
                        raise NumberLayerValidationError(
                            "Returned annotations or drawing changed during normalization"
                        )
            os.link(candidate, output)
    return {
        "input_sha256": sha(input_pdf),
        "trusted_pdf_sha256": sha(trusted_pdf),
        "trusted_sidecar_sha256": sha(trusted_sidecar),
        "cleaned_sha256": sha(output),
        "removed_number_count": removed,
        "annotations_preserved": True,
        "method": "attested_ordered_streams_and_full_page_render_v1",
    }
