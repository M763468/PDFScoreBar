from pathlib import Path


RUNNER = Path("tools/issue277/run_production_mmr_full68.py")


def test_production_full68_runner_uses_mmr_processor_directly():
    source = RUNNER.read_text(encoding="utf-8")

    assert "from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor" in source
    assert "processor = MMRProcessor(" in source
    assert "TargetedRetryProcessor" not in source
    assert '"processor_class": "src.measure_numbering.mmr.MMRProcessor"' in source
    assert '"targeted_retry_processor_used": False' in source
