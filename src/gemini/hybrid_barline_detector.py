import cv2
import numpy as np
import os
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont
import json
import sys
import os

# Add the workspace root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

# --- Configuration ---
# APIキーを環境変数から取得
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set.")
genai.configure(api_key=API_KEY)

# デバッグ用の出力ディレクトリ
DEBUG_OUTPUT_DIR = "/workspace/debug_outputs/"
os.makedirs(DEBUG_OUTPUT_DIR, exist_ok=True)

from src.hybrid.opencv_candidate_detector import detect_vertical_line_candidates

# --- Batch Classification with Gemini ---
def classify_single_batch(batch_candidates, original_pil_img, model, batch_num):
    """
    Creates a composite image for a single batch of candidates and asks Gemini to classify them.
    """
    if not batch_candidates:
        return []

    # --- Create Composite Image for Batch ---
    margin = 10
    max_h = 0
    cropped_images = []
    # The candidate list for this batch is a slice of the original candidates list
    for (x1, y1), (x2, y2) in batch_candidates:
        left, top = max(0, min(x1, x2) - margin), max(0, min(y1, y2))
        right, bottom = min(original_pil_img.width, max(x1, x2) + margin), min(original_pil_img.height, max(y1, y2))
        if left >= right or top >= bottom: continue
        cropped = original_pil_img.crop((left, top, right, bottom))
        cropped_images.append(cropped)
        if cropped.height > max_h: max_h = cropped.height

    if not cropped_images:
        return []

    # Arrange in a grid
    cols = 5
    rows = (len(cropped_images) + cols - 1) // cols
    # Estimate cell width based on average width of this batch
    avg_w = sum(img.width for img in cropped_images) // len(cropped_images) if cropped_images else 20
    cell_w = avg_w + 40 # Add padding
    canvas = Image.new('RGB', (cols * cell_w, rows * (max_h + 40)), 'white')
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 15)
    except IOError:
        font = ImageFont.load_default()

    candidate_map = {}
    for i, cropped in enumerate(cropped_images):
        row, col = divmod(i, cols)
        x_offset, y_offset = col * cell_w, row * (max_h + 40)
        canvas.paste(cropped, (x_offset + 10, y_offset + 20))
        # Use a 1-based index for display
        draw.text((x_offset + 10, y_offset), f"Candidate {i+1}", fill="black", font=font)
        # Map the 1-based index to the original candidate coordinate
        candidate_map[i+1] = batch_candidates[i]

    # Save a debug image for each batch
    composite_image_path = os.path.join(DEBUG_OUTPUT_DIR, f"debug_composite_batch_{batch_num}.png")
    canvas.save(composite_image_path)
    print(f"Saved composite image for batch {batch_num} to {composite_image_path}")

    # --- Prompt Gemini ---
    prompt = f"""
    The following image contains {len(cropped_images)} numbered regions cropped from a musical score.
    Each region shows a potential barline.
    Please identify which of these regions are actual barlines.
    Return your answer as a single JSON array of numbers corresponding to the candidates that are barlines.
    For example: [1, 3, 4, 8, 12]
    """

    response_text = ""
    try:
        response = model.generate_content([prompt, canvas])
        response_text = response.text
        # Find the JSON part of the response
        json_str = response_text[response_text.find('['):response_text.rfind(']')+1]
        print(f"Gemini response for batch {batch_num} (raw): {response_text}")
        print(f"Extracted JSON string for batch {batch_num}: {json_str}")
        confirmed_indices = json.loads(json_str)
        # Return the original coordinates of the confirmed barlines
        return [candidate_map[i] for i in confirmed_indices if i in candidate_map]
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"Error processing Gemini response for batch {batch_num}: {e}")
        print(f"Full response was: {response_text}")
        return []
    except Exception as e:
        # This will catch the image size error specifically if it happens again
        print(f"An unexpected error occurred during Gemini API call for batch {batch_num}: {e}")
        return []

def classify_candidates_in_batches(candidates, original_pil_img, model, batch_size=100):
    """
    Processes candidates in batches to avoid creating excessively large images.
    """
    all_confirmed_barlines = []
    for i in range(0, len(candidates), batch_size):
        batch_candidates = candidates[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        print(f"--- Processing Batch {batch_num} ({len(batch_candidates)} candidates) ---")
        confirmed_in_batch = classify_single_batch(batch_candidates, original_pil_img, model, batch_num)
        if confirmed_in_batch:
            all_confirmed_barlines.extend(confirmed_in_batch)
        print(f"--- Finished Batch {batch_num}. Found {len(confirmed_in_batch)} confirmed barlines in this batch. ---")
    return all_confirmed_barlines

# --- Main Orchestration ---
def main():
    image_path = "/workspace/data/input_images/page_3.png"
    output_image_path = "/workspace/output/gemini_results/page_3_hybrid_detected.png"
    
    print("1. Detecting vertical line candidates with OpenCV...")
    candidates, original_img_rgb = detect_vertical_line_candidates(image_path)
    if original_img_rgb is None: return
    print(f"Found {len(candidates)} candidates.")

    original_pil_img = Image.fromarray(original_img_rgb)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    
    print("\n2. Classifying candidates in batches with Gemini...")
    # Set a reasonable batch size to avoid the image size limit
    confirmed_barlines = classify_candidates_in_batches(candidates, original_pil_img, model, batch_size=100)

    print(f"3. Found {len(confirmed_barlines)} total confirmed barlines.")

    # Visualize and save
    output_img = cv2.imread(image_path)
    # Sort barlines by their x-coordinate to number them correctly
    confirmed_barlines.sort(key=lambda line: line[0][0])
    for i, ((x1, y1), (x2, y2)) in enumerate(confirmed_barlines):
        cv2.line(output_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(output_img, str(i + 1), (min(x1, x2) - 20, min(y1, y2) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)

    cv2.imwrite(output_image_path, output_img)
    print(f"\n4. Saved final image with measure numbers to {output_image_path}")

    coordinates_path = "/workspace/output/gemini_results/page_3_hybrid_coordinates.json"
    # Convert numpy types for JSON serialization
    barlines_for_json = [[(int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1]))] for p1, p2 in confirmed_barlines]
    with open(coordinates_path, 'w') as f:
        json.dump(barlines_for_json, f, indent=4)
    print(f"Saved barline coordinates to {coordinates_path}")


if __name__ == "__main__":
    main()
