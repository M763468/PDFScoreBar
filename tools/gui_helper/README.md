# GUI Helper Tool

This tool is a lightweight web interface for visually inspecting barline detection results.
It runs as a local Flask server and allows you to view a score page with overlaid detection boxes.

## Prerequisites
- Python 3.10+
- Flask (`pip install flask`)
- Pillow (`pip install Pillow`)

## Setup
1. Ensure your current working directory is the **repository root** (e.g., `/home/masaki_muramatsu/ws_PDFScoreBar`).
   ```bash
   cd /home/masaki_muramatsu/ws_PDFScoreBar
   ```
2. Activate your python environment (e.g., Poetry):
   ```bash
   poetry shell
   ```

## How to Run
Run the application directly using Python:
```bash
python tools/gui_helper/app.py
```

You should see output indicating the server is running.

## How to Access
Open your web browser and go to:
[http://127.0.0.1:5000](http://127.0.0.1:5000)

## Current Status
- **Step 2.3**: Interaction & Saving.
  - Displays the `page_3` image with overlay boxes.
  - **Click** a box to toggle "Ignored" status (turns red).
  - **Click "Save" button** to write the list of ignored IDs to `manual_ignore.json`.
  - Currently configured to view: `20251206T_homr_heuristic_final` (Page 3).

## How to use
1. Run the app: `python tools/gui_helper/app.py`
2. Open [http://127.0.0.1:5000](http://127.0.0.1:5000).
3. **Left Click** on any blue box that looks like a False Positive. It will turn **Red**.
4. Click the **"Save ignored barlines"** button at the bottom.
5. Check your console output or look for `tools/gui_helper/../../logs/.../manual_ignore.json`.

## Resetting
To clear your manual decisions, simply delete the `manual_ignore.json` file created in the log directory.
The tool will start fresh next time you reload the page.

## Troubleshooting
**Alignment Issues**:
The tool now supports responsive scaling.
1. If boxes seem misaligned, try **refreshing the page**.
2. If issues persist, ensure `config.METRICS_PATH` points to a detection file that contains `orig_bbox` fields (original image coordinates).

## Configuration
To change the page or metrics file being inspected, edit:
`tools/gui_helper/config.py`

Currently inspecting:
- **Run**: `20251206T_homr_heuristic_final`
- **File**: `page_3/page_3_detections.json`

## Limitations & Assumptions
- **Comparison Only**: This tool is designed for **rapid inspection** and **manual verification**. It is NOT a full production-grade annotation platform.
- **Single Page**: Currently hardcoded to load a single page defined in `config.py`. To view other pages, you must manually update `IMAGE_PATH` and `METRICS_PATH`.
- **Browser-Based**: Relies on the browser's rendering engine. If the image is extremely large (e.g., >100MB), performance may degrade.

## Future Extensions
To expand this tool for the full dataset, consider the following:
1. **Multi-Page Support**: Add a "Next/Prev" button and a route to load different images dynamically.
2. **Annotation Integration**: Automatically load `manual_ignore.json` on startup to pre-mark previously ignored items.
3. **Pipeline Integration**: Modify `homr_evaluator.py` to read `manual_ignore.json` and filter out marked FPs during metric calculation.
4. **Keyboard Shortcuts**: Add `j/k` for navigation and `x` to toggle ignore status for faster workflow.
