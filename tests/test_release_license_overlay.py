"""Main-only license overlay on the develop extraction (#505, #550).

develop never carries the license material. A sealed overlay adds/modifies only the paths the
develop manifest policy names, and later promotions must keep it without overwriting newer
develop changes. The license texts below are synthetic placeholders, not license grants.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.materialize_distribution import PROVENANCE, canonical_json, check_tree
from tools.release_candidate import (
    OVERLAY_FILES,
    OVERLAY_SPEC,
    check_candidate,
    create_candidate,
    derive_overlay,
)

TOOLS = Path(__file__).resolve().parents[1] / "tools"
README = "# Distribution\n\nInstall with Docker.\n\nRun the browser application.\n"
PYPROJECT = '[project]\nname = "example"\nversion = "0.1.0"\nreadme = "README.md"\n'
LICENSE_SECTION = "\n## Placeholder terms\n\nSee [LICENSE](LICENSE) and [NOTICE](NOTICE).\n"


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def commit(root, message):
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


def manifest(extra_selected=()):
    runtime = [
        {"pattern": "README.md", "role": "user guide"},
        {"pattern": "pyproject.toml", "role": "package"},
        {"pattern": "src/runtime.py", "role": "production"},
    ]
    runtime += [{"pattern": path, "role": "extra"} for path in extra_selected]
    return {
        "schema_version": 3,
        "runtime_bundle_patterns": runtime,
        "distribution_support_patterns": [],
        "distribution_metadata_patterns": [
            {"pattern": "docs/MINIMAL_MAINLINE_SURFACE.json", "role": "manifest"}
        ],
        "source_excluded": {"src/developer.py": "development only"},
        "runtime_optional_source_imports": {},
        "main_license_overlay_policy": {
            "description": "test policy",
            "additions": [
                {"pattern": "LICENSE", "role": "license", "required": True},
                {"pattern": "NOTICE", "role": "notice", "required": True},
                {"pattern": "LICENSES/Example.txt", "role": "optional text"},
            ],
            "modifications": [
                {"pattern": "README.md", "role": "license section"},
                {"pattern": "pyproject.toml", "role": "license expression"},
            ],
        },
    }


def write_manifest(root, data):
    (root / "docs/MINIMAL_MAINLINE_SURFACE.json").write_text(json.dumps(data, indent=2) + "\n")


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    git(root, "init", "-q", "-b", "develop")
    git(root, "config", "user.name", "Release tests")
    git(root, "config", "user.email", "release-tests@example.invalid")
    (root / "old-main.txt").write_text("must not carry into the release\n")
    main = commit(root, "old main without license")
    for directory in ("docs", "src", "tools"):
        (root / directory).mkdir()
    (root / "README.md").write_text(README)
    (root / "pyproject.toml").write_text(PYPROJECT)
    (root / "src/runtime.py").write_text("print('released')\n")
    (root / "src/runtime.py").chmod(0o755)
    (root / "src/developer.py").write_text("print('develop only')\n")
    for name in ("release_candidate.py", "materialize_distribution.py"):
        shutil.copyfile(TOOLS / name, root / "tools" / name)
    write_manifest(root, manifest())
    source = commit(root, "develop source")
    # Private license commit on the frozen source; never part of develop.
    git(root, "checkout", "-q", "-b", "private-license")
    (root / "LICENSE").write_text("Placeholder main-only license text v1\n")
    (root / "NOTICE").write_text("Placeholder notice v1\n")
    (root / "LICENSES").mkdir()
    (root / "LICENSES/Example.txt").write_text("Placeholder SPDX text\n")
    (root / "LICENSES/DevelopOnly.txt").write_text("outside the overlay policy\n")
    (root / "README.md").write_text(README + LICENSE_SECTION)
    (root / "pyproject.toml").write_text(PYPROJECT + 'license = "Placeholder"\n')
    data = manifest()
    data["distribution_metadata_patterns"].append({"pattern": "LICENSE", "role": "edit"})
    write_manifest(root, data)  # the license commit's own manifest edit must not be applied
    license_commit = commit(root, "private license")
    git(root, "checkout", "-q", "develop")
    return {"root": root, "main": main, "source": source, "license": license_commit}


def derive(repo, destination, base, license_commit, source, overlay_id="test-overlay"):
    return derive_overlay(repo["root"], destination, base, license_commit, source, overlay_id)


def first_release(repo, tmp_path, name="first"):
    overlay = tmp_path / f"{name}-overlay"
    derived = derive(repo, overlay, repo["source"], repo["license"], repo["source"])
    candidate = tmp_path / name
    report = create_candidate(
        repo["root"], candidate, repo["source"], repo["main"], f"release/{name}-rc1", overlay
    )
    return overlay, candidate, report, derived


def promote(repo, candidate):
    """Simulate the merged promotion: the candidate commit becomes the next main parent."""
    git(repo["root"], "fetch", "-q", str(candidate), "HEAD")
    return git(repo["root"], "rev-parse", "FETCH_HEAD")


def develop_change(repo, edits):
    root = repo["root"]
    for path, text in edits.items():
        (root / path).write_text(text)
    return commit(root, "newer develop change")


def blob(root, commit_id, path):
    return subprocess.check_output(["git", "-C", str(root), "show", f"{commit_id}:{path}"])


def rewrite_spec(overlay, change):
    spec = json.loads((overlay / OVERLAY_SPEC).read_text())
    change(spec)
    (overlay / OVERLAY_SPEC).write_bytes(canonical_json(spec))


def test_first_application_is_develop_extraction_plus_sealed_overlay(repo, tmp_path):
    overlay, candidate, report, derived = first_release(repo, tmp_path)
    root = repo["root"]
    assert derived["added"] == ["LICENSE", "LICENSES/Example.txt", "NOTICE"]
    assert derived["modified"] == ["README.md", "pyproject.toml"]
    # The license commit's manifest edit and unapproved license file are reported, not applied.
    assert derived["license_commit_changes_not_applied"] == [
        "LICENSES/DevelopOnly.txt",
        "docs/MINIMAL_MAINLINE_SURFACE.json",
    ]
    files = {
        "LICENSE",
        "LICENSES/Example.txt",
        "NOTICE",
        "README.md",
        "docs/MINIMAL_MAINLINE_SURFACE.json",
        "pyproject.toml",
        "src/runtime.py",
    }
    assert set(git(candidate, "ls-files").splitlines()) == files | {PROVENANCE}
    # Every develop-selected file is byte-identical except the approved modifications.
    for path in ("docs/MINIMAL_MAINLINE_SURFACE.json", "src/runtime.py"):
        assert (candidate / path).read_bytes() == blob(root, repo["source"], path)
    assert (candidate / "README.md").read_bytes() == blob(root, repo["license"], "README.md")
    assert (candidate / "src/runtime.py").stat().st_mode & 0o111
    assert not (candidate / "LICENSE").stat().st_mode & 0o111
    assert not (candidate / "old-main.txt").exists()
    assert git(candidate, "show", "-s", "--format=%P", "HEAD") == repo["main"]
    provenance = json.loads((candidate / PROVENANCE).read_text())
    spec = json.loads((overlay / OVERLAY_SPEC).read_text())
    assert provenance["release"]["main_overlay"]["spec"] == spec
    assert spec["derived_from"] == {
        "base_commit": repo["source"],
        "license_commit": repo["license"],
        "source_commit": repo["source"],
    }
    readme = next(e for e in spec["entries"] if e["path"] == "README.md")
    assert readme["base_sha256"] == hashlib.sha256(README.encode()).hexdigest()
    assert report["license_overlay"]["develop_selected_files"] == 4
    assert "Main license overlay SHA-256" in git(candidate, "show", "-s", "--format=%B", "HEAD")
    # Reproducible, and checkable with or without the private overlay package.
    second = create_candidate(
        root, tmp_path / "again", repo["source"], repo["main"], "release/again-rc1", overlay
    )
    assert second == report
    assert check_candidate(root, candidate, repo["source"], repo["main"]) == report
    assert check_candidate(root, candidate, repo["source"], repo["main"], overlay) == report
    assert check_tree(candidate, git_checkout=True) == []
    assert git(root, "rev-parse", "HEAD") == repo["source"]
    assert not (root / "LICENSE").exists()


def test_without_license_on_main_the_former_extraction_is_unchanged(repo, tmp_path):
    report = create_candidate(
        repo["root"], tmp_path / "plain", repo["source"], repo["main"], "release/plain-rc1"
    )
    provenance = json.loads((tmp_path / "plain" / PROVENANCE).read_text())
    assert "main_overlay" not in provenance["release"]
    assert "license_overlay" not in report
    assert report["shipped_files"] == 4
    assert "overlay" not in git(tmp_path / "plain", "show", "-s", "--format=%B", "HEAD")


def test_next_promotion_keeps_license_and_newer_develop_changes(repo, tmp_path):
    _, first, _, _ = first_release(repo, tmp_path)
    main1 = promote(repo, first)
    newer_pyproject = PYPROJECT.replace('version = "0.1.0"', 'version = "0.2.0"')
    source2 = develop_change(
        repo, {"src/runtime.py": "print('newer develop')\n", "pyproject.toml": newer_pyproject}
    )
    # A promotion without the overlay would silently drop the license: refuse it.
    with pytest.raises(ValueError, match="main-only license material"):
        create_candidate(repo["root"], tmp_path / "lost", source2, main1, "release/lost-rc2")
    assert not (tmp_path / "lost").exists()
    # The old overlay was sealed against the older develop pyproject: refuse to overwrite it.
    with pytest.raises(ValueError, match="stale for pyproject.toml"):
        create_candidate(
            repo["root"],
            tmp_path / "stale",
            source2,
            main1,
            "release/stale-rc2",
            tmp_path / "first-overlay",
        )
    with pytest.raises(ValueError, match="use it as --base-commit"):
        derive(repo, tmp_path / "wrong-base", source2, main1, source2)
    overlay2 = tmp_path / "second-overlay"
    derived = derive(repo, overlay2, repo["source"], main1, source2, "test-overlay-2")
    assert derived["three_way_merged"] == ["pyproject.toml"]
    assert derived["license_commit_changes_not_applied"] == []
    report = create_candidate(
        repo["root"], tmp_path / "second", source2, main1, "release/second-rc2", overlay2
    )
    second = tmp_path / "second"
    assert git(second, "show", "-s", "--format=%P", "HEAD") == main1
    assert (second / "LICENSE").read_text() == "Placeholder main-only license text v1\n"
    assert (second / "src/runtime.py").read_text() == "print('newer develop')\n"
    assert (second / "pyproject.toml").read_text() == newer_pyproject + 'license = "Placeholder"\n'
    assert (second / "README.md").read_text() == README + LICENSE_SECTION
    assert check_candidate(repo["root"], second, source2, main1, overlay2) == report


def test_conflicting_develop_change_fails_closed_until_re_authored(repo, tmp_path):
    _, first, _, _ = first_release(repo, tmp_path)
    main1 = promote(repo, first)
    # Develop edits the README tail exactly where the license section was appended.
    source2 = develop_change(repo, {"README.md": README + "\n## Troubleshooting\n"})
    with pytest.raises(ValueError, match="conflict with newer develop changes in README.md"):
        derive(repo, tmp_path / "conflict", repo["source"], main1, source2)
    assert not (tmp_path / "conflict").exists()
    # Re-author privately on the new source, then derive from that license commit.
    root = repo["root"]
    git(root, "checkout", "-q", "-b", "private-license-2")
    git(root, "checkout", main1, "--", "LICENSE", "NOTICE", "LICENSES/Example.txt")
    (root / "NOTICE").write_text("Placeholder notice v2\n")
    (root / "README.md").write_text(README + "\n## Troubleshooting\n" + LICENSE_SECTION)
    (root / "pyproject.toml").write_text(PYPROJECT + 'license = "Placeholder"\n')
    license2 = commit(root, "re-authored private license")
    git(root, "checkout", "-q", "develop")
    overlay2 = tmp_path / "re-authored"
    derive(repo, overlay2, source2, license2, source2)
    create_candidate(root, tmp_path / "second", source2, main1, "release/second-rc2", overlay2)
    second = tmp_path / "second"
    assert (second / "NOTICE").read_text() == "Placeholder notice v2\n"
    assert "## Troubleshooting" in (second / "README.md").read_text()
    assert "## Placeholder terms" in (second / "README.md").read_text()


@pytest.mark.parametrize("kind", ["required", "previous"])
def test_overlay_cannot_drop_license_material(repo, tmp_path, kind):
    overlay, first, _, _ = first_release(repo, tmp_path)
    parent = repo["main"]
    dropped = "NOTICE" if kind == "required" else "LICENSES/Example.txt"
    if kind == "previous":
        parent = promote(repo, first)
    rewrite_spec(
        overlay, lambda s: s.update(entries=[e for e in s["entries"] if e["path"] != dropped])
    )
    (overlay / OVERLAY_FILES / dropped).unlink()
    match = "omits required" if kind == "required" else "would drop main-only license"
    with pytest.raises(ValueError, match=match):
        create_candidate(
            repo["root"], tmp_path / "dropped", repo["source"], parent, "release/drop-rc1", overlay
        )


def test_main_license_without_overlay_record_still_blocks_plain_promotion(repo, tmp_path):
    root = repo["root"]
    git(root, "checkout", "-q", "-b", "hand-licensed-main", repo["main"])
    (root / "LICENSE").write_text("Placeholder license added directly on main\n")
    hand_main = commit(root, "license added on main by hand")
    git(root, "checkout", "-q", "develop")
    with pytest.raises(ValueError, match=r"main-only license material \['LICENSE'\]"):
        create_candidate(root, tmp_path / "plain", repo["source"], hand_main, "release/plain-rc2")


@pytest.mark.parametrize(
    "kind", ["unapproved-add", "manifest", "mode-field", "tampered", "extra", "non-canonical"]
)
def test_overlay_package_must_match_policy_and_seal(repo, tmp_path, kind):
    overlay = tmp_path / "overlay"
    derive(repo, overlay, repo["source"], repo["license"], repo["source"])
    if kind in {"unapproved-add", "manifest"}:
        path = "src/extra.py" if kind == "unapproved-add" else "docs/MINIMAL_MAINLINE_SURFACE.json"
        value = b"print('unreviewed')\n"
        (overlay / OVERLAY_FILES / path).parent.mkdir(parents=True, exist_ok=True)
        (overlay / OVERLAY_FILES / path).write_bytes(value)
        entry = {"path": path, "operation": "add", "sha256": hashlib.sha256(value).hexdigest()}
        if kind == "manifest":
            entry |= {"operation": "modify", "base_sha256": "0" * 64}
        rewrite_spec(
            overlay,
            lambda s: s.update(entries=sorted([*s["entries"], entry], key=lambda e: e["path"])),
        )
        match = "outside the approved policy"
    elif kind == "mode-field":
        rewrite_spec(overlay, lambda s: s["entries"][0].update(mode="100755"))
        match = "Invalid main license overlay entry"
    elif kind == "tampered":
        (overlay / OVERLAY_FILES / "LICENSE").write_text("edited after sealing\n")
        match = "content hash mismatch"
    elif kind == "extra":
        (overlay / OVERLAY_FILES / "src").mkdir()
        (overlay / OVERLAY_FILES / "src/unlisted.py").write_text("print('x')\n")
        match = "Unexpected license overlay files"
    else:
        (overlay / OVERLAY_SPEC).write_text((overlay / OVERLAY_SPEC).read_text() + "\n")
        match = "canonical JSON"
    with pytest.raises(ValueError, match=match):
        create_candidate(
            repo["root"], tmp_path / "bad", repo["source"], repo["main"], "release/bad-rc1", overlay
        )
    assert not (tmp_path / "bad").exists()


def test_develop_must_not_start_selecting_a_main_only_license_path(repo, tmp_path):
    root = repo["root"]
    (root / "NOTICE").write_text("develop started shipping this\n")
    write_manifest(root, manifest(extra_selected=["NOTICE"]))
    source2 = commit(root, "develop selects NOTICE")
    with pytest.raises(ValueError, match="Invalid main license overlay addition"):
        derive(repo, tmp_path / "overlay", repo["source"], repo["license"], source2)


@pytest.mark.parametrize("kind", ["license-edit", "license-removed", "forged-overlay"])
def test_candidate_check_rejects_overlay_tampering(repo, tmp_path, kind):
    overlay, candidate, _, _ = first_release(repo, tmp_path)
    root = repo["root"]
    git(candidate, "config", "user.name", "Forgery test")
    git(candidate, "config", "user.email", "forgery@example.invalid")
    if kind == "license-edit":
        (candidate / "LICENSE").write_text("changed in the working tree\n")
    elif kind == "license-removed":
        git(candidate, "rm", "-q", "LICENSE")
        git(candidate, "commit", "-qm", "drop license")
    else:
        # Re-seal different license text consistently inside the candidate itself.
        value = b"forged license text\n"
        (candidate / "LICENSE").write_bytes(value)
        provenance = json.loads((candidate / PROVENANCE).read_text())
        record = provenance["release"]["main_overlay"]
        next(e for e in record["spec"]["entries"] if e["path"] == "LICENSE")["sha256"] = (
            hashlib.sha256(value).hexdigest()
        )
        record["spec_sha256"] = hashlib.sha256(canonical_json(record["spec"])).hexdigest()
        provenance["files"]["LICENSE"] = hashlib.sha256(value).hexdigest()
        (candidate / PROVENANCE).write_text(json.dumps(provenance, indent=2) + "\n")
        git(candidate, "commit", "-qam", "forge overlay")
        # Bound to the approved overlay, the forgery is rejected.
        with pytest.raises(ValueError, match="provenance differs"):
            check_candidate(root, candidate, repo["source"], repo["main"], overlay)
        return
    with pytest.raises(ValueError):
        check_candidate(root, candidate, repo["source"], repo["main"])


def test_cli_derive_create_check_round_trip(repo, tmp_path):
    script = str(TOOLS / "release_candidate.py")
    base = [sys.executable, script, "--repository", str(repo["root"])]

    def run(*args):
        result = subprocess.run([*base, *args], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    overlay = tmp_path / "overlay"
    run(
        "derive-overlay",
        str(overlay),
        "--base-commit",
        repo["source"],
        "--license-commit",
        repo["license"],
        "--source-commit",
        repo["source"],
        "--overlay-id",
        "cli-overlay",
    )
    common = ["--source-commit", repo["source"], "--main-commit", repo["main"]]
    created = run(
        "create",
        str(tmp_path / "candidate"),
        *common,
        "--branch",
        "release/cli-rc1",
        "--license-overlay",
        str(overlay),
    )
    assert (
        run("check", str(tmp_path / "candidate"), *common, "--license-overlay", str(overlay))
        == created
    )
    assert created["license_overlay"]["overlay_id"] == "cli-overlay"
