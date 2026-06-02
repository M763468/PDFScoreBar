"""Patch the pinned HOMR ONNX provider options used in the Docker image.

Issue #172 showed that the pinned HOMR transformer fp16 encoder emits
ONNX Runtime CUDA Conv fallback warnings when `cudnn_conv_algo_search` is
`DEFAULT`. The Stage E smoke comparison found that `HEURISTIC` removes the
warning while keeping the change limited to HOMR ONNX provider options.
"""

from pathlib import Path

import homr


HOMR_ROOT = Path(homr.__file__).resolve().parent
ENCODER_PATH = HOMR_ROOT / "transformer" / "encoder_inference.py"
DECODER_PATH = HOMR_ROOT / "transformer" / "decoder_inference.py"


ENCODER_OLD = '''providers=[
                        (
                            "CUDAExecutionProvider",
                            {
                                "cudnn_conv_algo_search": "DEFAULT",
                            },
                        )
                    ],'''

ENCODER_NEW = '''providers=[
                        (
                            "CUDAExecutionProvider",
                            {
                                "cudnn_conv_algo_search": "HEURISTIC",
                            },
                        ),
                        "CPUExecutionProvider",
                    ],'''

DECODER_OLD = 'config.filepaths.decoder_path_fp16, providers=["CUDAExecutionProvider"]'

DECODER_NEW = (
    'config.filepaths.decoder_path_fp16, '
    'providers=[("CUDAExecutionProvider", {"cudnn_conv_algo_search": "HEURISTIC"}), '
    '"CPUExecutionProvider"]'
)


def replace_exact(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected HOMR patch target not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    replace_exact(ENCODER_PATH, ENCODER_OLD, ENCODER_NEW)
    replace_exact(DECODER_PATH, DECODER_OLD, DECODER_NEW)
    print("Patched HOMR transformer ONNX CUDA provider options to HEURISTIC")


if __name__ == "__main__":
    main()
