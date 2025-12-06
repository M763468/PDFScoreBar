# NOTE (2025-12 repo restructure): This script may still assume pre-restructure paths (src/tools, tools/fp_reduction). Adjust imports if reusing.
import cv2
import json
import os

def visualize_ground_truth(image_path, ground_truth_path, output_path):
    """Draws ground truth data on the image and saves it."""
    try:
        image = cv2.imread(image_path)
        if image is None:
            print(f"Error: Could not read the image file at {image_path}")
            return

        with open(ground_truth_path, 'r') as f:
            ground_truth_data = json.load(f)

        print(f"\n--- Visualizing {len(ground_truth_data)} ground truth entries... ---")

        for entry in ground_truth_data:
            # Draw number_location (Blue)
            num_loc = entry.get("number_location")
            if num_loc and len(num_loc) == 4:
                cv2.rectangle(image, (num_loc[0], num_loc[1]), (num_loc[2], num_loc[3]), (255, 0, 0), 2) # Blue

            # Draw barline_location (Red)
            bar_loc = entry.get("barline_location")
            if bar_loc and len(bar_loc) == 4:
                cv2.rectangle(image, (bar_loc[0], bar_loc[1]), (bar_loc[2], bar_loc[3]), (0, 0, 255), 2) # Red

        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)

        cv2.imwrite(output_path, image)
        print(f"Successfully saved visualized ground truth to: {output_path}")

    except FileNotFoundError:
        print(f"Error: Ground truth file not found at {ground_truth_path}")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {ground_truth_path}")
    except Exception as e:
        print(f"An error occurred during visualization: {e}")

if __name__ == "__main__":
    image_path = "data/training/images/page_1.png"
    ground_truth_path = "data/training/annotations/page_001/raw_boxes.json"
    output_path = "output/gemini_results/page_1_ground_truth_visualized.png"

    visualize_ground_truth(image_path, ground_truth_path, output_path)
