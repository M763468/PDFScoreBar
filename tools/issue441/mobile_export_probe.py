"""Read-only correspondence checks and private candidate PDFs for #441.

This probe accepts a known retained source and explicit retained result PDFs.
It is not a generic MobileSheets importer, MSF parser, or checkpoint apply API.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import fitz

from tools.issue441.phase0_probe import annotation_signature, sha


def inventory(path):
    pages = []
    totals = Counter()
    with fitz.open(path) as doc:
        for page in doc:
            counts = Counter(a.type[1] for a in page.annots() or [])
            totals.update(counts)
            image = page.get_images()[0]
            pages.append(
                {
                    "page": page.number + 1,
                    "media": list(page.mediabox),
                    "crop": list(page.cropbox),
                    "rotation": page.rotation,
                    "image_pixels": list(image[2:4]),
                    "image_count": len(page.get_images()),
                    "annotations": dict(counts),
                }
            )
    return {
        "sha256": sha(path),
        "page_count": len(pages),
        "annotations": dict(totals),
        "pages": pages,
    }


def note_signature(doc, page):
    # Preserve dictionary values and all rendered appearances, including Stamp
    # images. PDF dictionary key order can change on save without meaning change.
    # Avoid writing personal note text to the public report.
    dictionaries = [
        hashlib.sha256(
            json.dumps(
                {k: doc.xref_get_key(a.xref, k) for k in sorted(doc.xref_get_keys(a.xref))},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        for a in page.annots() or []
    ]
    return dictionaries, annotation_signature(page)


def match_source(export, source):
    with fitz.open(export) as sample, fitz.open(source) as original:
        if len(sample) != len(original):
            raise ValueError("source page count mismatch")
        xrefs = []
        for a, b in zip(sample, original, strict=True):
            if a.mediabox != b.mediabox or a.rotation != b.rotation or a.rotation != 0:
                raise ValueError("source MediaBox/rotation mismatch")
            if not a.mediabox.contains(a.cropbox):
                raise ValueError("export CropBox outside source MediaBox")
            if len(a.get_images()) != 1 or len(b.get_images()) != 1:
                raise ValueError("expected single background image")
            xref, ref = a.get_images()[0][0], b.get_images()[0][0]
            if sample.extract_image(xref)["image"] != original.extract_image(ref)["image"]:
                raise ValueError("source background mismatch")
            if a.read_contents() != b.read_contents():
                raise ValueError("source page content changed")
            # get_image_rects is in crop-relative coordinates. Compare in the
            # MediaBox frame explicitly; do not ignore differing CropBoxes.
            rects = a.get_image_rects(xref)
            if len(rects) != 1:
                raise ValueError("background placement count mismatch")
            rect = rects[0] + (a.cropbox.x0, a.cropbox.y0, a.cropbox.x0, a.cropbox.y0)
            if rect != b.rect or b.cropbox != b.mediabox:
                raise ValueError("source background placement mismatch")
            xrefs.append(xref)
        if len(set(xrefs)) != len(xrefs):
            raise ValueError("shared background image")
    return {
        "pages_matched": len(xrefs),
        "image_bytes_and_content": "exact",
        "crop_mapping": "explicit_crop_offset_to_unchanged_media",
    }


def replace_private_candidate(template, numbered, output, *, full_media=False):
    with fitz.open(template) as doc, fitz.open(numbered) as target:
        if len(doc) != len(target):
            raise ValueError("replacement page count mismatch")
        xrefs = [p.get_images()[0][0] for p in doc]
        if len(set(xrefs)) != len(xrefs):
            raise ValueError("shared background image")
        for index, page in enumerate(doc):
            if len(page.get_images()) != 1 or len(target[index].get_images()) != 1:
                raise ValueError("single image required")
            record = target[index].get_images()[0]
            if abs(record[2] / record[3] - page.mediabox.width / page.mediabox.height) > 1e-9:
                raise ValueError("replacement raster aspect mismatch")
            stream = target.extract_image(record[0])["image"]
            page.replace_image(xrefs[index], stream=stream)
            if full_media:
                page.set_cropbox(page.mediabox)
        doc.save(output)


def verify_candidate(original, numbered, output, *, full_media=False):
    annotation_count = 0
    with fitz.open(original) as source, fitz.open(numbered) as target, fitz.open(output) as actual:
        for index, result_page in enumerate(actual):
            original_page = source[index]
            expected_crop = original_page.mediabox if full_media else original_page.cropbox
            assert result_page.mediabox == original_page.mediabox
            assert (
                result_page.cropbox == expected_crop
                and result_page.rotation == original_page.rotation
            )
            if full_media:
                # Annotation API coordinates are crop-relative. Expose the same
                # full page on the reference copy before comparing coordinates.
                original_page.set_cropbox(original_page.mediabox)
            assert note_signature(source, original_page) == note_signature(actual, result_page)
            annotation_count += sum(1 for _ in result_page.annots() or [])
            with fitz.open() as expected:
                page = expected.new_page(
                    width=result_page.mediabox.width, height=result_page.mediabox.height
                )
                page.show_pdf_page(page.rect, target, index)
                page.set_cropbox(expected_crop)
                assert page.get_pixmap().samples == result_page.get_pixmap(annots=False).samples
    return {
        "pages": index + 1,
        "annotation_objects_and_appearances_preserved": annotation_count,
        "numbered_background_render": "exact",
        "media_and_crop": "full_media_explicit_preview" if full_media else "unchanged",
    }


def normalize_owned_candidate(source, output):
    """Separate experiment on our generated copy, never on an imported source."""
    with fitz.open(source) as doc:
        for page in doc:
            page.clean_contents(sanitize=True)
        doc.save(output)


def label_visibility(sample, numbered, summary):
    result = []
    with fitz.open(sample) as doc, fitz.open(numbered) as target:
        data = json.loads(summary.read_text())
        for index, page in enumerate(doc):
            image = target[index].get_images()[0]
            sx, sy = page.mediabox.width / image[2], page.mediabox.height / image[3]
            records = data["pages"][index]["row_labels"]
            inside = 0
            for record in records:
                x0, y0, x1, y1 = record["label_bbox"]
                rect = fitz.Rect(x0 * sx, y0 * sy, x1 * sx, y1 * sy)
                inside += int(page.cropbox.contains(rect))
            result.append(
                {
                    "page": index + 1,
                    "labels": len(records),
                    "bbox_inside_crop": inside,
                    "bbox_crossing_or_outside_crop": len(records) - inside,
                }
            )
    # Metadata bbox is a conservative visibility diagnostic, not an exact ink
    # mask. Any outside/crossing bbox prevents claiming complete label visibility.
    return {
        "kind": "retained_label_bbox_diagnostic",
        "pages": result,
        "total": sum(p["labels"] for p in result),
        "crossing_or_outside": sum(p["bbox_crossing_or_outside_crop"] for p in result),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exports", type=Path, required=True)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pdfs, msfs = list(args.exports.glob("*.pdf")), list(args.exports.glob("*.msf"))
    if len(pdfs) != 1 or len(msfs) != 1:
        parser.error("expected exactly one PDF and one MSF")
    sample, msf = pdfs[0], msfs[0]
    source = args.job / ".engine-retained/input/source.pdf"
    runs = args.job / "review/application_runs"
    first = next((runs / "attempt_0001/corrected/final").glob("*.pdf"))
    last = next((runs / "attempt_0012/corrected/final").glob("*.pdf"))
    summary = runs / "attempt_0012/corrected/review/corrected_final_summary.json"
    originals = {str(p): sha(p) for p in (sample, msf, source, first, last, summary)}
    args.output.mkdir(parents=True, exist_ok=False)
    match = match_source(sample, source)
    raw, embedded = msf.read_bytes(), source.read_bytes()
    offset = raw.find(embedded)
    if offset < 0:
        raise ValueError("known source PDF bytes not found in MSF; no generic parsing attempted")
    report = {
        "runtime": fitz.VersionBind,
        "pdf": inventory(sample),
        "source_match": match,
        "msf": {
            "sha256": sha(msf),
            "known_pdf_byte_offset": offset,
            "known_pdf_length": len(embedded),
            "known_pdf_sha256": sha(source),
            "source_bytes_exact": True,
            "trailing_bytes": len(raw) - offset - len(embedded),
            "android_path_hint_in_prefix": b"/Android/data/com.zubersoft.mobilesheetspro/"
            in raw[:offset],
            "structured_metadata_and_import": "not_run",
        },
        "sample_background_kind": "retained_original_score_not_pdfscorebar_numbered_result",
        "os_version_export_settings": "not_verified",
    }
    candidate = args.output / "candidate_attempt12_preserve_crop.pdf"
    replace_private_candidate(sample, last, candidate)
    report["preserve_crop"] = verify_candidate(sample, last, candidate)
    report["label_visibility"] = label_visibility(sample, last, summary)
    again = args.output / "candidate_second_cycle_attempt1.pdf"
    try:
        replace_private_candidate(candidate, first, again)
    except ValueError as exc:
        # Keep the original guard and preserve this failure. replace_image may
        # leave unused image resource aliases, so resource count is not the
        # painted-image count. A generic recurring-input validator is future work.
        report["second_cycle"] = {"status": "rejected", "reason": str(exc)}
        assert not again.exists()
    else:
        report["second_cycle"] = verify_candidate(sample, first, again)
    normalized = args.output / "normalized_owned_candidate.pdf"
    normalize_owned_candidate(candidate, normalized)
    report["owned_candidate_normalization"] = verify_candidate(sample, last, normalized)
    normalized_again = args.output / "candidate_second_cycle_after_normalization.pdf"
    replace_private_candidate(normalized, first, normalized_again)
    report["second_cycle_after_normalization"] = verify_candidate(sample, first, normalized_again)
    preview = args.output / "preview_attempt12_full_media.pdf"
    replace_private_candidate(sample, last, preview, full_media=True)
    report["explicit_full_media_preview"] = verify_candidate(sample, last, preview, full_media=True)
    report["overall_acceptance"] = (
        "not_passed_label_visibility_and_full_checkpoint_workflow_unverified"
    )
    for path, suffix in ((candidate, "crop"), (preview, "full_media")):
        with fitz.open(path) as doc:
            doc[2].get_pixmap().save(args.output / f"page3_{suffix}.png")
    assert originals == {str(p): sha(Path(p)) for p in originals}
    report["input_files_unchanged"] = True
    report["candidate_sha256"] = {
        p.name: sha(p)
        for p in (candidate, again, normalized, normalized_again, preview)
        if p.exists()
    }
    report["probe_sha256"] = sha(Path(__file__))
    (args.output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "pdf"}, indent=2))


if __name__ == "__main__":
    main()
