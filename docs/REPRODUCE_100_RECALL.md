# Reproducing 100% Barline Recall (Shostakovich Festival Overture)

## Background & Root Cause of the 97.7% Regression
In March 2026, we discovered a regression where barline detection recall dropped from a historic 100% baseline down to 97.7% on the `evaluation2` `Shostakovich-Festival_Overture_Va` dataset.

**Root Cause:** The `max_height` and other constraints in `src/homr_eval_scripts/core/predictor.py` (`ThinBarlineConfig`) were hard-coded to 400px. When high-resolution 600dpi scans or Super-Resolution (SR x2) was activated (effectively creating a 1200dpi equivalent), full-page long barlines exceeded this 400px limit and were silently rejected as False Positives by the low-level geometry filter before CNN scoring could even see them.

**The Fix:** We updated `predictor.py` to dynamically scale all bounding box constraints (like `max_height`) by multiplying the base 400px budget by the current image's resolution scale (`self.sr_scale * resolution_multiplier`).

## How to Verify the 100% Recall Baseline

To ensure this type of resolution-scaling degradation does not happen again, you must run the verification pipeline on the Shostakovich subset and use native tools to confirm the candidate count.

### 1. Run the Verification Pipeline
We use a dedicated configuration file that strictly mirrors the conditions under which 100% recall was originally established (SR enabled, matched CNN matching rules).

```bash
nohup bash -c 'make run-pipeline CONFIG=configs/repro_shostakovich_100.yaml > artifacts/eval_shostakovich_100.log 2>&1' &
```
*Note: Due to WSL drvfs (`/mnt/c/`) file I/O locks with Docker, we strongly recommend running the pipeline asynchronously and avoiding direct Python os.walk scripts on the output directory until the run fully completes.*

### 2. Bypass WSL File Locks for Evaluation
Python's `json.load()` and `Path.glob()` can randomly hang in WSL2 when scanning the deep, heavily-populated `/mnt/c/` directories modified by Docker containers (D-state locks). To calculate recall cleanly, use fast native bash utilities:

```bash
# Define paths
OUTPUT_DIR="logs/hybrid_generalization/shostakovich_repro_100/hybrid_results"
GT_DIR="data/evaluation2/annotations/Shostakovich-Festival_Overture_Va"

# Verify candidate counts against Ground Truth (GT) counts
total_gt=0
total_c=0
for p in 01 02 03 04 05 06 07 08 09; do
  cands=$(grep -o "\[" $OUTPUT_DIR/page_0${p}_hybrid.json | wc -l)
  gt=$(grep -o "barline_location" $GT_DIR/page_0${p}/boxes_sorted.json | wc -l)
  echo "Page $p: GT=$gt Cands=$cands"
  total_gt=$((total_gt + gt))
  total_c=$((total_c + cands))
done
echo "Total GT: $total_gt | Total Candidates: $total_c"
```

### 3. Success Criteria
To confirm no regression has occurred:
- The total GT should be exactly **351**.
- The Total output candidates must be **≥ 351** (e.g., typically `384` under optimal SNR configurations).
- **CRITICAL:** If the candidate total drops to `~120` or specific pages like Page 1 only produce `~41` candidates, the resolution-scaling bug has been re-introduced and the SR geometric limits are currently too tight.

## Regression Prevention Rule
Any changes made to geometric thresholds in the `homr` baseline detector, or changes affecting `cv2.resize()` operations on the input images, **MUST** be verified against this script to ensure `max_height` constraints securely wrap high-dpi full-page barlines. This sanity check has been linked to `docs/REGRESSION_TEST_WORKFLOW.md`.
