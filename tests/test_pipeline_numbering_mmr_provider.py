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


def test_run_mmr_batch_updates_default_engine_in_place(monkeypatch, tmp_path):
    cached_engine = MMROCREngine()
    provider_ocr = ProviderOCR()

    class DummyProcessor:
        def __init__(self, **kwargs):
            self.ocr_engine = kwargs["ocr_engine"]

        def process_pages(self, pages_data, image_paths, debug_root=None):
            assert self.ocr_engine is cached_engine
            assert cached_engine.ocr_engine is provider_ocr
            assert cached_engine._rapidocr_provider_mode == "cuda"
            return [{"pages": []}]

    writes = []
    monkeypatch.setattr(
        numbering, "write_json", lambda path, result: writes.append((path, result)), raising=False
    )
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
    )

    assert result == [{"pages": []}]
    assert cached_engine.ocr_engine is provider_ocr
    assert cached_engine._rapidocr_provider_mode == "cuda"
