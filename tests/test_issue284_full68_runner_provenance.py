import argparse

import pytest

from tools.issue284.run_full68_variant import (
    parse_source_commit,
    require_host_provenance,
    write_variant_summary,
)


def test_parse_source_commit_normalizes_full_sha() -> None:
    assert parse_source_commit("A" * 40) == "a" * 40


@pytest.mark.parametrize(
    "value",
    [
        "",
        "abc123",
        "g" * 40,
        "a" * 39,
        "a" * 41,
    ],
)
def test_parse_source_commit_rejects_invalid_sha(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_source_commit(value)


def test_host_provenance_requires_clean_verification() -> None:
    with pytest.raises(RuntimeError, match="host-verified clean checkout"):
        require_host_provenance(
            source_commit="a" * 40,
            clean_verified=False,
        )


def test_variant_summary_records_host_verified_provenance(tmp_path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    output = tmp_path / "output"
    output.mkdir()

    payload = write_variant_summary(
        output=output,
        label="control",
        root=root,
        config_sha="config-sha",
        source_commit="b" * 40,
        source_clean_verified=True,
        score_summaries=[],
    )

    assert payload["git_commit"] == "b" * 40
    assert payload["git_dirty"] is False
    assert payload["source_provenance"] == {
        "verification": "host",
        "git_commit": "b" * 40,
        "git_clean_verified": True,
    }
