from copy import deepcopy

from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.types import Barline, BBox, Page, Score, Staff, System
from src.pipeline.steps.numbering import rebase_mmr_overrides_to_page_local


def _one_page_score() -> Score:
    score = Score()
    page = Page(page_number=2)
    staff = Staff(bbox=BBox(0, 100, 1000, 200))
    for x in [100, 300, 500, 700, 900]:
        staff.barlines.append(Barline(bbox=BBox(x, 100, x + 2, 200)))
    page.systems.append(System(staves=[staff]))
    score.pages.append(page)
    return score


def test_page_one_mmr_override_is_rebased_for_one_page_score() -> None:
    persisted_payload = {
        "measure_overrides": [
            {
                "page": 1,
                "system": 0,
                "measure": 1,
                "skip": 3,
                "comment": "MMR page-one override",
                "source": "test:mmr",
            }
        ],
        "diagnostics": {"batch": "global"},
    }
    original_payload = deepcopy(persisted_payload)

    page_local_payload = rebase_mmr_overrides_to_page_local(persisted_payload)

    assert persisted_payload == original_payload
    assert page_local_payload is not persisted_payload
    assert page_local_payload == {
        "measure_overrides": [
            {
                "page": 0,
                "system": 0,
                "measure": 1,
                "skip": 3,
                "comment": "MMR page-one override",
                "source": "test:mmr",
            }
        ],
        "diagnostics": {"batch": "global"},
    }

    score = _one_page_score()
    MeasureNumberer().number_score(
        score,
        start_number=1,
        overrides=page_local_payload["measure_overrides"],
    )

    measures = score.pages[0].systems[0].measures
    assert [measure.number for measure in measures] == [1, 2, 6, 7]
