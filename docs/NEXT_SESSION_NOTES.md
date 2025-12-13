
# Next Session Notes

## Current Status
- **Goal Achieved**: Hybrid Barline Detection (`homr` Baseline + SR Validation) reached **152 TP, 8 FP, 0 FN** on `page_3`.
- **Method**: 
  - Candidates: `homr` (Standard).
  - Validation: Keep candidate if supported by `homr` (SR x4) OR `OMR-DLN` (SR x4).
- **Tool**: `tools/generate_hybrid_results.py` implements this logic.

## Next Steps
1.  **Productionize Hybrid Pipeline**:
    - Wrap the 3-step execution (homr -> homr_sr -> omr_sr -> filter) into a single master script.
    - Currently requires running 3 separate evaluation commands.
2.  **Performance Optimization**:
    - Real-ESRGAN x4 is slow (~45s per page).
    - Can we use a lighter SR model? Or tile detection efficiently?
    - Or run SR only on candidate regions (ROI)?
3.  **Expanded Evaluation**:
    - Test on `page_4`, `page_5`, etc. to ensure specific tuning for `page_3` generalizes.
    - Validate `thin_barline_finder` config scaling on other pages (hardcoded values might need more tuning).
4.  **OMR-DLN Improvement**:
    - `OMR-DLN` missed 15 barlines even with SR.
    - Investigate why (missed measures?). Maybe lower confidence threshold or use TTA.

## Key Files
- `src/common/preprocessing.py`: SR logic.
- `src/homr_eval_scripts/homr_evaluator.py`: Updated with SR support and scaling.
- `experiments/models/eval_omr_dln.py`: Updated for SR support.
- `experiments/fp_reduction/tune_hybrid_detector.py`: Analysis logic.
- `tools/generate_hybrid_results.py`: Final hybrid generator.
