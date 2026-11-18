from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest


class ReachedHomrInference(Exception):
    pass


@pytest.fixture
def evaluation(tmp_path, monkeypatch):
    evaluator = pytest.importorskip("src.homr_eval_scripts.homr_evaluator", exc_type=ImportError)
    image = tmp_path / "page.png"
    assert cv2.imwrite(str(image), np.zeros((8, 12, 3), dtype=np.uint8))
    output = tmp_path / "runs"

    def stop_before_homr(message):
        if message.startswith("Phase 2:"):
            raise ReachedHomrInference

    monkeypatch.setattr(evaluator, "download_weights", Mock())
    monkeypatch.setattr(evaluator, "eprint", stop_before_homr)
    return evaluator, ["--images", str(image), "--output-root", str(output)], output


@pytest.mark.parametrize("scale", ["2", "3"])
def test_unsupported_inference_scale_rejected_before_evaluation(evaluation, capsys, scale):
    evaluator, argv, output = evaluation
    with pytest.raises(SystemExit) as error:
        evaluator.run_evaluation([*argv, "--enable-sr", "--sr-scale", scale])
    assert error.value.code == 2
    assert f"--sr-scale {scale} is unsupported" in capsys.readouterr().err
    evaluator.download_weights.assert_not_called()
    assert not output.exists()


@pytest.mark.parametrize("failure", [None, "inference", "unchanged", "wrong_height", "write"])
def test_x4_inference_requires_strict_success(evaluation, monkeypatch, failure):
    evaluator, argv, output = evaluation
    upsampler = object()
    shape = {"unchanged": (8, 12), "wrong_height": (16, 48)}.get(failure, (32, 48))
    apply_sr = Mock(return_value=(np.zeros((*shape, 3), dtype=np.uint8), upsampler))
    monkeypatch.setattr(evaluator, "apply_advanced_sr", apply_sr)
    args = [*argv, "--enable-sr"]

    if failure == "inference":
        apply_sr.side_effect = RuntimeError("inference failed")
    elif failure == "write":
        monkeypatch.setattr(evaluator.cv2, "imwrite", lambda *_: False)

    if failure is None:
        with pytest.raises(ReachedHomrInference):
            evaluator.run_evaluation(args)
        assert cv2.imread(str(next(output.rglob("page.png")))).shape[:2] == (32, 48)
    else:
        expected_error = {
            "inference": "inference failed",
            "unchanged": "expected",
            "wrong_height": "expected",
            "write": "Failed to write SR output",
        }
        with pytest.raises(RuntimeError, match=expected_error[failure]):
            evaluator.run_evaluation(args)

    assert apply_sr.call_count == 1
    assert apply_sr.call_args.kwargs["strict"] is True
    assert apply_sr.call_args.kwargs["scale"] == 4


@pytest.mark.parametrize("precomputed", [False, True])
def test_scale_is_unused_without_sr_inference(evaluation, monkeypatch, precomputed):
    evaluator, argv, output = evaluation
    apply_sr = Mock(side_effect=AssertionError("unexpected SR inference"))
    monkeypatch.setattr(evaluator, "apply_advanced_sr", apply_sr)
    args = [*argv, "--sr-scale", "2"]
    expected_shape = (8, 12)
    if precomputed:
        image = Path(output.parent) / "precomputed.png"
        expected_shape = (16, 24)
        assert cv2.imwrite(str(image), np.zeros((*expected_shape, 3), dtype=np.uint8))
        args.extend(["--enable-sr", "--pre-computed-sr", str(image)])

    with pytest.raises(ReachedHomrInference):
        evaluator.run_evaluation(args)
    apply_sr.assert_not_called()
    assert cv2.imread(str(next(output.rglob("page.png")))).shape[:2] == expected_shape
