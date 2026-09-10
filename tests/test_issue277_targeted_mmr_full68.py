import pytest

from tools.issue277.rescore_targeted_mmr_full68 import (
    actual_override_index,
    page_exact,
    score_indices,
    zero_expected_pages,
)


def row(page, system, measure, skip):
    return {
        "page": page,
        "system": system,
        "measure": measure,
        "skip": skip,
        "comment": "test",
    }


def test_full68_scoring_separates_tp_fn_mismatch_and_fp():
    expected = {
        (0, 0, 0): 2,
        (1, 0, 0): 4,
        (2, 1, 3): 6,
    }
    actual = actual_override_index(
        [
            row(0, 0, 0, 2),
            row(1, 0, 0, 9),
            row(3, 0, 0, 5),
        ]
    )
    scored = score_indices(expected, actual)
    assert scored["counts"] == {
        "expected": 3,
        "detected": 3,
        "matched_tp": 1,
        "missed_fn": 1,
        "skip_mismatch": 1,
        "unexpected_fp": 1,
    }
    assert scored["matched"] == [{"key": [0, 0, 0], "skip": 2}]
    assert scored["missed"] == [{"key": [2, 1, 3], "expected_skip": 6}]
    assert scored["skip_mismatch"][0]["key"] == [1, 0, 0]
    assert scored["unexpected"][0]["key"] == [3, 0, 0]


def test_duplicate_actual_keys_are_rejected():
    with pytest.raises(RuntimeError, match="Duplicate full68 override key"):
        actual_override_index([row(0, 0, 0, 2), row(0, 0, 0, 3)])


def test_page_exact_requires_all_expected_values_and_no_extra_detection():
    expected = {(24, 0, 0): 4, (24, 1, 2): 6}
    exact = actual_override_index([row(24, 0, 0, 4), row(24, 1, 2, 6)])
    assert page_exact(page_index=24, expected=expected, actual=exact)
    assert page_exact(page_index=24, expected=expected, actual=exact, expected_count=2)
    assert not page_exact(page_index=24, expected=expected, actual=exact, expected_count=1)

    with_extra = actual_override_index(
        [row(24, 0, 0, 4), row(24, 1, 2, 6), row(24, 9, 9, 2)]
    )
    assert not page_exact(page_index=24, expected=expected, actual=with_extra)

    wrong = actual_override_index([row(24, 0, 0, 5), row(24, 1, 2, 6)])
    assert not page_exact(page_index=24, expected=expected, actual=wrong)


def test_zero_expected_pages_uses_full_68_domain():
    expected = {(0, 0, 0): 2, (67, 0, 0): 4}
    zero_pages = zero_expected_pages(expected)
    assert len(zero_pages) == 66
    assert 0 not in zero_pages
    assert 67 not in zero_pages
    assert 1 in zero_pages
