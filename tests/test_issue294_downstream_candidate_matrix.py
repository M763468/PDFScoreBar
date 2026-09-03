from __future__ import annotations

import sys
import types
from pathlib import Path

from tools.issue294.run_downstream_candidate_matrix import _comparison
from tools.issue294.run_latest_homr_detector_original import (
    DETECTOR_ONLY_MODULES,
    EXCLUDED_OPTIONAL_MODULES,
    _checkout_head,
    _ensure_segnet_model,
)


def _variant(*, final_count: int, total_measures: int, measures: list[int]) -> dict:
    return {
        "final_barline_count": final_count,
        "final_barlines": [[1, 2, 3, 4]],
        "numbering": {
            "total_measures": total_measures,
            "pages": [
                {
                    "systems": [
                        {
                            "staff_count": 2,
                            "measure_count": total_measures,
                            "measure_numbers": measures,
                        }
                    ]
                }
            ],
        },
    }


def test_operational_gate_does_not_require_exact_box_identity() -> None:
    control = _variant(final_count=10, total_measures=9, measures=list(range(1, 10)))
    candidate = _variant(final_count=10, total_measures=9, measures=list(range(1, 10)))
    candidate["final_barlines"] = [[2, 2, 4, 4]]

    comparison = _comparison(control, candidate)

    assert comparison["count_topology_numbering_pass"] is True
    assert comparison["final_barline_boxes_exact"] is False


def test_operational_gate_rejects_measure_count_drift() -> None:
    control = _variant(final_count=10, total_measures=9, measures=list(range(1, 10)))
    candidate = _variant(final_count=10, total_measures=8, measures=list(range(1, 9)))

    comparison = _comparison(control, candidate)

    assert comparison["final_barline_count_equal"] is True
    assert comparison["total_measures_equal"] is False
    assert comparison["count_topology_numbering_pass"] is False


def test_latest_materializes_only_selected_segnet_weight(tmp_path: Path, monkeypatch) -> None:
    fp32 = tmp_path / "segnet_fp32.onnx"
    fp16 = tmp_path / "segnet_fp16.onnx"
    requested_urls: list[str] = []

    download_utils = types.ModuleType("homr.download_utils")

    def download_file(url: str, destination: str) -> None:
        requested_urls.append(url)
        Path(destination).write_bytes(b"fake zip")

    def unzip_file(_archive: str, destination: str) -> None:
        Path(destination, fp16.name).write_bytes(b"segnet")

    download_utils.download_file = download_file  # type: ignore[attr-defined]
    download_utils.unzip_file = unzip_file  # type: ignore[attr-defined]
    homr = types.ModuleType("homr")
    homr.download_utils = download_utils  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "homr", homr)
    monkeypatch.setitem(sys.modules, "homr.download_utils", download_utils)

    config = types.SimpleNamespace(
        segnet_path_onnx=str(fp32),
        segnet_path_onnx_fp16=str(fp16),
    )

    resolved = _ensure_segnet_model(config, use_gpu=True)

    assert resolved == fp16
    assert resolved.read_bytes() == b"segnet"
    assert len(requested_urls) == 1
    assert requested_urls[0].endswith("/segnet_fp16.zip")
    assert "transformer" not in requested_urls[0]


def test_detector_only_import_contract_excludes_full_application_dependencies() -> None:
    assert set(DETECTOR_ONLY_MODULES).isdisjoint(EXCLUDED_OPTIONAL_MODULES)
    assert "homr.main" not in DETECTOR_ONLY_MODULES
    assert "homr.pdf_utils" not in DETECTOR_ONLY_MODULES
    assert "homr.title_detection" not in DETECTOR_ONLY_MODULES
    assert "homr.transformer.configs" not in DETECTOR_ONLY_MODULES
    assert "homr.music_xml_generator" not in DETECTOR_ONLY_MODULES


def test_detector_runner_source_does_not_import_excluded_optional_modules() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "tools/issue294/run_latest_homr_detector_original.py"
    ).read_text(encoding="utf-8")
    for module in EXCLUDED_OPTIONAL_MODULES:
        assert f"import {module}" not in source
        assert f"from {module} import" not in source


def test_checkout_head_reads_detached_head_without_git_binary(tmp_path: Path) -> None:
    commit = "b377620a3a55bd7ff657481cec5b688dfbc9cee9"
    source = tmp_path / "homr"
    git_dir = source / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_text(commit + "\n", encoding="utf-8")

    assert _checkout_head(source) == commit


def test_checkout_head_reads_packed_symbolic_ref_without_git_binary(tmp_path: Path) -> None:
    commit = "457e7c6518a10ba755db2e60883419e56c4d7369"
    source = tmp_path / "homr"
    git_dir = source / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git_dir / "packed-refs").write_text(
        f"# pack-refs with: peeled fully-peeled sorted\n{commit} refs/heads/main\n",
        encoding="utf-8",
    )

    assert _checkout_head(source) == commit
