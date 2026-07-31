import copy

import pytest

from tools.issue255.normalize_untracked_only_batch import normalize_batch


def _batch(status: str = "?? graphify-out/") -> dict:
    contract = {
        "status": "completed",
        "detector_input_contract": {
            "mode": "fresh_upstream",
            "fresh_upstream_authoritative": True,
            "override_keys": [],
        },
        "detection_config_changed": False,
        "pipeline_steps_changed": False,
        "repository": {
            "commit": "abc123",
            "branch": "fix/issue255-fresh-detector-production-recovery",
            "status": status,
        },
        "artifacts": {
            "image": {"exists": True},
            "clef_mask": None,
            "final_barlines": {"exists": True},
        },
    }
    run = {
        "runner_exit_code": 0,
        "contract": contract,
        "errors": ["repository was dirty during run"],
    }
    return {
        "schema_version": "issue255.focused_fresh_batch.v1",
        "status": "failed",
        "expected_commit": "abc123",
        "expected_branch": "fix/issue255-fresh-detector-production-recovery",
        "runs": [copy.deepcopy(run), copy.deepcopy(run)],
        "errors": [
            "ScoreA/page_001: repository was dirty during run",
            "ScoreB/page_002: repository was dirty during run",
        ],
    }


def test_normalize_batch_accepts_only_explicitly_allowed_untracked_paths() -> None:
    result = normalize_batch(
        payload=_batch(),
        allowed_untracked_prefixes=["graphify-out/"],
    )

    assert result["status"] == "completed"
    assert result["errors"] == []
    assert result["provenance_adjustment"]["observed_untracked_paths"] == [
        "graphify-out/"
    ]
    assert all(run["errors"] == [] for run in result["runs"])


def test_normalize_batch_rejects_tracked_changes() -> None:
    with pytest.raises(ValueError, match="tracked change"):
        normalize_batch(
            payload=_batch(" M configs/dense_full_pipeline.yaml"),
            allowed_untracked_prefixes=["graphify-out/"],
        )


def test_normalize_batch_rejects_other_untracked_paths() -> None:
    with pytest.raises(ValueError, match="disallowed untracked paths"):
        normalize_batch(
            payload=_batch("?? graphify-out/\n?? unexpected.py"),
            allowed_untracked_prefixes=["graphify-out/"],
        )


def test_normalize_batch_rejects_non_dirty_batch_errors() -> None:
    payload = _batch()
    payload["errors"].append("ScoreA/page_001: missing artifacts")

    with pytest.raises(ValueError, match="non-waivable error"):
        normalize_batch(
            payload=payload,
            allowed_untracked_prefixes=["graphify-out/"],
        )
