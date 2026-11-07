import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _strip_inherited_repository_env() -> None:
    """Keep every test's Git subprocess bound to the repository named by its own path.

    Inherited GIT_DIR/GIT_WORK_TREE (a container mapping, a Git hook) outrank `git -C`, so a
    fixture that runs `git init`/`commit` in tmp_path would write into the checkout under test
    (#513). Run Git-dependent suites from a checkout whose `.git` resolves directly instead; see
    docs/dev/LOCAL_VALIDATION.md.
    """
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR"):
        os.environ.pop(name, None)
    try:
        listed = subprocess.run(
            ["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True
        ).stdout.split()
    except OSError:  # Git-free runners have nothing to redirect.
        listed = []
    for name in listed:
        os.environ.pop(name, None)


_strip_inherited_repository_env()


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def mapped_worktree(tmp_path):
    """A manager checkout with a dirty linked worktree, plus the env that maps to it."""
    real, worktree = tmp_path / "real", tmp_path / "wt"
    real.mkdir()
    _git(real, "init", "-q", "-b", "main")
    (real / ".gitignore").write_text("*.pyc\n")
    _git(real, "add", ".gitignore")
    _git(
        real,
        "-c",
        "user.name=Real",
        "-c",
        "user.email=real@example.invalid",
        "commit",
        "-qm",
        "base",
    )
    _git(real, "worktree", "add", "-q", str(worktree), "-b", "topic")
    (worktree / "untracked_note.txt").write_text("untracked\n")
    (worktree / "ignored_cache.pyc").write_text("ignored\n")
    env = {
        "GIT_DIR": _git(worktree, "rev-parse", "--path-format=absolute", "--git-dir"),
        "GIT_WORK_TREE": str(worktree),
    }

    def state():
        return (
            _git(real, "rev-parse", "main", "topic"),
            (real / ".git/config").read_bytes(),
            _git(worktree, "status", "--porcelain", "--untracked-files=all", "--ignored"),
            _git(real, "rev-parse", "--show-toplevel"),
        )

    return env, state
