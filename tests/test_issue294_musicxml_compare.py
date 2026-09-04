from pathlib import Path

from tools.issue294.compare_musicxml_ab import compare_musicxml


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_issue294_musicxml_canonicalization_ignores_attribute_order_and_space(
    tmp_path: Path,
) -> None:
    left = tmp_path / "A.musicxml"
    right = tmp_path / "B.musicxml"
    _write(
        left,
        '<score-partwise version="4.0"><part id="P1"><measure number="1"><note><rest/></note></measure></part></score-partwise>',
    )
    _write(
        right,
        '<score-partwise version="4.0">\n  <part id="P1"><measure number="1"><note> <rest /> </note></measure></part>\n</score-partwise>',
    )

    result = compare_musicxml(left, right)

    assert result["raw_equal"] is False
    assert result["canonical_equal"] is True
    assert result["structural_counts_equal"] is True
    assert result["A_pinned"]["structural_counts"]["measure"] == 1
    assert result["A_pinned"]["structural_counts"]["note"] == 1
    assert result["A_pinned"]["structural_counts"]["rest"] == 1


def test_issue294_musicxml_structural_drift_is_reported(tmp_path: Path) -> None:
    left = tmp_path / "A.musicxml"
    right = tmp_path / "B.musicxml"
    _write(
        left,
        '<score-partwise><part id="P1"><measure number="1"><note><rest/></note></measure></part></score-partwise>',
    )
    _write(
        right,
        '<score-partwise><part id="P1"><measure number="1"><note><rest/></note><note><rest/></note></measure></part></score-partwise>',
    )

    result = compare_musicxml(left, right)

    assert result["canonical_equal"] is False
    assert result["structural_counts_equal"] is False
    assert result["B_maintained"]["structural_counts"]["note"] == 2
    assert result["B_maintained"]["structural_counts"]["rest"] == 2
    assert result["all_element_count_delta"] == 2
