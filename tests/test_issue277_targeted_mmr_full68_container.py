import pytest

from tools.issue277.run_targeted_mmr_full68_container import resolve_host_git_head


def test_resolve_host_git_head_accepts_and_normalizes_sha():
    assert resolve_host_git_head("A" * 40) == "a" * 40


def test_resolve_host_git_head_rejects_missing_or_invalid_values():
    with pytest.raises(RuntimeError, match="ISSUE277_GIT_HEAD"):
        resolve_host_git_head(None)
    with pytest.raises(RuntimeError, match="ISSUE277_GIT_HEAD"):
        resolve_host_git_head("not-a-sha")
