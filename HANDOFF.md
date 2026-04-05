# HANDOFF: 100% Recall Recovery (Issue #117)

## Status Update (2026-04-05)

We are in the final stages of recovering the 100% recall baseline (resolving the last 7 FNs).

### 1. Architectural Improvements (Completed & Committed)
- **Robust Coordinate Scaling**: Integrated into core `src/pipeline/steps/probe_scan.py`. The tool now automatically detects and corrects scaling mismatches (300 DPI vs 600 DPI) by comparing seed coordinates to image width.
- **Resolution-Aware Inference**: Updated `verify_repro_batch_final.py` to use `input_image_scale=2.0`, ensuring the CNN receives standardized 1x crops (300 DPI) even when running on 2x images.
- **Improved Verification Logic**: Implemented wildcard path resolution in `verify_repro_batch_final.py` to handle auto-generated score/page subdirectories.

### 2. Current Investigation
The verification script was reporting 0% recall in the latest run.
- **Root Cause Identified**: The probe scan runner was failing to find the seeds because of a filename mismatch (`predictions.json` vs expected `pipeline2_no_peak_candidates.json`).
- **Fix Applied**: Updated `reorganize_seeds.py` to use the standardized filename.
- **Remaining Task**: The very last run showed the probe scan *finding* barlines (e.g. 824 for page 001) but the evaluation summary still reported 0% TP. This suggests a final disconnect in the path aggregation in `verify_repro_batch_final.py` (multiple matching folders or glob specificity).

### 3. Immediate Next Steps for Next Session
1. **Confirm Seed Loading**: Verify that `pipeline2_no_peak_candidates.json` is correctly loaded into the `final_set` in `probe_scan.py`.
2. **Execute Full Cycle**:
   ```bash
   rm -rf logs/repro_v12_recovery
   PYTHONPATH=. .venv_cnn_classifier/bin/python tools/repro_accuracy/reproduce_clean_seed_v12.py
   PYTHONPATH=. .venv_cnn_classifier/bin/python tools/repro_accuracy/reorganize_seeds.py
   PYTHONPATH=. .venv_cnn_classifier/bin/python tools/repro_accuracy/verify_repro_batch_final.py
   ```
3. **Verify Target**: Confirm **3581 TP / 0 FN**.

### 4. Key Files to Reference
- `src/pipeline/steps/probe_scan.py`: Now contains the robust scaling logic.
- `tools/repro_accuracy/verify_repro_batch_final.py`: The final evaluation suite.
- `tools/repro_accuracy/reorganize_seeds.py`: Standardizes seed storage.
