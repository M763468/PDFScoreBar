from pathlib import Path

import pytest

from src.pipeline.detector_routes.dense_probe_candidate import (
    TARGET_DETECTOR,
    DenseProbeCandidateConfig,
    build_route_provenance,
    build_score_eval_command,
    cleanup_targets,
    config_from_yaml,
    make_logged_command_runner,
    require_under_logs,
    resolve_paths,
    validate_workflow_config,
)
from src.pipeline.detector_routes.dense_probe_candidate_route import build_parser


def test_dense_probe_candidate_target_tracks_issue291_canonical_gt() -> None:
    assert TARGET_DETECTOR == {"tp": 3566, "fp": 3, "fn": 1}


def test_dense_probe_candidate_config_records_nms_disabled():
    config = DenseProbeCandidateConfig()
    assert config.cnn_apply_nms is False

    paths = resolve_paths(config)
    cmd = build_score_eval_command(config, paths)

    assert "--disable-pipeline-nms" in cmd


def test_dense_probe_candidate_no_clean_suppresses_cleanup_targets():
    config = DenseProbeCandidateConfig(no_clean_output=True)
    paths = resolve_paths(config)

    assert cleanup_targets(config, paths) == []


def test_dense_probe_candidate_skip_probe_rescue_preserves_candidates():
    config = DenseProbeCandidateConfig(skip_probe_rescue_regeneration=True)
    paths = resolve_paths(config)

    assert paths.probe_rescue_candidates_root not in cleanup_targets(config, paths)
    assert paths.scoring_output_dir in cleanup_targets(config, paths)


def test_dense_probe_candidate_skip_probe_rescue_requires_skipping_issue36():
    config = DenseProbeCandidateConfig(
        skip_issue36_regeneration=False,
        skip_probe_rescue_regeneration=True,
    )

    with pytest.raises(ValueError, match="skip_probe_rescue_regeneration"):
        validate_workflow_config(config)


def test_dense_probe_candidate_outputs_must_live_under_logs():
    with pytest.raises(ValueError):
        require_under_logs(Path("data/not_allowed"), label="output_root")


def test_dense_probe_candidate_provenance_separates_measure_count_metrics():
    config = DenseProbeCandidateConfig(output_root=Path("logs/test_dense_probe_candidate_route"))
    paths = resolve_paths(config)
    provenance = build_route_provenance(config, paths, comparisons=None)

    assert provenance["schema_version"] == "pipeline.detector_routes.dense_probe_candidate.v1"
    assert provenance["pipeline_scope"]["level"] == "detector_level_partial_route"
    assert provenance["cnn_scoring"]["cnn_apply_nms"] is False
    assert provenance["measure_count_summary"]["status"] == "not_run_in_dense_probe_candidate_route"
    assert provenance["scope_guards"]["nms_policy_owner"] == "#142"
    assert provenance["scope_guards"]["full_slow_pipeline_owner"] == "#141"
    assert "probe_rescue" in provenance
    assert "probe_rescue_candidates_root" in provenance["outputs"]


def test_dense_probe_candidate_yaml_config_round_trip():
    config = config_from_yaml(
        Path("configs/detector_routes/issue120_dense_probe_candidate_route.yaml")
    )

    assert config.output_root == Path("logs/issue120_e2e_recovery/dense_probe_candidate_route")
    assert config.cnn_apply_nms is False
    assert config.require_candidate_match is True
    assert config.skip_probe_rescue_regeneration is False
    assert config.skip_existing_probe_rescue is False


def test_dense_probe_candidate_yaml_rejects_legacy_issue53_keys(tmp_path):
    config_path = tmp_path / "route.yaml"
    config_path.write_text(
        "dense_probe_candidate_route:\n  workflow:\n    skip_issue53_regeneration: true\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="skip_issue53_regeneration"):
        config_from_yaml(config_path)


def test_dense_probe_candidate_yaml_null_path_uses_default(tmp_path):
    config_path = tmp_path / "route.yaml"
    config_path.write_text(
        "dense_probe_candidate_route:\n  inventory: null\n",
        encoding="utf-8",
    )

    config = config_from_yaml(config_path)

    assert config.inventory == DenseProbeCandidateConfig.inventory


def test_dense_probe_candidate_yaml_rejects_non_mapping(tmp_path):
    config_path = tmp_path / "route.yaml"
    config_path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a mapping"):
        config_from_yaml(config_path)


def test_dense_probe_candidate_logged_runner_redirects_output(tmp_path):
    runner = make_logged_command_runner(tmp_path)

    runner(["python3", "-c", "print('hello from child')"])

    logs = list(tmp_path.glob("*.log"))
    assert len(logs) == 1
    assert "hello from child" in logs[0].read_text(encoding="utf-8")


def test_dense_probe_candidate_formal_cli_is_config_first():
    help_text = build_parser().format_help()

    assert "--config" in help_text
    assert "--require-detector-target" in help_text
    assert "--skip-probe-rescue-regeneration" in help_text
    assert "--skip-issue53-regeneration" not in help_text
    assert "--inventory" not in help_text
    assert "--model-path" not in help_text
