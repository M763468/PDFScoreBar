"""Annotation-only PDF rewrites must prove numbering ownership before removal."""

import json
from collections import Counter
from copy import deepcopy

import fitz
import pytest
from test_issue441_annotated_layer import fixture
from test_review_correction_history import _checkpoint, _pdf_package

from src.pipeline.review.number_layer import (
    note_signature,
    sha,
    strip_returned_layer,
    write_number_layer,
)
from tools.review_correction.resume import create_session, prepare_pdf
from tools.review_correction.server import ReviewPackage


def _returned(tmp_path):
    source = tmp_path / "source.pdf"
    data = fixture(source)
    with fitz.open(source) as doc:
        unused = doc.get_new_xref()
        doc.update_object(unused, "<< /Unused true >>")
        doc.save(tmp_path / "with_unused.pdf")
    (tmp_path / "with_unused.pdf").replace(source)
    numbered = tmp_path / "numbered.pdf"
    sidecar, _ = write_number_layer(source, source, data, numbered)
    returned = tmp_path / "returned.pdf"
    with fitz.open(numbered) as doc:
        doc[0].add_freetext_annot(fitz.Rect(80, 20, 150, 40), "test", fontsize=12).update()
        doc.save(returned, garbage=4, deflate=True)
    return source, data, numbered, sidecar, returned


def test_remapped_xrefs_preserve_new_annotations_and_replace_only_old_numbers(tmp_path):
    source, data, numbered, sidecar, returned = _returned(tmp_path)
    assert sha(returned) != sha(numbered)
    with fitz.open(numbered) as old, fitz.open(returned) as new:
        assert old[0].get_contents() != new[0].get_contents()
    cleaned = tmp_path / "cleaned.pdf"
    proof = strip_returned_layer(returned, numbered, sidecar, source, cleaned)
    assert proof["removed_number_count"] == 1
    with fitz.open(returned) as new, fitz.open(cleaned) as clean:
        assert note_signature(new, new[0]) == note_signature(clean, clean[0])
        assert clean[0].get_text().split() == ["test"]
    changed = deepcopy(data)
    changed[0]["rows"][0]["row_start_measure_number"] = 321
    output = tmp_path / "updated.pdf"
    write_number_layer(cleaned, cleaned, changed, output)
    with fitz.open(output) as final:
        assert Counter(final[0].get_text().split()) == Counter(["test", "321"])
        assert len(list(final[0].annots())) == 2
    assert sha(returned) == proof["input_sha256"]


@pytest.mark.parametrize(
    "tamper", ["content", "marker", "rotation", "resources", "unused_font_key"]
)
def test_unknown_changes_are_rejected_without_publishing(tmp_path, tamper):
    source, _, numbered, sidecar, returned = _returned(tmp_path)
    corrupted = tmp_path / "corrupted.pdf"
    with fitz.open(returned) as doc:
        page = doc[0]
        owned = page.get_contents()[-1]
        if tamper == "content":
            doc.update_stream(
                owned, doc.xref_stream(owned).replace(b"12", b"99") + b"\n% unknown edit"
            )
        elif tamper == "marker":
            doc.xref_set_key(owned, "PDFScoreBarNumbers", "null")
        elif tamper == "rotation":
            page.set_rotation(90)
        elif tamper == "unused_font_key":
            font = next(x[0] for x in page.get_fonts() if x[4] == "hebo")
            doc.xref_set_key(font, "Unexpected", "(unused)")
        else:
            # Preserve text commands but replace the font resource they reference.
            page.insert_font(fontname="cour")
            resources = int(doc.xref_get_key(page.xref, "Resources")[1].split()[0])
            courier = next(x[0] for x in page.get_fonts() if x[4] == "cour")
            doc.xref_set_key(resources, "Font/hebo", f"{courier} 0 R")
        doc.save(corrupted)
    output = tmp_path / "rejected.pdf"
    with pytest.raises(ValueError):
        strip_returned_layer(corrupted, numbered, sidecar, source, output)
    assert not output.exists()


def test_marker_without_attested_result_is_not_authority(tmp_path):
    package, _ = _pdf_package(tmp_path / "package")
    source, _, _, _, returned = _returned(tmp_path)
    with pytest.raises(ValueError, match="attested"):
        prepare_pdf(package, returned, source, tmp_path / "rejected.pdf")
    assert not (tmp_path / "rejected.pdf").exists()


def test_return_with_unnumbered_page_preserves_annotations_and_rejects_background_change(tmp_path):
    source = tmp_path / "source.pdf"
    data = fixture(source)
    with fitz.open(source) as doc:
        page = doc.new_page(width=200, height=260)
        page.insert_text((30, 80), "unnumbered page")
        doc.save(tmp_path / "two_pages.pdf")
    (tmp_path / "two_pages.pdf").replace(source)
    data.append({"source_pixels": [200, 260], "rows": []})
    numbered = tmp_path / "numbered.pdf"
    sidecar, _ = write_number_layer(source, source, data, numbered)
    returned = tmp_path / "returned.pdf"
    with fitz.open(numbered) as doc:
        assert not any(font[4] == "hebo" for font in doc[1].get_fonts())
        doc[1].add_freetext_annot(fitz.Rect(30, 120, 160, 150), "new note").update()
        doc.save(returned, garbage=4, deflate=True)
    cleaned = tmp_path / "cleaned.pdf"
    proof = strip_returned_layer(returned, numbered, sidecar, source, cleaned)
    assert proof["removed_number_count"] == 1
    with fitz.open(cleaned) as doc, fitz.open(returned) as incoming:
        assert len(doc) == 2
        assert "12" not in doc[0].get_text().split()
        assert "unnumbered page" in doc[1].get_text()
        assert note_signature(doc, doc[1]) == note_signature(incoming, incoming[1])
    corrupted = tmp_path / "changed.pdf"
    with fitz.open(returned) as doc:
        doc[1].insert_text((30, 180), "unexpected content")
        doc.save(corrupted)
    rejected = tmp_path / "rejected.pdf"
    with pytest.raises(ValueError):
        strip_returned_layer(corrupted, numbered, sidecar, source, rejected)
    assert not rejected.exists()


def test_product_resume_records_original_and_cleaned_pdf_and_preserves_test(tmp_path):
    package, annotated = _pdf_package(tmp_path)
    original = tmp_path / "annotated.pdf"
    original.write_bytes(annotated)
    output = package.root / "application_runs/attempt_0001/corrected/final/numbered.pdf"
    output.parent.mkdir(parents=True)
    data = [
        {
            "source_pixels": [200, 260],
            "rows": [
                {
                    "row_id": "row_001",
                    "row_start_measure_number": 12,
                    "top_staff_bbox": [60, 100, 180, 125],
                }
            ],
        }
    ]
    sidecar, _ = write_number_layer(original, original, data, output)
    with package.history.transaction():
        package.history.application_record(
            "attempt_0001",
            {
                "status": "succeeded",
                "result": {
                    "final_pdf": str(output),
                    "final_pdf_sha256": sha(output),
                    "number_layer_sidecar": str(sidecar),
                    "number_layer_sidecar_sha256": sha(sidecar),
                },
            },
        )
    with fitz.open(output) as doc:
        doc[0].add_freetext_annot(fitz.Rect(80, 20, 150, 40), "test").update()
        returned = doc.tobytes(garbage=4)
    session = create_session(package, _checkpoint(package), returned)
    handoff = package.root / f"resumed_sessions/{session}/review/manual_correction_input.json"
    resumed = ReviewPackage(handoff)
    payload = json.loads(handoff.read_text())["resume"]
    assert payload["input_sha256"] != payload["background_sha256"]
    assert payload["roundtrip"]["removed_number_count"] == 1
    assert resumed.state.snapshot()["package"]["current_result"] is None
    with fitz.open(resumed.root / payload["background_pdf"]) as doc:
        assert doc[0].get_text().split() == ["test"]
    before = resumed.state.capture_identity()
    (resumed.root / payload["background_pdf"]).write_bytes(b"changed")
    assert resumed.state.capture_identity() != before


def test_second_resume_uses_product_result_and_selected_session_checkpoint(tmp_path, monkeypatch):
    from tools.review_correction import application

    package, annotated = _pdf_package(tmp_path)
    first_id = create_session(package, _checkpoint(package), annotated)
    first = ReviewPackage(
        package.root / f"resumed_sessions/{first_id}/review/manual_correction_input.json"
    )
    older = _checkpoint(first)
    first.record_correction(0, "barline_construction", [])

    def engine(handoff, **kwargs):
        run = kwargs["output_root"] / kwargs["run_id"]
        (run / "review").mkdir(parents=True)
        (run / "review/correction_summary.json").write_text("{}")
        target = run / "outputs/page_001/numbering_final.json"
        target.parent.mkdir(parents=True)
        target.write_text(
            json.dumps(
                {
                    "pages": [
                        {
                            "systems": [
                                {
                                    "staves": [{"bbox": [60, 100, 180, 125]}],
                                    "measures": [{"number": 12, "bbox": [60, 100, 180, 125]}],
                                }
                            ]
                        }
                    ]
                }
            )
        )
        return run

    monkeypatch.setattr(application, "apply_corrections_and_rerun", engine)
    app = application.CorrectionApplication(first, first.handoff_path)
    app.start()
    app.thread.join(5)
    with fitz.open(app.result()) as doc:
        doc[0].add_freetext_annot(fitz.Rect(80, 20, 150, 40), "second round").update()
        returned = doc.tobytes(garbage=4, deflate=True)
    second_id = create_session(
        first, older, returned, session_root=package.root, ownership_package=package
    )
    second = ReviewPackage(
        package.root / f"resumed_sessions/{second_id}/review/manual_correction_input.json"
    )
    assert (
        second.state.capture_identity()["corrections_identity"]
        == first.history.get(older)["identity"]["corrections_identity"]
    )
    assert (
        second.state.capture_identity()["corrections_identity"]
        != first.state.capture_identity()["corrections_identity"]
    )
    app2 = application.CorrectionApplication(second, second.handoff_path)
    app2.start()
    app2.thread.join(5)
    with fitz.open(app2.result()) as doc:
        assert len(list(doc[0].annots())) == 2
        assert Counter(doc[0].get_text().split()) == Counter(["second", "round", "12"])
    assert first.state.snapshot()["package"]["current_result"] is not None

    # A checkpoint captured from the normalized session retains background.pdf.
    # Exercise two more returns and keep the existing session's artifacts immutable.
    for index in (3, 4):
        previous_pdf = app2.result()
        previous_hash = sha(previous_pdf)
        previous_background = second.root / "resume/background.pdf"
        background_hash = sha(previous_background)
        checkpoint = _checkpoint(second)
        with fitz.open(previous_pdf) as doc:
            doc[0].add_freetext_annot(
                fitz.Rect(80, 40 + index * 20, 150, 55 + index * 20), f"round{index}"
            ).update()
            returned = doc.tobytes(garbage=4, deflate=True)
        next_id = create_session(
            second, checkpoint, returned, session_root=package.root, ownership_package=package
        )
        assert sha(previous_background) == background_hash
        assert sha(previous_pdf) == previous_hash
        second = ReviewPackage(
            package.root / f"resumed_sessions/{next_id}/review/manual_correction_input.json"
        )
        app2 = application.CorrectionApplication(second, second.handoff_path)
        app2.start()
        app2.thread.join(5)
        with fitz.open(app2.result()) as doc:
            assert len(list(doc[0].annots())) == index
            assert doc[0].get_text().split().count("12") == 1
            assert f"round{index}" in doc[0].get_text()
