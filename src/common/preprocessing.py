import logging
import os
from typing import Any, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

IMAGE_SIZE_THRESHOLD_FOR_TILING = 1000
DEFAULT_TILE_SIZE = 400


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
    model_name: str = "RealESRGAN_x2plus",
    scale: int = 2,
    tile: Optional[int] = None,
    tile_pad: int = 10,
    pre_pad: int = 0,
    fp32: bool = False,
    upsampler: Optional[Any] = None,
) -> Any:
    """
    Applies advanced super-resolution using a locally cloned Real-ESRGAN repository.

    Args:
        image: Input image (BGR numpy array).
        model_name: "RealESRGAN_x4plus" or other supported models.
        scale: Upscale factor (default 4).
        tile: Tile size for processing (0 for auto/none).
        tile_pad: Padding for tiles.
        pre_pad: Pre-padding.
        fp32: If True, uses full precision (fp32). If False, tries to use fp16 on CUDA.
        upsampler: Pre-initialized RealESRGANer instance.

    Returns:
        Upscaled image (if upsampler was provided) OR Tuple[Upscaled image, upsampler].
        For backward compatibility, it returns just the image if upsampler was provided.
    """
    realesrgan_path = os.path.abspath(os.path.join(__file__, "../../..", "external", "realesrgan"))
    try:
        import torch
        from basicsr.archs.rrdbnet_arch import RRDBNet
        from realesrgan import RealESRGANer
    except ImportError as e:
        logger.error("Error importing Real-ESRGAN dependencies: %s", e)
        logger.error("Please ensure you have installed the realesrgan package.")
        return image, upsampler

    # Check device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    if upsampler is None:
        logger.info("Initializing Real-ESRGAN (%s) using device: %s", model_name, device)
        if model_name == "RealESRGAN_x4plus":
            model = RRDBNet(
                num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4
            )
            netscale = 4
            model_path = os.path.join(realesrgan_path, "weights", f"{model_name}.pth")
        elif model_name == "RealESRGAN_x2plus":
            model = RRDBNet(
                num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=2
            )
            netscale = 2
            model_path = os.path.join(realesrgan_path, "weights", f"{model_name}.pth")
        else:
            logger.warning(
                "Model %s not explicitly supported. A default (x2plus) will be used.",
                model_name,
            )
            model = RRDBNet(
                num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=2
            )
            netscale = 2
            model_path = os.path.join(realesrgan_path, "weights", "RealESRGAN_x2plus.pth")

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
            logger.error("Real-ESRGAN initialization failed: %s", e)
            return image, upsampler

    try:
        if image.ndim != 3 or image.shape[2] != 3:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

        output, _ = upsampler.enhance(image, outscale=scale)
        return output, upsampler
    except Exception as e:
        logger.error("Real-ESRGAN inference failed: %s", e)
        return image, upsampler
