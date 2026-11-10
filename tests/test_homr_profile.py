from src.pipeline.detection.maintained_profile import PROFILE_PATH
from src.pipeline.detection.profile_contract import load_profile_manifest


def load_homr_profile(name):
    return load_profile_manifest(name, PROFILE_PATH)


def test_maintained_original_profile_is_immutable_and_original_space() -> None:
    profile = load_homr_profile("maintained_original")

    assert profile["historical_detector_artifact_runtime_input"] is False
    assert profile["homr"]["commit"] == "457e7c6518a10ba755db2e60883419e56c4d7369"
    assert profile["input_contract"] == {
        "sr_scale": 1,
        "coordinate_space": "original_page",
        "connector_capture": True,
    }
    assert profile["production_dispatch"]["floating_upstream"] is False
