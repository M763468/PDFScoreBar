from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.issue294 import run_downstream_candidate_matrix_host as host


def _capture_for(values: dict[tuple[str, ...], str]):
    def capture(command: list[str], *, cwd=None) -> str:
        key = tuple(command)
        if key not in values:
            raise AssertionError(f"Unexpected command: {command}")
        return values[key]

    return capture


def test_issue294_downstream_checkout_allows_develop_to_advance(monkeypatch) -> None:
    advanced_develop = "c7fc1e3da42caf304be0098c529c1cf7da01176c"
    branch_head = "1904c3cc052d66e6ceb49b516f80e30925538415"
    values = {
        ("git", "status", "--porcelain"): "",
        ("git", "branch", "--show-current"): host.ISSUE294_BRANCH,
        ("git", "rev-parse", "HEAD"): branch_head,
        ("git", "rev-parse", "develop"): advanced_develop,
        ("git", "merge-base", host.ISSUE294_BASE_COMMIT, "develop"): host.ISSUE294_BASE_COMMIT,
        ("git", "merge-base", "HEAD", "develop"): host.ISSUE294_BASE_COMMIT,
    }
    monkeypatch.setattr(host.base, "capture", _capture_for(values))

    checkout = host._require_issue294_checkout()

    assert checkout == {
        "branch": host.ISSUE294_BRANCH,
        "head": branch_head,
        "base_commit": host.ISSUE294_BASE_COMMIT,
        "develop_head": advanced_develop,
    }


def test_issue294_downstream_checkout_names_required_branch(monkeypatch) -> None:
    values = {
        ("git", "status", "--porcelain"): "",
        ("git", "branch", "--show-current"): "develop",
    }
    monkeypatch.setattr(host.base, "capture", _capture_for(values))

    with pytest.raises(RuntimeError, match=f"git switch {host.ISSUE294_BRANCH}"):
        host._require_issue294_checkout()


def test_issue294_upstream_cache_uses_ignored_temp_tree() -> None:
    assert host.HOMR_CACHE_ROOT == host.PROJECT_ROOT / "temp/issue294_upstream_homr"


def test_issue294_explicit_latest_commit_stays_immutable(monkeypatch) -> None:
    commit = "457e7c6518a10ba755db2e60883419e56c4d7369"
    monkeypatch.setattr(
        host,
        "_latest_main_commit",
        lambda: (_ for _ in ()).throw(AssertionError("floating main must not be resolved")),
    )

    assert host._resolve_latest_commit(commit) == commit


def test_issue294_rejects_invalid_explicit_latest_commit() -> None:
    with pytest.raises(ValueError, match="Invalid immutable HOMR commit"):
        host._resolve_latest_commit("main")


def test_issue294_downstream_reuses_completed_same_original_run(tmp_path, monkeypatch) -> None:
    run_tag = "resume"
    run_root = tmp_path / "logs/issue294" / run_tag
    run_root.mkdir(parents=True)
    summary = run_root / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "status": "completed",
                "pages": [
                    {
                        "image": "/workspace/data/evaluation2/images/Shostakovich-Sym5-Va/page_013.png"
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    container_checks: list[bool] = []
    monkeypatch.setattr(host, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(host.base, "require_container", lambda: container_checks.append(True))
    monkeypatch.setattr(
        host.historical,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("A/B must not rerun")),
    )

    resolved, reused = host._resolve_same_original_summary(
        run_tag,
        ["013"],
        {"head": "unused"},
    )

    assert resolved == summary.resolve()
    assert reused is True
    assert container_checks == [True]


def test_issue294_detector_preflight_uses_source_first_pythonpath(tmp_path, monkeypatch) -> None:
    source = tmp_path / "temp/issue294_upstream_homr" / host.B_COMMIT
    source.mkdir(parents=True)
    monkeypatch.setattr(host, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(host.base, "container_path", lambda _path: Path("/workspace/temp/candidate"))
    observed: list[list[str]] = []

    payload = {
        "status": "completed",
        "homr_commit": host.B_COMMIT,
        "optional_modules_imported": [],
    }

    def fake_run(command, **kwargs):
        observed.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload) + "\n", stderr="")

    monkeypatch.setattr(host.subprocess, "run", fake_run)

    result = host._run_detector_preflight("B", source, host.B_COMMIT)

    assert result == payload
    assert "PYTHONPATH=/workspace/temp/candidate:/workspace" in observed[0]
    assert "--preflight-only" in observed[0]


def test_issue294_detector_preflight_rejects_optional_application_imports(
    tmp_path, monkeypatch
) -> None:
    source = tmp_path / "candidate"
    source.mkdir()
    monkeypatch.setattr(host, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(host.base, "container_path", lambda _path: Path("/workspace/candidate"))
    payload = {
        "status": "completed",
        "homr_commit": host.B_COMMIT,
        "optional_modules_imported": ["homr.pdf_utils"],
    }
    monkeypatch.setattr(
        host.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(payload) + "\n",
            stderr="",
        ),
    )

    with pytest.raises(RuntimeError, match="excluded optional HOMR modules"):
        host._run_detector_preflight("B", source, host.B_COMMIT)


def test_issue294_downstream_discards_only_incomplete_matrix_tree(tmp_path) -> None:
    matrix_root = tmp_path / "downstream_candidate_matrix"
    partial = matrix_root / "01_page_013" / "B_b377_material.log"
    partial.parent.mkdir(parents=True)
    partial.write_text("failed", encoding="utf-8")

    report, reused = host._prepare_matrix_output(matrix_root)

    assert report == matrix_root / "report.json"
    assert reused is False
    assert not matrix_root.exists()


def test_issue294_downstream_reuses_completed_matrix_tree(tmp_path) -> None:
    matrix_root = tmp_path / "downstream_candidate_matrix"
    matrix_root.mkdir(parents=True)
    report = matrix_root / "report.json"
    report.write_text(json.dumps({"status": "completed"}), encoding="utf-8")

    resolved_report, reused = host._prepare_matrix_output(matrix_root)

    assert resolved_report == report
    assert reused is True
    assert matrix_root.is_dir()
