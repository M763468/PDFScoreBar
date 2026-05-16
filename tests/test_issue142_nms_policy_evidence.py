import json

from tools.issue120.summarize_nms_policy_evidence import (
    load_case,
    write_json,
    write_markdown,
)


def test_load_case_reports_detector_and_measure_count_separately(tmp_path):
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "detector_metrics.json").write_text(
        json.dumps({"gt": 20, "pred": 19, "tp": 18, "fp": 1, "fn": 2}),
        encoding="utf-8",
    )
    (eval_dir / "stage_b_provenance.json").write_text(
        json.dumps({"pipeline_nms_enabled": True}),
        encoding="utf-8",
    )
    (eval_dir / "evaluation_contract.json").write_text(
        json.dumps(
            {
                "measure_count_summary": {
                    "status": "provided",
                    "net_delta": -1,
                    "abs_delta_sum": 3,
                    "delta_pages": 2,
                }
            }
        ),
        encoding="utf-8",
    )

    case = load_case("nms_on", eval_dir)

    assert case.cnn_apply_nms is True
    assert case.tp == 18
    assert case.fp == 1
    assert case.fn == 2
    assert case.measure_count_status == "provided"
    assert case.measure_count_net_delta == -1
    assert case.measure_count_abs_delta_sum == 3
    assert case.measure_count_delta_pages == 2


def test_write_outputs_preserve_missing_measure_count_status(tmp_path):
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "detector_metrics.json").write_text(
        json.dumps({"gt": 20, "pred": 20, "tp": 20, "fp": 0, "fn": 0}),
        encoding="utf-8",
    )
    (eval_dir / "evaluation_contract.json").write_text(
        json.dumps({"measure_count_summary": {"status": "not_provided"}}),
        encoding="utf-8",
    )

    case = load_case("nms_off", eval_dir)
    output_json = tmp_path / "summary.json"
    output_md = tmp_path / "summary.md"

    write_json(output_json, [case], "default off")
    write_markdown(output_md, [case], "default off")

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["decision"] == "default off"
    assert payload["cases"][0]["measure_count_status"] == "not_provided"
    assert "not_provided" in output_md.read_text(encoding="utf-8")
