from __future__ import annotations

from tools.issue294.run_downstream_candidate_matrix import _comparison
from tools.issue294.run_latest_homr_detector_original import _download_segnet


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


def test_latest_download_requests_segnet_gpu_without_transformer_gpu() -> None:
    observed: dict[str, bool] = {}

    def latest_download(
        segnet_use_gpu: bool,
        transformer_use_gpu: bool,
        coreml_encoder: bool,
    ) -> None:
        observed.update(
            {
                "segnet_use_gpu": segnet_use_gpu,
                "transformer_use_gpu": transformer_use_gpu,
                "coreml_encoder": coreml_encoder,
            }
        )

    _download_segnet(latest_download, use_gpu=True)

    assert observed == {
        "segnet_use_gpu": True,
        "transformer_use_gpu": False,
        "coreml_encoder": False,
    }
