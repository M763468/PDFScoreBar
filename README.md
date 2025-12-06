# PDF Score Measure Number Adder

This project aims to develop a Python-based tool that automatically adds measure numbers to sheet music provided in PDF format.

> **Status notice (2024-06-14):** Active development is concentrated on the `homr`-based evaluation workflow and related tooling. Historical experiments remain documented below; when in doubt, start from `docs/README.md` for the current documentation map and follow the pointers there.

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
├── docs/
│   ├── README.md            # Documentation index and update policy
│   ├── NEXT_SESSION_NOTES.md  # Session handover notes
│   ├── DEVELOPMENT_LOG.md     # History and key decisions
│   ├── ENVIRONMENTS.md        # Environment setup and usage
│   └── AGENTS.md              # Assistant runbook
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
│   │   └── incontext_barline_detector.py # Legacy Gemini prototype.
│   ├── pdf_to_images.py      # Script to convert PDFs to PNGs.
│   ├── add_measure_numbers.py  # (Legacy) Simple script to draw numbers.
│   └── archive/            # Deprecated scripts.
└── ...
```

## Barline FP Reduction Project (Dec 2025)
We have completed an extensive heuristic optimization project to reduce False Positives (FPs) in barline detection on `page_3`.
- **Outcome**: Reduced FPs by ~15% (35 -> 30) with **0 False Negatives**.
- **Conclusion**: Visual heuristics are exhausted. Remaining FPs are indistinguishable from fragmented TPs.
- **Details**: See [FINAL_SUMMARY.md](docs/fp_reduction/FINAL_SUMMARY.md).

## Development Environment

All development and script execution should be performed inside the provided Docker container to ensure consistency.

-   **Container Name:** `pdf_score_dev_gpu`
-   **Attaching to the container:** Use your IDE's features (e.g., VS Code Remote - Containers) or the standard `docker exec` command.
-   **Container Workspace:** The host project directory (`/home/masaki_muramatsu/ws_PDFScoreBar`) is mounted to `/workspace` inside the container. All file paths within scripts executed inside the container should use `/workspace` as their base.

## AI Assistant Guides

-   **Gemini / Codex CLI sessions:** See `docs/AGENTS.md` for the unified bootstrap checklist and execution style.
-   **Serena helper script:** `setup_scripts/setup.sh` indexes the project and starts the Serena MCP server when needed.

### How to Use

**Important:** All evaluation commands should be executed *inside* the `pdf_score_dev_gpu` Docker container. Refer to `docs/ENVIRONMENTS.md` for container lifecycle and helper scripts.

1.  **Prepare PDFs:** Place the score you want to analyse in `data/evaluation/pdfs/` (see `data/README.md` for naming rules).

2.  **Convert PDF to Images:** Generate page images before running detectors.
    ```bash
    python src/pdf_to_images.py
    ```

3.  **Run Detection & Evaluation:**
    -   The active workflow pairs the `homr` evaluator with the `oemer` baseline; follow the run commands and parameter notes in `docs/ENVIRONMENTS.md` and `docs/NEXT_SESSION_NOTES.md`.
    -   Store metrics and overlays under `logs/` using the timestamped layout described in those docs so results stay comparable across runs.

**Historical prototype:** The Gemini + OpenCV experiment (`src/gemini/incontext_barline_detector.py`) remains for reference but is no longer maintained as the primary detection flow.
