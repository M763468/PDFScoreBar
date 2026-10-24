"""Focused synthetic method comparison for #441, not a PDF import API.

No MobileSheets export is synthesized or claimed here. App/device acceptance is
separate. Use a fresh output directory under logs/issue441/.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import fitz
from PIL import Image, ImageChops, ImageDraw

from tools.issue441.phase0_probe import (
    annotation_signature,
    make_raster_pdf,
    replace_backgrounds,
    sha,
)


def png(image):
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue()


def raster_pdf(path, image, size=(300, 400)):
    with fitz.open() as doc:
        page = doc.new_page(width=size[0], height=size[1])
        page.insert_image(page.rect, stream=png(image))
        doc.save(path)


def notes(page, scale=1):
    points = [(30, 65), (42, 76), (34, 70), (50, 65)]
    ink = page.add_ink_annot([[(x * scale, y * scale) for x, y in points]])
    ink.set_colors(stroke=(1, 0, 0))
    ink.set_info(content="handwritten practice phrase")
    ink.update()
    highlight = page.add_highlight_annot(fitz.Rect(30, 60, 60, 83) * scale)
    highlight.set_opacity(0.35)
    highlight.update()
    text = page.add_freetext_annot(
        fitz.Rect(160, 260, 270, 290) * scale, "practice softly", fontsize=10 * scale
    )
    text.update()


def render(doc, annots=True, matrix=None):
    return doc[0].get_pixmap(annots=annots, matrix=matrix or fitz.Matrix(1, 1)).samples


def expect_rejection(call):
    try:
        call()
    except ValueError as exc:
        return str(exc)
    raise AssertionError("unsafe case accepted")


def annotation_method(root):
    old, new, annotated = [root / f"a_{n}.pdf" for n in ("old", "new", "annotated")]
    make_raster_pdf(old, 12)
    make_raster_pdf(new, 42)
    with fitz.open(old) as doc:
        notes(doc[0])
        doc.save(annotated)
    before = {str(p): sha(p) for p in (old, new, annotated)}
    output = root / "a_replaced.pdf"
    replace_backgrounds(old, annotated, new, output)
    with fitz.open(annotated) as original, fitz.open(output) as result, fitz.open(new) as target:
        assert annotation_signature(original[0]) == annotation_signature(result[0])
        assert render(result, False) == render(target, False)
        result[0].get_pixmap(matrix=fitz.Matrix(2, 2)).save(root / "a_replaced.png")
    with fitz.open(annotated) as doc:
        doc[0].set_mediabox(fitz.Rect(0, 0, 301, 400))
        doc.save(root / "a_wrong_size.pdf")
    error = expect_rejection(
        lambda: replace_backgrounds(old, root / "a_wrong_size.pdf", new, root / "a_rejected.pdf")
    )
    assert not (root / "a_rejected.pdf").exists()
    assert before == {str(p): sha(p) for p in (old, new, annotated)}
    return {
        "synthetic": "passed",
        "notes": ["Ink", "Highlight", "FreeText"],
        "size_rejected": error,
    }


MARKER = "PDFScoreBar.fixture.label.1"


def vector_pdf(path, number, kind):
    image = Image.new("RGB", (600, 800), "white")
    ImageDraw.Draw(image).line((120, 180, 550, 180), fill="black", width=2)
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=400)
        page.insert_image(page.rect, stream=png(image))
        if kind == "annotation":
            label = page.add_freetext_annot(fitz.Rect(30, 60, 62, 83), str(number), fontsize=15)
            label.set_info(title=MARKER)
            label.set_flags(fitz.PDF_ANNOT_IS_PRINT)
            label.update()
        else:
            layer = doc.add_ocg(MARKER) if kind == "ocg" else 0
            page.insert_text((32, 80), str(number), fontsize=15, oc=layer)
            xref = page.get_contents()[-1]
            doc.xref_set_key(xref, "PDFScoreBarLabel", f"({MARKER})")
        doc.set_metadata({"keywords": MARKER})
        notes(page)
        doc.save(path)


def label_stream(doc):
    candidates = [
        x for x in doc[0].get_contents() if doc.xref_get_key(x, "PDFScoreBarLabel")[1] == MARKER
    ]
    if len(candidates) != 1:
        raise ValueError("label stream identity missing after rewrite/flatten")
    return candidates[0]


def user_notes(page):
    return [s for s in annotation_signature(page) if s["info"].get("title") != MARKER]


def independent_numbers(root):
    result = {}
    for kind in ("stream", "ocg", "annotation"):
        old, expected, output = [root / f"c_{kind}_{n}.pdf" for n in ("old", "expected", "new")]
        vector_pdf(old, 12, kind)
        vector_pdf(expected, 42, kind)
        before = sha(old)
        with fitz.open(old) as doc, fitz.open(expected) as target:
            page = doc[0]
            if kind == "annotation":
                labels = [a for a in page.annots() if a.info.get("title") == MARKER]
                assert len(labels) == 1 and labels[0].flags & fitz.PDF_ANNOT_IS_PRINT
                page.delete_annot(labels[0])
                annot = page.add_freetext_annot(fitz.Rect(30, 60, 62, 83), "42", fontsize=15)
                annot.set_info(title=MARKER)
                annot.set_flags(fitz.PDF_ANNOT_IS_PRINT)
                annot.update()
            else:
                xref = label_stream(doc)
                original_stream = doc.xref_stream(xref)
                assert original_stream != target.xref_stream(label_stream(target))
                doc.update_stream(xref, target.xref_stream(label_stream(target)))
            doc.save(output)
        with fitz.open(old) as original, fitz.open(output) as actual, fitz.open(expected) as target:
            assert user_notes(original[0]) == user_notes(actual[0])
            appearance_matches = render(actual) == render(target)
            if kind != "annotation":
                assert appearance_matches
            if kind != "annotation":
                words = actual[0].get_text().split()
                assert "42" in words and "12" not in words
            else:
                assert [
                    a.info["content"] for a in actual[0].annots() if a.info.get("title") == MARKER
                ] == ["42"]
            # Flattening preserves appearance but removes independent identity.
            pix = actual[0].get_pixmap(matrix=fitz.Matrix(2, 2))
            flat_image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            raster_pdf(root / f"c_{kind}_flattened.pdf", flat_image)
        with fitz.open(root / f"c_{kind}_flattened.pdf") as flat:
            if kind == "annotation":
                assert list(flat[0].annots() or []) == []
            else:
                expect_rejection(lambda: label_stream(flat))
        rewrite_result = "not_applicable"
        if kind != "annotation":
            with fitz.open(old) as doc:
                before_rewrite = render(doc)
                doc.save(root / f"c_{kind}_cleaned.pdf", clean=True)
            with fitz.open(root / f"c_{kind}_cleaned.pdf") as cleaned:
                assert render(cleaned) == before_rewrite
                rewrite_result = expect_rejection(lambda: label_stream(cleaned))
        assert sha(old) == before
        result[kind] = {
            "replace_only_label": "passed" if appearance_matches else "failed",
            "appearance_matches_target": appearance_matches,
            "note": "annotation delete/readd changes stacking under highlight"
            if not appearance_matches
            else "",
            "flattened_identity": "lost",
            "clean_rewrite_identity": rewrite_result,
            "mobilesheets_and_print": "not_run",
        }

    with fitz.open(root / "c_stream_old.pdf") as doc:
        expected_pixels = render(doc)
        doc.set_metadata({})
        doc.save(root / "c_metadata_stripped.pdf")
    with fitz.open(root / "c_metadata_stripped.pdf") as stripped:
        assert not stripped.metadata.get("keywords")
        assert render(stripped) == expected_pixels
        label_stream(stripped)  # Separate stream marker survives this specific save.
    return {
        "variants": result,
        "metadata_stripping_without_visual_change": "passed",
        "metadata_is_auxiliary": True,
    }


def local_patch(baseline, annotated, replacement, region, *, disjoint_proven=False):
    if annotated.size != baseline.size or annotated.size != replacement.size:
        raise ValueError("raster geometry mismatch")
    if ImageChops.difference(baseline.crop(region), annotated.crop(region)).getbbox():
        raise ValueError("writing or recompression in label update region")
    # Exact equality cannot detect a black mark hidden on a black old number.
    # Only fixture ground truth supplies this proof, never pixel equality alone.
    if not disjoint_proven:
        raise ValueError("non-overlap cannot be established from raster alone")
    output = annotated.copy()
    output.paste(replacement.crop(region), region)
    return output


def local_method(root):
    with fitz.open(root / "a_old.pdf") as old, fitz.open(root / "a_new.pdf") as new:
        baseline = Image.open(
            io.BytesIO(old.extract_image(old[0].get_images()[0][0])["image"])
        ).convert("RGB")
        replacement = Image.open(
            io.BytesIO(new.extract_image(new[0].get_images()[0][0])["image"])
        ).convert("RGB")
    # Includes old/new label paint and halo in this controlled fixture.
    region = (50, 110, 140, 190)
    outside = baseline.copy()
    ImageDraw.Draw(outside).line((400, 600, 500, 620), fill="red", width=5)
    fixed = local_patch(baseline, outside, replacement, region, disjoint_proven=True)
    expected = replacement.copy()
    ImageDraw.Draw(expected).line((400, 600, 500, 620), fill="red", width=5)
    assert fixed.tobytes() == expected.tobytes()
    fixed.save(root / "d_local_patch.png")
    unproven = expect_rejection(lambda: local_patch(baseline, outside, replacement, region))
    overlap = outside.copy()
    ImageDraw.Draw(overlap).line((60, 140, 110, 150), fill="red", width=3)
    visible_error = expect_rejection(
        lambda: local_patch(baseline, overlap, replacement, region, disjoint_proven=True)
    )
    encoded = io.BytesIO()
    outside.save(encoded, "JPEG", quality=90)
    recompressed = Image.open(io.BytesIO(encoded.getvalue())).convert("RGB")
    jpeg_error = expect_rejection(
        lambda: local_patch(baseline, recompressed, replacement, region, disjoint_proven=True)
    )
    return {
        "oracle_disjoint_lossless_patch": "passed",
        "unproven": unproven,
        "visible_overlap": visible_error,
        "jpeg_recompression": jpeg_error,
        "production_safe_nonoverlap_detection": "not_established",
    }


def scale_gate(page, target_size):
    if page.rotation or page.cropbox != page.mediabox or page.mediabox.top_left != fitz.Point(0, 0):
        raise ValueError("crop/rotation/nonzero origin needs explicit coordinate mapping")
    sx, sy = target_size[0] / page.rect.width, target_size[1] / page.rect.height
    if abs(sx - sy) > 1e-9:
        raise ValueError("nonuniform mapping not covered")
    if any(a.type[1] != "Ink" for a in page.annots() or []):
        raise ValueError("only Ink reconstruction covered in scale fixture")
    return sx


def legacy_geometry(root):
    image = Image.new("RGB", (600, 780), "white")
    ImageDraw.Draw(image).line((100, 200, 500, 200), fill="black", width=2)
    legacy = root / "legacy_3000x3900.pdf"
    raster_pdf(legacy, image, (3000, 3900))
    with fitz.open(legacy) as doc:
        annot = doc[0].add_ink_annot([[(600, 1000), (1000, 1100)]])
        annot.set_colors(stroke=(1, 0, 0))
        annot.set_border(width=8)
        annot.set_info(content="legacy note")
        annot.update()
        doc.save(root / "legacy_ink.pdf")
    with fitz.open(root / "legacy_ink.pdf") as source, fitz.open() as target:
        source_page = source[0]
        scale = scale_gate(source_page, (720, 936))
        page = target.new_page(width=720, height=936)
        page.show_pdf_page(page.rect, source, 0)
        # show_pdf_page does not transfer annotations. Rebuild only known Ink.
        old = next(source_page.annots())
        vertices = [[(x * scale, y * scale) for x, y in line] for line in old.vertices]
        note = page.add_ink_annot(vertices)
        note.set_colors(stroke=old.colors["stroke"])
        note.set_border(width=old.border["width"] * scale)
        note.set_info(content=old.info["content"])
        note.update()
        target.save(root / "legacy_explicit_scaled.pdf")
        expected_vertices = vertices
    with (
        fitz.open(root / "legacy_ink.pdf") as original,
        fitz.open(root / "legacy_explicit_scaled.pdf") as scaled,
    ):
        scaled_page = scaled[0]
        assert scaled_page.rect == fitz.Rect(0, 0, 720, 936)
        actual = next(scaled_page.annots())
        for line, expected_line in zip(actual.vertices, expected_vertices, strict=True):
            for actual_point, expected_point in zip(line, expected_line, strict=True):
                assert (
                    max(abs(a - b) for a, b in zip(actual_point, expected_point, strict=True))
                    < 0.001
                )
        # Compare equivalent physical resolution, including the transformed Ink.
        assert render(original, matrix=fitz.Matrix(scale, scale)) == render(scaled)
    refused = {}
    for name in ("rotation", "crop", "aspect", "unknown_note"):
        with fitz.open(root / "legacy_ink.pdf") as doc:
            page = doc[0]
            if name == "rotation":
                page.set_rotation(90)
            elif name == "crop":
                page.set_cropbox(fitz.Rect(20, 20, 2900, 3800))
            elif name == "unknown_note":
                page.add_highlight_annot(fitz.Rect(100, 100, 200, 200))
            refused[name] = expect_rejection(
                lambda: scale_gate(page, (720, 900) if name == "aspect" else (720, 936))
            )
    return {
        "legacy_preserve_dimensions": "covered_by_A",
        "explicit_scale": scale,
        "ink_render_and_coordinates": "passed",
        "refused": refused,
        "actual_legacy_import_and_device": "not_run",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    result = {
        "runtime": fitz.VersionBind,
        "A": annotation_method(args.output),
        "B_device_swap_file": "not_run",
        "C": independent_numbers(args.output),
        "D": local_method(args.output),
        "legacy": legacy_geometry(args.output),
        "mobilesheets": {
            "os": "unknown",
            "version": "unknown",
            "settings": "unknown",
            "export_pdf": "not_available",
            "device": "not_run",
        },
    }
    result["probe_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (args.output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
