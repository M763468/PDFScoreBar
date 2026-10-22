"""Disposable #441 feasibility probes; this is not a production resume/import API.

Run with the maintained pipeline interpreter and PYTHONPATH at the checkout root.
Outputs must use a fresh directory under logs/issue441/. Original PDFs are read only.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import fitz
from PIL import Image, ImageDraw


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def annotation_signature(page):
    """Capture visible appearance, geometry, metadata, and ink vertices."""
    result = []
    for annot in page.annots() or []:
        appearance = annot.get_pixmap(alpha=True)
        result.append(
            {
                "type": annot.type,
                "rect": list(annot.rect),
                "info": annot.info,
                "vertices": annot.vertices,
                "colors": annot.colors,
                "opacity": annot.opacity,
                "appearance": hashlib.sha256(appearance.samples).hexdigest(),
            }
        )
    return result


def page_signature(document, page):
    """Deliberately strict annotation-only edit gate for these generated fixtures.

    Content stream equality may reject a harmless rewritten PDF. That is acceptable
    for this PoC: it must never infer that arbitrary raster edits are annotations.
    This is not a complete security validator for untrusted PDF documents.
    """
    return {
        "media": list(page.mediabox),
        "crop": list(page.cropbox),
        "rect": list(page.rect),
        "rotation": page.rotation,
        "contents": page.read_contents(),
        "images": [
            (tuple(image[1:]), document.xref_stream(image[0]))
            for image in page.get_images(full=True)
        ],
    }


def replace_backgrounds(baseline, annotated, replacement, output):
    """Replace whole raster objects, retaining independent annotation objects."""
    with fitz.open(baseline) as base, fitz.open(annotated) as edited, fitz.open(replacement) as new:
        if len(base) != len(edited) or len(base) != len(new):
            raise ValueError("page count mismatch")
        xrefs = []
        for index in range(len(base)):
            if page_signature(base, base[index]) != page_signature(edited, edited[index]):
                raise ValueError(f"page {index + 1}: background or geometry changed")
            for doc in (base, edited, new):
                if len(doc[index].get_images()) != 1:
                    raise ValueError("expected one raster per page")
            if list(new[index].rect) != list(base[index].rect):
                raise ValueError("replacement geometry mismatch")
            xrefs.append(edited[index].get_images()[0][0])
        # replace_image is global; shared image references need a separate design.
        if len(set(xrefs)) != len(xrefs):
            raise ValueError("shared page image")
        for index, xref in enumerate(xrefs):
            stream = new.extract_image(new[index].get_images()[0][0])["image"]
            edited[index].replace_image(xref, stream=stream)
        edited.save(output)


def make_raster_pdf(path, number):
    image = Image.new("RGB", (600, 800), "white")
    draw = ImageDraw.Draw(image)
    for y in range(180, 221, 10):
        draw.line((120, y, 550, y), fill="black", width=2)
    draw.text((65, 130), str(number), fill="black", font_size=30)
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=400)
        page.insert_image(page.rect, stream=encoded.getvalue())
        doc.save(path)


def add_notes(baseline, output):
    with fitz.open(baseline) as doc:
        page = doc[0]
        for points in ([(30, 65), (50, 70), (30, 80)], [(210, 300), (260, 310)]):
            annot = page.add_ink_annot([points])
            annot.set_colors(stroke=(1, 0, 0))
            annot.set_info(content="practice note")
            annot.update()
        doc.save(output)


def verify_replacement(annotated, replacement, output):
    with fitz.open(annotated) as old, fitz.open(replacement) as new, fitz.open(output) as out:
        for index in range(len(out)):
            assert annotation_signature(old[index]) == annotation_signature(out[index])
            assert list(out[index].rect) == list(old[index].rect)
            # Full background render equality establishes removal of old labels,
            # rather than just detecting the presence of a new number.
            assert (
                out[index].get_pixmap(annots=False).samples
                == new[index].get_pixmap(annots=False).samples
            )
        assert len(annotation_signature(out[0])) == 2


def synthetic_probe(root):
    old, new = root / "old.pdf", root / "new.pdf"
    make_raster_pdf(old, 12)
    make_raster_pdf(new, 42)
    annotated, output = root / "annotated.pdf", root / "resumed.pdf"
    add_notes(old, annotated)
    originals = {str(p): sha(p) for p in (old, new, annotated)}
    replace_backgrounds(old, annotated, new, output)
    verify_replacement(annotated, new, output)
    with fitz.open(output) as doc:
        doc[0].get_pixmap(matrix=fitz.Matrix(2, 2)).save(root / "resumed.png")

    cases = {}
    # Burn the annotations into the background, including the note across 12.
    with fitz.open(annotated) as doc:
        image = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
        with fitz.open() as flat:
            page = flat.new_page(width=300, height=400)
            page.insert_image(page.rect, stream=image.tobytes("png"))
            flat.save(root / "flattened.pdf")
    cases["flattened_overlap"] = root / "flattened.pdf"
    for name in ("rotation", "crop", "size", "page_count", "different_score", "native_content"):
        path = root / f"{name}.pdf"
        with fitz.open(old) as doc:
            page = doc[0]
            if name == "rotation":
                page.set_rotation(90)
            elif name == "crop":
                page.set_cropbox(fitz.Rect(10, 10, 290, 390))
            elif name == "size":
                page.set_mediabox(fitz.Rect(0, 0, 310, 400))
            elif name == "page_count":
                doc.new_page()
            elif name == "different_score":
                with fitz.open(new) as other:
                    stream = other.extract_image(other[0].get_images()[0][0])["image"]
                page.replace_image(page.get_images()[0][0], stream=stream)
            else:
                page.insert_text((20, 300), "flattened native writing")
            doc.save(path)
        cases[name] = path
    # A flattened note away from the label also requires a different algorithm.
    with fitz.open(old) as doc:
        image = Image.open(io.BytesIO(doc.extract_image(doc[0].get_images()[0][0])["image"]))
        ImageDraw.Draw(image).line((400, 600, 500, 620), fill="red", width=5)
        encoded = io.BytesIO()
        image.save(encoded, "PNG")
        doc[0].replace_image(doc[0].get_images()[0][0], stream=encoded.getvalue())
        doc.save(root / "flattened_disjoint.pdf")
    cases["flattened_disjoint"] = root / "flattened_disjoint.pdf"
    rejected = {}
    for name, path in cases.items():
        target = root / f"rejected_{name}.pdf"
        before = sha(path)
        try:
            replace_backgrounds(old, path, new, target)
        except ValueError as exc:
            rejected[name] = str(exc)
        else:
            raise AssertionError(f"unsafe input accepted: {name}")
        assert not target.exists() and sha(path) == before
    assert originals == {str(p): sha(p) for p in (old, new, annotated)}

    # A black practice mark on an already black old-number pixel is invisible
    # after flattening. Its presence cannot be recovered from PDF differences.
    with fitz.open(old) as doc:
        image = Image.open(io.BytesIO(doc.extract_image(doc[0].get_images()[0][0])["image"]))
        black = next(
            (x, y)
            for y in range(130, 175)
            for x in range(65, 110)
            if image.getpixel((x, y))[:3] == (0, 0, 0)
        )
        marked = image.copy()
        marked.putpixel(black, (0, 0, 0))
        assert image.tobytes() == marked.tobytes()
    return {
        "annotation_overlap_and_disjoint": "passed",
        "flattened_overlap_information_loss": {
            "indistinguishable_black_mark_pixel": list(black),
            "same_flattened_pixels_with_or_without_mark": True,
        },
        "rejected": rejected,
        "originals": originals,
    }


def real_probe(source, root):
    first = source / "review/application_runs/attempt_0001/corrected/final"
    last = source / "review/application_runs/attempt_0012/corrected/final"
    baseline, replacement = next(first.glob("*.pdf")), next(last.glob("*.pdf"))
    hashes = {str(p): sha(p) for p in (baseline, replacement)}
    annotated, output = root / "real_annotated.pdf", root / "real_resumed.pdf"
    add_notes(baseline, annotated)
    replace_backgrounds(baseline, annotated, replacement, output)
    verify_replacement(annotated, replacement, output)
    with fitz.open(baseline) as old, fitz.open(replacement) as new:
        changed = [
            i + 1
            for i in range(len(old))
            if old[i].get_pixmap(annots=False).samples != new[i].get_pixmap(annots=False).samples
        ]
        sizes = [list(page.rect) for page in old]
    assert changed, "real fixture must actually change numbers/background"
    assert hashes == {str(p): sha(p) for p in (baseline, replacement)}
    return {
        "pages": len(sizes),
        "changed_pages": changed,
        "geometry": sizes[0],
        "backgrounds_and_annotation_appearance": "passed",
        "originals": hashes,
    }


def audit(source):
    from tools.review_correction.server import ReviewPackage

    state = json.loads((source / "review/corrections/.correction_state.json").read_text())
    last_success = state.get("last_successful_result") or {}
    attempts = []
    for path in sorted((source / "review/application_runs").glob("attempt_*")):
        consumed = path / "consumed_inputs.json"
        snapshot = path / "input_review/manual_correction_input.json"
        pdfs = list((path / "corrected/final").glob("*.pdf"))
        corrections = {}
        for correction in (path / "input_review/corrections").glob("*.json"):
            value = json.loads(correction.read_text())
            if value.get("correction_type"):
                corrections[correction.name] = {
                    "sha256": sha(correction),
                    "items": len(value.get("items", [])),
                }
        provenance = json.loads(consumed.read_text()) if consumed.exists() else None
        record = {
            "attempt": path.name,
            "consumed": provenance,
            "snapshot_sha256": sha(snapshot) if snapshot.exists() else None,
            "corrections": corrections,
            "pdfs": [
                {
                    "name": p.name,
                    "sha256": sha(p),
                    "attested_by_last_success": sha(p) == last_success.get("final_pdf_sha256"),
                }
                for p in pdfs
            ],
        }
        if snapshot.exists() and provenance:
            actual = ReviewPackage(snapshot).state.capture_identity()
            record["corrections_identity_matches"] = (
                actual["corrections_identity"] == provenance["corrections_identity"]
            )
            record["relocated_source_identity_matches"] = (
                actual["source_identity"] == provenance["source_identity"]
            )
        attempts.append(record)
    original = source / ".engine-retained/input/source.pdf"
    with fitz.open(original) as doc:
        geometry = [list(p.rect) for p in doc]
    return {
        "source": str(source),
        "attempts": attempts,
        "original_geometry": geometry,
        "original_pdf_sha256": sha(original),
        "state": state,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    if args.audit_only:
        if args.source is None:
            parser.error("--audit-only requires --source")
        result = audit(args.source)
    else:
        if args.output is None:
            parser.error("--output is required")
        args.output.mkdir(parents=True, exist_ok=False)
        result = {"runtime": fitz.VersionBind, "synthetic": synthetic_probe(args.output)}
        if args.source:
            result["real"] = real_probe(args.source, args.output)
        (args.output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
