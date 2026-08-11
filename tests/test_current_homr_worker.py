from src.pipeline.detection.current_homr_worker import _build_processing_config


def test_processing_config_without_gpu_field_uses_five_arguments() -> None:
    captured = {}

    class LegacyProcessingConfig:
        def __init__(self, *args):
            captured["args"] = args

    _build_processing_config(
        LegacyProcessingConfig,
        enable_debug=True,
        enable_cache=True,
        write_staff_positions=False,
        use_gpu_inference=True,
    )

    assert captured["args"] == (True, True, False, False, -1)


def test_processing_config_with_gpu_field_uses_six_arguments() -> None:
    captured = {}

    class NewProcessingConfig:
        use_gpu_inference = False

        def __init__(self, *args):
            captured["args"] = args

    _build_processing_config(
        NewProcessingConfig,
        enable_debug=True,
        enable_cache=False,
        write_staff_positions=True,
        use_gpu_inference=True,
    )

    assert captured["args"] == (True, False, True, False, -1, True)
