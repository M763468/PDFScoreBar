import cv2
import numpy as np
import os
from typing import Optional

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


def apply_super_resolution(image: np.ndarray, model_path: str, model_name: str, scale: int) -> np.ndarray:
    """
    Applies super-resolution to an image using OpenCV's dnn_superres module.

    Args:
        image: The input image (NumPy array).
        model_path: Path to the pre-trained super-resolution model file.
        model_name: The name of the model algorithm (e.g., 'fsrcnn').
        scale: The upscale factor (e.g., 2, 3, 4).

    Returns:
        The upscaled image as a NumPy array.
    """
    sr = cv2.dnn_superres.DnnSuperResImpl_create()
    sr.readModel(str(model_path))
    sr.setModel(model_name, scale)
    
    # Check if the image has 3 channels, if not, convert it.
    # DNN SuperRes models typically expect 3-channel BGR images.
    if image.ndim != 3 or image.shape[2] != 3:
        # Convert grayscale to BGR
        print("Input image is not 3-channel, converting to BGR for super-resolution.")
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

    print(f"Upscaling image by factor of {scale} using {model_name}...")
    result = sr.upsample(image)
    print("Upscaling complete.")
    
    return result