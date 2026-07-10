from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.pipeline.detector_routes.input_profile import (
    DENSE_PDF_RASTER_DPI,
    normalize_dense_input_profile,
    pop_dense_input_profile_metadata,
)
from src.pipeline.main import run_pipeline


def test_dense_pdf_input_overrides_stale_300_dpi_and_preserves_provenance() -> None:
    config: dict[str, Any] = {
        "steps": {"pdf_to_images": True, "detection": True},
        "inputs": {
            "pdf_path": "score.pdf",
            "pdf_to_images": {"dpi": 300},
        },
        "detection": {},
    }

    normalize_dense_input_profile(config)
    # The detection wrapper calls normalization again. It must remain idempotent
    # and retain the original configured value for the manifest.
    normalize_dense_input_profile(config)

    assert config["inputs"]["pdf_to_images"]["dpi"] == DENSE_PDF_RASTER_DPI
    metadata = pop_dense_input_profile_metadata(config["detection"])
    assert metadata == {
        "source": "pdf",
        "managed": True,
        "dpi": {"configured": 300, "effective": DENSE_PDF_RASTER_DPI},
    }


def test_explicit_ordinary_route_keeps_configured_pdf_dpi() -> None:
    config: dict[str, Any] = {
        "steps": {"pdf_to_images": True, "detection": True},
        "inputs": {"pdf_to_images": {"dpi": 300}},
        "detection": {"route": "ordinary"},
    }

    normalize_dense_input_profile(config)

    assert config["inputs"]["pdf_to_images"]["dpi"] == 300
    assert pop_dense_input_profile_metadata(config["detection"]) is None


def test_run_pipeline_normalizes_dense_dpi_before_orchestrator(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "run": {"run_id": "test"},
                "steps": {"pdf_to_images": True, "detection": True},
                "inputs": {
                    "pdf_path": "score.pdf",
                    "pdf_to_images": {"dpi": 300},
                },
                "detection": {},
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}
    expected_run_dir = tmp_path / "runs" / "test"

    class FakeOrchestrator:
        def __init__(self, *, config: dict[str, Any], **kwargs: Any) -> None:
            captured["config"] = config

        def run(self, page_limit: int | None = None) -> Path:
            captured["page_limit"] = page_limit
            return expected_run_dir

    from src.pipeline import main as pipeline_main

    monkeypatch.setattr(pipeline_main, "PipelineOrchestrator", FakeOrchestrator)

    result = run_pipeline(
        config_path,
        run_id="test",
        output_root=tmp_path / "runs",
    )

    assert result == expected_run_dir
    assert captured["config"]["inputs"]["pdf_to_images"]["dpi"] == DENSE_PDF_RASTER_DPI
