from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.materialize_distribution import check_tree, materialize, selected_files

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def candidate(tmp_path):
    destination = tmp_path / "candidate"
    materialize(ROOT, destination)
    return destination


def test_isolated_candidate_and_user_app_assets(candidate):
    assert check_tree(candidate) == []
    assert not (candidate / ".git").exists()
    assert not (candidate / "data").exists()
    assert not (candidate / "tests").exists()
    assert not (candidate / "tools/gt_relabel_gui").exists()
    assert not (candidate / "tools/review_correction/acceptance.py").exists()
    assert not (candidate / "src/common/barline_evaluation.py").exists()
    result = subprocess.run(
        [
            "python3",
            "-I",
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "from src.common import Box, barline_iou; "
            "assert 'src.common.barline_evaluation' not in sys.modules; "
            "from src.pipeline.core import load_json, load_yaml, run_with_logging; "
            "from src.measure_numbering.types import BBox, score_to_dict; "
            "from src.pipeline.steps.numbering_phases import NumberingPhaseServices; "
            "assert BBox(0, 0, 2, 3).height == 3; "
            "assert not any(name in sys.modules for name in ('cv2', 'numpy', 'torch', 'homr'))",
            str(candidate),
        ],
        cwd=candidate,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "path", ["tools/review_correction/strings.js", "src/common/barline_geometry.py"]
)
def test_candidate_rejects_missing_dependency(candidate, path):
    (candidate / path).unlink()
    assert any(path in error for error in check_tree(candidate))


def test_candidate_rejects_corrupt_or_extra_content(candidate):
    (candidate / "README.md").write_text("modified")
    (candidate / "evaluation.json").write_text("{}")
    errors = check_tree(candidate)
    assert any("hash mismatch: README.md" in error for error in errors)
    assert any("Unexpected candidate files" in error for error in errors)


def test_materializer_rejects_existing_output_and_symlink(tmp_path):
    with pytest.raises(ValueError, match="already exists"):
        materialize(ROOT, tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    (source / "docs").mkdir()
    data = json.loads((ROOT / "docs/MINIMAL_MAINLINE_SURFACE.json").read_text())
    (source / "docs/MINIMAL_MAINLINE_SURFACE.json").write_text(json.dumps(data))
    (source / "Dockerfile").symlink_to(ROOT / "Dockerfile")
    with pytest.raises(ValueError, match="unsafe source"):
        materialize(source, tmp_path / "isolated")


@pytest.mark.parametrize("path", ["../secret", "/absolute", "src/**", "a/../b", "a//b"])
def test_manifest_rejects_non_exact_or_unsafe_paths(path):
    data = {
        k: []
        for k in (
            "runtime_bundle_patterns",
            "distribution_support_patterns",
            "distribution_metadata_patterns",
        )
    }
    data["runtime_bundle_patterns"] = [{"pattern": path, "role": "fixture"}]
    with pytest.raises(ValueError):
        selected_files(data)


def test_geometry_compatibility_exports_and_numerical_contract():
    from src.common import barline_evaluation, barline_geometry

    for name in ("expand_barline_box", "barline_iou", "barline_vertical_overlap"):
        assert getattr(barline_evaluation, name) is getattr(barline_geometry, name)
    assert barline_geometry.BARLINE_DEFAULT_MIN_WIDTH == 12
    assert barline_geometry.BARLINE_X_MARGIN == 3
    assert barline_geometry.BARLINE_Y_MARGIN == 3
    assert barline_geometry.expand_barline_box((10, 20, 11, 40)) == (1, 17, 19, 43)
    assert barline_geometry.expand_barline_box((11, 40, 10, 20)) == (1, 17, 19, 43)
    assert barline_geometry.barline_iou((10, 20, 11, 40), (12, 20, 13, 40)) == 0.8
    assert barline_geometry.barline_vertical_overlap((10, 20, 11, 40), (12, 30, 13, 50)) == 0.5
    with pytest.raises(ValueError, match="min_width"):
        barline_geometry.expand_barline_box((1, 2, 3, 4), min_width=0)


def test_release_launcher_uses_pinned_image_and_isolated_paths(tmp_path, monkeypatch):
    from docker import distribution

    image_id = "sha256:fixture"
    captures = []
    calls = []

    def capture(command):
        captures.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            return json.dumps(
                [
                    {
                        "Id": image_id,
                        "Config": {
                            "Labels": {
                                "pdfscore.runtime.asset_contract": "v1",
                                "pdfscore.runtime.source_fingerprint": "fixture-source",
                            }
                        },
                    }
                ]
            )
        return "runtime"

    monkeypatch.setattr(distribution, "capture", capture)
    monkeypatch.setattr(
        distribution,
        "source_identity",
        lambda: {"source_commit": "fixture", "source_branch": "release"},
    )
    monkeypatch.setattr(distribution, "runtime_fingerprint", lambda root: "runtime")
    monkeypatch.setattr(
        distribution, "resolve_model_artifact", lambda *a, **k: tmp_path / "weight.pt"
    )
    monkeypatch.setattr(
        distribution.subprocess, "call", lambda command, **kw: calls.append(command) or 0
    )
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF-")
    monkeypatch.setattr(
        "sys.argv",
        [
            "distribution.py",
            "--image",
            "release-tag",
            "run",
            str(pdf),
            "--output",
            str(tmp_path / "output"),
            "--pages",
            "1",
        ],
    )
    assert distribution.main() == 0
    assert captures[1][captures[1].index("--entrypoint") + 1] == "/opt/venv_pipeline/bin/python"
    assert image_id in calls[0] and image_id in calls[1]
    assert f"{tmp_path}:/input:ro" in calls[1]
    assert f"{(tmp_path / 'output').resolve()}:/results" in calls[1]
    assert "-m" in calls[1] and "docker.distribution_job" in calls[1]
    assert "--expected-fingerprint-value" in calls[0]


def test_local_review_bridge_preserves_original_and_rebinds_paths(tmp_path):
    import hashlib

    from docker.distribution_job import prepare_local_review

    package = tmp_path / "job-one"
    review = package / "review"
    review.mkdir(parents=True)
    handoff = review / "manual_correction_input.json"
    handoff.write_text(json.dumps({"source_job_id": "job-one", "pages": []}))
    original = package / ".engine-retained/runs/job-one/manifest.json"
    original.parent.mkdir(parents=True)
    source = {
        "run_dir": "/results/job-one/.engine-work/runs/job-one",
        "config": {"detection": {"cnn_threshold": 0.4965248107910156}},
        "pages": [{"image": "/results/job-one/.engine-work/runs/job-one/inputs/images/page.png"}],
    }
    original.write_text(json.dumps(source))
    original_bytes = original.read_bytes()
    result_path = package / "result.json"
    result_path.write_text(
        json.dumps(
            {"artifacts": [{"reference": "review/manual_correction_input.json", "sha256": "old"}]}
        )
    )
    digest = prepare_local_review(package)
    assert original.read_bytes() == original_bytes
    local = json.loads(original.with_name("local_manifest.json").read_text())
    assert local["config"] == source["config"]
    assert Path(local["pages"][0]["image"]).is_relative_to(package / ".engine-retained")
    assert (
        local["local_distribution_source"]["original_manifest_sha256"]
        == hashlib.sha256(original_bytes).hexdigest()
    )
    assert json.loads(result_path.read_text())["artifacts"][0]["sha256"] == digest
    payload = json.loads(handoff.read_text())
    assert (review / payload["source_manifest"]).resolve() == original.with_name(
        "local_manifest.json"
    )
    assert prepare_local_review(package) == digest
