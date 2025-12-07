
import cv2
import numpy as np
import os

def create_synthetic_image(output_path: str, width: int = 512, height: int = 512):
    """
    Creates a synthetic image with a white background, one long vertical black line (barline),
    and one shorter vertical black line (stem).
    """
    # Create a white image (255)
    image = np.full((height, width, 3), 255, dtype=np.uint8)

    # Define colors
    black = (0, 0, 0)

    # Draw the long "barline"
    barline_x = width // 3
    cv2.line(image, (barline_x, 50), (barline_x, height - 50), black, 3)

    # Draw the shorter "stem"
    stem_x = (width * 2) // 3
    cv2.line(image, (stem_x, 150), (stem_x, height - 250), black, 2)

    # Ensure the output directory exists
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Save the image
    cv2.imwrite(output_path, image)
    print(f"Synthetic image saved to {output_path}")

if __name__ == "__main__":
    # Default path for the output image
    DEFAULT_OUTPUT_PATH = "data/workbench/synthetic_barline_test.png"
    create_synthetic_image(DEFAULT_OUTPUT_PATH)
