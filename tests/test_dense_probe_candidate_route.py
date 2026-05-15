from pathlib import Path

import pytest

from src.pipeline.detector_routes.dense_probe_candidate import (
    DenseProbeCandidateConfig,
    build_route_provenance,
    build_score_eval_command,
    cleanup_targets,
    config_from_yaml,
    require_under_logs,
    resolve_paths,
)
from src.pipeline.detector_routes.dense_probe_candidate_route import build_parser


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


def test_dense_probe_candidate_yaml_config_round_trip():
    config = config_from_yaml(
        Path("configs/detector_routes/issue120_dense_probe_candidate_route.yaml")
    )

    assert config.output_root == Path("logs/issue120_e2e_recovery/dense_probe_candidate_route")
    assert config.cnn_apply_nms is False
    assert config.require_candidate_match is True


def test_dense_probe_candidate_formal_cli_is_config_first():
    help_text = build_parser().format_help()

    assert "--config" in help_text
    assert "--require-detector-target" in help_text
    assert "--inventory" not in help_text
    assert "--model-path" not in help_text
