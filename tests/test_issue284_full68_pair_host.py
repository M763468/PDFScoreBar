import argparse

import pytest

from tools.issue284.run_full68_pair_host import (
    parse_windows_free_bytes,
    validate_run_tag,
)


def test_parse_windows_free_bytes() -> None:
    assert parse_windows_free_bytes("179218006016") == 179218006016


def test_parse_windows_free_bytes_uses_numeric_payload() -> None:
    assert parse_windows_free_bytes("FreeBytes=123456") == 123456


def test_parse_windows_free_bytes_rejects_missing_number() -> None:
    with pytest.raises(ValueError):
        parse_windows_free_bytes("missing")


@pytest.mark.parametrize(
    "value",
    [
        "issue284-full68-20260825",
        "control_candidate.v1",
        "fresh_01",
    ],
)
def test_validate_run_tag_accepts_safe_values(value: str) -> None:
    assert validate_run_tag(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "../escape",
        "has space",
        "semi;colon",
    ],
)
def test_validate_run_tag_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        validate_run_tag(value)
