from pathlib import Path

from src.measure_numbering.pipeline import MeasureNumberingPipeline
from tools.issue294 import run_downstream_candidate_matrix_mapping_guarded as guarded_matrix
from tools.issue294.evaluate_mapping_guarded_connector_positive_candidate import (
    MappingGuardedConnectorPositivePipeline,
)
from tools.issue294.run_post277_mapping_guarded_full68_host import (
    MAPPING_GUARDED_MATRIX_SCRIPT,
    STANDARD_MATRIX_SCRIPT,
    rewrite_matrix_command,
)


def test_rewrite_matrix_command_only_swaps_issue294_matrix_entrypoint() -> None:
    command = [
        "docker",
        "exec",
        "container",
        "python",
        STANDARD_MATRIX_SCRIPT,
        "--summary",
        "/workspace/logs/summary.json",
    ]
    rewritten = rewrite_matrix_command(command)
    assert rewritten != command
    assert MAPPING_GUARDED_MATRIX_SCRIPT in rewritten
    assert STANDARD_MATRIX_SCRIPT not in rewritten
    assert command[4] == STANDARD_MATRIX_SCRIPT


def test_rewrite_matrix_command_leaves_other_commands_unchanged() -> None:
    command = [
        "docker",
        "exec",
        "container",
        "chown",
        "-R",
        "1000:1000",
        "/workspace/logs",
    ]
    assert rewrite_matrix_command(command) == command


def test_mapping_guarded_mode_keeps_A_on_production_grouping(monkeypatch) -> None:
    seen: list[tuple[str, type]] = []

    def fake_run_variant(pipeline_type: type, **kwargs):
        label = str(kwargs["label"])
        seen.append((label, pipeline_type))
        return {
            "label": label,
            "final_barline_count": 1,
            "final_barlines": [[0, 0, 1, 1]],
            "numbering": {
                "total_measures": 1,
                "pages": [
                    {
                        "systems": [
                            {
                                "staff_count": 1,
                                "measure_count": 1,
                                "measure_numbers": [1],
                                "measure_bboxes": [[0, 0, 1, 1]],
                            }
                        ]
                    }
                ],
            },
        }

    monkeypatch.setattr(guarded_matrix, "_run_variant_with_pipeline", fake_run_variant)
    guarded_matrix._run_mode(
        mode="candidate_native_geometry",
        image=Path("page.png"),
        detections={
            "A_pinned": Path("a.json"),
            "B_b377": Path("b.json"),
            "C_latest": Path("c.json"),
        },
        geometry={
            label: {"staff": Path("staff.png"), "clef": Path("clef.png")}
            for label in ("A_pinned", "B_b377", "C_latest")
        },
        support={},
        output_root=Path("out"),
        detection_config={},
    )

    assert seen == [
        ("A_pinned", MeasureNumberingPipeline),
        ("B_b377", MappingGuardedConnectorPositivePipeline),
        ("C_latest", MappingGuardedConnectorPositivePipeline),
    ]
