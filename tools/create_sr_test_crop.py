import os

import cv2

IMAGE_PATH = "/workspace/data/evaluation/images/page_3.png"
OUTPUT_PATH = "/workspace/data/workbench/sr_test_crop.png"


def create_crop():
    if not os.path.exists(IMAGE_PATH):
        print(f"Error: {IMAGE_PATH} not found.")
        return

    img = cv2.imread(IMAGE_PATH)
    if img is None:
        print(f"Error: Could not read {IMAGE_PATH}.")
        return

    # Crop a region that likely has barlines and notes.
    # Arbitrary choice: 500x500 area from (500, 500)
    h, w = img.shape[:2]
    crop = img[500:1000, 500:1000]

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    cv2.imwrite(OUTPUT_PATH, crop)
    print(f"Created crop at {OUTPUT_PATH}")


if __name__ == "__main__":
    create_crop()
