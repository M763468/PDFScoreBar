"""The retained replay must audit silent misapplication, including last rests."""

from copy import deepcopy

import pytest
from PIL import Image

from src.pipeline.core import write_json
from src.pipeline.review.final_output import materialize_corrected_final_outputs
from tools.issue413.replay_phase_c import audit_score, verify_pdf_images


def page(page_id, numbers, next_number):
    return {
        "page_id": page_id,
        "pages": [
            {
                "systems": [
                    {
                        "staves": [{"bbox": [0, 0, 100, 40]}],
                        "measures": [
                            {"number": number, "bbox": [index * 20, 0, index * 20 + 19, 40]}
                            for index, number in enumerate(numbers)
                        ],
                    }
                ]
            }
        ],
        "numbering_metadata": {"next_number": next_number},
    }


def test_audit_includes_unrecognized_targets_page_boundary_and_terminal_skip():
    baseline = [page("page_001", [1, 5], 6), page("page_002", [6, 7], 8)]
    candidate = [page("page_001", [1, 2], 6), page("page_002", [6, 7], 10)]
    predictions = [
        {"measure_overrides": [{"page": 0, "system": 0, "measure": 1, "skip": 3}]},
        {"measure_overrides": [{"page": 1, "system": 0, "measure": 1, "skip": 2}]},
    ]
    records = audit_score("fixture", baseline, candidate, predictions)
    assert [r["recognized_skip"] for r in records] == [0, 3, 0, 2]
    assert [r["old_applied_skip"] for r in records] == [3, 0, 0, 0]
    assert [r["new_applied_skip"] for r in records] == [0, 3, 0, 2]


def test_audit_rejects_changed_geometry_and_missing_override_target():
    baseline = [page("page_001", [1, 2], 3)]
    candidate = deepcopy(baseline)
    candidate[0]["pages"][0]["systems"][0]["measures"][0]["bbox"][0] += 1
    with pytest.raises(AssertionError, match="geometry"):
        audit_score("fixture", baseline, candidate, [{"measure_overrides": []}])
    with pytest.raises(AssertionError, match="missing override target"):
        audit_score(
            "fixture",
            baseline,
            baseline,
            [{"measure_overrides": [{"page": 0, "system": 1, "measure": 0, "skip": 2}]}],
        )


def test_pdf_verification_reads_embedded_pixels_and_detects_stale_labels(tmp_path):
    source = tmp_path / "source.png"
    Image.new("RGB", (300, 200), "white").save(source)
    numbering = page("page_001", [1, 2], 3)
    numbering_path = tmp_path / "outputs/page_001/numbering_final.json"
    write_json(numbering_path, numbering)
    handoff = tmp_path / "handoff.json"
    write_json(handoff, {"pages": [{"page_id": "page_001", "source_image": "source.png"}]})
    summary = materialize_corrected_final_outputs(handoff_path=handoff, corrected_run_dir=tmp_path)
    assert len(verify_pdf_images(summary)) == 1
    numbering["pages"][0]["systems"][0]["measures"][0]["number"] = 42
    write_json(numbering_path, numbering)
    with pytest.raises(AssertionError, match="PDF pixel mismatch"):
        verify_pdf_images(summary)
