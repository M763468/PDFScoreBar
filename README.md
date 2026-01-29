# PDF Score Measure Number Adder

This project aims to develop a Python-based tool that automatically adds measure numbers to sheet music provided in PDF format.

> **Status notice (2026-01-16):** The measure-numbering pipeline and MMR OCR/CNN work have been integrated in this repo. The authoritative history is in `docs/DEVLOG_MEASURE_NUMBERING.md`. CNN training history is in `docs/DEVLOG_CNN_TRAINING.md`. Historical logs (pre-2026-01-03) are preserved in `docs/DEVELOPMENT_LOG.md`. Start from `docs/README.md` for the up-to-date documentation map.



---
## Ultimate Goal (Very Long Term)

Automatically add correct measure numbers to PDF sheet music with minimal human intervention.

The long-term vision is a system that is:
- Robust across publishers and layouts
- Explainable and debuggable
- Practical as a preprocessing tool for musicians and researchers

This repository serves as an experimental and research-driven workspace toward that goal.
---


## Repository Structure

- **`src/`**: Stable, core application code.
- **`external/`**: Cloned third-party libraries.
- **`tools/`**: Reusable utility scripts.
- **`experiments/`**: Experimental scripts and analysis.
- **`docs/`**: Documentation and notes.

## License

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
│   ├── evaluation2/      # Newer evaluation set (current GT rebuild lives here)
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

## Detect Barline project
楽譜（の画像）から小節線を検出する機能
homr, oemerなどのAIやそれらのhaybrid検出、ヒューリスティック後処理などを検討する。
独自モデルなども考慮に入れ、正確な小節線検出を目指す

### Barline FP Reduction Project (Dec 2025, Historical)

An extensive heuristic optimization project reduced False Positives (FPs) in barline detection on `page_3`.

- **Outcome**: Achieved FP reductions while preserving FN=0 on the legacy page_3 setup
- **Conclusion**: Visual heuristics are largely exhausted; remaining FPs are hard to separate from fragmented TPs
- **Details (historical, likely stale)**: `docs/fp_reduction/FINAL_SUMMARY.md` (note: this subtree is ~3 weeks behind current work)

---

## Current Focus (Post-Phase 6)

The latest confirmed state (GT rebuild + recheck) and next actions are tracked in `docs/NEXT_SESSION_NOTES.md`. In brief:

- **GT cleanup complete** for all 35 detector-miss items; **10 true detector-miss cases remain** after recheck.
- **Baseline**: `var88` (clefs_keys left filter + `probe_notehead_dilate=13` + `notehead_dilate=7`) maintains **FN=0** in the current evaluation set.
- **Next steps**: detector-side FN analysis and FP-source cleanup (clef/time/rest/accidental/stem), prioritizing no FN regressions.

## Count barline project　（未着手） 
検出した小節線と、楽譜の中の複数小節の休みの検出や楽章の分割を使って最終的に小節番号をつけるプログラムとして完成させる
Detect Barlineを適用するかの「楽譜かどうか」の判断もできる必要がある

## Application（未着手） 
これまでの結果をすべて使って、アプリケーションの形にまとめる
pdfを入れたら、実用的な処理時間で小節番号付きのPDFが戻ってくることが必要



## GUI Helper Tool

The `tools/gui_helper` is a lightweight browser-based tool for visual inspection of detection results.
It allows for rapid manual verification of False Positives (FPs).

- **Location**: `tools/gui_helper/`
- **Docs**: [README.md](tools/gui_helper/README.md)
- **Status**: Experimental (supports page 3 inspection)

## Development Environment

All development and evaluation should be performed inside the provided Docker container.

- **Container name**: `pdf_score_dev_gpu`
- **Workspace mount**: Project root → `/workspace`
- All script paths inside the container assume `/workspace` as base.

See `docs/ENVIRONMENTS.md` for details.

## Development Commands

This project uses a `Makefile` to simplify common development tasks.
Ensure you have `uv` installed.

- **Check code style (lint):**
  ```bash
  make lint
  ```

- **Format code:**
  ```bash
  make format
  ```

- **Show available commands:**
  ```bash
  make help
  ```

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
