from __future__ import annotations

from tools.issue294.run_downstream_candidate_matrix import _comparison
from tools.issue294.run_latest_homr_detector_original import _processing_config


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


def test_latest_processing_config_supports_split_gpu_fields() -> None:
    class LatestProcessingConfig:
        def __init__(
            self,
            enable_debug: bool,
            enable_cache: bool,
            write_staff_positions: bool,
            read_staff_positions: bool,
            selected_staff: int,
            transformer_use_gpu: bool,
            segnet_use_gpu: bool,
            coreml_encoder: bool,
            title_detection: bool,
        ) -> None:
            self.transformer_use_gpu = transformer_use_gpu
            self.segnet_use_gpu = segnet_use_gpu
            self.title_detection = title_detection

    config = _processing_config(LatestProcessingConfig, use_gpu=True)

    assert config.segnet_use_gpu is True
    assert config.transformer_use_gpu is False
    assert config.title_detection is False
