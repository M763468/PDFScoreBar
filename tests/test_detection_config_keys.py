"""Unknown detection settings share one contract across execution entrances."""

from pathlib import Path

import pytest
import yaml

from src.pipeline.detection.config import resolve_detector_route, validate_detection_config


@pytest.mark.parametrize(
    "key", ["unexpected", "cnn_threhold", "omr_job_reuse", "omr_dln_model_path", "omr_dln_device"]
)
@pytest.mark.parametrize("value", [False, None, ""])
def test_unknown_keys_rejected_by_presence(key, value):
    with pytest.raises(ValueError, match=rf"Unknown configuration.*detection\.{key}"):
        resolve_detector_route({key: value})


def test_all_shipped_detection_settings_are_known():
    for path in Path("configs").rglob("*.yaml"):
        config = yaml.safe_load(path.read_text())
        if isinstance(config, dict):
            validate_detection_config(config.get("detection"))


@pytest.mark.parametrize("mode", ["production", "exploration", "comparison"])
def test_runtime_and_experiment_settings(mode):
    resolve_detector_route(
        {
            "model_validation": mode,
            "model_sha256": {"cnn": "a" * 64},
            "cnn_device": "cpu",
            "probe_skip_existing": True,
        }
    )


def test_historical_profile_cannot_be_selected():
    with pytest.raises(ValueError, match="detection.homr_profile"):
        resolve_detector_route({"homr_profile": "stage_e_verified"})


@pytest.mark.parametrize("validate_only", [False, True])
def test_cli_entry_rejects_unknown_before_creating_outputs(tmp_path, validate_only):
    from src.pipeline.main import run_pipeline

    config = tmp_path / "config.yaml"
    config.write_text("detection:\n  cnn_threhold: 0.5\n")
    out = tmp_path / "output"
    with pytest.raises(ValueError, match="Unknown configuration.*detection.cnn_threhold"):
        run_pipeline(config, output_root=out, validate_only=validate_only)
    assert not out.exists()
