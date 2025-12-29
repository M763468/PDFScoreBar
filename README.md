# PDF Score Measure Number Adder

This project aims to develop a Python-based tool that automatically adds measure numbers to sheet music provided in PDF format.

> **Status notice (2024-06-14):** Active development is concentrated on the `homr`-based evaluation workflow and related tooling. Historical experiments remain documented below; when in doubt, start from `docs/README.md` for the current documentation map and follow the pointers there.


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

### Barline FP Reduction Project (Dec 2025)

We completed an extensive heuristic optimization project to reduce False Positives (FPs) in barline detection on `page_3`.

- **Outcome**: Reduced FPs with **0 False Negatives**
- **Conclusion**: Visual heuristics are exhausted; remaining FPs are indistinguishable from fragmented TPs
- **Details**: See `docs/fp_reduction/FINAL_SUMMARY.md`

---

## Current Capability (Phase 4 complete; Phase 5 planned)

The current best-known evaluation pipeline for `page_3` (hybrid detector outputs) is:

1. **Hybrid detection** (multi-model OMR pipeline; produces `logs/hybrid_results.json`)
2. **Row-based geometric consistency filter** (Phase 3)
3. **Optional geometry-based note-context filter** (Phase 4)

With Phase 4 enabled, the pipeline is confirmed to reach **TP=152, FP=0, FN=0** on `page_3` by using `homr` note-related outputs (notehead context) to reject stem-like false barlines.

### Status & Limitations
- Confirmed correctness milestone is **`page_3` only**.
- Phase 4 (FP reduction) is **complete**; cross-dataset review indicates the FP rule is conservative and does not introduce new false negatives.
- Remaining false negatives observed on other pages are treated as an **upstream attribution/recovery problem** (Phase 5), not a Phase 4 regression.

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
