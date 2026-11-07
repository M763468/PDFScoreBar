"""Inherited GIT_DIR/GIT_WORK_TREE must not redirect temporary-repository writes (#513)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Each writes to a repository it creates under tmp_path (`git init`, `config user.*`, `add -f -A`,
# `commit`); under an inherited mapping those writes used to land in the mapped worktree.
TEMPORARY_REPOSITORY_TESTS = (
    "tests/test_distribution_surface.py"
    "::test_launcher_accepts_ignored_output_only_in_development_checkout",
    "tests/test_distribution_surface.py"
    "::test_candidate_gitignore_keeps_supported_help_command_checkout_clean",
    "tests/test_release_candidate.py"
    "::test_candidate_rejects_additional_commit_even_when_tree_matches",
    "tests/test_doc_translations.py"
    "::TranslationChecks::test_unrelated_commit_does_not_invalidate_source",
)


def test_temporary_repository_fixtures_ignore_inherited_repository_env(mapped_worktree, tmp_path):
    env, state = mapped_worktree
    before = state()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            f"--basetemp={tmp_path / 'nested'}",
            *TEMPORARY_REPOSITORY_TESTS,
        ],
        cwd=ROOT,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert state() == before
