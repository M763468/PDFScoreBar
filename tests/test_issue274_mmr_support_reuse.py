from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from src.measure_numbering.mmr import MMRProcessor
from src.measure_numbering.types import BBox, Staff
from src.pipeline.core.manifest import build_manifest
from src.pipeline.detection.utils import resolve_paths_from_detection
from src.pipeline.mmr_geometry_handoff import build_mmr_page_context
from src.pipeline.mmr_support_reuse import build_mmr_support_data


def _page(*, staves: list[list[int]], measures: list[list[int]]) -> dict:
    return {
        "pages": [
            {
                "page_number": 1,
                "width": 400,
                "height": 300,
                "systems": [
                    {
                        "staves": [{"bbox": bbox} for bbox in staves],
                        "measures": [
                            {"number": index + 1, "bbox": bbox}
                            for index, bbox in enumerate(measures)
                        ],
                    }
                ],
            }
        ]
    }


def _support_with_current(
    monkeypatch: pytest.MonkeyPatch, current: list[list[int]], base: dict
) -> dict:
    class Extractor:
        def extract(self, _path, _size):
            return [Staff(bbox=BBox(*bbox)) for bbox in current]

    monkeypatch.setattr("src.pipeline.mmr_support_reuse.StaffExtractor", Extractor)
    return build_mmr_support_data(base, Path("current_staff_mask.png"))


def test_support_preserves_phase_a_topology_numbers_and_normal_x(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = _page(staves=[[20, 100, 380, 140]], measures=[[20, 100, 180, 140], [190, 100, 380, 140]])
    support = _support_with_current(monkeypatch, [[5, 110, 390, 135]], base)
    primary = support["views"]["primary"]
    measures = primary["pages"][0]["systems"][0]["measures"]

    assert [item["number"] for item in measures] == [1, 2]
    assert [item["bbox"][0::2] for item in measures] == [[20, 180], [190, 380]]
    assert [item["bbox"][1::2] for item in measures] == [[110, 135], [110, 135]]


def test_support_mapping_handles_single_many_to_one_union_and_unmapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    many_base = _page(
        staves=[[20, 100, 380, 140], [20, 105, 380, 145]], measures=[[20, 100, 380, 145]]
    )
    many = _support_with_current(monkeypatch, [[5, 110, 390, 135]], many_base)
    assert many["provenance"]["mapped_count"] == 2
    assert [record["mode"] for record in many["provenance"]["mappings"]] == [
        "single_current_staff",
        "single_current_staff",
    ]

    union_base = _page(staves=[[20, 100, 380, 150]], measures=[[20, 100, 380, 150]])
    union = _support_with_current(monkeypatch, [[5, 100, 390, 121], [5, 125, 390, 150]], union_base)
    assert union["provenance"]["union_count"] == 1
    assert union["provenance"]["mappings"][0]["effective_bbox"] == [20, 100, 380, 150]

    unmatched = _support_with_current(monkeypatch, [[5, 220, 390, 250]], union_base)
    assert unmatched["provenance"]["fallback_count"] == 1
    assert unmatched["provenance"]["mappings"][0]["mode"] == "phase_a_fallback"


def test_implicit_start_changes_only_alternate_start_x(monkeypatch: pytest.MonkeyPatch) -> None:
    base = _page(staves=[[20, 100, 380, 140]], measures=[[21, 100, 180, 140], [190, 100, 380, 140]])
    support = _support_with_current(monkeypatch, [[5, 110, 390, 135]], base)
    primary = support["views"]["primary"]["pages"][0]["systems"][0]["measures"]
    alternate = support["views"]["implicit_start_alternate"]["pages"][0]["systems"][0]["measures"]
    assert alternate[0]["bbox"][0] == 6
    assert alternate[1]["bbox"][0] == 190
    assert [item["bbox"][0] for item in primary] == [21, 190]


def test_implicit_start_uses_system_minimum_base_and_mapped_x(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = _page(
        staves=[[100, 100, 380, 140], [20, 200, 380, 240]],
        measures=[[21, 100, 380, 240], [200, 100, 380, 240]],
    )
    support = _support_with_current(
        monkeypatch,
        [[90, 110, 390, 135], [5, 210, 390, 235]],
        base,
    )
    primary = support["views"]["primary"]["pages"][0]["systems"][0]["measures"]
    alternate = support["views"]["implicit_start_alternate"]["pages"][0]["systems"][0]["measures"]

    assert alternate[0]["bbox"][0] == 6
    assert primary[0]["bbox"][0] == 21
    assert alternate[1]["bbox"][0] == primary[1]["bbox"][0] == 200


def test_near_staff_left_normal_measure_does_not_enable_alternate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = _page(staves=[[20, 100, 380, 140]], measures=[[22, 100, 180, 140], [190, 100, 380, 140]])
    support = _support_with_current(monkeypatch, [[5, 110, 390, 135]], base)
    primary = support["views"]["primary"]["pages"][0]["systems"][0]["measures"]
    alternate = support["views"]["implicit_start_alternate"]["pages"][0]["systems"][0]["measures"]

    assert [item["bbox"][0] for item in alternate] == [item["bbox"][0] for item in primary]


class _FixedClassifier:
    def __init__(self, prob: float = 0.9):
        self.prob = prob
        self.calls = 0

    def predict(self, _crop):
        self.calls += 1
        return self.prob


class _ScriptedProcessor(MMRProcessor):
    def __init__(self, classifier, responses):
        super().__init__(
            model_path=Path("unused"),
            device=torch.device("cpu"),
            classifier=classifier,
            ocr_engine=object(),
        )
        self.responses = responses

    def _detect_number_with_evidence(self, _image, system, *_args):
        key = tuple(system["staves"][0]["bbox"])
        return self.responses[key]


def _gate_support() -> tuple[dict, dict]:
    base = _page(staves=[[10, 30, 190, 60]], measures=[[10, 30, 190, 60]])
    primary = _page(staves=[[10, 10, 190, 40]], measures=[[10, 10, 190, 40]])
    alternate = _page(staves=[[10, 10, 190, 40]], measures=[[0, 10, 190, 40]])
    return base, {
        "views": {"primary": primary, "implicit_start_alternate": alternate, "fallback": base}
    }


def test_alternate_can_veto_but_never_create_positive_override(tmp_path: Path) -> None:
    base, support = _gate_support()
    image = np.zeros((100, 220, 3), dtype=np.uint8)
    image_path = tmp_path / "page.png"
    import cv2

    cv2.imwrite(str(image_path), image)
    classifier = _FixedClassifier(0.55)
    processor = _ScriptedProcessor(
        classifier,
        {(10, 10, 190, 40): (3, -1.0, "", 0), (10, 30, 190, 60): (9, 99.0, "", 0)},
    )

    # The alternate uses the same staff geometry but exposes two one-bar evidence items.
    def detect(_image, system, x1, *_args):
        if x1 == 0:
            return 1, -1.0, "", 2
        return processor.responses[tuple(system["staves"][0]["bbox"])]

    processor._detect_number_with_evidence = detect
    assert processor.process_pages(
        base["pages"] and [base], [image_path], support_data=[support]
    ) == [{"measure_overrides": []}]


def test_phase_a_fallback_is_ocr_only_and_never_replaces_valid_primary(tmp_path: Path) -> None:
    base, support = _gate_support()
    image_path = tmp_path / "page.png"
    import cv2

    cv2.imwrite(str(image_path), np.zeros((100, 220, 3), dtype=np.uint8))
    classifier = _FixedClassifier()
    processor = _ScriptedProcessor(
        classifier,
        {(10, 10, 190, 40): (None, 0.0, "", 0), (10, 30, 190, 60): (4, 99.0, "", 0)},
    )
    result = processor.process_pages([base], [image_path], support_data=[support])
    assert result[0]["measure_overrides"][0]["skip"] == 3
    assert classifier.calls == 1

    classifier = _FixedClassifier()
    processor = _ScriptedProcessor(
        classifier,
        {(10, 10, 190, 40): (5, 99.0, "", 0), (10, 30, 190, 60): (9, 99.0, "", 0)},
    )
    result = processor.process_pages([base], [image_path], support_data=[support])
    assert result[0]["measure_overrides"][0]["skip"] == 4
    assert classifier.calls == 1


def test_support_none_keeps_legacy_processor_path(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    import cv2

    cv2.imwrite(str(image_path), np.zeros((100, 220, 3), dtype=np.uint8))
    base = _page(staves=[[10, 10, 190, 40]], measures=[[10, 10, 190, 40]])
    processor = _ScriptedProcessor(_FixedClassifier(), {(10, 10, 190, 40): (3, 99.0, "", 0)})
    assert (
        processor.process_pages([base], [image_path], support_data=None)[0]["measure_overrides"][0][
            "skip"
        ]
        == 2
    )


def test_ocr_candidate_scoring_receives_processed_dimensions() -> None:
    class OCR:
        enable_rotation_tta = False

        def __init__(self):
            self.dimensions = []

        def mask_hbar_candidates(self, image, *_args):
            return image

        def preprocess_variant(self, _image, **_kwargs):
            return np.zeros((60, 80, 3), dtype=np.uint8)

        def ocr_engine(self, _image):
            return [], None

        def collect_one_bar_evidence(self, _result):
            return []

        def select_best_candidate(self, _result, width, height):
            self.dimensions.append((width, height))
            return None, 0.0, ""

    ocr = OCR()
    processor = MMRProcessor(
        model_path=Path("unused"), device=torch.device("cpu"), classifier=object(), ocr_engine=ocr
    )
    processor._detect_number_with_evidence(
        np.zeros((100, 200, 3), dtype=np.uint8),
        {"staves": [{"bbox": [0, 20, 200, 60]}]},
        10,
        20,
        100,
        60,
        0.9,
        200,
        100,
    )
    assert ocr.dimensions == [(80, 60)] * 5


def test_handoff_uses_sidecar_not_original_homr_worker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / "numbering_base.json"
    base.write_text('{"pages": []}', encoding="utf-8")
    current = tmp_path / "current_staff_mask.png"
    current.write_bytes(b"mask")
    ctx = {
        "page_001": {
            "numbering_base": base,
            "intermediate_dir": tmp_path,
            "resolved": {"current_homr_staff_mask": str(current)},
        }
    }
    monkeypatch.setattr(
        "src.pipeline.mmr_geometry_handoff.build_mmr_support",
        lambda **_kwargs: {"provenance": {"original_image_homr": False}},
    )
    monkeypatch.setattr(
        "src.pipeline.mmr_staff_support.prepare_mmr_staff_masks",
        lambda *_args: pytest.fail("old worker path must be unreachable"),
    )
    result = build_mmr_page_context(object(), ["page_001"], set(), ctx)
    assert result["page_001"]["numbering_base"] == base
    assert result["page_001"]["mmr_support"] == tmp_path / "mmr_support.json"


def test_manifest_and_detection_resolve_explicit_current_support(tmp_path: Path) -> None:
    hybrid = tmp_path / "hybrid"
    current = hybrid / "current_support" / "score" / "page_001_staff_mask.png"
    current.parent.mkdir(parents=True)
    current.write_bytes(b"mask")
    (hybrid / "hybrid_results").mkdir()
    (hybrid / "hybrid_results" / "page_001_hybrid.json").write_text("[]", encoding="utf-8")
    image = tmp_path / "page_001.png"
    image.write_bytes(b"image")
    resolved = resolve_paths_from_detection({}, tmp_path / "probe", hybrid, ["page_001"], [image])
    assert resolved[0]["current_homr_staff_mask"] == str(current)
    resolved[0]["mmr_support"] = {"source": "current_x4_support"}
    manifest = build_manifest(
        {},
        run_id="x",
        run_dir=tmp_path,
        images=[image],
        page_ids=["page_001"],
        page_runs=["page_001"],
        resolved=resolved,
        commands=[],
        page_statuses=[],
        barline_override_stats={},
    )
    assert manifest["pages"][0]["mmr_support"] == {"source": "current_x4_support"}
