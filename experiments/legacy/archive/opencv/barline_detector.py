import os

import cv2
import numpy as np

DEBUG_OUTPUT_DIR = "/workspace/debug_outputs/"


def detect_barlines(image_path):
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not read image {image_path}")
        return []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # --- Preprocessing: Gaussian Blur for noise reduction ---
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)  # 5x5のカーネルでガウシアンブラー

    # --- Preprocessing: CLAHE for contrast enhancement ---
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced_contrast = clahe.apply(blurred)

    # 二値化 (Otsu's Binarization)
    _, binary = cv2.threshold(enhanced_contrast, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # --- 五線除去のための水平方向のカーネル ---
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (70, 1))
    staff_lines_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=3)

    # 五線を除去した画像を作成
    no_staff_img = cv2.subtract(binary, staff_lines_mask)

    # --- 垂直線の検出 (ハフ変換) ---
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 30))
    vertical_lines_img = cv2.morphologyEx(
        no_staff_img, cv2.MORPH_OPEN, vertical_kernel, iterations=1
    )

    # ハフ変換で直線検出
    lines = cv2.HoughLinesP(vertical_lines_img, 1, np.pi / 180, 20, minLineLength=5, maxLineGap=10)

    barlines = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            angle_rad = np.arctan2(y2 - y1, x2 - x1)
            angle_deg = np.degrees(angle_rad)

            is_vertical = abs(angle_deg) > 80 and abs(angle_deg) < 100

            if is_vertical and length > 30:
                barlines.append(((x1, y1), (x2, y2)))
                cv2.line(img, (x1, y1), (x2, y2), (0, 255, 0), 2)

    # デバッグ用に処理結果を保存
    cv2.imwrite(os.path.join(DEBUG_OUTPUT_DIR, "debug_gray.png"), gray)
    cv2.imwrite(os.path.join(DEBUG_OUTPUT_DIR, "debug_blurred.png"), blurred)
    cv2.imwrite(os.path.join(DEBUG_OUTPUT_DIR, "debug_enhanced_contrast.png"), enhanced_contrast)
    cv2.imwrite(os.path.join(DEBUG_OUTPUT_DIR, "debug_binary.png"), binary)
    cv2.imwrite(os.path.join(DEBUG_OUTPUT_DIR, "debug_staff_lines_mask.png"), staff_lines_mask)
    cv2.imwrite(os.path.join(DEBUG_OUTPUT_DIR, "debug_no_staff_img.png"), no_staff_img)
    cv2.imwrite(os.path.join(DEBUG_OUTPUT_DIR, "debug_vertical_lines_img.png"), vertical_lines_img)
    cv2.imwrite(os.path.join(DEBUG_OUTPUT_DIR, "debug_barlines_detected.png"), img)

    return barlines


if __name__ == "__main__":
    image_path = "/workspace/images/page_3.png"
    detected_barlines = detect_barlines(image_path)
    print(f"Detected {len(detected_barlines)} barlines.")
    for i, barline in enumerate(detected_barlines):
        print(f"Barline {i + 1}: {barline}")
