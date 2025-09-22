# PDF Score Measure Number Adder

This project aims to develop a Python-based tool that automatically adds measure numbers to sheet music provided in PDF format.

## Core Technology

This tool utilizes a hybrid approach, combining the power of Google's Gemini for advanced image recognition and OpenCV for precise image manipulation.

-   **Gemini (The Brain):** Analyzes the sheet music image to accurately identify the coordinates of all barlines, using in-context learning for improved accuracy.
-   **OpenCV (The Hands):** Takes the coordinate data from Gemini to draw measure numbers onto the image and save the final output.

## Directory Structure

The project is organized as follows:

```
./
├── Dockerfile
├── README.md
├── NEXT_SESSION_NOTES.md
├── DEVELOPMENT_LOG.md
├── data/
│   ├── input_pdfs/       # Place source PDFs to be processed here.
│   ├── training_pdfs/    # PDFs with existing measure numbers for training/fine-tuning.
│   ├── input_images/       # PNGs converted from source PDFs.
│   └── ground_truth_page_1.json # Ground truth data for in-context learning.
├── output/
│   └── ...
├── src/
│   ├── gemini/
│   │   └── incontext_barline_detector.py # Main script for barline detection.
│   ├── pdf_to_images.py      # Script to convert PDFs to PNGs.
│   ├── add_measure_numbers.py  # (Legacy) Simple script to draw numbers.
│   └── archive/            # Deprecated scripts.
└── ...
```

## Development Environment

All development and script execution should be performed inside the provided Docker container to ensure consistency.

-   **Container Name:** `pdf_score_dev_gpu`
-   **Attaching to the container:** Use your IDE's features (e.g., VS Code Remote - Containers) or the standard `docker exec` command.
-   **Container Workspace:** The host project directory (`/home/masaki_muramatsu/ws_PDFScoreBar`) is mounted to `/workspace` inside the container. All file paths within scripts executed inside the container should use `/workspace` as their base.

## AI Assistant Guides

-   **Gemini / Codex CLI sessions:** See `docs/AGENTS.md` for the unified bootstrap checklist and execution style.
-   **Serena helper script:** `setup_scripts/setup.sh` indexes the project and starts the Serena MCP server when needed.

### How to Use

**Important:** All `python` commands listed below should be executed *inside* the `pdf_score_dev_gpu` Docker container.

**Example:**
```bash
docker exec pdf_score_dev_gpu python src/pdf_to_images.py
```

1.  **Prepare PDF:** Place the sheet music PDF you want to process into the `data/input_pdfs/` directory.

2.  **Convert PDF to Images:** Run the conversion script.
    ```bash
    python src/pdf_to_images.py
    ```

3.  **Run Barline Detection:**
    -   The main script for detection is `src/gemini/incontext_barline_detector.py`.
    -   This script is currently configured to use example data. You may need to edit the file to change the target image.
    -   Run the script:
        ```bash
        docker exec pdf_score_dev_gpu python src/gemini/incontext_barline_detector.py
        ```
    -   The script will output the detected coordinates. (Drawing functionality is TBD).
