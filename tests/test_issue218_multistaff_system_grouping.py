"""3div./4div. connector chains, split guards, and shared measure progression."""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.measure_numbering.connector_aware_builder import ConnectorAwareSystemBuilder
from src.measure_numbering.connector_evidence import SystemConnectorEvidenceExtractor
from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.types import Barline, BBox, Page, Score, Staff
from tools.verification.evaluate_issue218_measure_gt import (
    align_intervals,
    score_page,
    validate_gt,
)

FIXTURES = Path(__file__).parent / "fixtures" / "system_grouping"


def test_manual_gt_does_not_shift_indices_to_hide_a_missing_measure():
    assert align_intervals([[0, 200], [200, 300]], [[0, 100], [100, 200], [200, 300]]) == [(1, 2)]


def test_manual_gt_shared_rest_and_page_index_follow_production_override_contract():
    expected = {
        "page_id": "page_009",
        "systems": [
            {
                "staff_center_y": [20, 40, 60],
                "staff_spacing": 2,
                "shared_boundaries_x": [0, 100, 200],
                "measures": [
                    {
                        "x_interval": [0, 100],
                        "duration_bars": 5,
                        "expected_run_number": 10,
                        "expected_page_local_number": 1,
                    },
                    {
                        "x_interval": [100, 200],
                        "duration_bars": 1,
                        "expected_run_number": 15,
                        "expected_page_local_number": 6,
                    },
                ],
            }
        ],
    }
    page = {
        "systems": [
            {
                "staves": [{"bbox": [0, y - 4, 200, y + 4]} for y in (20, 40, 60)],
                "measures": [
                    {"bbox": [0, 16, 100, 64], "number": 10},
                    {"bbox": [100, 16, 200, 64], "number": 15},
                ],
            }
        ]
    }
    overrides = {"measure_overrides": [{"page": 2, "system": 0, "measure": 0, "skip": 4}]}
    result = score_page(page, expected, overrides, page_index=2)
    assert result["mmr"]["gt"] == result["mmr"]["pred"] == result["mmr"]["exact_count"] == 1
    assert result["systems"][0]["numbers_correct"] == 2
    with pytest.raises(ValueError, match="Invalid or duplicate MMR"):
        score_page(page, expected, overrides, page_index=0)
    overrides["measure_overrides"][0]["skip"] = 1
    result = score_page(page, expected, overrides, page_index=2)
    assert result["mmr"]["exact_count"] == 0
    assert result["mmr"]["count_errors"][0]["pred_count"] == 2


def test_manual_gt_numbers_must_agree_with_rest_durations():
    annotation = json.loads((FIXTURES / "issue218_measure_gt.json").read_text())
    validate_gt(annotation)
    annotation["works"][0]["pages"][0]["systems"][0]["measures"][3]["expected_run_number"] -= 1
    with pytest.raises(ValueError, match="numbering disagrees with durations"):
        validate_gt(annotation)


@pytest.fixture(params=[3, 4], ids=["3div", "4div"])
def excerpt(request):
    stem = f"issue218_{request.param}div"
    metadata = json.loads((FIXTURES / f"{stem}.json").read_text())
    image = cv2.imread(str(FIXTURES / f"{stem}_score.png"), cv2.IMREAD_GRAYSCALE)
    symbols = cv2.imread(str(FIXTURES / f"{stem}_symbols.png"), cv2.IMREAD_GRAYSCALE)
    assert image is not None and symbols is not None
    assert image.shape == symbols.shape == tuple(reversed(metadata["image_size"]))
    return stem, metadata, image, symbols


def build(excerpt, *, scale=1, image_mode="score", reverse=False, absent_pair=None):
    _, metadata, image, symbols = excerpt
    staves = [
        Staff(
            BBox(*(int(value * scale) for value in item["bbox"])),
            unit_size=item["unit_size"] * scale,
        )
        for item in metadata["staves"]
    ]
    barlines = [
        Barline(BBox(*(int(value * scale) for value in box))) for box in metadata["barlines"]
    ]
    expected_presence = metadata["expected_connector_presence"].copy()
    if absent_pair is not None:
        # Generate absence from a changed semantic mask while retaining the
        # original page ink, rather than hand-authoring pair evidence.
        symbols = symbols.copy()
        upper_bottom = metadata["staves"][absent_pair]["bbox"][3]
        lower_top = metadata["staves"][absent_pair + 1]["bbox"][1]
        symbols[upper_bottom:lower_top] = 0
        expected_presence[absent_pair] = False
    size = tuple(int(value * scale) for value in metadata["image_size"])
    symbols = cv2.resize(symbols, size, interpolation=cv2.INTER_NEAREST)
    evidence = SystemConnectorEvidenceExtractor().extract(staves, size, symbol_mask=symbols)
    assert [pair["left_connector_present"] for pair in evidence["staff_pairs"]] == expected_presence
    if image_mode == "score":
        image = cv2.resize(image, size, interpolation=cv2.INTER_NEAREST)
    elif image_mode == "blank":
        image = np.full((size[1], size[0]), 255, dtype=np.uint8)
    else:
        assert image_mode == "none"
        image = None
    systems = ConnectorAwareSystemBuilder().build_systems(
        list(reversed(staves)) if reverse else staves,
        barlines,
        image=image,
        connector_evidence=evidence,
    )
    # Compare identities, not dataclass equality or just system/staff counts.
    indices = {id(staff): index for index, staff in enumerate(staves)}
    membership = [[indices[id(staff)] for staff in system.staves] for system in systems]
    return systems, membership


@pytest.mark.parametrize("scale", [0.5, 1, 2])
@pytest.mark.parametrize("image_mode", ["score", "blank", "none"])
@pytest.mark.parametrize("reverse", [False, True], ids=["ordered", "reversed"])
def test_transitive_divisi_merge_preserves_neighbor_and_measure_progression(
    excerpt, scale, image_mode, reverse
):
    _, metadata, _, _ = excerpt
    systems, membership = build(excerpt, scale=scale, image_mode=image_mode, reverse=reverse)
    assert membership == metadata["expected_systems"]

    score = Score(pages=[Page(systems=systems)])
    assert MeasureNumberer().number_score(score) == 5
    assert [[measure.number for measure in system.measures] for system in systems] == metadata[
        "expected_measure_numbers"
    ]
    for system in systems:
        # Shared measures span all divisi staves exactly once.
        assert len(system.measures) == 2
        for measure in system.measures:
            assert measure.bbox.y1 == system.staves[0].bbox.y1
            assert measure.bbox.y2 == system.staves[-1].bbox.y2


@pytest.mark.parametrize("image_mode", ["score", "none"])
def test_absent_connector_breaks_each_link_without_transitive_bypass(excerpt, image_mode):
    _, metadata, _, _ = excerpt
    divisi = metadata["expected_systems"][0]
    for index in range(len(divisi) - 1):
        _, membership = build(excerpt, image_mode=image_mode, absent_pair=index)
        assert membership == [divisi[: index + 1], divisi[index + 1 :], [len(divisi)]]


def test_guard_is_required_even_with_an_aligned_nonleft_ink_bridge(excerpt):
    _, metadata, image, _ = excerpt
    staves = [
        Staff(BBox(*item["bbox"]), unit_size=item["unit_size"]) for item in metadata["staves"]
    ]
    bars = [Barline(BBox(*box)) for box in metadata["barlines"]]
    # With no evidence, the legacy ink/alignment rule merges the independent
    # neighbor. The positive test proves that generated absence blocks this.
    systems = ConnectorAwareSystemBuilder().build_systems(staves[-2:], bars, image=image)
    assert len(systems) == 1
    assert systems[0].staves == staves[-2:]


@pytest.mark.parametrize("mask_key", ["symbols", "brace_dot"])
def test_pipeline_extracts_pair_evidence_and_numbers_divisi_once(excerpt, mask_key):
    stem, metadata, image, symbols = excerpt
    pipeline = MeasureNumberingPipeline()
    page = pipeline.process_page(
        metadata["barlines"],
        FIXTURES / f"{stem}_staff.png",
        tuple(metadata["image_size"]),
        image=image,
        connector_masks={mask_key: symbols},
    )
    # Staff extraction expands boxes vertically; identify membership by the
    # original staff center contained in each extracted box.
    centers = [(item["bbox"][1] + item["bbox"][3]) / 2 for item in metadata["staves"]]
    membership = [
        [
            next(index for index, y in enumerate(centers) if staff.bbox.y1 <= y < staff.bbox.y2)
            for staff in system.staves
        ]
        for system in page.systems
    ]
    assert membership == metadata["expected_systems"]
    assert MeasureNumberer().number_score(Score(pages=[page])) == 5
    assert [[measure.number for measure in system.measures] for system in page.systems] == metadata[
        "expected_measure_numbers"
    ]


@pytest.mark.parametrize("case_index", [0, 1, 2], ids=["real-3div", "real-4div", "real-full-page"])
def test_actual_model_outputs_preserve_every_voice_and_shared_boundaries(case_index):
    fixture = json.loads((FIXTURES / "issue218_real_detection.json").read_text())
    case = fixture["cases"][case_index]
    staves = [Staff(BBox(*s["bbox"]), unit_size=s["unit_size"]) for s in case["staves"]]
    bars = [Barline(BBox(*box)) for box in case["barlines"]]
    systems = ConnectorAwareSystemBuilder().build_systems(
        staves, bars, connector_evidence=case["connector_evidence"]
    )
    assert [len(system.staves) for system in systems] == case["expected_system_staff_counts"]
    assert [id(staff) for system in systems for staff in system.staves] == [id(s) for s in staves]
    MeasureNumberer().number_score(Score(pages=[Page(systems=systems)]))
    assert [len(system.measures) for system in systems] == case["expected_measures_per_system"]


@pytest.mark.parametrize("evidence", [None, False, True])
@pytest.mark.parametrize("staff_count", [2, 3, 4])
def test_barline_free_voice_requires_positive_multistaff_chain(evidence, staff_count):
    staves = [
        Staff(BBox(100, 100 + i * 152, 502, 180 + i * 152), unit_size=20)
        for i in range(staff_count)
    ]
    bars = [Barline(BBox(x, 100, x + 2, 180)) for x in (100, 300, 500)]
    pairs = None if evidence is None else {f"{i}-{i + 1}": evidence for i in range(staff_count - 1)}
    systems = ConnectorAwareSystemBuilder().build_systems(staves, bars, connector_evidence=pairs)
    expected = [staff_count] if evidence and staff_count >= 3 else [1] * staff_count
    assert [len(system.staves) for system in systems] == expected


@pytest.mark.parametrize("support", ["isolated-short", "aligned-short", "full-staff"])
def test_multistaff_boundary_needs_staff_span_or_cross_staff_support(support):
    from src.measure_numbering.types import System

    staves = [Staff(BBox(100, y, 502, y + 80), unit_size=20) for y in (100, 252, 404)]
    for staff in staves:
        staff.barlines = [Barline(BBox(x, staff.bbox.y1, x + 2, staff.bbox.y2)) for x in (100, 500)]
    height = 80 if support == "full-staff" else 10
    staves[0].barlines.append(Barline(BBox(300, 100, 302, 100 + height)))
    if support == "aligned-short":
        staves[1].barlines.append(Barline(BBox(300, 252, 302, 262)))
    system = System(staves=staves)
    MeasureNumberer().number_system(system, 1)
    assert len(system.measures) == (1 if support == "isolated-short" else 2)
