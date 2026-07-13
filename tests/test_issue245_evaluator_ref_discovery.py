from __future__ import annotations

import pytest

from tools.issue245.discover_pdfscore_evaluator_ref_candidates import (
    FIELD_SEPARATOR,
    group_distinct_snapshots,
    parse_commit_lines,
)


def test_parse_commit_lines() -> None:
    output = (
        f"abc{FIELD_SEPARATOR}2026-01-01T00:00:00+09:00"
        f"{FIELD_SEPARATOR}first\n"
        f"def{FIELD_SEPARATOR}2026-01-02T00:00:00+09:00"
        f"{FIELD_SEPARATOR}second"
    )

    records = parse_commit_lines(output)

    assert [record.sha for record in records] == ["abc", "def"]
    assert records[1].subject == "second"


def test_parse_commit_lines_rejects_invalid_record() -> None:
    with pytest.raises(ValueError, match="Unexpected git log record"):
        parse_commit_lines("not-a-valid-record")


def test_group_distinct_snapshots_uses_newest_equivalent_commit() -> None:
    snapshots = [
        {
            "commit": "a1",
            "committed_at": "2026-01-01T00:00:00+09:00",
            "subject": "first A",
            "source_signature": "sig-a",
            "source_blobs": [{"path": "file.py", "blob_oid": "blob-a"}],
        },
        {
            "commit": "a2",
            "committed_at": "2026-01-02T00:00:00+09:00",
            "subject": "second A",
            "source_signature": "sig-a",
            "source_blobs": [{"path": "file.py", "blob_oid": "blob-a"}],
        },
        {
            "commit": "b1",
            "committed_at": "2026-01-03T00:00:00+09:00",
            "subject": "B",
            "source_signature": "sig-b",
            "source_blobs": [{"path": "file.py", "blob_oid": "blob-b"}],
        },
    ]

    groups = group_distinct_snapshots(snapshots)

    assert [group["candidate_ref"] for group in groups] == ["b1", "a2"]
    assert [
        record["commit"] for record in groups[1]["equivalent_touching_commits"]
    ] == ["a1", "a2"]
