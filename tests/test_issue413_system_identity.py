"""Model-free regressions for the compact numbering system namespace."""

from copy import deepcopy

import pytest

from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.types import Barline, BBox, Page, Score, Staff, System, score_to_dict
from src.pipeline.core import write_json
from src.pipeline.steps.numbering import final_numbering_metadata, persisted_final_next_number


def music(y=100):
    return System(
        staves=[
            Staff(
                BBox(90, y, 940, y + 100),
                [Barline(BBox(x, y, x + 2, y + 100)) for x in [100, 300, 500, 700, 900]],
                unit_size=10,
            )
        ]
    )


def empty():
    return System(staves=[Staff(BBox(90, 0, 940, 80), unit_size=10)])


@pytest.mark.parametrize("pre_numbered", [False, True])
@pytest.mark.parametrize("positions", [[0], [1], [0, 1, 2, 4, 5]])
def test_overrides_address_same_physical_system_as_compact_json(positions, pre_numbered):
    visible = [music(), music(300), music(500)]
    systems = list(visible)
    for position in positions:
        systems.insert(position, empty())
    score = Score(pages=[Page(systems=systems)])
    numberer = MeasureNumberer()
    if pre_numbered:
        numberer.number_score(score)
    overrides = [
        {"page": 0, "system": 0, "measure": 0, "skip": 2},
        {"page": 0, "system": 2, "measure": 1, "skip": 3},
    ]
    original = deepcopy(overrides)
    next_number = numberer.number_score(score, overrides=overrides)
    payload = score_to_dict(score)["pages"][0]
    assert len(payload["empty_systems"]) == len(positions)
    assert [[m["number"] for m in s["measures"]] for s in payload["systems"]] == [
        [1, 4, 5, 6],
        [7, 8, 9, 10],
        [11, 12, 16, 17],
    ]
    assert [s.measures[0].bbox.y1 for s in visible] == [100, 300, 500]
    assert next_number == 18
    assert overrides == original
    # Repeated Phase C numbering must not depend on the preceding attributes.
    assert numberer.number_score(score, overrides=overrides) == next_number


def test_empty_predictions_and_multiple_pages_preserve_continuity():
    score = Score(
        pages=[
            Page(systems=[]),
            Page(systems=[empty(), System()]),
            Page(systems=[empty(), music(), empty(), music(300)]),
            Page(systems=[music()]),
        ]
    )
    next_number = MeasureNumberer().number_score(
        score,
        overrides=[
            {"page": 2, "system": 1, "measure": 3, "skip": 5},
            {"page": 3, "system": 0, "measure": 0, "skip": 2},
        ],
    )
    pages = score_to_dict(score)["pages"]
    assert pages[0]["systems"] == pages[1]["systems"] == []
    assert [m["number"] for m in pages[3]["systems"][0]["measures"]] == [14, 17, 18, 19]
    assert next_number == 20


def test_visibility_uses_constructed_measures_not_barline_count_or_stale_measures():
    stale = music()
    numberer = MeasureNumberer()
    numberer.number_system(stale, 1)
    stale.staves = []
    # The two close lines deduplicate into one, yielding no physical measure.
    deduplicated = System(
        staves=[
            Staff(
                BBox(90, 0, 940, 80),
                [Barline(BBox(100, 0, 102, 80)), Barline(BBox(105, 0, 107, 80))],
                unit_size=10,
            )
        ]
    )
    score = Score(pages=[Page(systems=[stale, deduplicated, music()])])
    numberer.number_score(score, overrides=[{"page": 0, "system": 0, "measure": 0, "skip": 2}])
    assert stale.measures == deduplicated.measures == []
    assert [m.number for m in score.pages[0].systems[2].measures] == [1, 4, 5, 6]


def test_movement_reset_and_set_number_share_compact_identity():
    score = Score(pages=[Page(systems=[empty(), music(), empty(), music(300)])])
    next_number = MeasureNumberer().number_score(
        score,
        start_number=10,
        boundary_resets={(0, 1): 1},
        overrides=[{"page": 0, "system": 1, "measure": 0, "set_number": 7, "skip": 2}],
    )
    assert [m.number for m in score.pages[0].systems[1].measures] == [10, 11, 12, 13]
    assert [m.number for m in score.pages[0].systems[3].measures] == [7, 10, 11, 12]
    assert next_number == 13
    with pytest.raises(ValueError, match="missing score systems"):
        MeasureNumberer().number_score(score, boundary_resets={(0, 2): 1})
    with pytest.raises(ValueError, match="missing score systems"):
        MeasureNumberer().number_score(
            Score(pages=[Page(systems=[empty()])]), boundary_resets={(0, 0): 1}
        )


def test_skip_existing_rejects_pre_fix_numbering_metadata(tmp_path):
    metadata = final_numbering_metadata(page_index=0, start_number=1, next_number=7, boundaries=[])
    path = tmp_path / "numbering_final.json"
    old_metadata = dict(metadata)
    old_metadata.pop("system_index_contract")
    write_json(path, {"numbering_metadata": old_metadata})
    assert (
        persisted_final_next_number(path, expected_start_number=1, expected_boundaries=[]) is None
    )
    write_json(path, {"numbering_metadata": metadata})
    assert persisted_final_next_number(path, expected_start_number=1, expected_boundaries=[]) == 7
