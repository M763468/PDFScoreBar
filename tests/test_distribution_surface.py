from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.materialize_distribution import PROVENANCE, check_tree, materialize, selected_files

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
    for path in (
        "src/pipeline/probe_detector/debug.py",
        "src/pipeline/utils/wide_split_utils.py",
        "src/measure_numbering/cli.py",
    ):
        assert not (candidate / path).exists()
    assert not (candidate / "src/pipeline/detection/current_sr_worker.py").exists()
    assert not (candidate / "src/common/preprocessing.py").exists()
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


def test_distribution_source_identity_verifies_complete_provenance(candidate, monkeypatch):
    from docker import distribution

    _init_candidate_git(candidate)
    monkeypatch.setattr(distribution, "ROOT", candidate)
    identity = distribution.source_identity()
    assert (
        identity["source_dirty"] is json.loads((candidate / PROVENANCE).read_text())["source_dirty"]
    )
    assert len(identity["files"]) == len(
        selected_files(json.loads((candidate / "docs/MINIMAL_MAINLINE_SURFACE.json").read_text()))
    )


def test_distribution_source_identity_accepts_extracted_candidate(candidate, monkeypatch):
    from docker import distribution

    monkeypatch.setattr(distribution, "ROOT", candidate)

    identity = distribution.source_identity()

    assert identity["files"]


def test_distribution_source_identity_ignores_python_cache_in_extracted_candidate(
    candidate, monkeypatch
):
    from docker import distribution

    cache = candidate / "src/common/__pycache__"
    cache.mkdir()
    (cache / "local.cpython-312.pyc").write_bytes(b"runtime cache")
    monkeypatch.setattr(distribution, "ROOT", candidate)

    identity = distribution.source_identity()

    assert identity["files"]


def test_distribution_source_identity_rejects_unexpected_extracted_file(candidate, monkeypatch):
    from docker import distribution

    (candidate / "unlisted.txt").write_text("not part of this release\n")
    monkeypatch.setattr(distribution, "ROOT", candidate)

    with pytest.raises(ValueError, match="Extracted distribution inventory differs"):
        distribution.source_identity()


@pytest.mark.parametrize(
    "path",
    [
        "src/pipeline/main.py",
        "configs/dense_full_pipeline.yaml",
        "models/mmr/mmr_classifier_best.pth",
    ],
)
def test_distribution_source_identity_rejects_tampered_runtime_bytes(candidate, monkeypatch, path):
    from docker import distribution

    _init_candidate_git(candidate)
    target = candidate / path
    target.write_bytes(target.read_bytes() + b"\nchanged")
    monkeypatch.setattr(distribution, "ROOT", candidate)
    with pytest.raises(ValueError, match=f"distribution content hash mismatch: {path}"):
        distribution.source_identity()


def test_distribution_source_identity_rejects_missing_and_unexpected_files(candidate, monkeypatch):
    from docker import distribution

    _init_candidate_git(candidate)
    monkeypatch.setattr(distribution, "ROOT", candidate)
    (candidate / "README.md").unlink()
    with pytest.raises(ValueError, match="missing or unsafe distributed file: README.md"):
        distribution.source_identity()


def test_distribution_source_identity_rejects_unexpected_file(candidate, monkeypatch):
    from docker import distribution

    _init_candidate_git(candidate)
    (candidate / "unlisted.txt").write_text("not part of this release\n")
    monkeypatch.setattr(distribution, "ROOT", candidate)
    with pytest.raises(ValueError, match="checkout is dirty"):
        distribution.source_identity()


def test_distribution_source_identity_rejects_provenance_inventory_mismatch(candidate, monkeypatch):
    from docker import distribution

    _init_candidate_git(candidate)
    provenance_path = candidate / PROVENANCE
    provenance = json.loads(provenance_path.read_text())
    provenance["files"].pop("README.md")
    provenance_path.write_text(json.dumps(provenance))
    monkeypatch.setattr(distribution, "ROOT", candidate)
    with pytest.raises(ValueError, match="file selection differs from manifest"):
        distribution.source_identity()


def test_candidate_gitignore_keeps_supported_help_command_checkout_clean(candidate):
    _init_candidate_git(candidate)

    result = subprocess.run(
        ["python3", "docker/distribution.py", "--help"],
        cwd=candidate,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (
        subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=candidate,
            text=True,
        )
        == ""
    )


def _init_candidate_git(candidate: Path) -> None:
    for command in (
        ["git", "init", "-q"],
        ["git", "config", "user.name", "Distribution test"],
        ["git", "config", "user.email", "distribution-test@example.invalid"],
        ["git", "add", "-f", "-A"],
        ["git", "commit", "-qm", "fixture candidate"],
    ):
        subprocess.run(command, cwd=candidate, capture_output=True, text=True, check=True)


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


@pytest.mark.parametrize(
    "path",
    ["../secret", "/absolute", "src/**", "a/../b", "a//b", ".git/config", PROVENANCE],
)
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

    # A later review uses the same external output without dirtying the distribution.
    handoff = tmp_path / "output/job-one/review/manual_correction_input.json"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("{}")
    monkeypatch.setattr(
        "sys.argv",
        [
            "distribution.py",
            "review",
            "--output",
            str(tmp_path / "output"),
            "--handoff",
            str(handoff),
        ],
    )
    assert distribution.main() == 0
    assert "tools.review_correction.server" in calls[-1]
    assert "--prepare-review" in calls[-2]


@pytest.mark.parametrize("git_checkout", [False, True])
@pytest.mark.parametrize("command", ["run", "review"])
@pytest.mark.parametrize("location", ["root", "child", "symlink"])
def test_launcher_rejects_internal_output_before_identity_or_docker(
    candidate, tmp_path, monkeypatch, git_checkout, command, location
):
    from docker import distribution

    if git_checkout:
        _init_candidate_git(candidate)
    output = candidate if location == "root" else candidate / "results"
    if location == "symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(candidate, target_is_directory=True)
        output = alias / "results"
    monkeypatch.setattr(distribution, "ROOT", candidate)
    monkeypatch.setattr(
        distribution, "source_identity", lambda: pytest.fail("must reject output before identity")
    )
    args = ["distribution.py", command, "--output", str(output)]
    args += [str(tmp_path / "source.pdf")] if command == "run" else ["--handoff", "unused.json"]
    monkeypatch.setattr("sys.argv", args)
    with pytest.raises(ValueError, match="outside the distribution root"):
        distribution.main()
    assert not (candidate / "results").exists()


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


@pytest.mark.parametrize(
    ("case", "error_code"),
    [
        ("invalid", "input_pdf_invalid"),
        ("encrypted", "input_pdf_encrypted"),
        ("pages", "request_page_out_of_range"),
    ],
)
def test_local_job_persists_early_pdf_failure(tmp_path, monkeypatch, capsys, case, error_code):
    import fitz

    from docker import distribution_job
    from src.pipeline.engine_executor import PipelineJobExecutor

    pdf = tmp_path / "source.pdf"
    if case == "invalid":
        pdf.write_bytes(b"not a PDF")
    else:
        document = fitz.open()
        document.new_page()
        options = (
            {"encryption": fitz.PDF_ENCRYPT_AES_256, "owner_pw": "owner", "user_pw": "secret"}
            if case == "encrypted"
            else {}
        )
        document.save(pdf, **options)
        document.close()
    output = tmp_path / "new-results"
    monkeypatch.setattr(
        distribution_job,
        "PipelineJobExecutor",
        lambda **kwargs: PipelineJobExecutor(
            **kwargs,
            job_id_factory=lambda: "job-early-failure",
            pipeline_runner=lambda *args, **kwargs: pytest.fail("input must fail before inference"),
        ),
    )
    args = ["distribution_job", str(pdf), "--output", str(output)]
    if case == "pages":
        args += ["--pages", "3"]
    monkeypatch.setattr("sys.argv", args)
    assert distribution_job.main() == 1
    persisted = json.loads((output / "job-early-failure/result.json").read_text())
    printed = json.loads(capsys.readouterr().out)
    assert persisted["status"] == printed["status"] == "failed"
    assert persisted["failure"]["code"] == printed["failure"]["code"] == error_code
    assert "debug_context" not in persisted["failure"]
    assert not (output / "job-early-failure/.engine-work").exists()


def test_local_job_does_not_persist_result_through_job_directory_symlink(tmp_path, monkeypatch):
    from docker import distribution_job
    from src.pipeline.engine_executor import PipelineJobExecutor

    output = tmp_path / "results"
    output.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (output / "job-fixed").symlink_to(outside, target_is_directory=True)
    pdf = tmp_path / "invalid.pdf"
    pdf.write_bytes(b"not a PDF")
    monkeypatch.setattr(
        distribution_job,
        "PipelineJobExecutor",
        lambda **kwargs: PipelineJobExecutor(**kwargs, job_id_factory=lambda: "job-fixed"),
    )
    monkeypatch.setattr("sys.argv", ["distribution_job", str(pdf), "--output", str(output)])
    with pytest.raises(ValueError, match="inside the output root"):
        distribution_job.main()
    assert not (outside / "result.json").exists()


def test_canonical_direct_run_discovers_established_external_images(tmp_path, monkeypatch):
    from src.pipeline.core import load_yaml
    from src.pipeline.orchestrator import PipelineOrchestrator
    from src.pipeline.utils.images import collect_images

    config = load_yaml(ROOT / "configs/dense_full_pipeline.yaml")
    assert config["steps"]["pdf_to_images"] is False
    assert config["inputs"]["pdf_to_images"]["output_dir"] == "data/evaluation2/images"
    monkeypatch.chdir(tmp_path)
    image = tmp_path / "data/evaluation2/images/page_001.png"
    image.parent.mkdir(parents=True)
    image.touch()  # Discovery does not decode the file or run inference.
    run_dir = tmp_path / "run"
    orchestrator = PipelineOrchestrator(config, "direct-run", run_dir)
    orchestrator._validate_external_image_inputs(config["inputs"]["pdf_to_images"])
    assert [p.resolve() for p in collect_images(config, run_dir)] == [image]
    assert not (tmp_path / "logs/input_images").exists()


def test_isolated_pdf_config_removes_develop_input_dependency(candidate, tmp_path):
    from src.pipeline.core import load_yaml
    from src.pipeline.engine_executor import PipelineJobExecutor

    executor = PipelineJobExecutor(
        input_root=tmp_path,
        artifact_root=tmp_path / "results",
        base_config_path=candidate / "configs/dense_full_pipeline.yaml",
    )
    config = executor._load_config()
    request_config = executor._write_config(
        config,
        input_path=tmp_path / "input.pdf",
        pages=(1,),
        job_id="isolated",
        work_root=tmp_path / "work",
    )
    resolved = load_yaml(request_config)
    assert resolved["steps"]["pdf_to_images"] is True
    assert resolved["steps"]["overlay"] is False
    assert "output_dir" not in resolved["inputs"]["pdf_to_images"]
    assert not (candidate / "data").exists()


def test_isolated_probe_imports_do_not_load_develop_optional_modules(candidate):
    import sys

    script = """
import sys
sys.path.insert(0, sys.argv[1])
import src.pipeline.probe_detector
import src.pipeline.steps.probe_scan
import src.pipeline.steps.numbering_phases
assert not any(name in sys.modules for name in (
    'src.pipeline.probe_detector.debug', 'src.pipeline.utils.wide_split_utils',
    'src.measure_numbering.cli'))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(candidate)],
        cwd=candidate,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
