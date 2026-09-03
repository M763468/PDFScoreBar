from __future__ import annotations

import json

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
