"""Focused safety checks for the experimental numbering layer, no real score data."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import fitz
from PIL import Image

from src.pipeline.review import number_layer as crop_label_layer
from src.pipeline.review.number_layer import (
    FONT_POINTS,
    NumberLayerValidationError,
    write_number_layer,
)
from tools.issue441.phase0_probe import sha


def fixture(path, *, color="white", blocking_annotation=False):
    encoded = io.BytesIO()
    Image.new("RGB", (200, 260), color).save(encoded, "PNG")
    with fitz.open() as doc:
        page = doc.new_page(width=200, height=260)
        page.insert_image(page.rect, stream=encoded.getvalue())
        page.set_cropbox(fitz.Rect(10, 10, 190, 250))
        if blocking_annotation:
            note = page.add_rect_annot(page.rect)
            note.set_colors(stroke=(1, 1, 1), fill=(1, 1, 1))
        else:
            note = page.add_ink_annot([[(110, 150), (150, 155)]])
        note.update()
        doc.save(path)
    return [
        {
            "source_pixels": [200, 260],
            "rows": [
                {
                    "row_id": "row_001",
                    "row_start_measure_number": 12,
                    "top_staff_bbox": [60, 100, 180, 130],
                }
            ],
        }
    ]


class AnnotatedNumberLayerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_update_removes_only_owned_numbers_and_preserves_cropped_score(self):
        source = self.root / "source.pdf"
        data = fixture(source)
        original_hash = sha(source)
        sidecar, report = write_number_layer(source, source, data, self.root / "first.pdf")
        updated = deepcopy(data)
        updated[0]["rows"][0]["row_start_measure_number"] = 321
        _, result = write_number_layer(
            self.root / "first.pdf",
            source,
            updated,
            self.root / "second.pdf",
            previous_sidecar=sidecar,
        )
        with fitz.open(self.root / "second.pdf") as doc:
            self.assertEqual(doc[0].get_text().split(), ["321"])
            self.assertEqual(doc[0].cropbox, fitz.Rect(10, 10, 190, 250))
        self.assertTrue(result["previous_layer_removed_to_exact_original"])
        self.assertEqual(report["label_count"], 1)
        self.assertEqual(sha(source), original_hash)

    def test_no_free_space_refuses_without_creating_output(self):
        source = self.root / "black.pdf"
        data = fixture(source, color="black")
        before = sha(source)
        with self.assertRaisesRegex(ValueError, "No safe"):
            write_number_layer(source, source, data, self.root / "rejected.pdf")
        self.assertFalse((self.root / "rejected.pdf").exists())
        self.assertEqual(sha(source), before)

    def test_invisible_white_annotation_still_blocks_placement(self):
        source = self.root / "white_note.pdf"
        data = fixture(source, blocking_annotation=True)
        with self.assertRaisesRegex(ValueError, "No safe"):
            write_number_layer(source, source, data, self.root / "rejected.pdf")
        self.assertFalse((self.root / "rejected.pdf").exists())

    def test_unknown_modified_result_cannot_reuse_owned_layer_identity(self):
        source = self.root / "source.pdf"
        data = fixture(source)
        sidecar, _ = write_number_layer(source, source, data, self.root / "first.pdf")
        with (self.root / "first.pdf").open("ab") as stream:
            stream.write(b"\n")
        with self.assertRaisesRegex(ValueError, "provenance"):
            write_number_layer(
                self.root / "first.pdf",
                source,
                data,
                self.root / "rejected.pdf",
                previous_sidecar=sidecar,
            )
        self.assertFalse((self.root / "rejected.pdf").exists())

    def test_corrupt_stream_digest_is_rejected_before_deletion(self):
        source = self.root / "source.pdf"
        data = fixture(source)
        sidecar, _ = write_number_layer(source, source, data, self.root / "first.pdf")
        payload = json.loads(sidecar.read_text())
        payload["pages"][0]["number_streams"][0]["sha256"] = "0" * 64
        sidecar.write_text(json.dumps(payload))
        before = sha(self.root / "first.pdf")
        with self.assertRaisesRegex(ValueError, "stream changed"):
            write_number_layer(
                self.root / "first.pdf",
                source,
                data,
                self.root / "rejected.pdf",
                previous_sidecar=sidecar,
            )
        self.assertEqual(sha(self.root / "first.pdf"), before)
        self.assertFalse((self.root / "rejected.pdf").exists())

    def test_different_staff_heights_use_one_document_font_size(self):
        source = self.root / "source.pdf"
        data = fixture(source)
        data[0]["rows"].append(
            {
                "row_id": "row_002",
                "row_start_measure_number": 321,
                "top_staff_bbox": [60, 190, 180, 245],
            }
        )
        _, report = write_number_layer(source, source, data, self.root / "uniform.pdf")
        self.assertEqual(
            {x["font_size"] for p in report["pages"] for x in p["labels"]}, {FONT_POINTS}
        )
        with fitz.open(self.root / "uniform.pdf") as doc:
            sizes = {
                span["size"]
                for block in doc[0].get_text("dict", flags=0)["blocks"]
                if block["type"] == 0
                for line in block["lines"]
                for span in line["spans"]
            }
        self.assertEqual(sizes, {FONT_POINTS})
        self.assertTrue(
            all(x["distance_to_staff_start_points"] < 3 for x in report["pages"][0]["labels"])
        )

    def test_save_then_validation_failure_never_publishes_result(self):
        source = self.root / "source.pdf"
        data = fixture(source)
        previous = self.root / "previous.pdf"
        sidecar, _ = write_number_layer(source, source, data, previous)
        retained = {p: sha(p) for p in (source, previous, sidecar)}
        output = self.root / "rejected.pdf"

        def fail_after_save(candidate, *_):
            self.assertTrue(candidate.is_file())
            self.assertTrue(candidate.read_bytes().startswith(b"%PDF-"))
            raise NumberLayerValidationError("injected post-save failure")

        with patch.object(crop_label_layer, "_validate_saved_output", side_effect=fail_after_save):
            with self.assertRaisesRegex(NumberLayerValidationError, "post-save"):
                write_number_layer(previous, source, data, output, previous_sidecar=sidecar)
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix(".layer.json").exists())
        self.assertEqual(retained, {p: sha(p) for p in retained})
        self.assertFalse(list(self.root.glob(".rejected-*")))

    def test_pdf_publish_failure_removes_only_own_sidecar(self):
        source = self.root / "source.pdf"
        data = fixture(source)
        output = self.root / "rejected.pdf"
        real_link = os.link

        def fail_pdf_link(src, dst):
            if Path(dst) == output:
                raise OSError("injected publication failure")
            return real_link(src, dst)

        with patch.object(crop_label_layer.os, "link", side_effect=fail_pdf_link):
            with self.assertRaisesRegex(OSError, "publication"):
                write_number_layer(source, source, data, output)
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix(".layer.json").exists())
        self.assertFalse(list(self.root.glob(".rejected-*")))

    def test_concurrent_output_is_not_overwritten_or_deleted(self):
        source = self.root / "source.pdf"
        data = fixture(source)
        output = self.root / "concurrent.pdf"
        validate = crop_label_layer._validate_saved_output

        def concurrent_write(*args):
            validate(*args)
            output.write_bytes(b"another writer")

        with patch.object(crop_label_layer, "_validate_saved_output", side_effect=concurrent_write):
            with self.assertRaises(FileExistsError):
                write_number_layer(source, source, data, output)
        self.assertEqual(output.read_bytes(), b"another writer")
        self.assertFalse(output.with_suffix(".layer.json").exists())

    def test_orphan_sidecar_is_not_reused(self):
        source = self.root / "source.pdf"
        data = fixture(source)
        output = self.root / "orphan.pdf"
        sidecar = output.with_suffix(".layer.json")
        sidecar.write_text("interrupted previous writer")
        with self.assertRaises(FileExistsError):
            write_number_layer(source, source, data, output)
        self.assertEqual(sidecar.read_text(), "interrupted previous writer")
        self.assertFalse(output.exists())

    def test_post_save_checks_still_run_under_python_optimization(self):
        source = self.root / "source.pdf"
        fixture(source)
        output = self.root / "optimized.pdf"
        program = """
from pathlib import Path
import os, sys
from unittest.mock import patch
import fitz
from src.pipeline.review import number_layer as layer
source, output = map(Path, sys.argv[1:])
data = [{"source_pixels": [200,260], "rows": [{"row_id":"row_001", "row_start_measure_number":12, "top_staff_bbox":[60,100,180,130]}]}]
validate = layer._validate_saved_output
def corrupt_then_validate(candidate, *args):
    changed = candidate.with_name("corrupt.pdf")
    with fitz.open(candidate) as doc:
        crop = doc[0].cropbox
        doc[0].set_cropbox(fitz.Rect(crop.x0, crop.y0, crop.x1-1, crop.y1))
        doc.save(changed)
    os.replace(changed, candidate)
    validate(candidate, *args)
with patch.object(layer, "_validate_saved_output", side_effect=corrupt_then_validate):
    try:
        layer.write_number_layer(source, source, data, output)
    except layer.NumberLayerValidationError:
        pass
    else:
        raise RuntimeError("post-save validation was disabled")
if output.exists() or output.with_suffix(".layer.json").exists():
    raise RuntimeError("failed result was published")
"""
        result = subprocess.run(
            [sys.executable, "-O", "-c", program, str(source), str(output)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()


def test_four_and_ten_digit_numbers_are_inside_crop_and_do_not_touch_page_edges(tmp_path):
    import numpy as np

    from src.pipeline.review.number_layer import pix_array

    source = tmp_path / "source.pdf"
    data = fixture(source)
    for number in [1003, 1011, 1234567890]:
        data[0]["rows"][0]["row_start_measure_number"] = number
        data[0]["rows"][0]["top_staff_bbox"] = [12, 24, 180, 40]
        _, report = write_number_layer(source, source, data, tmp_path / f"{number}.pdf")
        with fitz.open(tmp_path / f"{number}.pdf") as doc:
            assert doc[0].rect.contains(fitz.Rect(report["pages"][0]["labels"][0]["rect"]))
            assert doc[0].get_text().strip() == str(number)
            pixels = pix_array(doc[0])
            assert (
                min(
                    np.min(pixels[0]),
                    np.min(pixels[-1]),
                    np.min(pixels[:, 0]),
                    np.min(pixels[:, -1]),
                )
                == 255
            )


def test_post_save_validator_rejects_an_outside_number_bbox(tmp_path):
    import pytest

    from src.pipeline.review.number_layer import _validate_saved_output

    source = tmp_path / "source.pdf"
    data = fixture(source)
    output = tmp_path / "output.pdf"
    _, report = write_number_layer(source, source, data, output)
    report["pages"][0]["labels"][0]["rect"] = [-1, 0, 5, 5]
    with pytest.raises(NumberLayerValidationError, match="CropBox"):
        _validate_saved_output(output, source, report)


def test_page_font_alias_cannot_bypass_number_ink_bounds(tmp_path):
    import pytest

    source = tmp_path / "source.pdf"
    data = fixture(source)
    changed = tmp_path / "wrong_font.pdf"
    with fitz.open(source) as doc:
        xref = doc[0].insert_font(fontname="cour")
        resources = int(doc.xref_get_key(doc[0].xref, "Resources")[1].split()[0])
        doc.xref_set_key(resources, "Font/hebo", f"{xref} 0 R")
        doc.save(changed)
    output = tmp_path / "rejected.pdf"
    with pytest.raises(NumberLayerValidationError, match="metrics"):
        write_number_layer(changed, changed, data, output)
    assert not output.exists()
    assert not output.with_suffix(".layer.json").exists()
