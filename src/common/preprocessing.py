import contextlib
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from src.common.model_artifacts import resolve_first_party_sr

FIRST_PARTY_SR_MODEL_NAME = "pdfscorebar_sr_x4"

logger = logging.getLogger(__name__)

IMAGE_SIZE_THRESHOLD_FOR_TILING = 1000
DEFAULT_TILE_SIZE = 400


def _env_flag_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@contextlib.contextmanager
def _perf_span(name: str, *, cuda: bool = False):
    """Use pipeline perf tracing only when the opt-in trace is enabled."""
    if not os.environ.get("PDFSCORE_PERF_TRACE_DIR"):
        yield
        return
    from src.pipeline.perf_trace import span

    with span(name, cuda=cuda):
        yield


class _RealESRGANTileLogFilter:
    """Drop Real-ESRGAN per-tile progress prints while forwarding other stdout."""

    def __init__(self, stream: Any) -> None:
        self.stream = stream
        self._pending = ""

    def write(self, text: str) -> int:
        self._pending += text
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            self._write_line(line + "\n")
        return len(text)

    def flush(self) -> None:
        if self._pending:
            self._write_line(self._pending)
            self._pending = ""
        self.stream.flush()

    def _write_line(self, line: str) -> None:
        stripped = line.strip()
        if stripped.startswith("Tile ") and "/" in stripped:
            return
        self.stream.write(line)


@contextlib.contextmanager
def _suppress_realesrgan_tile_logs():
    if _env_flag_enabled("PDFSCORE_SR_TILE_LOGS"):
        yield
        return
    stream = _RealESRGANTileLogFilter(sys.stdout)
    with contextlib.redirect_stdout(stream):
        try:
            yield
        finally:
            stream.flush()


def apply_vertical_closing(
    image: np.ndarray,
    kernel_height: int = 50,
    kernel_width: int = 1,
    binarize: bool = True,
    debug_dir: Optional[str] = None,
) -> np.ndarray:
    """
    Applies a vertical closing operation to an image to connect broken vertical lines.

    Args:
        image: The input image (NumPy array). Can be grayscale or BGR.
        kernel_height: The height of the morphological kernel. This should be chosen
                       based on the maximum expected gap between line segments.
        kernel_width: The width of the morphological kernel. This should be small
                      to avoid merging adjacent vertical lines.
        binarize: If True, applies Otsu's binarization to the image before the
                  morphological operation. Set to False if the input is already
                  binary or doesn't require it.
        debug_dir: If specified, saves intermediate images to this directory.

    Returns:
        The processed image, converted back to 3-channel BGR.
    """
    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)

    if image.ndim == 3 and image.shape[2] == 3:
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray_image = image

    if debug_dir:
        cv2.imwrite(os.path.join(debug_dir, "00_grayscale.png"), gray_image)

    if binarize:
        # Thresholding can help isolate the lines from the background.
        # THRESH_BINARY_INV is used assuming dark lines on a light background.
        _, processed_image = cv2.threshold(
            gray_image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        if debug_dir:
            cv2.imwrite(os.path.join(debug_dir, "01_binarized.png"), processed_image)
    else:
        processed_image = gray_image

    # Define a tall, thin kernel to close vertical gaps.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, kernel_height))

    # Apply the closing operation.
    closed_image = cv2.morphologyEx(processed_image, cv2.MORPH_CLOSE, kernel)

    if debug_dir:
        cv2.imwrite(os.path.join(debug_dir, "02_closed.png"), closed_image)

    # Invert the image back to dark lines on a light background if binarization was used.
    if binarize:
        final_processed_image = cv2.bitwise_not(closed_image)
        if debug_dir:
            cv2.imwrite(os.path.join(debug_dir, "03_inverted.png"), final_processed_image)
    else:
        final_processed_image = closed_image

    # Convert back to a 3-channel BGR format, as this is a common input
    # format for many computer vision models.
    final_image = cv2.cvtColor(final_processed_image, cv2.COLOR_GRAY2BGR)

    if debug_dir:
        cv2.imwrite(os.path.join(debug_dir, "99_final_output.png"), final_image)

    return final_image


def apply_super_resolution(
    image: np.ndarray, model_path: str, model_name: str, scale: int
) -> np.ndarray:
    """
    Applies super-resolution to an image using OpenCV's dnn_superres module.
    (Legacy/Lightweight models like FSRCNN).
    """
    sr = cv2.dnn_superres.DnnSuperResImpl_create()
    sr.readModel(str(model_path))
    sr.setModel(model_name, scale)

    if image.ndim != 3 or image.shape[2] != 3:
        logger.info("Input image is not 3-channel, converting to BGR for super-resolution.")
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

    logger.info("Upscaling image by factor of %s using %s...", scale, model_name)
    result = sr.upsample(image)
    logger.info("Upscaling complete.")

    return result


def apply_advanced_sr(
    image: np.ndarray,
    model_name: str = "pdfscorebar_sr_x4",
    scale: int = 4,
    tile: Optional[int] = None,
    tile_pad: int = 10,
    pre_pad: int = 0,
    fp32: bool = False,
    upsampler: Optional[Any] = None,
    *,
    strict: bool = False,
) -> Any:
    """
    Applies advanced super-resolution using the installed Real-ESRGAN runtime.

    Args:
        image: Input image (BGR numpy array).
        model_name: only "pdfscorebar_sr_x4" (first-party x4 model, Issue #533).
        scale: Upscale factor (default 4).
        tile: Tile size for processing (0 for auto/none).
        tile_pad: Padding for tiles.
        pre_pad: Pre-padding.
        fp32: If True, uses full precision (fp32). If False, tries to use fp16 on CUDA.
        upsampler: Pre-initialized RealESRGANer instance.
        strict: Propagate dependency/model/inference errors instead of returning the input.

    Returns:
        Upscaled image (if upsampler was provided) OR Tuple[Upscaled image, upsampler].
        For backward compatibility, it returns just the image if upsampler was provided.
    """
    try:
        with _perf_span("sr_worker.realesrgan_heavy_imports"):
            import torch

            from src.third_party.realesrgan_sr import RealESRGANer, RRDBNet
    except ImportError as e:
        if strict:
            raise
        logger.error("Error importing Real-ESRGAN dependencies: %s", e)
        logger.error("The vendored src.third_party.realesrgan_sr runtime is unavailable.")
        return image, upsampler

    # Check device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    if upsampler is None:
        with _perf_span("sr_worker.realesrgan_model_initialization", cuda=True):
            logger.info("Initializing Real-ESRGAN (%s) using device: %s", model_name, device)
            if model_name != FIRST_PARTY_SR_MODEL_NAME or scale != 4:
                # Issue #533: the Real-ESRGAN x4plus/x2plus release weights were removed.
                # Only the first-party x4 model exists; there is no x2 model.
                if strict:
                    raise ValueError(
                        f"Unsupported SR model/scale: {model_name} x{scale}; "
                        f"only {FIRST_PARTY_SR_MODEL_NAME} x4 is available"
                    )
                logger.error(
                    "Unsupported SR model/scale %s x%s; returning input.", model_name, scale
                )
                return image, upsampler
            try:
                sr_model = resolve_first_party_sr(project_root=Path(__file__).resolve().parents[2])
            except Exception as e:
                if strict:
                    raise
                logger.error("First-party SR model unavailable: %s", e)
                return image, upsampler
            model = RRDBNet(**sr_model.rrdbnet_kwargs())
            netscale = sr_model.scale
            model_path = str(sr_model.path)

            if strict and not Path(model_path).is_file():
                raise FileNotFoundError(f"SR model weight not found: {model_path}")

            try:
                # Determine tiling strategy
                if tile is None or tile == -1:
                    tile_size = (
                        0
                        if max(image.shape[:2]) <= IMAGE_SIZE_THRESHOLD_FOR_TILING
                        else DEFAULT_TILE_SIZE
                    )
                else:
                    tile_size = tile

                # Determine precision
                use_half = False
                if "cuda" in str(device) and not fp32:
                    use_half = True

                upsampler = RealESRGANer(
                    scale=netscale,
                    model_path=model_path,
                    model=model,
                    tile=tile_size,
                    tile_pad=tile_pad,
                    pre_pad=pre_pad,
                    half=use_half,
                    device=device,
                )
            except Exception as e:
                if strict:
                    raise
                logger.error("Real-ESRGAN initialization failed: %s", e)
                return image, upsampler

    try:
        if image.ndim != 3 or image.shape[2] != 3:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

        with _perf_span("sr_worker.synchronized_enhance", cuda=True):
            with _suppress_realesrgan_tile_logs():
                output, _ = upsampler.enhance(image, outscale=scale)
        return output, upsampler
    except Exception as e:
        if strict:
            raise
        logger.error("Real-ESRGAN inference failed: %s", e)
        return image, upsampler
