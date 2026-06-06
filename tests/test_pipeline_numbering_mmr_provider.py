from src.measure_numbering.mmr import MMROCREngine
from src.pipeline.steps import numbering


class CustomInjectedEngine:
    pass


def test_should_replace_absent_engine():
    assert numbering._should_replace_mmr_ocr_engine(None)


def test_should_replace_default_engine_by_exact_type():
    assert numbering._should_replace_mmr_ocr_engine(MMROCREngine())


def test_should_preserve_custom_injected_engine():
    assert not numbering._should_replace_mmr_ocr_engine(CustomInjectedEngine())
