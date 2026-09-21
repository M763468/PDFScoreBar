from pathlib import Path

from src.pipeline.core.config import load_yaml

ROOT = Path(__file__).resolve().parents[1]


def _without(payload, ignored):
    return {key: value for key, value in payload.items() if key not in ignored}


def test_standard_smoke_uses_production_detector_contract():
    smoke = load_yaml(ROOT / "configs/smoke_test.yaml")
    production = load_yaml(ROOT / "configs/dense_full_pipeline.yaml")

    validation = smoke["validation"]["detector_accuracy"]
    ignored = set(validation["allowed_detection_differences"])

    assert _without(smoke["detection"], ignored) == _without(production["detection"], ignored)
    assert "cnn_model_path" not in smoke["detection"]
    assert smoke["detection"]["cnn_model_manifest"] == "models/barline_cnn/manifest.json"


def test_standard_smoke_uses_accepted_evaluation_input_contract():
    smoke = load_yaml(ROOT / "configs/smoke_test.yaml")

    render = smoke["inputs"]["pdf_to_images"]
    assert smoke["inputs"]["pdf_path"] == ("data/evaluation2/pdfs/Va_Prokofiev_Symphony1.pdf")
    assert render["dpi"] == 360
    assert render["pages"] == "1"
    assert render["target_width"] is None
    assert render["target_height"] is None

    validation = smoke["validation"]["detector_accuracy"]
    assert validation["page_key"] == "Va_Prokofiev_Symphony1/page_001"
    assert validation["expected_gt_count"] == 85
    assert validation["expected_hard_fp_count"] == 0
    assert validation["expected_fn_count"] == 0
    assert validation["expected_soft_count"] == 0
    assert validation["expected_input_sha256"] == (
        "48e073dd8184495b9751ad62e85a872bc93cce751ba0a8c988300f7c5ae444a6"
    )


def test_standard_smoke_runs_post_pipeline_accuracy_gate():
    runtime_script = (ROOT / "scripts/docker_runtime_validation.sh").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "tools/verification/verify_detector_accuracy_smoke.py" in runtime_script
    assert 'smoke_run_id="smoke_test_detection_$(date -u +%Y%m%dT%H%M%SZ)"' in (runtime_script)
    assert "bash scripts/docker_runtime_validation.sh" in makefile
    assert "--config configs/smoke_test.yaml" in makefile
