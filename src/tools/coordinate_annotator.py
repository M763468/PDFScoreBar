import cv2
import json
import os

# --- Configuration ---
IMAGE_PATH = "data/training/images/page_1.png"
GROUND_TRUTH_OUTPUT_PATH = "data/training/annotations/page_001/raw_boxes.json"
BARLINE_RECT_WIDTH = 5  # Width of the rectangle when converting a line to a box
MAX_DISPLAY_WIDTH = 1200 # Maximum width for display
MAX_DISPLAY_HEIGHT = 800 # Maximum height for display

# --- Global Variables ---
original_img = None # Stores the original high-resolution image
display_img = None  # Stores the image resized for display
drawing_display_img = None # Image for drawing annotations on display_img
scale_factor = 1.0  # Scale factor from original to display size
annotations = []  # List of {'type': 'barline', 'coords': [x1, y1, x2, y2]} (original coords)
current_points = [] # Stores the two clicks for a single annotation (display coords)

# --- Mouse Callback Function ---
def mouse_callback(event, x, y, flags, param):
    global original_img, display_img, drawing_display_img, annotations, current_points, scale_factor

    if event == cv2.EVENT_LBUTTONDOWN:
        # Convert display coords to original coords
        x_original = int(x / scale_factor)
        y_original = int(y / scale_factor)
        current_points.append((x_original, y_original))

        if len(current_points) == 2:
            # Two points clicked, form a line and convert to rect
            p1_orig = current_points[0]
            p2_orig = current_points[1]

            # Ensure y_min is top, y_max is bottom for consistent rect definition
            y_min = min(p1_orig[1], p2_orig[1])
            y_max = max(p1_orig[1], p2_orig[1])

            # For a vertical line, x_start and x_end are close to the clicked x
            # We use the average x for the center of the barline
            x_center = (p1_orig[0] + p2_orig[0]) // 2
            x_start = x_center - BARLINE_RECT_WIDTH // 2
            x_end = x_center + BARLINE_RECT_WIDTH // 2

            # Store as a barline annotation (original coords)
            annotations.append({
                'type': 'barline',
                'coords': [x_start, y_min, x_end, y_max]
            })
            current_points = [] # Reset for next annotation
            draw_annotations()

    elif event == cv2.EVENT_MOUSEMOVE and len(current_points) == 1:
        # Draw a temporary line from the first point to the current mouse position (on display_img)
        drawing_display_img = display_img.copy()
        cv2.line(drawing_display_img, current_points[0], (int(x/scale_factor), int(y/scale_factor)), (0, 255, 255), 2) # Cyan temporary line
        cv2.imshow("Annotator", drawing_display_img)

# --- Drawing Function ---
def draw_annotations():
    global original_img, display_img, drawing_display_img, annotations, scale_factor
    drawing_display_img = display_img.copy()

    for ann in annotations:
        coords_orig = ann['coords']
        # Convert original coords to display coords for drawing
        x1_disp = int(coords_orig[0] * scale_factor)
        y1_disp = int(coords_orig[1] * scale_factor)
        x2_disp = int(coords_orig[2] * scale_factor)
        y2_disp = int(coords_orig[3] * scale_factor)

        if ann['type'] == 'barline':
            # Draw as a rectangle for visualization of the saved format
            cv2.rectangle(drawing_display_img, (x1_disp, y1_disp), (x2_disp, y2_disp), (0, 255, 0), 2) # Green for barlines
            # Optionally, draw the line itself for clarity
            cv2.line(drawing_display_img, ((x1_disp + x2_disp) // 2, y1_disp), ((x1_disp + x2_disp) // 2, y2_disp), (0, 0, 255), 1) # Thin red line

    cv2.imshow("Annotator", drawing_display_img)

# --- Save Annotations ---
def save_annotations():
    output_data = []
    # For ground truth, we need measure_number, number_location, barline_location
    # This tool only captures barline_location for now. User will need to manually add measure_number and number_location.
    for i, ann in enumerate(annotations):
        output_data.append({
            "measure_number": i + 1, # Placeholder, user needs to adjust
            "number_location": [0,0,0,0], # Placeholder, user needs to adjust
            "barline_location": ann['coords']
        })

    output_dir = os.path.dirname(GROUND_TRUTH_OUTPUT_PATH)
    os.makedirs(output_dir, exist_ok=True)

    with open(GROUND_TRUTH_OUTPUT_PATH, 'w') as f:
        json.dump(output_data, f, indent=2)
    print(f"Annotations saved to {GROUND_TRUTH_OUTPUT_PATH}")

# --- Main Function ---
def main():
    global original_img, display_img, drawing_display_img, annotations, scale_factor

    original_img = cv2.imread(IMAGE_PATH)
    if original_img is None:
        print(f"Error: Could not load image from {IMAGE_PATH}")
        return

    # Calculate resize factor
    h, w = original_img.shape[:2]
    if w > MAX_DISPLAY_WIDTH or h > MAX_DISPLAY_HEIGHT:
        scale_w = MAX_DISPLAY_WIDTH / w
        scale_h = MAX_DISPLAY_HEIGHT / h
        scale_factor = min(scale_w, scale_h)
        display_img = cv2.resize(original_img, (int(w * scale_factor), int(h * scale_factor)))
    else:
        display_img = original_img.copy()
        scale_factor = 1.0

    drawing_display_img = display_img.copy()

    cv2.namedWindow("Annotator")
    cv2.setMouseCallback("Annotator", mouse_callback)

    draw_annotations()

    print("\n--- Coordinate Annotator Tool ---")
    print(f"Image: {IMAGE_PATH} (Original: {w}x{h}, Display: {display_img.shape[1]}x{display_img.shape[0]}, Scale: {scale_factor:.2f})")
    print("Left-click to define start and end points of a barline.")
    print("Press 'z' to undo last annotation.")
    print("Press 's' to save annotations to {GROUND_TRUTH_OUTPUT_PATH}.")
    print("Press 'q' to quit.")

    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('z'):
            if annotations:
                annotations.pop()
                print("Last annotation undone.")
                draw_annotations()
            else:
                print("No annotations to undo.")
        elif key == ord('s'):
            save_annotations()

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
