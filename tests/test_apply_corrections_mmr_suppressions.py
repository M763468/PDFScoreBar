import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

sys.modules.setdefault("fitz", types.SimpleNamespace())

from src.pipeline.review.apply_corrections import apply_corrections_and_rerun


def test_apply_corrections_preserves_mmr_suppressions_in_corrected_rerun(
    tmp_path: Path,
):
    run_dir = tmp_path / "original_run"
    review_dir = run_dir / "review"
    corrections_dir = review_dir / "corrections"
    page_dir = review_dir / "pages" / "page_001"
    corrections_dir.mkdir(parents=True)
    page_dir.mkdir(parents=True)

    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "config": {
                    "inputs": {},
                    "steps": {"mmr_overrides": True},
                    "outputs": {},
                }
            }
        ),
        encoding="utf-8",
    )

    source_mmr_override = {
        "measure_overrides": [
            {
                "page": 1,
                "system": 1,
                "measure": 1,
                "skip": 3,
                "source": "auto:mmr",
            }
        ]
    }
    (page_dir / "mmr_overrides.json").write_text(
        json.dumps(source_mmr_override), encoding="utf-8"
    )

    (corrections_dir / "mmr_measure_spans.json").write_text(
        json.dumps(
            {
                "correction_type": "mmr_measure_span",
                "items": [
                    {
                        "op": "suppress",
                        "page": 1,
                        "system": 1,
                        "measure": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    handoff_path = review_dir / "manual_correction_input.json"
    handoff = {
        "schema_version": 1,
        "pages": [
            {
                "page_id": "page_001",
                "page_number": 1,
                "source_image": "pages/page_001/source.png",
                "numbering_final": "pages/page_001/numbering_final.json",
                "mmr_overrides": "pages/page_001/mmr_overrides.json",
                "correction_output": "corrections",
            }
        ],
    }
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

    with patch("src.pipeline.review.apply_corrections.run_pipeline"):
        new_run_dir = apply_corrections_and_rerun(handoff_path, dry_run=True)

    measure_payload = json.loads(
        (corrections_dir / "measure_overrides.json").read_text(encoding="utf-8")
    )
    assert measure_payload["measure_overrides"] == []

    rerun_config = json.loads(
        (new_run_dir / "corrected_pipeline_config.json").read_text(encoding="utf-8")
    )
    assert rerun_config["steps"]["mmr_overrides"] is False
    assert rerun_config["steps"]["apply_measure_overrides"] is True
