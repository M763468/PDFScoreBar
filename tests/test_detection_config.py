import importlib.util
from pathlib import Path


def load_detection_config():
    path = Path(__file__).resolve().parents[1] / "src/pipeline/detection/config.py"
    spec = importlib.util.spec_from_file_location("detection_config_under_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cnn_apply_nms_defaults_to_false():
    config = load_detection_config()

    assert config.DEFAULT_CNN_APPLY_NMS is False
    assert config.get_cnn_apply_nms({}) is False


def test_cnn_apply_nms_can_opt_in():
    config = load_detection_config()

    assert config.get_cnn_apply_nms({"cnn_apply_nms": True}) is True
