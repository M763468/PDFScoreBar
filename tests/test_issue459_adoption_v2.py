import pytest

from tools.issue459 import adoption_v2 as v2


def blocks(*pairs):
    return [([b, b], [o, o]) for b, o in pairs]


def test_performance_gates_pass_reproducible_improvement():
    result = v2.performance_gates(blocks((100, 97), (101, 98), (102, 99)))
    assert result["P1"] == result["P2"] == result["P3"] == "passed"
    assert result["baseline_noise_percent"] == pytest.approx(2 / 101 * 100)


def test_one_regressed_block_fails_direction_gate():
    result = v2.performance_gates(blocks((100, 97), (100, 101), (100, 97)))
    assert result["P1"] == "failed"


def test_improvement_inside_noise_fails_noise_gate():
    # B spread 10% -> pooled improvement must be >= 5%.
    result = v2.performance_gates(blocks((95, 92), (100, 97), (105, 101)))
    assert result["P1"] == "passed"
    assert result["P2"] == "failed"


def test_negligible_improvement_fails_floor():
    result = v2.performance_gates(blocks((100, 99), (100, 99), (100, 99)))
    assert result["P2"] == "passed"
    assert result["P3"] == "failed"


def test_performance_gates_require_three_complete_blocks():
    with pytest.raises(ValueError):
        v2.performance_gates(blocks((100, 97), (100, 97)))
    with pytest.raises(ValueError):
        v2.performance_gates([([100], [97, 97])] + blocks((100, 97), (100, 97)))


def test_memory_gate_limits():
    base = {"ram_peak_bytes": 100, "vram_peak_mib": 3000}
    assert v2.memory_gate(base, {"ram_peak_bytes": 110, "vram_peak_mib": 3512}) == "passed"
    assert v2.memory_gate(base, {"ram_peak_bytes": 111, "vram_peak_mib": 3000}) == "failed"
    assert v2.memory_gate(base, {"ram_peak_bytes": 100, "vram_peak_mib": 3513}) == "failed"


@pytest.mark.parametrize(
    ("gates", "decision"),
    [
        ({"P1": "passed", "F1": "passed"}, "eligible_for_production_integration_proposal"),
        ({"P1": "passed", "F1": "not_run"}, "undecided"),
        ({"P1": "failed", "F1": "not_run"}, "not_eligible"),
    ],
)
def test_decision_never_treats_missing_gate_as_pass(gates, decision):
    assert v2.decide(gates) == decision


def test_omr_process_count_distinguishes_entrypoints():
    resources = {
        "process_residency_not_additive": [
            {"pid": 1, "command": "python tools/issue447/pipeline_poc.py --config x"},
            {"pid": 7, "command": "python -m tools.issue459.job_worker --request r"},
            {"pid": 8, "command": "python -m src.pipeline.detection.omr_dln_worker --images a"},
            {"pid": 9, "command": "python -m src.pipeline.detection.current_homr_worker"},
            {"pid": 10, "command": "python x --request logs/tools.issue459.job_worker.json"},
        ]
    }
    assert v2.omr_process_count(resources) == 2
