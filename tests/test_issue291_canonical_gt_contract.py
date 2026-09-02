from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GT_ROOT = ROOT / "data/evaluation2/annotations"
PROFILE_PATH = ROOT / "configs/detector_profiles/stage_e_verified_homr.json"

EXPECTED_PAGE_COUNT = 68
EXPECTED_GT_COUNT = 3567

DECLARED_MULTI_TYPES = {"double_barline", "end_barline", "repeat"}
HIGH_Y_OVERLAP = 0.70
SAME_INK_X_OVERLAP = 0.25
CLOSE_X_CENTER_REVIEW = 15.0

# (relative page path, kept bbox, removed bbox(es))
REVIEWED_CORRECTIONS = (
    (
        "Shostakovich-Festival_Overture_Va/page_009",
        (1232, 1848, 1236, 1959),
        ((1234, 1848, 1238, 1959),),
    ),
    (
        "Shostakovich-Sym5-Va/page_004",
        (1690, 2627, 1699, 2727),
        ((1688, 2626, 1692, 2725),),
    ),
    (
        "Shostakovich-Sym5-Va/page_004",
        (2730, 1893, 2739, 1995),
        ((2728, 1896, 2732, 1995),),
    ),
    (
        "Shostakovich-Sym5-Va/page_006",
        (2728, 2612, 2737, 2714),
        ((2726, 2619, 2730, 2718),),
    ),
    (
        "Shostakovich-Sym5-Va/page_008",
        (2745, 428, 2754, 530),
        ((2743, 428, 2747, 528),),
    ),
    (
        "Shostakovich-Sym5-Va/page_010",
        (2715, 1512, 2724, 1615),
        ((2713, 1520, 2717, 1620),),
    ),
    (
        "Shostakovich-Sym5-Va/page_013",
        (1679, 1168, 1683, 1270),
        ((1679, 1202, 1683, 1296),),
    ),
    (
        "Shostakovich-Sym5-Va/page_015",
        (2294, 2244, 2298, 2344),
        ((2296, 2246, 2305, 2344),),
    ),
    (
        "Shostakovich-Sym5-Va/page_022",
        (2732, 2247, 2741, 2351),
        ((2730, 2255, 2734, 2355),),
    ),
    (
        "Sibelius-Violin_Concerto-Viola/page_004",
        (1514, 4015, 1518, 4195),
        ((1514, 4092, 1518, 4196),),
    ),
    (
        "Sibelius-Violin_Concerto-Viola/page_004",
        (1924, 4015, 1928, 4195),
        ((1923, 4092, 1927, 4196),),
    ),
    (
        "Va__Prokofiev_Symphony5/page_007",
        None,
        (
            (665, 908, 669, 1018),
            (668, 908, 672, 1018),
        ),
    ),
)


def _canonical_files() -> list[Path]:
    return sorted(GT_ROOT.glob("*/page_*/boxes_sorted.json"))


def _load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, list), path
    assert all(isinstance(row, dict) for row in payload), path
    return payload


def _bbox(row: dict[str, Any]) -> tuple[int, int, int, int]:
    raw = row["barline_location"]
    assert isinstance(raw, list)
    assert len(raw) >= 4
    return tuple(int(round(float(value))) for value in raw[:4])


def _barline_type(row: dict[str, Any]) -> str:
    return str(row.get("barline_type") or "barline")


def _overlap(a1: int, a2: int, b1: int, b2: int) -> int:
    return max(0, min(a2, b2) - max(a1, b1))


def _pair_metrics(
    first: dict[str, Any],
    second: dict[str, Any],
) -> tuple[float, float, float]:
    ax1, ay1, ax2, ay2 = _bbox(first)
    bx1, by1, bx2, by2 = _bbox(second)

    aw = max(1, ax2 - ax1)
    bw = max(1, bx2 - bx1)
    ah = max(1, ay2 - ay1)
    bh = max(1, by2 - by1)

    x_overlap = _overlap(ax1, ax2, bx1, bx2)
    y_overlap = _overlap(ay1, ay2, by1, by2)

    x_center_delta = abs((ax1 + ax2) / 2 - (bx1 + bx2) / 2)
    x_overlap_over_min = x_overlap / min(aw, bw)
    y_overlap_over_min = y_overlap / min(ah, bh)

    return x_center_delta, x_overlap_over_min, y_overlap_over_min


def test_issue291_canonical_gt_count() -> None:
    files = _canonical_files()
    assert len(files) == EXPECTED_PAGE_COUNT

    total = sum(len(_load_rows(path)) for path in files)
    assert total == EXPECTED_GT_COUNT


def test_issue291_stage_e_profile_uses_corrected_final_accepted_contract() -> None:
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    metrics = profile["verified_stage_e_full68"]

    assert metrics["gt"] == EXPECTED_GT_COUNT
    assert {key: metrics[key] for key in ("pred", "tp", "fp", "fn", "fn_det", "fn_cnn")} == {
        "pred": 3599,
        "tp": 3565,
        "fp": 3,
        "fn": 2,
        "fn_det": 0,
        "fn_cnn": 2,
    }
    assert metrics["soft_duplicate_or_repeat_like"] == 31
    assert metrics["canonical_gt_rebase_issue"] == 291
    assert metrics["evaluated_artifact"] == "pipeline2_no_peak_filtered_cnn.json"


def test_issue291_changed_pages_are_sequentially_renumbered() -> None:
    relative_pages = {
        relative_page for relative_page, _kept_bbox, _removed_bboxes in REVIEWED_CORRECTIONS
    }
    assert len(relative_pages) == 10

    for relative_page in sorted(relative_pages):
        path = GT_ROOT / relative_page / "boxes_sorted.json"
        rows = _load_rows(path)
        numbers = [row.get("measure_number") for row in rows]
        assert numbers == list(range(1, len(rows) + 1)), path


def test_issue291_reviewed_p1_corrections_are_canonical() -> None:
    for relative_page, kept_bbox, removed_bboxes in REVIEWED_CORRECTIONS:
        path = GT_ROOT / relative_page / "boxes_sorted.json"
        rows = _load_rows(path)
        bboxes = [_bbox(row) for row in rows]

        if kept_bbox is not None:
            assert bboxes.count(kept_bbox) == 1, path

        for removed_bbox in removed_bboxes:
            assert removed_bbox not in bboxes, path


def test_issue291_no_plain_same_ink_conflicts_and_p3_is_preserved() -> None:
    p1_conflicts: list[tuple[str, tuple[int, ...], tuple[int, ...]]] = []
    p3_pairs: list[tuple[str, tuple[int, ...], tuple[int, ...]]] = []

    for path in _canonical_files():
        rows = _load_rows(path)

        for first, second in combinations(rows, 2):
            x_center_delta, x_overlap_over_min, y_overlap_over_min = _pair_metrics(first, second)
            first_type = _barline_type(first)
            second_type = _barline_type(second)
            both_plain = first_type == second_type == "barline"

            record = (
                str(path.relative_to(ROOT)),
                _bbox(first),
                _bbox(second),
            )

            if (
                both_plain
                and x_overlap_over_min >= SAME_INK_X_OVERLAP
                and y_overlap_over_min >= HIGH_Y_OVERLAP
            ):
                p1_conflicts.append(record)
            elif (
                {first_type, second_type} & DECLARED_MULTI_TYPES
                and x_center_delta <= CLOSE_X_CENTER_REVIEW
                and y_overlap_over_min >= HIGH_Y_OVERLAP
            ):
                p3_pairs.append(record)

    assert p1_conflicts == []
    assert len(p3_pairs) == 51


def test_issue291_prokofiev_assignment_case_is_not_deleted() -> None:
    path = GT_ROOT / "Va_Prokofiev_Symphony1" / "page_004" / "boxes_sorted.json"
    rows = _load_rows(path)

    # This is the separate #274 greedy-assignment case, not a P1 deletion target.
    assert len(rows) == 120

    bboxes_and_types = {(_bbox(row), _barline_type(row)) for row in rows}
    assert ((1441, 2166, 1445, 2269), "repeat") in bboxes_and_types
    assert ((1456, 2166, 1460, 2269), "repeat") in bboxes_and_types
    assert ((2844, 1615, 2857, 1720), "repeat") in bboxes_and_types
    assert ((2862, 1618, 2869, 1721), "repeat") in bboxes_and_types
