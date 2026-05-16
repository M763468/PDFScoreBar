from src.pipeline.detection.config import DEFAULT_CNN_APPLY_NMS, get_cnn_apply_nms


def test_cnn_apply_nms_defaults_to_false():
    assert DEFAULT_CNN_APPLY_NMS is False
    assert get_cnn_apply_nms({}) is False


def test_cnn_apply_nms_can_opt_in():
    assert get_cnn_apply_nms({"cnn_apply_nms": True}) is True
