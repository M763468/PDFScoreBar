from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.common.realesrgan_assets import resolve_realesrgan_weight
from src.pipeline.detection.omr_dln_model import resolve_omr_dln_model_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_runtime_contract_module():
    module_path = PROJECT_ROOT / "docker" / "runtime_contract.py"
    spec = importlib.util.spec_from_file_location("pdfscore_runtime_contract", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_image_resolver_module():
    module_path = PROJECT_ROOT / "scripts" / "docker_image_resolver.py"
    spec = importlib.util.spec_from_file_location("pdfscore_docker_image_resolver", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_realesrgan_weight_override_is_independent_of_workspace(tmp_path: Path) -> None:
    asset_root = tmp_path / "image-assets"
    expected = asset_root / "RealESRGAN_x2plus.pth"

    resolved = resolve_realesrgan_weight(
        "RealESRGAN_x2plus",
        project_root=tmp_path / "workspace",
        environment={"PDFSCORE_REALESRGAN_WEIGHTS_DIR": str(asset_root)},
    )

    assert resolved == expected


def test_omr_dln_model_accepts_explicit_external_asset(tmp_path: Path) -> None:
    expected = tmp_path / "YOLOv8m_Measures.pt"

    resolved = resolve_omr_dln_model_path(
        repository_root=tmp_path / "workspace",
        environment={"OMR_DLN_MODEL_PATH": str(expected)},
    )

    assert resolved == expected


def test_source_fingerprint_detects_runtime_source_drift_but_ignores_config(tmp_path: Path) -> None:
    runtime_contract = _load_runtime_contract_module()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "smoke.yaml").write_text("value: 1\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")

    initial = runtime_contract.source_fingerprint(tmp_path)
    (tmp_path / "configs" / "smoke.yaml").write_text("value: 2\n", encoding="utf-8")
    assert runtime_contract.source_fingerprint(tmp_path) == initial

    (tmp_path / "src" / "worker.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert runtime_contract.source_fingerprint(tmp_path) != initial


def test_runtime_fingerprint_ignores_bind_mounted_source_and_provenance_tail(
    tmp_path: Path,
) -> None:
    runtime_contract = _load_runtime_contract_module()
    boundary = (
        "# Copy source code. Canonical runtime mounts the active checkout over /workspace,\n"
    )
    (tmp_path / "Dockerfile").write_text(
        "FROM runtime\nRUN install-runtime\n" + boundary + "COPY . /workspace\nLABEL source=old\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (tmp_path / "docker").mkdir()
    (tmp_path / "docker" / "patch_homr_onnx_provider.py").write_text(
        "PATCH = 1\n", encoding="utf-8"
    )
    manifest = tmp_path / "models" / "barline_cnn" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"sha256": "abc"}\n', encoding="utf-8")
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "worker.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")

    initial = runtime_contract.runtime_fingerprint(tmp_path)

    source.write_text("VALUE = 2\n", encoding="utf-8")
    assert runtime_contract.runtime_fingerprint(tmp_path) == initial

    (tmp_path / "Dockerfile").write_text(
        "FROM runtime\nRUN install-runtime\n" + boundary + "COPY . /workspace\nLABEL source=new\n",
        encoding="utf-8",
    )
    assert runtime_contract.runtime_fingerprint(tmp_path) == initial

    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='fixture'\ndependencies=['new-runtime']\n", encoding="utf-8"
    )
    assert runtime_contract.runtime_fingerprint(tmp_path) != initial


def test_runtime_contract_mismatch_defers_rebuild_classification(tmp_path: Path, capsys) -> None:
    runtime_contract = _load_runtime_contract_module()
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "worker.py").write_text("VALUE = 1\n", encoding="utf-8")
    expected = tmp_path / "expected.txt"
    expected.write_text("different-fingerprint\n", encoding="utf-8")

    status = runtime_contract.run_preflight(
        workspace,
        tmp_path / "unused-config.yaml",
        expected,
    )

    captured = capsys.readouterr()
    assert status == 2
    assert "image/environment-defining inputs" in captured.err
    assert "Rebuild the image." not in captured.err


def test_image_mismatch_classifies_stale_topic_base() -> None:
    resolver = _load_image_resolver_module()

    category, guidance = resolver.classify_mismatch(
        active_fingerprint="old-topic",
        image_fingerprint="current-develop",
        head_fingerprint="old-topic",
        develop_fingerprint="current-develop",
        topic_has_runtime_diff=False,
    )

    assert category == "stale_topic_base"
    assert "Refresh the topic branch" in guidance
    assert "do not rebuild solely" in guidance


def test_image_mismatch_classifies_topic_runtime_change() -> None:
    resolver = _load_image_resolver_module()

    category, guidance = resolver.classify_mismatch(
        active_fingerprint="topic-runtime",
        image_fingerprint="current-develop",
        head_fingerprint="topic-runtime",
        develop_fingerprint="current-develop",
        topic_has_runtime_diff=True,
    )

    assert category == "topic_runtime_change"
    assert "build a runtime image" in guidance


def test_image_mismatch_classifies_stale_image() -> None:
    resolver = _load_image_resolver_module()

    category, guidance = resolver.classify_mismatch(
        active_fingerprint="current-develop",
        image_fingerprint="old-image",
        head_fingerprint="current-develop",
        develop_fingerprint="current-develop",
        topic_has_runtime_diff=False,
    )

    assert category == "stale_image"
    assert "Build the canonical image" in guidance


def test_default_image_resolution_reuses_matching_local_image(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    resolver = _load_image_resolver_module()
    requested = resolver.ImageInfo(
        image_id="sha256:requested",
        tags=("pdfscore_pipeline_gpu:latest",),
        created="2026-09-20T00:00:00Z",
        asset_contract="v1",
        source_fingerprint="other-source",
        source_commit="old",
        source_branch="develop",
    )
    compatible = resolver.ImageInfo(
        image_id="sha256:compatible",
        tags=("pdfscore_issue352:latest",),
        created="2026-09-21T00:00:00Z",
        asset_contract="v1",
        source_fingerprint="active-source",
        source_commit="new",
        source_branch="topic",
    )

    monkeypatch.setattr(resolver, "image_info", lambda _ref: requested)
    monkeypatch.setattr(resolver, "working_tree_source_fingerprint", lambda _root: "active-source")
    monkeypatch.setattr(resolver, "working_tree_fingerprint", lambda _root: "active-runtime")
    monkeypatch.setattr(
        resolver,
        "_embedded_runtime_fingerprint",
        lambda info: "active-runtime" if info.image_id == compatible.image_id else "other-runtime",
    )
    monkeypatch.setattr(
        resolver,
        "git_ref_fingerprint",
        lambda _root, ref: "active-runtime" if ref == "HEAD" else "develop-runtime",
    )
    monkeypatch.setattr(resolver, "_find_develop_ref", lambda _root: "origin/develop")
    monkeypatch.setattr(resolver, "_topic_has_runtime_diff", lambda _root, _ref: True)
    monkeypatch.setattr(resolver, "list_runtime_images", lambda: [requested, compatible])

    status = resolver._resolve(
        SimpleNamespace(
            repo_root=tmp_path,
            image_ref="pdfscore_pipeline_gpu",
            explicit=False,
        )
    )

    captured = capsys.readouterr()
    assert status == 0
    assert captured.out.strip() == "sha256:compatible"
    assert "matching runtime environment contract" in captured.err


def test_matching_source_still_requires_runtime_contract_match(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    resolver = _load_image_resolver_module()
    requested = resolver.ImageInfo(
        image_id="sha256:requested",
        tags=("pdfscore_pipeline_gpu:latest",),
        created=None,
        asset_contract="v1",
        source_fingerprint="same-source",
        source_commit="same",
        source_branch="develop",
    )
    monkeypatch.setattr(resolver, "image_info", lambda _ref: requested)
    monkeypatch.setattr(resolver, "working_tree_source_fingerprint", lambda _root: "same-source")
    monkeypatch.setattr(resolver, "working_tree_fingerprint", lambda _root: "new-runtime")
    monkeypatch.setattr(resolver, "_embedded_runtime_fingerprint", lambda _info: "old-runtime")
    monkeypatch.setattr(resolver, "git_ref_fingerprint", lambda _root, _ref: "new-runtime")
    monkeypatch.setattr(resolver, "_find_develop_ref", lambda _root: "origin/develop")
    monkeypatch.setattr(resolver, "_topic_has_runtime_diff", lambda _root, _ref: True)
    monkeypatch.setattr(
        resolver,
        "list_runtime_images",
        lambda: (_ for _ in ()).throw(AssertionError("explicit image must not be substituted")),
    )

    status = resolver._resolve(
        SimpleNamespace(repo_root=tmp_path, image_ref="pdfscore_pipeline_gpu", explicit=True)
    )

    captured = capsys.readouterr()
    assert status == 2
    assert "runtime compatibility mismatch" in captured.err


def test_source_only_mismatch_reuses_requested_runtime_compatible_image(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    resolver = _load_image_resolver_module()
    requested = resolver.ImageInfo(
        image_id="sha256:requested",
        tags=("pdfscore_pipeline_gpu:latest",),
        created=None,
        asset_contract="v1",
        source_fingerprint="image-source",
        source_commit="old",
        source_branch="develop",
    )
    monkeypatch.setattr(resolver, "image_info", lambda _ref: requested)
    monkeypatch.setattr(resolver, "working_tree_source_fingerprint", lambda _root: "new-source")
    monkeypatch.setattr(resolver, "working_tree_fingerprint", lambda _root: "same-runtime")
    monkeypatch.setattr(resolver, "_embedded_runtime_fingerprint", lambda _info: "same-runtime")

    status = resolver._resolve(
        SimpleNamespace(repo_root=tmp_path, image_ref="pdfscore_pipeline_gpu", explicit=False)
    )

    captured = capsys.readouterr()
    assert status == 0
    assert captured.out.strip() == requested.image_id
    assert "build source differs" in captured.err
    assert "runtime environment contract matches" in captured.err


def test_stale_topic_base_does_not_reuse_older_matching_image(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    resolver = _load_image_resolver_module()
    requested = resolver.ImageInfo(
        image_id="sha256:develop",
        tags=("pdfscore_pipeline_gpu:latest",),
        created=None,
        asset_contract="v1",
        source_fingerprint="develop-source",
        source_commit="develop",
        source_branch="develop",
    )
    stale_matching = resolver.ImageInfo(
        image_id="sha256:stale",
        tags=("old-topic:latest",),
        created=None,
        asset_contract="v1",
        source_fingerprint="old-topic",
        source_commit="old",
        source_branch="topic",
    )

    monkeypatch.setattr(resolver, "image_info", lambda _ref: requested)
    monkeypatch.setattr(resolver, "working_tree_source_fingerprint", lambda _root: "old-topic")
    monkeypatch.setattr(resolver, "working_tree_fingerprint", lambda _root: "old-runtime")
    monkeypatch.setattr(
        resolver,
        "_embedded_runtime_fingerprint",
        lambda info: "develop-runtime" if info.image_id == requested.image_id else "old-runtime",
    )
    monkeypatch.setattr(
        resolver,
        "git_ref_fingerprint",
        lambda _root, ref: "old-runtime" if ref == "HEAD" else "develop-runtime",
    )
    monkeypatch.setattr(resolver, "_find_develop_ref", lambda _root: "origin/develop")
    monkeypatch.setattr(resolver, "_topic_has_runtime_diff", lambda _root, _ref: False)
    monkeypatch.setattr(resolver, "list_runtime_images", lambda: [requested, stale_matching])

    status = resolver._resolve(
        SimpleNamespace(
            repo_root=tmp_path,
            image_ref="pdfscore_pipeline_gpu",
            explicit=False,
        )
    )

    captured = capsys.readouterr()
    assert status == 2
    assert captured.out == ""
    assert "category: stale_topic_base" in captured.err
    assert "Refresh the topic branch" in captured.err


def test_explicit_image_override_is_not_substituted(tmp_path: Path, monkeypatch, capsys) -> None:
    resolver = _load_image_resolver_module()
    requested = resolver.ImageInfo(
        image_id="sha256:explicit",
        tags=("explicit:latest",),
        created=None,
        asset_contract="v1",
        source_fingerprint="other-source",
        source_commit="other",
        source_branch="other",
    )

    monkeypatch.setattr(resolver, "image_info", lambda _ref: requested)
    monkeypatch.setattr(resolver, "working_tree_source_fingerprint", lambda _root: "active-source")
    monkeypatch.setattr(resolver, "working_tree_fingerprint", lambda _root: "active-runtime")
    monkeypatch.setattr(resolver, "_embedded_runtime_fingerprint", lambda _info: "other-runtime")
    monkeypatch.setattr(resolver, "git_ref_fingerprint", lambda _root, _ref: "active-runtime")
    monkeypatch.setattr(resolver, "_find_develop_ref", lambda _root: "origin/develop")
    monkeypatch.setattr(resolver, "_topic_has_runtime_diff", lambda _root, _ref: True)
    monkeypatch.setattr(
        resolver,
        "list_runtime_images",
        lambda: (_ for _ in ()).throw(AssertionError("must not search alternate images")),
    )

    status = resolver._resolve(
        SimpleNamespace(
            repo_root=tmp_path,
            image_ref="explicit",
            explicit=True,
        )
    )

    captured = capsys.readouterr()
    assert status == 2
    assert "DOCKER_IMAGE is explicit" in captured.err


def _write_fake_docker(bin_dir: Path) -> Path:
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf "%s\\n" "$*" >>"$DOCKER_CALL_LOG"\n'
        'if [[ "${1:-} ${2:-}" == "image ls" ]]; then\n'
        '  case "${FAKE_IMAGE_STATE:-present}" in\n'
        "    absent) exit 0 ;;\n"
        '    error) echo "Docker daemon unavailable" >&2; exit 42 ;;\n'
        '    *) echo "fake-image-id" ;;\n'
        "  esac\n"
        "fi\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    return docker


def _run_make_with_fake_docker(
    target: str, tmp_path: Path, *args: str, image_state: str = "present", fails: bool = False
) -> list[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_docker(bin_dir)
    call_log = tmp_path / "docker_calls.log"
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["DOCKER_CALL_LOG"] = str(call_log)
    env["FAKE_IMAGE_STATE"] = image_state
    # Build tests must not truncate a real build's artifacts/provenance in the checkout.
    env["GIT_DIR"] = subprocess.check_output(
        ["git", "rev-parse", "--absolute-git-dir"], cwd=PROJECT_ROOT, text=True
    ).strip()
    for relative in ("scripts/docker_build.sh", "docker/runtime_contract.py"):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / relative, destination)

    result = subprocess.run(
        ["make", "-f", str(PROJECT_ROOT / "Makefile"), target, *args],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if fails:
        assert result.returncode != 0
        assert "Docker daemon unavailable" in result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
    return call_log.read_text(encoding="utf-8").splitlines()


def test_docker_clean_removes_only_the_canonical_container(tmp_path: Path) -> None:
    calls = _run_make_with_fake_docker("docker-clean", tmp_path)

    assert calls == ["rm -f pdfscore_pipeline_gpu"]


def test_temporary_build_does_not_clean_or_retag_canonical(tmp_path: Path) -> None:
    calls = _run_make_with_fake_docker(
        "docker-build", tmp_path, "DOCKER_IMAGE=pdfscore-test:temporary"
    )
    assert len(calls) == 1
    assert calls[0].startswith("build --build-arg PDFSCORE_SOURCE_FINGERPRINT=")
    assert " -t pdfscore-test:temporary ." in calls[0]
    assert "pdfscore_pipeline_gpu" not in calls[0]


def test_direct_build_creates_artifact_directory_before_tempfile(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n", encoding="utf-8")
    docker.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["GIT_DIR"] = subprocess.check_output(
        ["git", "rev-parse", "--absolute-git-dir"], cwd=PROJECT_ROOT, text=True
    ).strip()

    (tmp_path / "scripts").mkdir()
    (tmp_path / "docker").mkdir()
    shutil.copyfile(PROJECT_ROOT / "scripts/docker_build.sh", tmp_path / "scripts/docker_build.sh")
    shutil.copyfile(
        PROJECT_ROOT / "docker/runtime_contract.py", tmp_path / "docker/runtime_contract.py"
    )

    artifacts = tmp_path / "artifacts"
    assert not artifacts.exists()

    result = subprocess.run(
        ["bash", "scripts/docker_build.sh"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (artifacts / "docker_build.log").is_file()
    assert (artifacts / "docker_build_provenance.txt").is_file()
    assert not list(artifacts.glob(".docker_build_provenance.*"))


def test_failed_build_preserves_previous_provenance(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'printf "%s\\n" "$*" >>"$DOCKER_CALL_LOG"\n'
        'if [[ "${1:-}" == "build" ]]; then exit 17; fi\n',
        encoding="utf-8",
    )
    docker.chmod(0o755)
    call_log = tmp_path / "docker_calls.log"
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    provenance = artifacts / "docker_build_provenance.txt"
    provenance.write_text("previous_success\n", encoding="utf-8")
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["DOCKER_CALL_LOG"] = str(call_log)
    env["GIT_DIR"] = subprocess.check_output(
        ["git", "rev-parse", "--absolute-git-dir"], cwd=PROJECT_ROOT, text=True
    ).strip()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "docker").mkdir()
    shutil.copyfile(PROJECT_ROOT / "scripts/docker_build.sh", tmp_path / "scripts/docker_build.sh")
    shutil.copyfile(
        PROJECT_ROOT / "docker/runtime_contract.py", tmp_path / "docker/runtime_contract.py"
    )
    result = subprocess.run(
        ["bash", "scripts/docker_build.sh"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 17
    assert provenance.read_text(encoding="utf-8") == "previous_success\n"
    assert not list(artifacts.glob(".docker_build_provenance.*"))


def test_image_inventory_filters_before_inspecting(monkeypatch) -> None:
    resolver = _load_image_resolver_module()
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(resolver, "_run", run)
    assert resolver.list_runtime_images() == []
    assert calls == [
        [
            "docker",
            "image",
            "ls",
            "--no-trunc",
            "--quiet",
            "--filter",
            "label=pdfscore.runtime.asset_contract=v1",
        ]
    ]


def test_missing_default_image_reuses_local_but_explicit_does_not(tmp_path, monkeypatch, capsys):
    resolver = _load_image_resolver_module()
    candidate = resolver.ImageInfo("sha256:match", (), None, "v1", "active", None, None)
    monkeypatch.setattr(resolver, "image_info", lambda ref: None)
    monkeypatch.setattr(resolver, "working_tree_fingerprint", lambda root: "active")
    monkeypatch.setattr(resolver, "_embedded_runtime_fingerprint", lambda info: "active")
    monkeypatch.setattr(resolver, "list_runtime_images", lambda: [candidate])
    args = SimpleNamespace(repo_root=tmp_path, image_ref="missing", explicit=False)
    assert resolver._resolve(args) == 0
    assert capsys.readouterr().out.strip() == candidate.image_id
    args.explicit = True
    assert resolver._resolve(args) == 2
    assert capsys.readouterr().out == ""


def test_docker_clean_full_removes_container_then_image(tmp_path: Path) -> None:
    calls = _run_make_with_fake_docker("docker-clean-full", tmp_path)

    assert calls == [
        "rm -f pdfscore_pipeline_gpu",
        "image ls --quiet pdfscore_pipeline_gpu",
        "rmi pdfscore_pipeline_gpu",
    ]


@pytest.mark.parametrize("image_state", ["absent", "error"])
def test_full_cleanup_distinguishes_absence_from_docker_error(tmp_path, image_state):
    calls = _run_make_with_fake_docker(
        "docker-clean-full",
        tmp_path,
        "DOCKER_IMAGE=pdfscore-test:temporary",
        image_state=image_state,
        fails=image_state == "error",
    )
    assert calls == ["rm -f pdfscore_pipeline_gpu", "image ls --quiet pdfscore-test:temporary"]


@pytest.mark.parametrize("contract", [None, "v2", "v1"])
def test_legacy_fingerprint_only_starts_recognized_contract_images(
    monkeypatch, tmp_path, capsys, contract
):
    resolver = _load_image_resolver_module()
    labels = {} if contract is None else {resolver.ASSET_CONTRACT_LABEL: contract}
    monkeypatch.setattr(
        resolver,
        "_inspect_image",
        lambda ref: {
            "Id": "sha256:fixture",
            "Config": {"Labels": labels},
        },
    )
    calls = []

    def embedded(image_id):
        calls.append(image_id)
        return "a" * 64

    monkeypatch.setattr(resolver, "_embedded_fingerprint", embedded)
    info = resolver.image_info("fixture")
    assert info.asset_contract == contract
    if contract == "v1":
        assert calls == ["sha256:fixture"]
        assert info.source_fingerprint == "a" * 64
    else:
        assert calls == []
        assert info.source_fingerprint is None
        assert (
            resolver._resolve(
                SimpleNamespace(
                    repo_root=tmp_path,
                    image_ref="fixture",
                    explicit=True,
                )
            )
            == 2
        )
        assert "expected PDFScoreBar runtime contract label" in capsys.readouterr().err
        assert calls == []
