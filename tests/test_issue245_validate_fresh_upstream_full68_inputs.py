import sys
from pathlib import Path

import pytest

from tools.issue245 import validate_fresh_upstream_full68_inputs as validator


def test_validator_accepts_expected_historical_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image = tmp_path / "data/evaluation2/images/score/page_001.png"
    detection = tmp_path / "historical.json"
    monkeypatch.setattr(validator, "discover_canonical_images", lambda _root: [image])
    monkeypatch.setattr(
        validator,
        "build_inventory",
        lambda *_args: [{"historical_detection": str(detection)}],
    )
    monkeypatch.setattr(
        validator,
        "load_records",
        lambda _path: [{}] * validator.EXPECTED_HISTORICAL_DETECTION_COUNT,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["validator", "--main-repo-root", str(tmp_path), "--expected-pages", "1"],
    )

    assert validator.main() == 0


def test_validator_rejects_wrong_historical_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image = tmp_path / "data/evaluation2/images/score/page_001.png"
    detection = tmp_path / "historical.json"
    monkeypatch.setattr(validator, "discover_canonical_images", lambda _root: [image])
    monkeypatch.setattr(
        validator,
        "build_inventory",
        lambda *_args: [{"historical_detection": str(detection)}],
    )
    monkeypatch.setattr(validator, "load_records", lambda _path: [{}])
    monkeypatch.setattr(
        sys,
        "argv",
        ["validator", "--main-repo-root", str(tmp_path), "--expected-pages", "1"],
    )

    with pytest.raises(RuntimeError, match="Retained baseline count mismatch"):
        validator.main()
