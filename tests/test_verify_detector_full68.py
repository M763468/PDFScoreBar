from pathlib import Path

import pytest

from tools.verification import verify_detector_full68 as verify


def _images() -> list[Path]:
    return [
        Path("/workspace/data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png"),
        Path("/workspace/data/evaluation2/images/Shostakovich-Sym5-Va/page_014.png"),
        Path("/workspace/data/evaluation2/images/Shostakovich-Sym5-Va/page_015.png"),
    ]


def test_focused_stage_e_contract_is_exact_reconstruction_target() -> None:
    assert verify.FOCUSED_STAGE_E_PAGES == (
        "Va_Prokofiev_Symphony1/page_004",
        "Shostakovich-Sym5-Va/page_014",
    )
    assert verify.FOCUSED_STAGE_E_EXPECTED == {
        "gt": 174,
        "pred": 174,
        "tp": 174,
        "fp": 0,
        "fn": 0,
        "fn_det": 0,
        "fn_cnn": 0,
    }


def test_select_images_accepts_explicit_canonical_pages() -> None:
    images = _images()

    selected = verify._select_images(
        images,
        pages=[
            "Shostakovich-Sym5-Va/page_014",
            "Va_Prokofiev_Symphony1/page_004",
        ],
        page_limit=None,
    )

    assert selected == [images[1], images[0]]


def test_select_images_rejects_unknown_page() -> None:
    with pytest.raises(ValueError, match="not in the canonical evaluation2 manifest"):
        verify._select_images(
            _images(),
            pages=["Va_Prokofiev_Symphony1/page_999"],
            page_limit=None,
        )


def test_select_images_rejects_duplicate_page() -> None:
    selector = "Va_Prokofiev_Symphony1/page_004"
    with pytest.raises(ValueError, match="Duplicate --page selector"):
        verify._select_images(
            _images(),
            pages=[selector, selector],
            page_limit=None,
        )


def test_select_images_rejects_page_and_limit_together() -> None:
    with pytest.raises(ValueError, match="cannot be used together"):
        verify._select_images(
            _images(),
            pages=["Va_Prokofiev_Symphony1/page_004"],
            page_limit=1,
        )


def test_metric_mismatches_reports_only_drifted_fields() -> None:
    summary = dict(verify.FOCUSED_STAGE_E_EXPECTED)
    summary["fp"] = 1

    assert verify._metric_mismatches(summary, verify.FOCUSED_STAGE_E_EXPECTED) == {
        "fp": {"expected": 0, "actual": 1}
    }


def test_partial_evaluation_args_allow_missing_manifest_pages(tmp_path: Path) -> None:
    args = verify._evaluation_args(
        results_dir=tmp_path / "results",
        gt_root=tmp_path / "gt",
        output_dir=tmp_path / "eval",
        score_threshold=0.1,
        allow_partial=True,
    )

    assert args.allow_partial is True
    assert args.score_threshold == 0.1
    assert args.xdist_threshold == 12.0
