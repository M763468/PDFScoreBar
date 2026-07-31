import tarfile
from pathlib import Path

from tools.issue255.package_gate05_trace_compact import build_compact_archive


def test_compact_archive_excludes_large_debug_artifacts(tmp_path: Path) -> None:
    trace_root = tmp_path / "issue255_gate_05_trace"
    target_root = trace_root / "prokofiev" / "inventory" / "target_001"
    variant_root = target_root / "suppression_default"
    variant_root.mkdir(parents=True)

    (trace_root / "issue255_gate05_first_loss_summary.json").write_text("{}")
    inventory = (
        trace_root
        / "prokofiev"
        / "inventory"
        / "focused_detector_inventory.json"
    )
    inventory.write_text("{}")
    (target_root / "probe_boundary_report.json").write_text("{}")
    (variant_root / "variant_report.json").write_text("{}")
    (variant_root / "probe_debug.json").write_text("{}")
    (variant_root / "probe_debug.png").write_bytes(b"large")
    (variant_root / "raw_candidates.json").write_text("[]")

    output = tmp_path / "compact.tar.gz"
    report = build_compact_archive(trace_root=trace_root, output=output)

    assert report["status"] == "completed"
    with tarfile.open(output, "r:gz") as archive:
        names = set(archive.getnames())
    assert any(name.endswith("compact_manifest.json") for name in names)
    assert any(name.endswith("probe_boundary_report.json") for name in names)
    assert any(name.endswith("variant_report.json") for name in names)
    assert not any(name.endswith(".png") for name in names)
    assert not any(name.endswith("_candidates.json") for name in names)
