from pathlib import Path

from tools.issue255.bootstrap_homr_models import invoke_download_weights, model_artifact


def test_invoke_download_weights_supports_known_homr_apis() -> None:
    calls: list[tuple[bool, ...]] = []

    def historical() -> None:
        calls.append(())

    def single(use_gpu_inference: bool) -> None:
        calls.append((use_gpu_inference,))

    def current(segnet_use_gpu: bool, transformer_use_gpu: bool, coreml_encoder: bool) -> None:
        calls.append((segnet_use_gpu, transformer_use_gpu, coreml_encoder))

    assert invoke_download_weights(historical)["arguments"] == []
    assert invoke_download_weights(single)["arguments"] == [True]
    assert invoke_download_weights(current)["arguments"] == [True, True, False]
    assert calls == [(), (True,), (True, True, False)]


def test_model_artifact_records_hash_and_size(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"issue255-homr-model")

    artifact = model_artifact(model)

    assert artifact["path"] == str(model.resolve())
    assert artifact["size_bytes"] == len(b"issue255-homr-model")
    assert len(artifact["sha256"]) == 64
