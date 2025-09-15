import base64
import json
import os
import re

import cv2
import google.generativeai as genai
import numpy as np
import google.api_core.exceptions

def configure_api_key():
    """Configure the Gemini API key from environment variables."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set.")
        return False
    genai.configure(api_key=api_key)
    return True

def encode_image(image_path):
    """Encodes an image file to a base64 string."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def load_ground_truth(json_path):
    """Loads the ground truth data from a JSON file."""
    try:
        with open(json_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Ground truth file not found at {json_path}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {json_path}")
        return None

def generate_prompt_with_examples(image_to_analyze_path, ground_truth_path):
    """Generates the prompt for barline detection using in-context examples."""
    encoded_image = encode_image(image_to_analyze_path)
    ground_truth_data = load_ground_truth(ground_truth_path)

    if ground_truth_data is None:
        return None

    # Create a more descriptive example format
    descriptive_examples = []
    for item in ground_truth_data:
        descriptive_examples.append({
            "comment": "This is a standard barline, a thin vertical line separating measures.",
            "barline_location": item["barline_location"]
        })

    examples_str = json.dumps({"barlines": descriptive_examples}, indent=2)

    prompt_parts = [
        "You are a world-class expert in Optical Music Recognition (OMR). Your sole task is to identify barlines in a sheet music image.",
        "Follow these instructions precisely, using a step-by-step reasoning process:",
        "Step 1: Identify all vertical lines in the image that could potentially be barlines. Do not filter yet.",
        "Step 2: From the identified vertical lines, filter out those that are NOT barlines. Remember that barlines are thin, vertical lines that stretch across the staff lines to separate measures. You MUST IGNORE:",
        "   - Note stems (the lines attached to note heads).",
        "   - The vertical lines of clefs (like Treble or Bass clefs).",
        "   - The vertical lines of time signatures.",
        "   - The vertical lines of key signatures (sharps and flats).",
        "   - Thick double barlines or final barlines (for now, only detect single, thin barlines).",
        "Step 3: For each remaining barline, provide its bounding box coordinates in the format `[x_start, y_start, x_end, y_end]`.",
        "Step 4: Return your final output as a single, valid JSON object. This object must have a single key, \"barlines\", which contains a list of the coordinate arrays you found.",
        "\nHere is an example of a correctly formatted output based on a different score. I have included comments to help your understanding.",
        f"--- EXAMPLE START ---\n{examples_str}\n--- EXAMPLE END ---",
        "Now, analyze the following image and provide the coordinates of all barlines you can find. Remember to only detect the single, thin barlines and ignore all other vertical lines.",
        "Image to analyze:",
        {
            "mime_type": "image/png",
            "data": encoded_image
        }
    ]

    return prompt_parts

def detect_barlines_with_gemini(prompt, model_name):
    """Calls the Gemini API to detect barlines and returns the cleaned JSON string."""

    print(f"\n--- Calling Gemini API with {model_name} ---")
    try:
        # Upgraded to the more powerful model
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        print("--- API Response Received ---")
        cleaned_json = re.sub(r'^```json\s*|\s*```', '', response.text, flags=re.MULTILINE | re.DOTALL).strip()
        return cleaned_json
    except Exception as e:
        print(f"An error occurred during the API call: {e}")
        return None


def draw_and_save_results(image_path, detected_data, output_dir):
    """Draws the detected barlines on the image and saves it."""
    try:
        image = cv2.imread(image_path)
        if image is None:
            print(f"Error: Could not read the image file at {image_path}")
            return

        barlines = detected_data.get("barlines", [])
        print(f"\n--- Drawing {len(barlines)} detected barlines... ---")

        for item in barlines:
            x1, y1, x2, y2 = item["barline_location"]
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2) # Green color, 2px thickness

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Create a unique output path
        base_name = os.path.basename(image_path)
        file_name, ext = os.path.splitext(base_name)
        output_path = os.path.join(output_dir, f"{file_name}_detected{ext}")

        cv2.imwrite(output_path, image)
        print(f"Successfully saved result image to: {output_path}")

    except Exception as e:
        print(f"An error occurred during image processing or saving: {e}")

def main():
    """Main function to run the barline detection and evaluation."""
    if not configure_api_key():
        return

    # --- Parameters ---
    image_to_analyze = "data/input_images/page_3.png"
    ground_truth_file = "data/ground_truth_page_1_sorted.json"
    output_directory = "output/gemini_results"
    MODEL_NAME = "gemini-1.5-flash-latest" # Change to "gemini-1.5-flash-latest" for flash model

    print(f"Starting analysis for: {image_to_analyze}")
    print(f"Using ground truth from: {ground_truth_file}")

    prompt = generate_prompt_with_examples(image_to_analyze, ground_truth_file)

    if prompt is None:
        print("Could not generate prompt. Exiting.")
        return

    detected_barlines_json_str = detect_barlines_with_gemini(prompt, MODEL_NAME)

    if detected_barlines_json_str:
        print("\n--- Detection Result (JSON String) ---")
        print(detected_barlines_json_str)
        try:
            detected_data = json.loads(detected_barlines_json_str)
            print("\n--- JSON Parsed Successfully ---")
            draw_and_save_results(image_to_analyze, detected_data, output_directory)
        except json.JSONDecodeError:
            print("\n--- Error: Failed to parse JSON from API response ---")
    else:
        print("\n--- No result from detection ---")

if __name__ == "__main__":
    main()
