import cv2
import numpy as np
import os

# --- Configuration ---
DEBUG_OUTPUT_DIR = "/workspace/debug_outputs/"
os.makedirs(DEBUG_OUTPUT_DIR, exist_ok=True)

def plot_projection(profile, title):
    """Creates an image of the projection profile for debugging."""
    h, w = 400, len(profile)
    img = np.zeros((h, w), dtype=np.uint8)
    # Normalize profile for visualization
    max_val = np.max(profile)
    if max_val == 0: return # Avoid division by zero if profile is all zeros
    profile_normalized = (profile / max_val * (h * 0.9)).astype(int)

    for x, value in enumerate(profile_normalized):
        cv2.line(img, (x, h), (x, h - value), 255, 1)
    
    cv2.imwrite(os.path.join(DEBUG_OUTPUT_DIR, f"debug_projection_{title}.png"), img)

# --- OpenCV-based Vertical Line Detection (Vertical Projection Profile) ---
def detect_vertical_line_candidates(image_path):
    """
    Uses a vertical projection profile on the original binary image to find vertical lines.
    This approach avoids staff line removal, which can be destructive.
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not read image {image_path}")
        return [], None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # --- Preprocessing: Invert and Binarize ---
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2
    )
    cv2.imwrite(os.path.join(DEBUG_OUTPUT_DIR, "debug_detector_binary.png"), binary)

    # --- Staff Line Removal (DISABLED) ---
    # This step is disabled to prevent destruction of barline data.
    # We now perform projection on the full binary image.

    # --- Calculate Vertical Projection Profile on the original binary image ---
    projection = np.sum(binary // 255, axis=0)
    plot_projection(projection, "vertical_with_staff")

    # --- Find Peaks in the Profile ---
    img_height = img.shape[0]
    # Threshold is set higher to distinguish barlines from shorter elements like note stems.
    peak_threshold = img_height * 0.1
    peak_indices = np.where(projection > peak_threshold)[0]

    if len(peak_indices) == 0:
        return [], img

    # --- Group consecutive peak indices ---
    grouped_peaks = []
    current_group = [peak_indices[0]]
    for i in range(1, len(peak_indices)):
        if peak_indices[i] == peak_indices[i-1] + 1:
            current_group.append(peak_indices[i])
        else:
            if current_group:
                grouped_peaks.append(current_group)
            current_group = [peak_indices[i]]
    if current_group:
        grouped_peaks.append(current_group)

    candidate_x_coords = [int(np.mean(group)) for group in grouped_peaks]

    # --- Extract line segments from candidate x-coordinates ---
    candidates = []
    min_line_height = img_height * 0.1 # Increased min height to filter out shorter lines

    for x in candidate_x_coords:
        # Use the original binary image for segment extraction
        column = binary[:, x]
        # Find vertical runs of white pixels
        diff = np.diff(np.concatenate(([0], column, [0])))
        run_starts = np.where(diff > 0)[0]
        run_ends = np.where(diff < 0)[0]

        if len(run_starts) > 0 and len(run_ends) > 0:
             # Sometimes the first run_end is before the first run_start, so we align them
            if run_ends[0] < run_starts[0]:
                run_ends = run_ends[1:]
            if len(run_starts) > len(run_ends):
                run_starts = run_starts[:len(run_ends)]

            for y_start, y_end in zip(run_starts, run_ends):
                height = y_end - y_start
                if height > min_line_height:
                    # Add the full-height line segment as a candidate
                    candidates.append(((x, 0), (x, img_height)))
                    # We only need one candidate per x-coordinate since we assume it's a barline
                    break 

    return candidates, img

# --- Main execution block for standalone testing ---
if __name__ == "__main__":
    image_path = "/workspace/data/input_images/page_3.png"
    output_image_path = "/workspace/debug_outputs/opencv_candidates_visualization.png"
    
    print(f"1. Detecting vertical line candidates in {image_path} using Vertical Projection with Staff Removal...")
    candidates, original_img = detect_vertical_line_candidates(image_path)
    
    if original_img is None:
        print("Exiting due to image loading error.")
    else:
        print(f"\n2. Found {len(candidates)} final candidates.")

        img_with_candidates = original_img.copy()
        for i, ((x1, y1), (x2, y2)) in enumerate(candidates):
            cv2.line(img_with_candidates, (x1, y1), (x2, y2), (0, 255, 0), 2)

        cv2.imwrite(output_image_path, img_with_candidates)
        print(f"3. Saved visualization with detected candidates to {output_image_path}")
