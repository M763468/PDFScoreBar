# PDF Score Measure Number Adder

This project aims to develop a Python-based tool that automatically adds measure numbers to sheet music provided in PDF format.

> **Status notice (2024-06-14):** Active development is concentrated on the `homr`-based evaluation workflow and related tooling. Historical experiments remain documented below; when in doubt, prefer the up-to-date references in `docs/ENVIRONMENTS.md`, `docs/DEVELOPMENT_LOG.md`, and `docs/NEXT_SESSION_NOTES.md`.

## Core Technology

This tool currently explores multiple detection backends (legacy Gemini + OpenCV hybrid, `oemer`-inspired ML detector, and the `homr` pipeline). The README captures high-level concepts; see the docs mentioned above for day-to-day workflows.

-   **Gemini + OpenCV (historical baseline):** Provided early prototypes combining LLM-assisted barline proposals with classical post-processing.
-   **oemer-derived ML detector:** Two-stage segmentation and filtering pipeline implemented under `src/ml_detector/`.
-   **homr integration:** Transformer-based OMR system under active evaluation inside a dedicated Docker environment.

## Directory Structure

The project is organized as follows:

```
./
├── Dockerfile
├── README.md
├── NEXT_SESSION_NOTES.md
├── DEVELOPMENT_LOG.md
├── data/
│   ├── README.md         # Data management policy and directory map
│   ├── training/
│   │   ├── pdfs/         # Source PDFs for annotated training material
│   │   ├── images/       # Page images converted from the training PDFs
│   │   └── annotations/  # Ground truth JSON grouped per page (page_xxx/)
│   ├── evaluation/
│   │   ├── pdfs/         # PDFs under evaluation
│   │   ├── images/       # Converted evaluation images (e.g., page_3.png)
│   │   └── annotations/  # Evaluation GT (to be added as page_xxx/)
│   └── workbench/        # Temporary captures and legacy drafts
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

1.  **Prepare PDF:** Place the sheet music PDF you want to process into the `data/evaluation/pdfs/` directory (see `data/README.md` for details).

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
