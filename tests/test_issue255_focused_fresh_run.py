import json
from argparse import Namespace
from pathlib import Path

from tools.issue255.run_focused_fresh_detector import build_effective_config


def test_build_effective_config_preserves_detection_and_steps(tmp_path: Path) -> None:
    image_dir = tmp_path / "Score"
    image_dir.mkdir()
    image = image_dir / "page_004.png"
    image.write_bytes(b"image")
    canonical = {
        "run": {"run_id": "dense", "output_root": "logs/full"},
        "inputs": {
            "pdf_to_images": {
                "output_dir": "data/images",
                "image_glob": "page_*.png",
            }
        },
        "steps": {"detection": True, "numbering_base": True},
        "detection": {"cnn_threshold": 0.1, "enable_sr": True},
    }

    effective = build_effective_config(
        canonical,
        image=image,
        run_id="issue255_score_page004",
        output_root=tmp_path / "logs",
    )

    assert effective["detection"] == canonical["detection"]
    assert effective["steps"] == canonical["steps"]
    assert effective["inputs"]["pdf_to_images"]["output_dir"] == str(image_dir.resolve())
    assert effective["inputs"]["pdf_to_images"]["image_glob"] == image.name
    assert effective["run"]["run_id"] == "issue255_score_page004"


def test_focused_runner_records_authoritative_fresh_artifacts(tmp_path: Path, monkeypatch) -> None:
    import tools.issue255.run_focused_fresh_detector as runner

    config_path = tmp_path / "configs" / "dense_full_pipeline.yaml"
    config_path.parent.mkdir()
    config_path.write_text("detection: {}\n", encoding="utf-8")
    image_dir = tmp_path / "Score"
    image_dir.mkdir()
    image = image_dir / "page_004.png"
    image.write_bytes(b"image")
    canonical = {
        "run": {"run_id": "dense", "output_root": "logs/full"},
        "inputs": {
            "pdf_to_images": {
                "output_dir": "data/images",
                "image_glob": "page_*.png",
            }
        },
        "steps": {"detection": True, "numbering_base": True},
        "detection": {
            "cnn_threshold": 0.1,
            "enable_sr": True,
            "sr_scale": 2,
        },
    }
    monkeypatch.setattr(runner, "CANONICAL_CONFIG", config_path)
    monkeypatch.setattr(runner, "load_yaml", lambda path: canonical)
    monkeypatch.setattr(runner, "_git", lambda *args, **kwargs: None)

    def write(path: Path, payload=b"artifact") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, bytes):
            path.write_bytes(payload)
        else:
            path.write_text(json.dumps(payload), encoding="utf-8")

    def fake_detection(config, images, page_ids, run_id, run_dir, *, dry_run):
        assert config["detection"] == canonical["detection"]
        assert images == [image.resolve()]
        assert page_ids == ["page_004"]
        assert dry_run is False
        hybrid = tmp_path / "hybrid" / run_id
        probe = run_dir / "intermediate" / "probe_scan"
        stem = image.stem
        write(hybrid / "baseline" / "batch" / stem / f"{stem}_detections.json", [])
        write(hybrid / "sr" / "batch" / stem / f"{stem}_detections.json", [])
        write(hybrid / "sr" / "batch" / stem / f"{stem}.png")
        write(hybrid / "sr" / "batch" / stem / f"{stem}_staff_mask.png")
        write(hybrid / "omr_sr" / stem / "predictions.json", [])
        write(hybrid / "hybrid_results" / f"{stem}_hybrid.json", [])
        probe_page = probe / runner.build_probe_run_id(image.resolve(), score_name="Score")
        write(probe_page / "pipeline2_no_peak_candidates.json", [])
        write(probe_page / "pipeline2_no_peak_scored.json", [])
        write(probe_page / "pipeline2_no_peak_filtered_cnn.json", [])
        contract = {
            "mode": "fresh_upstream",
            "fresh_upstream_authoritative": True,
            "override_keys": [],
        }
        write(run_dir / "intermediate" / "detector_input_contract.json", contract)
        return {
            "hybrid_output_dir": hybrid,
            "probe_output_dir": probe,
            "detector_input_contract": contract,
            "commands": [["inprocess:test"]],
        }

    monkeypatch.setattr(runner, "run_detection_step", fake_detection)
    report = runner.build_report(
        Namespace(
            config=config_path,
            image=image,
            score="Score",
            page="page_004",
            run_id="issue255_test",
            output_root=tmp_path / "output",
        )
    )

    assert report["status"] == "completed"
    assert report["detector_input_contract"]["mode"] == "fresh_upstream"
    assert report["detection_config_changed"] is False
    assert report["pipeline_steps_changed"] is False
    assert report["artifacts"]["final_barlines"]["exists"] is True
