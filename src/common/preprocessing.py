import os
import sys
from typing import Optional

import cv2
import numpy as np


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
        print("Input image is not 3-channel, converting to BGR for super-resolution.")
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

    print(f"Upscaling image by factor of {scale} using {model_name}...")
    result = sr.upsample(image)
    print("Upscaling complete.")

    return result


def apply_advanced_sr(
    image: np.ndarray,
    model_name: str = "RealESRGAN_x4plus",
    scale: int = 4,
    tile: Optional[int] = None,
    tile_pad: int = 10,
    pre_pad: int = 0,
    fp32: bool = False,
) -> np.ndarray:
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

    Returns:
        Upscaled image.
    """
    # Add the cloned repo to the path to ensure local source is used
    realesrgan_path = os.path.abspath(os.path.join(__file__, "../../..", "external", "realesrgan"))
    if realesrgan_path not in sys.path:
        sys.path.insert(0, realesrgan_path)

    try:
        import torch
        from basicsr.archs.rrdbnet_arch import RRDBNet
        from realesrgan import RealESRGANer
    except ImportError as e:
        print(f"Error importing Real-ESRGAN dependencies from local source: {e}")
        print(
            "Please ensure you have cloned the repository to 'external/realesrgan' and installed its requirements."
        )
        return image

    # Check device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Real-ESRGAN using device: {device}")

    # The RealESRGANer will handle model download and caching automatically
    # when model_path is not specified. It looks for models in the 'weights' directory.
    if model_name == "RealESRGAN_x4plus":
        model = RRDBNet(
            num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4
        )
        netscale = 4
        # The local RealESRGANer implementation expects a file path.
        # We construct the path to where the model should be. It will be downloaded
        # by the library if it doesn't exist.
        model_path = os.path.join(realesrgan_path, "weights", f"{model_name}.pth")
    else:
        print(
            f"Model {model_name} not explicitly supported. A default will be used, but may not be optimal."
        )
        model = RRDBNet(
            num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4
        )
        netscale = 4
        model_path = os.path.join(realesrgan_path, "weights", "RealESRGAN_x4plus.pth")  # Fallback

    try:
        # Determine tiling strategy
        if tile is None or tile == -1:
            # Default auto logic
            # tile=0 processes the whole image at once and can be extremely slow / OOM on large pages.
            # Use a conservative tiling default for large inputs while keeping the original behaviour for small images.
            tile_size = 0 if max(image.shape[:2]) <= 1000 else 512
        else:
            tile_size = tile

        # Determine precision
        # half=True means fp16. So if fp32 is requested, half should be False.
        # Also ensure device is cuda for half.
        use_half = False
        if "cuda" in str(device) and not fp32:
            use_half = True

        upsampler = RealESRGANer(
            scale=netscale,
            model_path=model_path,  # Pass None to let it use its default model download logic
            model=model,
            tile=tile_size,
            tile_pad=tile_pad,
            pre_pad=pre_pad,
            half=use_half,
            device=device,
        )

        # The upsampler expects the model file in its `weights` dir. Let's trigger a download if needed.
        # This is a bit of a hack, but it forces the download if the file isn't there.
        if not os.path.exists(os.path.join(realesrgan_path, "weights", f"{model_name}.pth")):
            print("Model not found locally, RealESRGANer will attempt to download it...")
            # The constructor should handle this, but let's be explicit.
            pass

        if image.ndim != 3 or image.shape[2] != 3:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

        print(
            f"DEBUG: Calling enhance with tile={tile_size}, tile_pad={tile_pad}, pre_pad={pre_pad}, half={use_half}"
        )
        output, _ = upsampler.enhance(image, outscale=scale)
        return output
    except Exception as e:
        print(f"Real-ESRGAN inference failed: {e}")
        return image
