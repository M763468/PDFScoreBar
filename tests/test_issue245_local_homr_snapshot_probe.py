import hashlib
from pathlib import Path

from tools.issue245 import run_local_homr_snapshot_probe as probe


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_prepare_build_context_uses_clean_archive_and_retained_models(
    tmp_path: Path, monkeypatch
) -> None:
    local_homr = tmp_path / "local_homr"
    destination = tmp_path / "context"
    source_content = b"clean source\n"
    model_content = b"retained model\n"
    source_relative = "homr/main.py"
    model_relative = "homr/segmentation/segnet_test.onnx"

    model_source = local_homr / model_relative
    model_source.parent.mkdir(parents=True)
    model_source.write_bytes(model_content)

    monkeypatch.setattr(
        probe,
        "EXPECTED_CLEAN_SOURCE_HASHES",
        {source_relative: digest(source_content)},
    )
    monkeypatch.setattr(
        probe,
        "MODEL_HASHES",
        {model_relative: digest(model_content)},
    )
    monkeypatch.setattr(
        probe,
        "git_output",
        lambda _repo, *_args: probe.HOMR_SOURCE_COMMIT,
    )

    def fake_archive(_repo: Path, _commit: str, target: Path) -> None:
        path = target / source_relative
        path.parent.mkdir(parents=True)
        path.write_bytes(source_content)

    monkeypatch.setattr(probe, "archive_commit", fake_archive)

    result = probe.prepare_build_context(local_homr, destination)

    assert (destination / source_relative).read_bytes() == source_content
    assert (destination / model_relative).read_bytes() == model_content
    assert result["source_commit"] == probe.HOMR_SOURCE_COMMIT
    assert result["source_records"] == [
        {
            "path": source_relative,
            "sha256": digest(source_content),
            "source": "git_archive",
        }
    ]
    assert result["model_records"][0]["source"] == str(model_source)
    assert {item["path"] for item in result["excluded_dirty_changes"]} == {
        "homr/autocrop.py",
        "homr/segmentation/inference_segnet.py",
        "pyproject.toml",
    }
