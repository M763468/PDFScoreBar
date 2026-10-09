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

FIXTURES = Path(__file__).parent / "fixtures" / "system_grouping"


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
