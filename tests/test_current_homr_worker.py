from types import SimpleNamespace

import pytest

from src.pipeline.detection.current_support_worker import PROJECT_ROOT, _build_worker_environment
from src.pipeline.detection.homr_profile_compat import (
    build_processing_config_compat,
    install_current_homr_consumer_compat,
)


def test_processing_config_without_gpu_field_uses_five_arguments() -> None:
    captured = {}

    class LegacyProcessingConfig:
        def __init__(
            self,
            enable_debug,
            enable_cache,
            write_staff_positions,
            read_staff_positions,
            selected_staff,
        ):
            captured["args"] = (
                enable_debug,
                enable_cache,
                write_staff_positions,
                read_staff_positions,
                selected_staff,
            )

    build_processing_config_compat(
        LegacyProcessingConfig,
        enable_debug=True,
        enable_cache=True,
        write_staff_positions=False,
        use_gpu_inference=True,
    )

    assert captured["args"] == (True, True, False, False, -1)


def test_processing_config_with_gpu_field_uses_six_arguments() -> None:
    captured = {}

    class CurrentProcessingConfig:
        def __init__(
            self,
            enable_debug,
            enable_cache,
            write_staff_positions,
            read_staff_positions,
            selected_staff,
            use_gpu_inference,
        ):
            captured["args"] = (
                enable_debug,
                enable_cache,
                write_staff_positions,
                read_staff_positions,
                selected_staff,
                use_gpu_inference,
            )

    build_processing_config_compat(
        CurrentProcessingConfig,
        enable_debug=True,
        enable_cache=False,
        write_staff_positions=True,
        use_gpu_inference=True,
    )

    assert captured["args"] == (True, False, True, False, -1, True)


def test_consumer_compat_adapts_legacy_bound_symbols() -> None:
    calls = {}

    def legacy_download_weights() -> None:
        calls["download"] = True

    def legacy_load_predictions(image_path, enable_debug, enable_cache):
        calls["load"] = (image_path, enable_debug, enable_cache)
        return "predictions"

    def legacy_parse_staffs(debug, staffs, image, selected_staff=-1):
        calls["parse"] = (debug, staffs, image, selected_staff)
        return "staffs"

    predictor_module = SimpleNamespace(download_weights=legacy_download_weights)
    heuristics_module = SimpleNamespace(load_and_preprocess_predictions=legacy_load_predictions)
    homr_main = SimpleNamespace(parse_staffs=legacy_parse_staffs)

    modes = install_current_homr_consumer_compat(
        homr_main,
        predictor_module,
        heuristics_module,
        use_gpu_inference=True,
    )

    predictor_module.download_weights(True)
    assert (
        heuristics_module.load_and_preprocess_predictions("page.png", True, False, True)
        == "predictions"
    )
    assert (
        homr_main.parse_staffs("debug", "staffs", "image", object(), selected_staff=3) == "staffs"
    )

    assert calls == {
        "download": True,
        "load": ("page.png", True, False),
        "parse": ("debug", "staffs", "image", 3),
    }
    assert modes == {
        "download_weights_mode": "native_zero_argument",
        "load_predictions_mode": "native_without_gpu_argument",
        "parse_staffs_mode": "native_without_config_argument",
    }


def test_consumer_compat_preserves_current_bound_symbols() -> None:
    calls = {}

    def current_download_weights(use_gpu_inference) -> None:
        calls["download"] = use_gpu_inference

    def current_load_predictions(image_path, enable_debug, enable_cache, use_gpu_inference):
        calls["load"] = (image_path, enable_debug, enable_cache, use_gpu_inference)
        return "predictions"

    def current_parse_staffs(debug, staffs, image, config, selected_staff=-1):
        calls["parse"] = (
            debug,
            staffs,
            image,
            config.use_gpu_inference,
            selected_staff,
        )
        return "staffs"

    class Config:
        use_gpu_inference = False

    predictor_module = SimpleNamespace(download_weights=current_download_weights)
    heuristics_module = SimpleNamespace(load_and_preprocess_predictions=current_load_predictions)
    homr_main = SimpleNamespace(parse_staffs=current_parse_staffs)

    modes = install_current_homr_consumer_compat(
        homr_main,
        predictor_module,
        heuristics_module,
        use_gpu_inference=True,
    )

    predictor_module.download_weights(True)
    assert (
        heuristics_module.load_and_preprocess_predictions("page.png", False, True, True)
        == "predictions"
    )
    assert (
        homr_main.parse_staffs("debug", "staffs", "image", Config(), selected_staff=2) == "staffs"
    )

    assert calls == {
        "download": True,
        "load": ("page.png", False, True, True),
        "parse": ("debug", "staffs", "image", True, 2),
    }
    assert modes == {
        "download_weights_mode": "gpu_argument_injected",
        "load_predictions_mode": "gpu_argument_injected_when_missing",
        "parse_staffs_mode": "transformer_config_injected_when_missing",
    }


def test_consumer_parse_staffs_does_not_swallow_internal_type_error() -> None:
    def current_download_weights(use_gpu_inference) -> None:
        del use_gpu_inference

    def current_load_predictions(image_path, enable_debug, enable_cache, use_gpu_inference):
        del image_path, enable_debug, enable_cache, use_gpu_inference

    def broken_parse_staffs(debug, staffs, image, config, selected_staff=-1):
        del debug, staffs, image, config, selected_staff
        raise TypeError("internal parse failure")

    class Config:
        use_gpu_inference = False

    predictor_module = SimpleNamespace(download_weights=current_download_weights)
    heuristics_module = SimpleNamespace(load_and_preprocess_predictions=current_load_predictions)
    homr_main = SimpleNamespace(parse_staffs=broken_parse_staffs)

    install_current_homr_consumer_compat(
        homr_main,
        predictor_module,
        heuristics_module,
        use_gpu_inference=False,
    )

    with pytest.raises(TypeError, match="internal parse failure"):
        homr_main.parse_staffs("debug", "staffs", "image", Config(), selected_staff=-1)


def test_consumer_compat_is_idempotent_for_already_wrapped_symbols() -> None:
    calls = {"download": 0}

    def legacy_download_weights() -> None:
        calls["download"] += 1

    def legacy_load_predictions(image_path, enable_debug, enable_cache):
        return image_path, enable_debug, enable_cache

    def legacy_parse_staffs(debug, staffs, image, selected_staff=-1):
        return debug, staffs, image, selected_staff

    predictor_module = SimpleNamespace(download_weights=legacy_download_weights)
    heuristics_module = SimpleNamespace(load_and_preprocess_predictions=legacy_load_predictions)
    homr_main = SimpleNamespace(parse_staffs=legacy_parse_staffs)

    install_current_homr_consumer_compat(
        homr_main,
        predictor_module,
        heuristics_module,
        use_gpu_inference=True,
    )
    install_current_homr_consumer_compat(
        homr_main,
        predictor_module,
        heuristics_module,
        use_gpu_inference=True,
    )

    predictor_module.download_weights(True)
    assert calls["download"] == 1


def test_current_worker_environment_removes_homr_shadow_paths() -> None:
    workspace_homr = str(PROJECT_ROOT / "homr")
    external_homr = str(PROJECT_ROOT / "external" / "homr")
    base_env = {
        "PYTHONPATH": ":".join(
            [
                external_homr,
                workspace_homr,
                "/opt/homr_stage_e_profile",
                "/opt/pdfscore_stage_e_profile/src",
                "/keep-me",
            ]
        ),
        "OTHER": "value",
    }

    env = _build_worker_environment(base_env)
    entries = env["PYTHONPATH"].split(":")

    assert entries[0] == str(PROJECT_ROOT)
    assert external_homr not in entries
    assert workspace_homr not in entries
    assert "/opt/homr_stage_e_profile" not in entries
    assert "/opt/pdfscore_stage_e_profile/src" not in entries
    assert "/keep-me" in entries
    assert env["OTHER"] == "value"
