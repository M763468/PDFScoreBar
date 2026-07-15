from pathlib import Path

from tools.issue245 import run_fresh_upstream_homr_probe as probe


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "tools/issue245/Dockerfile.fresh_upstream_homr_probe"
WRAPPER = REPO_ROOT / "tools/issue245/run_fresh_upstream_homr_probe.sh"


def test_fresh_probe_uses_public_upstream_source_and_downloads_models() -> None:
    content = DOCKERFILE.read_text(encoding="utf-8")

    assert probe.HOMR_REPOSITORY == "https://github.com/liebharc/homr.git"
    assert probe.HOMR_SOURCE_COMMIT in content
    assert "git clone" in content
    assert "from homr.main import download_weights" in content
    assert "download_weights()" in content
    assert "COPY . /opt/issue245_homr" not in content


def test_fresh_probe_pins_reproduced_dependency_versions() -> None:
    content = DOCKERFILE.read_text(encoding="utf-8")

    assert "numpy==2.2.6" in content
    assert "opencv-python-headless==4.12.0.88" in content
    assert "onnxruntime-gpu==1.22.0" in content


def test_fresh_probe_verifies_all_recovered_model_hashes() -> None:
    content = DOCKERFILE.read_text(encoding="utf-8")

    for expected in (
        "e6a7c1e84f8d2f19f20a47e0889be2392cd487d27fa77984e4877b86534dee83",
        "381646983d14f17a11e4be671aaf6e4f81727b3a9edf0cf4890109a321ffce68",
        "22a443b2ea18da82128ae52e85436d6fb4728ab68aee24adb2ac9dfc2003a30c",
    ):
        assert expected in content


def test_fresh_probe_wrapper_sets_repository_pythonpath() -> None:
    content = WRAPPER.read_text(encoding="utf-8")

    assert 'PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"' in content
    assert "-m tools.issue245.run_fresh_upstream_homr_probe" in content
