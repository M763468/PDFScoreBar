"""CI license fixture: PR candidates keep main's license material without per-PR re-authoring.

The fixture commit replays the promoted main's license material onto a PR source; the unchanged
release tool then derives, creates and checks the candidate (#505, #558, PR #560).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests import test_release_license_overlay as overlay_tests
from tests.test_release_license_overlay import (
    LICENSE_SECTION,
    PYPROJECT,
    README,
    commit,
    derive,
    develop_change,
    first_release,
    git,
    promote,
)
from tools.materialize_distribution import check_tree
from tools.release_candidate import check_candidate, create_candidate

HELPER = (
    Path(__file__).resolve().parents[1] / "tools" / "verification" / "ci_main_license_commit.py"
)
repo = overlay_tests.repo  # the shared source/main/private-license repository fixture
spec = importlib.util.spec_from_file_location("ci_main_license_commit", HELPER)
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


def ci_candidate(repo, tmp_path, source, main, name):
    fixture = ci.fixture_commit(repo["root"], source, main)
    overlay = tmp_path / f"{name}-overlay"
    license_commit = fixture["license_commit"]
    derive(repo, overlay, source, license_commit, source, "ci-main-license-fixture")
    candidate = tmp_path / name
    report = create_candidate(repo["root"], candidate, source, main, f"release/{name}", overlay)
    assert check_candidate(repo["root"], candidate, source, main, overlay) == report
    assert check_tree(candidate, git_checkout=True) == []
    return fixture, candidate, report


def test_conflicting_readme_pr_passes_ci_while_real_promotion_still_fails_closed(repo, tmp_path):
    _, first, _, _ = first_release(repo, tmp_path)
    main1 = promote(repo, first)
    root = repo["root"]
    source2 = develop_change(repo, {"README.md": README + "\n## Troubleshooting\n"})
    # The real promotion must still be re-authored: the strict derivation refuses the conflict.
    with pytest.raises(ValueError, match="conflict with newer develop changes in README.md"):
        derive(repo, tmp_path / "strict", repo["source"], main1, source2)
    # A plain promotion is still refused against the licensed main.
    with pytest.raises(ValueError, match="main-only license material"):
        create_candidate(root, tmp_path / "plain", source2, main1, "release/plain")
    fixture, candidate, report = ci_candidate(repo, tmp_path, source2, main1, "ci-a")
    assert fixture["main_overlay_source"] == repo["source"]
    assert fixture["copied"] == ["LICENSE", "LICENSES/Example.txt", "NOTICE"]
    assert fixture["modified"] == ["README.md", "pyproject.toml"]
    assert fixture["union_merged"] == ["README.md"]
    readme = (candidate / "README.md").read_text()
    assert "## Troubleshooting" in readme and "## Placeholder terms" in readme
    assert (candidate / "LICENSE").read_bytes() == subprocess.check_output(
        ["git", "-C", str(root), "show", f"{main1}:LICENSE"]
    )
    assert ci.verify_candidate(root, candidate, main1)["kept"] == fixture["copied"] + [
        "README.md",
        "pyproject.toml",
    ]
    # Deterministic: the fixture commit and the candidate identities reproduce exactly.
    again, _, report_b = ci_candidate(repo, tmp_path, source2, main1, "ci-b")
    assert again == fixture
    assert report_b == report
    # Only unreferenced objects are written: refs, index and working tree are untouched.
    assert git(root, "rev-parse", "HEAD") == source2 and git(root, "status", "--porcelain") == ""
    assert fixture["license_commit"] not in git(root, "for-each-ref", "--format=%(objectname)")


def test_non_conflicting_pr_matches_the_strict_promotion_overlay(repo, tmp_path):
    _, first, _, _ = first_release(repo, tmp_path)
    main1 = promote(repo, first)
    newer = PYPROJECT.replace('version = "0.1.0"', 'version = "0.2.0"')
    source2 = develop_change(repo, {"pyproject.toml": newer})
    strict = tmp_path / "strict"
    derive(repo, strict, repo["source"], main1, source2)
    fixture, candidate, _ = ci_candidate(repo, tmp_path, source2, main1, "ci")
    assert fixture["union_merged"] == []
    for path in ("LICENSE", "NOTICE", "LICENSES/Example.txt", "README.md", "pyproject.toml"):
        assert (candidate / path).read_bytes() == (strict / "files" / path).read_bytes()
    assert (candidate / "pyproject.toml").read_text() == newer + 'license = "Placeholder"\n'
    assert (candidate / "README.md").read_text() == README + LICENSE_SECTION


def test_unlicensed_main_needs_no_fixture(repo):
    fixture = ci.fixture_commit(repo["root"], repo["source"], repo["main"])
    assert fixture["main_license"] is False and fixture["license_commit"] is None


def test_main_license_without_overlay_record_fails_closed(repo):
    root = repo["root"]
    git(root, "checkout", "-q", "-b", "hand-licensed-main", repo["main"])
    (root / "LICENSE").write_text("Placeholder license added directly on main\n")
    hand_main = commit(root, "license added on main by hand")
    git(root, "checkout", "-q", "develop")
    with pytest.raises(ValueError, match="without a recorded overlay"):
        ci.fixture_commit(root, repo["source"], hand_main)


@pytest.mark.parametrize("kind", ["missing", "changed"])
def test_verify_rejects_candidate_that_lost_license_material(repo, tmp_path, kind):
    _, first, _, _ = first_release(repo, tmp_path)
    main1 = promote(repo, first)
    _, candidate, _ = ci_candidate(repo, tmp_path, repo["source"], main1, "ci")
    if kind == "missing":
        git(candidate, "rm", "-q", "NOTICE")
    else:
        (candidate / "NOTICE").write_text("altered\n")
        git(candidate, "add", "NOTICE")
    git(candidate, "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-qm", kind)
    with pytest.raises(ValueError, match=f"{kind}=\\['NOTICE'\\]"):
        ci.verify_candidate(repo["root"], candidate, main1)


def test_cli_commit_round_trip_and_mutable_ref_rejection(repo, tmp_path):
    _, first, _, _ = first_release(repo, tmp_path)
    main1 = promote(repo, first)
    report = tmp_path / "fixture.json"
    run = [sys.executable, str(HELPER), "--repository", str(repo["root"])]
    subprocess.run(
        [*run, "commit", "--source-commit", repo["source"], "--main-commit", main1,
         "--report", str(report)],
        check=True, capture_output=True,
    )  # fmt: skip
    fixture = json.loads(report.read_text())
    assert fixture == ci.fixture_commit(repo["root"], repo["source"], main1)
    failed = subprocess.run(
        [*run, "commit", "--source-commit", "develop", "--main-commit", main1],
        capture_output=True, text=True,
    )  # fmt: skip
    assert failed.returncode == 1 and "frozen 40-character" in failed.stderr
