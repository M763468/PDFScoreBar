from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.materialize_distribution import PROVENANCE, check_tree
from tools.release_candidate import check_candidate, create_candidate


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def commit(root, message):
    git(root, "add", ".")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Release tests")
    git(root, "config", "user.email", "release-tests@example.invalid")
    (root / "old-main.txt").write_text("must not carry into the release\n")
    parent = commit(root, "old main")
    (root / "docs").mkdir()
    (root / "src").mkdir()
    (root / "README.md").write_text("# Distribution\n")
    (root / "src/runtime.py").write_text("print('released')\n")
    (root / "src/runtime.py").chmod(0o755)
    (root / "src/developer.py").write_text("print('develop only')\n")
    manifest = {
        "schema_version": 3,
        "runtime_bundle_patterns": [
            {"pattern": "README.md", "role": "user guide"},
            {"pattern": "src/runtime.py", "role": "production"},
        ],
        "distribution_support_patterns": [],
        "distribution_metadata_patterns": [
            {"pattern": "docs/MINIMAL_MAINLINE_SURFACE.json", "role": "manifest"}
        ],
        "source_excluded": {"src/developer.py": "development only"},
        "runtime_optional_source_imports": {},
    }
    (root / "docs/MINIMAL_MAINLINE_SURFACE.json").write_text(json.dumps(manifest))
    head = commit(root, "develop source")
    return root, head, parent


def create(source, destination, branch="release/test-rc1"):
    root, head, parent = source
    return create_candidate(root, destination, head, parent, branch)


def test_pinned_candidate_is_minimal_independent_and_reproducible(source, tmp_path):
    root, head, parent = source
    first, second = tmp_path / "first", tmp_path / "second"
    # A pinned extraction must consume committed blobs, never local WIP or extra files.
    (root / "README.md").write_text("uncommitted product change\n")
    (root / "secret-local.txt").write_text("not part of the source commit\n")
    first_report = create(source, first)
    second_report = create(source, second, "release/test-rc2")
    assert first_report == second_report
    assert first_report["static_checks"] == "PASS"
    assert first_report["release_accepted"] is False
    assert first_report["shipped_files"] == 3
    assert (first / "README.md").read_text() == "# Distribution\n"
    assert (first / "src/runtime.py").stat().st_mode & 0o111
    assert not (first / "old-main.txt").exists()
    assert not (first / "src/developer.py").exists()
    assert not (first / "secret-local.txt").exists()
    assert not (first / ".git/objects/info/alternates").exists()
    assert git(first, "show", "-s", "--format=%P", "HEAD") == parent
    assert git(root, "rev-parse", "HEAD") == head
    # Git metadata is ignored only at the explicit Git-checkout boundary.
    assert check_tree(first, git_checkout=True) == []
    assert any("Unexpected candidate files" in e for e in check_tree(first))
    assert check_candidate(root, first, head, parent) == first_report
    # Candidate objects and checked-out files remain usable without the source repository.
    relocated = tmp_path / "source-away"
    root.rename(relocated)
    assert git(first, "show", "HEAD:README.md") == "# Distribution"
    assert git(first, "cat-file", "-t", parent) == "commit"


@pytest.mark.parametrize("kind", ["missing", "tampered", "extra", "symlink-dir"])
def test_candidate_rejects_working_tree_corruption(source, tmp_path, kind):
    destination = tmp_path / "candidate"
    create(source, destination)
    if kind == "missing":
        (destination / "src/runtime.py").unlink()
    elif kind == "tampered":
        (destination / "README.md").write_text("changed\n")
    elif kind == "extra":
        (destination / "developer-only.json").write_text("{}")
    else:
        (destination / "hidden").symlink_to(source[0], target_is_directory=True)
    with pytest.raises(ValueError, match="Candidate check failed"):
        check_candidate(source[0], destination, source[1], source[2])


def test_candidate_rejects_forged_committed_content_and_provenance(source, tmp_path):
    destination = tmp_path / "candidate"
    create(source, destination)
    git(destination, "config", "user.name", "Forgery test")
    git(destination, "config", "user.email", "forgery@example.invalid")
    provenance = json.loads((destination / PROVENANCE).read_text())
    provenance["source_commit"] = source[2]
    (destination / PROVENANCE).write_text(json.dumps(provenance, indent=2) + "\n")
    commit(destination, "forge source identity")
    with pytest.raises(ValueError, match="provenance differs"):
        check_candidate(source[0], destination, source[1], source[2])


def test_candidate_rejects_additional_commit_even_when_tree_matches(source, tmp_path):
    destination = tmp_path / "candidate"
    create(source, destination)
    git(destination, "config", "user.name", "Parent test")
    git(destination, "config", "user.email", "parent@example.invalid")
    git(destination, "commit", "--allow-empty", "-qm", "unreviewed follow-up")
    with pytest.raises(ValueError, match="exactly the frozen main"):
        check_candidate(source[0], destination, source[1], source[2])


def test_candidate_rejects_changed_commit_metadata(source, tmp_path):
    destination = tmp_path / "candidate"
    create(source, destination)
    git(destination, "config", "user.name", "Metadata test")
    git(destination, "config", "user.email", "metadata@example.invalid")
    git(destination, "commit", "--amend", "--no-edit", "--reset-author", "--quiet")
    with pytest.raises(ValueError, match="deterministic identity"):
        check_candidate(source[0], destination, source[1], source[2])


def test_candidate_rejects_executable_bit_loss_even_when_git_ignores_modes(source, tmp_path):
    destination = tmp_path / "candidate"
    create(source, destination)
    git(destination, "config", "core.filemode", "false")
    (destination / "src/runtime.py").chmod(0o644)
    with pytest.raises(ValueError, match="working file mode mismatch"):
        check_candidate(source[0], destination, source[1], source[2])


def test_candidate_rejects_wrong_expected_source_and_parent(source, tmp_path):
    destination = tmp_path / "candidate"
    create(source, destination)
    root, head, parent = source
    with pytest.raises(ValueError):
        check_candidate(root, destination, parent, parent)
    with pytest.raises(ValueError, match="provenance differs"):
        check_candidate(root, destination, head, head)


@pytest.mark.parametrize("kind", ["missing", "symlink", "undeclared", "unknown-module"])
def test_source_dependencies_fail_before_candidate_creation(source, tmp_path, kind):
    root, _, parent = source
    if kind == "missing":
        (root / "README.md").unlink()
    elif kind == "symlink":
        (root / "README.md").unlink()
        (root / "README.md").symlink_to("old-main.txt")
    elif kind == "undeclared":
        (root / "src/runtime.py").write_text("from src import developer\n")
    else:
        (root / "src/runtime.py").write_text("import src.unlisted_dependency\n")
    head = commit(root, "invalid release source")
    destination = tmp_path / "candidate"
    with pytest.raises(ValueError, match="unsafe committed|Candidate check failed"):
        create_candidate(root, destination, head, parent, "release/invalid-rc1")
    assert not destination.exists()


def test_candidate_does_not_overwrite_existing_destination_or_accept_mutable_refs(source, tmp_path):
    destination = tmp_path / "candidate"
    create(source, destination)
    before = git(destination, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="already exists"):
        create(source, destination)
    assert git(destination, "rev-parse", "HEAD") == before
    with pytest.raises(ValueError, match="full, frozen"):
        create_candidate(source[0], tmp_path / "other", "HEAD", source[2], "release/test-rc1")
    with pytest.raises(ValueError, match="versioned under release/"):
        create(source, tmp_path / "main", "main")


def test_candidate_rejects_source_nested_destination(source):
    with pytest.raises(ValueError, match="outside the source"):
        create(source, source[0] / "candidate")


def test_cli_report_cannot_contaminate_candidate(source, tmp_path):
    result = subprocess.run(
        [
            "python3",
            str(Path(__file__).resolve().parents[1] / "tools/release_candidate.py"),
            "--repository",
            str(source[0]),
            "create",
            str(tmp_path / "candidate"),
            "--source-commit",
            source[1],
            "--main-commit",
            source[2],
            "--branch",
            "release/cli-rc1",
            "--report",
            str(tmp_path / "candidate/report.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "outside the exact candidate" in result.stderr
    assert not (tmp_path / "candidate").exists()
