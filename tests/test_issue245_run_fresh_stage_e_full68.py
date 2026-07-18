from pathlib import Path

import pytest

from tools.issue245 import run_fresh_stage_e_full68 as runner


def test_selected_scores_preserves_canonical_order_and_rejects_unknown() -> None:
    requested = ["Va_Prokofiev_Symphony1", "Shostakovich-Sym5-Va"]

    assert runner.selected_scores(requested) == [
        "Shostakovich-Sym5-Va",
        "Va_Prokofiev_Symphony1",
    ]
    with pytest.raises(ValueError, match="Unknown canonical score"):
        runner.selected_scores(["not-a-score"])


def test_score_images_requires_only_the_canonical_pages(tmp_path: Path) -> None:
    score = "Va_Prokofiev_Symphony1"
    score_dir = tmp_path / score
    score_dir.mkdir()
    for page in runner.SCORES[score]:
        (score_dir / f"{page}.png").write_bytes(b"png")
    (score_dir / "page_999.png").write_bytes(b"not canonical")

    assert runner.score_images(tmp_path, score) == [
        score_dir / f"{page}.png" for page in runner.SCORES[score]
    ]
