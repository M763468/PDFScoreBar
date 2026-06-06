from src.pipeline.steps import numbering


class MMROCREngine:
    pass


class CustomInjectedEngine:
    pass


def test_should_replace_absent_engine():
    assert numbering._should_replace_mmr_ocr_engine(None)


def test_should_replace_default_named_engine():
    assert numbering._should_replace_mmr_ocr_engine(MMROCREngine())


def test_should_preserve_custom_injected_engine():
    assert not numbering._should_replace_mmr_ocr_engine(CustomInjectedEngine())
