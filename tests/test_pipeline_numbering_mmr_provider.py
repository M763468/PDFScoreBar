import json

import pytest

from src.measure_numbering.mmr import MMROCREngine
from src.pipeline.steps import numbering


class CustomInjectedEngine:
    pass


class ProviderOCR:
    pass


def test_should_replace_absent_engine():
    assert numbering._should_replace_mmr_ocr_engine(None)


def test_should_replace_default_engine_without_provider_mode():
    assert numbering._should_replace_mmr_ocr_engine(MMROCREngine())


def test_should_preserve_default_engine_with_matching_provider_mode():
    engine = MMROCREngine()
    engine._rapidocr_provider_mode = "auto"

    assert not numbering._should_replace_mmr_ocr_engine(engine, "auto")


def test_should_preserve_custom_injected_engine():
    assert not numbering._should_replace_mmr_ocr_engine(CustomInjectedEngine())


@pytest.mark.parametrize("targets", [None, {(0, 0, 1)}])
def test_run_mmr_batch_updates_default_engine_in_place(monkeypatch, tmp_path, targets):
    cached_engine = MMROCREngine()
    provider_ocr = ProviderOCR()

    class DummyProcessor:
        def __init__(self, **kwargs):
            self.ocr_engine = kwargs["ocr_engine"]

        def process_pages(self, pages_data, image_paths, debug_root=None, target_measure_keys=None):
            assert target_measure_keys == targets
            assert self.ocr_engine is cached_engine
            assert cached_engine.ocr_engine is provider_ocr
            assert cached_engine._rapidocr_provider_mode == "cuda"
            return [{"pages": []}]

    monkeypatch.setattr(
        "src.measure_numbering.rapidocr_provider.create_mmr_rapidocr",
        lambda provider: provider_ocr,
    )
    monkeypatch.setattr("src.measure_numbering.mmr.MMRProcessor", DummyProcessor)

    output_path = tmp_path / "out.json"
    result = numbering.run_mmr_batch(
        pages_data=[{"pages": []}],
        image_paths=[tmp_path / "page.png"],
        output_paths=[output_path],
        model_path=tmp_path / "model.pt",
        device="cpu",
        ocr_engine=cached_engine,
        rapidocr_provider="cuda",
        target_measure_keys=targets,
    )

    assert result == [{"pages": []}]
    assert cached_engine.ocr_engine is provider_ocr
    assert cached_engine._rapidocr_provider_mode == "cuda"
    assert json.loads(output_path.read_text(encoding="utf-8")) == result[0]


@pytest.mark.parametrize("configured, expected", [(None, "auto"), ("cpu", "cpu"), ("cuda", "cuda")])
def test_pipeline_phase_passes_configured_provider(monkeypatch, tmp_path, configured, expected):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from src.pipeline.steps.numbering_phases import run_mmr_batch_detection

    config = {"steps": {"mmr_overrides": True}, "mmr": {"model_path": "model.pt"}}
    if configured is not None:
        config["mmr"]["rapidocr_provider"] = configured
    owner = SimpleNamespace(
        config=config,
        validate_only=False,
        skip_existing=False,
        dry_run=False,
        _mmr_persistence={},
        _telemetry_progress=Mock(),
    )
    base = tmp_path / "base.json"
    base.write_text("{}")
    page = {
        "numbering_base": base,
        "intermediate_dir": tmp_path,
        "image_path": tmp_path / "page.png",
        "index": 1,
    }
    services = SimpleNamespace(
        logger=Mock(),
        load_json=lambda path: {},
        run_mmr_batch=Mock(),
        torch=SimpleNamespace(
            cuda=SimpleNamespace(is_available=lambda: False),
            device=lambda value: SimpleNamespace(type=value),
        ),
    )
    monkeypatch.setattr("src.measure_numbering.mmr.MMRClassifier", Mock())
    monkeypatch.setattr("src.measure_numbering.mmr.MMROCREngine", Mock())

    run_mmr_batch_detection(owner, ["page"], set(), {"page": page}, services=services)

    assert services.run_mmr_batch.call_args.kwargs["rapidocr_provider"] == expected
