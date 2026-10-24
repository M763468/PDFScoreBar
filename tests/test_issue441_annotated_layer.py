"""Focused safety checks for the experimental numbering layer, no real score data."""

import io
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import fitz
from PIL import Image

from tools.issue441.crop_label_layer import write_number_layer
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


if __name__ == "__main__":
    unittest.main()
