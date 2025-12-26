---
## Phase 6 completed; see NEXT_SESSION_NOTES.md for confirmed outcomes

This log has been cleaned to retain only confirmed Phase 6 results and references.

---
## Phase 6 confirmed outcomes

- Detector-miss total: 35 (page_10=9, page_15=15, page_001=1, page_004=10)
  - Source: `logs/phase5b/trace_stage_analysis/20251221T222504/fn_trace_table.csv`
- GT cleanup completed for all 35 detector-miss items; post-GT recheck:
  - resolved=25, remaining_miss=10, total=35
  - Summary: `logs/phase6_detector_miss/gt_fix_review_full/near_hit_recheck/near_hit_recheck_summary.json`
- Remaining true detector-miss list + categories:
  - `logs/phase6_detector_miss/gt_fix_review_full/POST_GT_RECHECK_SUMMARY.md`

---
## Remaining true detector-miss cases (detector-side work)

- page_004 fn_000 (end_barline)
- page_004 fn_003 (text_dynamic_overlap)
- page_004 fn_005 (dense_chord_accidental)
- page_004 fn_008 (text_dynamic_overlap)
- page_004 fn_011 (double_or_repeat_bar)
- page_10 fn_000 (end_barline)
- page_15 fn_003 (text_dynamic_overlap)
- page_15 fn_007 (notehead_overlap)
- page_15 fn_010 (dense_chord_accidental)
- page_15 fn_021 (double_or_repeat_bar)

[Session] Read README.md, docs/README.md, docs/NEXT_SESSION_NOTES.md; prepared to start detector-side analysis for remaining 10 detector-miss items.

[Session] Detector-side analysis for remaining 10 detector-miss cases (Phase 6 post-GT recheck)
Evidence base:
- Remaining list + categories: logs/phase6_detector_miss/gt_fix_review_full/POST_GT_RECHECK_SUMMARY.md#L11
- Remaining_miss status by page/gt_index: logs/phase6_detector_miss/gt_fix_review_full/near_hit_recheck/near_hit_recheck.csv#L3
- Visual classification notes + crop paths: logs/phase6_detector_miss/detector_miss_classification.csv#L2

Per-case notes (what failed + evidence):
- page_004 fn_000 (gt_index 0) end_barline: staff-end barline under slur; detector missed a staff-end vertical under slur/ornament overlap. Likely candidate generation or confidence suppression under slur overlap. Evidence: classification note + crop path in logs/phase6_detector_miss/detector_miss_classification.csv#L27; remaining_miss status in logs/phase6_detector_miss/gt_fix_review_full/near_hit_recheck/near_hit_recheck.csv#L3; category in logs/phase6_detector_miss/gt_fix_review_full/POST_GT_RECHECK_SUMMARY.md#L11.
- page_004 fn_003 (gt_index 3) text_dynamic_overlap: barline near text/marking ('r.'); missed barline adjacent to text marking. Potential text/marking interference causing low confidence or suppression. Evidence: logs/phase6_detector_miss/detector_miss_classification.csv#L29; remaining_miss status logs/phase6_detector_miss/gt_fix_review_full/near_hit_recheck/near_hit_recheck.csv#L5; category logs/phase6_detector_miss/gt_fix_review_full/POST_GT_RECHECK_SUMMARY.md#L12.
- page_004 fn_005 (gt_index 5) dense_chord_accidental: barline with stacked notes/tremolo; missed barline overlapped by dense chord/accidentals. Likely occlusion/visual clutter reducing detector confidence. Evidence: logs/phase6_detector_miss/detector_miss_classification.csv#L31; remaining_miss logs/phase6_detector_miss/gt_fix_review_full/near_hit_recheck/near_hit_recheck.csv#L7; category logs/phase6_detector_miss/gt_fix_review_full/POST_GT_RECHECK_SUMMARY.md#L13.
- page_004 fn_008 (gt_index 8) text_dynamic_overlap: barline near digit/marking; missed barline adjacent to a marking. Potential text adjacency causing suppression or missed candidate. Evidence: logs/phase6_detector_miss/detector_miss_classification.csv#L34; remaining_miss logs/phase6_detector_miss/gt_fix_review_full/near_hit_recheck/near_hit_recheck.csv#L10; category logs/phase6_detector_miss/gt_fix_review_full/POST_GT_RECHECK_SUMMARY.md#L14.
- page_004 fn_011 (gt_index 11) double_or_repeat_bar: multiple close verticals (double bar); detector missed double/repeat bar structure. Potential NMS/merging suppression or model not tuned for closely spaced verticals. Evidence: logs/phase6_detector_miss/detector_miss_classification.csv#L36; remaining_miss logs/phase6_detector_miss/gt_fix_review_full/near_hit_recheck/near_hit_recheck.csv#L12; category logs/phase6_detector_miss/gt_fix_review_full/POST_GT_RECHECK_SUMMARY.md#L15.
- page_10 fn_000 (gt_index 0) end_barline: staff-end barline with nearby notehead/stem; missed staff-end barline with nearby notehead/stem. Likely occlusion by notehead/stem or confidence threshold. Evidence: logs/phase6_detector_miss/detector_miss_classification.csv#L2; remaining_miss logs/phase6_detector_miss/gt_fix_review_full/near_hit_recheck/near_hit_recheck.csv#L13; category logs/phase6_detector_miss/gt_fix_review_full/POST_GT_RECHECK_SUMMARY.md#L16.
- page_15 fn_003 (gt_index 3) text_dynamic_overlap: barline under text ('ad li'); missed barline with text directly over/near. Potential text overlap reducing detector response. Evidence: logs/phase6_detector_miss/detector_miss_classification.csv#L13; remaining_miss logs/phase6_detector_miss/gt_fix_review_full/near_hit_recheck/near_hit_recheck.csv#L24; category logs/phase6_detector_miss/gt_fix_review_full/POST_GT_RECHECK_SUMMARY.md#L17.
- page_15 fn_007 (gt_index 7) notehead_overlap: barline between noteheads; missed barline in tight notehead context. Possible candidate suppression when vertical strokes are embedded in noteheads. Evidence: logs/phase6_detector_miss/detector_miss_classification.csv#L17; remaining_miss logs/phase6_detector_miss/gt_fix_review_full/near_hit_recheck/near_hit_recheck.csv#L28; category logs/phase6_detector_miss/gt_fix_review_full/POST_GT_RECHECK_SUMMARY.md#L18.
- page_15 fn_010 (gt_index 10) dense_chord_accidental: barline overlapped by beamed notes/dynamics; missed barline in dense chord/beam region. Likely clutter/occlusion reduces detector confidence. Evidence: logs/phase6_detector_miss/detector_miss_classification.csv#L18; remaining_miss logs/phase6_detector_miss/gt_fix_review_full/near_hit_recheck/near_hit_recheck.csv#L29; category logs/phase6_detector_miss/gt_fix_review_full/POST_GT_RECHECK_SUMMARY.md#L19.
- page_15 fn_021 (gt_index 21) double_or_repeat_bar: multiple close verticals (double bar); missed double/repeat bar. Potential suppression of close verticals or model bias toward single-stroke barlines. Evidence: logs/phase6_detector_miss/detector_miss_classification.csv#L25; remaining_miss logs/phase6_detector_miss/gt_fix_review_full/near_hit_recheck/near_hit_recheck.csv#L36; category logs/phase6_detector_miss/gt_fix_review_full/POST_GT_RECHECK_SUMMARY.md#L20.

Potential detector-side improvement directions (analysis only):
- Overlap-robust candidate generation: address text_dynamic_overlap (page_004 fn_003/fn_008, page_15 fn_003) and notehead_overlap (page_15 fn_007) by improving detection under overprinted text/notes. Evidence: overlap notes in logs/phase6_detector_miss/detector_miss_classification.csv#L13,#L17,#L29,#L34. Risks/unknowns: may increase FPs by admitting text strokes or note stems as barlines; needs careful thresholding and regression guard.
- Dense-chord/accidental clutter handling: address dense_chord_accidental (page_004 fn_005, page_15 fn_010) by adding clutter-tolerant features or lower confidence thresholds for vertical strokes in chord stacks. Evidence: dense-chord notes in logs/phase6_detector_miss/detector_miss_classification.csv#L18,#L31. Risks/unknowns: could over-detect in busy passages; needs evaluation against page_3 FP=0 guard.
- Double/repeat bar specialization: address double_or_repeat_bar (page_004 fn_011, page_15 fn_021) by supporting close-parallel verticals (e.g., relaxed NMS or explicit double-bar pattern detection). Evidence: “multiple close verticals” notes in logs/phase6_detector_miss/detector_miss_classification.csv#L25,#L36. Risks/unknowns: could merge into spurious candidates or duplicate detections; needs integration-aware handling.
- Staff-end barline recall: address end_barline cases (page_004 fn_000, page_10 fn_000) with sensitivity to staff-end barlines under slurs or near noteheads/stems. Evidence: staff-end notes with slur/notehead context in logs/phase6_detector_miss/detector_miss_classification.csv#L2,#L27. Risks/unknowns: relaxing detection at staff ends may create FPs at system margins or near vertical text strokes.

Ambiguity note: these failures could stem from missing raw detector candidates, low confidence thresholds, or suppression during detector-side NMS. No direct raw detection traces were located in the Phase 6 logs for these 10 cases.

[Session] Priority analysis (historical attempts + IDEAS + feasibility tiers)
Historical attempts (docs/DEVELOPMENT_LOG.md):
- homr parameter tuning: barline_min_height_factor / barline_max_width_factor sweeps (Phase 16/2025-09-27). Lowering min_height to 0.6 increased FP and did not improve recall materially; min=1.2/max=0.8 slight change with still very low recall; later sweeps (min 1.1/1.3, max 0.7–0.9) stayed low F1; conclusion: threshold tuning alone hit recall ceiling without upstream preproc changes. Evidence: docs/DEVELOPMENT_LOG.md#L244-L281.
- homr min-height tweak (0.9) later increased FP with minor recall gain; recorded as regression. Evidence: docs/DEVELOPMENT_LOG.md#L337-L346.
- Vertical-closing preprocessing: improved recall modestly (homr TP104/FN48; oemer TP133/FN19), but top-hat and aggressive thresholding degraded detection; preprocessing sensitivity noted. Evidence: docs/DEVELOPMENT_LOG.md#L288-L289.
- Binarization + closing experiments: both homr and OMR-DLN failed (No staffs / No noteheads); aggressive pixel-level preprocessing incompatible. Evidence: docs/DEVELOPMENT_LOG.md#L720-L732.
- Super-resolution (FSRCNN x2): degraded homr and OMR-DLN performance; SR not beneficial. Evidence: docs/DEVELOPMENT_LOG.md#L739-L750.
- Real-ESRGAN x4 SR: improved precision but reduced recall (homr 144TP/8FN); not acceptable for recall-critical target. Evidence: docs/DEVELOPMENT_LOG.md#L755-L767.
- Thin-barline recovery heuristic (thin_barline_finder): added candidate recovery via per-column ink runs, improving recall (homr TP116/FN36; oemer TP135/FN17), later refinements adjust FP; still limited, and some FN attributed to model limits. Evidence: docs/DEVELOPMENT_LOG.md#L351-L363, #L368-L371, #L454-L462.
- DPI / PDF render sweeps: dpi200_area improved oemer recall (FN 18) and slightly improved homr; sensitivity to rendering choices exists. Evidence: docs/DEVELOPMENT_LOG.md#L290-L318.
- Legacy CV tuning (Hough/morphology) and oemer parse_barlines filtering adjustments are documented but were insufficient/overly strict for recall vs FP tradeoff. Evidence: docs/DEVELOPMENT_LOG.md#L93-L187.

Overlap with newly proposed directions:
- “Overlap-robust candidate generation” and “clutter-tolerant detection” conceptually overlap with prior thin_barline_finder and preprocessing attempts (vertical closing, min-height tuning) but not explicitly targeted to text/notehead overlap; no evidence of targeted overlap handling being tried.
- “Staff-end barline recall” overlaps with min-height factor tuning and preprocessing; not explicitly targeted to staff-end context.
- “Double/repeat bar specialization” is not clearly covered by prior tuning or thin_barline_finder changes; appears novel relative to documented attempts.
- “Preprocessing / SR / DPI adjustments” already explored extensively (binarize/closing, SR, DPI); SR and binarize/closing were negative; DPI gave some recall lift (esp. oemer).

IDEAS.md review (docs/notes/IDEAS.md#L6):
- Apply row-based processing to OMR-DLN (line-wise processing) to recover FN. Overlaps with “overlap-robust candidate generation” as a structural change to candidate extraction/scoring, not just thresholds.
- SR on/off comparison: overlaps with prior SR attempts (FSRCNN x2, Real-ESRGAN x4) that reduced recall; suggests likely low priority unless new SR method.
- Merge overlapping bboxes: overlaps with detector-side suppression/NMS handling (could impact double/repeat barlines), but also touches merge logic (non-detector stage). Needs care with scope constraint.
- Reintroduce OpenCV rule-based candidates and combine with homr + row/geom filter: overlaps with “add candidate source” direction, but is not detector-only; it is candidate generation before merge/filter; feasibility depends on staying within detector-side scope.

Feasibility under segmentation-based detector (conceptual stage + config vs structural):
- Overlap-robust candidate generation (text/notehead overlap): stage = candidate extraction/scoring from segmentation masks; likely needs logic changes (mask morphology / component handling), not just config.
- Dense-chord/accidental clutter tolerance: stage = candidate extraction/scoring; could be mild config if thresholds exist, but likely structural (mask cleanup or component merge rules).
- Double/repeat bar handling: stage = suppression/NMS or candidate clustering; likely structural change (allow close parallel verticals) rather than simple config.
- Staff-end barline recall: stage = candidate extraction/scoring; could be threshold-based (config) if per-location thresholds exist, but no evidence of such knobs; likely structural if staff-end context must be used.
- Row-wise processing for OMR-DLN (IDEA): stage = post-detection grouping or candidate validation; structural change (pipeline logic), not pure config.
- SR / DPI / preprocessing (IDEAS): stage = input preprocessing; config-like but prior attempts show sensitivity and recall regression; SR not promising, DPI had limited gains.
- OpenCV rule-based candidates + union with homr (IDEA): stage = additional candidate generator; structural integration (not mere parameter change); may conflict with “detector-only” scope depending on interpretation.
- Merge overlapping bboxes (IDEA): stage = suppression/NMS/merge; structural, not config; may be considered integration rather than detector.

Priority framing (no decision):
- Worth early investigation (if detector-side scope allows structural tweaks):
  - Double/repeat bar specialization (close-vertical handling) — not clearly attempted before; directly matches fn_011/fn_021; likely structural (NMS/cluster).
  - Overlap-robust candidate extraction for text/notehead overlap — aligns with 4/10 remaining misses; not explicitly tried; structural.
- Risky / higher cost (structural + broader pipeline impact):
  - Dense-chord/accidental clutter handling — likely increases FP; limited evidence of safe thresholds.
  - Staff-end context-aware recall tweaks — may require staff-end detection context; risk of edge FPs.
  - OpenCV candidate union / row-wise OMR-DLN processing — new pipeline branch; higher integration cost and scope risk.
- Already explored / low priority (unless new variant):
  - Simple threshold tuning (min_height/max_width) — repeatedly ineffective for recall (docs/DEVELOPMENT_LOG.md#L244-L281, #L337-L346).
  - Aggressive preprocessing (binarize/closing) and SR (FSRCNN, Real-ESRGAN) — recall regressions or failures (docs/DEVELOPMENT_LOG.md#L720-L767).
  - DPI sweeps — some gains but limited; not targeted to specific 10 FN cases and already explored (docs/DEVELOPMENT_LOG.md#L290-L318).

Uncertainties:
- Not all Phase 28+ logic is guaranteed to map to the current detector pipeline (segmentation internals may not expose config hooks). Several directions likely need structural changes rather than parameter tuning.

[Session] Double/repeat barline FN focus: proposal-only (no code)
Target cases: page_004 fn_011, page_15 fn_021 (double_or_repeat_bar) per logs/phase6_detector_miss/gt_fix_review_full/POST_GT_RECHECK_SUMMARY.md#L15 and logs/phase6_detector_miss/detector_miss_classification.csv#L25,#L36.

Approach A: Close-parallel vertical recovery (NMS/cluster relaxation for double bars)
- Mechanism: during detector-side suppression/clustering, allow two close vertical strokes to survive as separate candidates if they are parallel, tall enough, and within a small x-gap window (double-bar pattern). Instead of NMS removing the lower-confidence neighbor, keep both and optionally tag as a “double-bar pair.”
- Stage affected: suppression/NMS or candidate clustering stage (detector-side post-processing). It’s adjacent to merge logic but can be kept inside detector output generation.
- Why it should work: both FN cases are annotated as “multiple close verticals (double bar)” (classification notes). If current suppression collapses these into a single candidate or drops both, relaxing the suppression for near-parallel verticals should preserve the true barline(s).
- Expected benefits: recover page_004 fn_011 and page_15 fn_021; may also improve other repeat/double barline occurrences.
- Likely risks/FP patterns: duplicate detections on single barlines with nearby stems; increased FP from closely spaced stem pairs or ledger artifacts.
- Evaluation: re-run detector outputs and check recall on the two FN cases; monitor FP increase on page_3 regression guard and a small sample of FN-only pages; success = both double-bar FN recovered without unacceptable FP increase.

Approach B: Double-bar candidate synthesis from segmentation mask (paired-vertical detection)
- Mechanism: add a targeted detection pass that scans segmentation-derived vertical components and explicitly detects “double-bar” patterns: two thin vertical components within a bounded x-gap, overlapping in y-span by a high ratio. Emit a single “double-bar” candidate or two linked candidates.
- Stage affected: candidate extraction (from segmentation masks) with an additional pattern detector; minor post-processing to keep these candidates.
- Why it should work: double-bar structures may be split into two components that are individually below thresholds or suppressed; explicit pattern detection can reintroduce them.
- Expected benefits: recover the two FN cases even if single-vertical thresholds are strict; better control via explicit gap/overlap thresholds.
- Likely risks/FP patterns: accidental pairing of stem + barline, or paired stems in dense chords; could elevate FP in notehead_overlap regions.
- Evaluation: same as Approach A, with added check that detected pairs align to known double-bar widths; success = recovery of both FN cases with acceptable FP and no regression on page_3.

Assumptions/uncertainties:
- Current detector suppression/clustering details are not confirmed in Phase 6 logs; these approaches assume double-bar misses are due to suppression or thresholding rather than complete absence in raw segmentation.
- Gap/overlap thresholds for “double-bar” pattern need empirical tuning; unknown whether existing mask resolution supports stable pairing.

### [Approach A] Design
- Goal: allow close-parallel vertical strokes to survive when merging thin_barline_finder candidates into detector predictions, to recover double/repeat barlines.
- Scope: modify only the thin-barline merge/suppression path in homr evaluator; no GT/filter/merge baseline changes.
- Mechanism: detect a narrow double-bar pattern via x-gap, vertical overlap, height, and width constraints; when matched, skip replacement so both candidates are kept.

### [Approach A] Implementation details
- Location: src/homr_eval_scripts/homr_evaluator.py (thin_barline_finder merge into mapped_predictions).
- Added double-bar guard with small constants:
  - double_bar_min_height=18
  - double_bar_max_width=6
  - double_bar_min_overlap=0.75
  - double_bar_max_gap=6 (edge-to-edge x gap)
  - double_bar_scan_gap=8 (center scan window)
- Added _x_gap helper to compute positive edge gap (0 if overlapping).
- If a candidate pair meets double-bar conditions, replacement is skipped so both survive.
- Change is localized to the extra_barlines merge loop and should be reversible.

### [Approach A] Results and evaluation
- Not executed yet in this session. Planned checks:
  - Re-run detector output for page_004 and page_15 to verify fn_011/fn_021 recovery.
  - Run page_3 guard to spot obvious FP regressions.
  - If FPs increase modestly and double-bar FN are recovered, treat as candidate baseline.
- Rollback: revert the double-bar guard block in homr_evaluator.py if FP increases are unacceptable.
- Executed commands:
  - docker start homr_eval_gpu
  - docker exec homr_eval_gpu bash -lc "cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/evaluation/images/page_3.png --ground-truth page_3:/workspace/data/evaluation/annotations/page_003/boxes_sorted.json --output-root /workspace/logs/homr_eval"
- Page_004/page_15 evaluation status:
  - BLOCKED: images not present in repo (`data/evaluation/images` only contains page_3.png). No page_004.png or page_15.png found, so fn_011/fn_021 recovery could not be directly verified.
- Page_3 guard metrics (run_id 20251226T190753JST):
  - TP=149, FP=30, FN=3 (Precision=0.8324, Recall=0.9803, F1=0.9003) from logs/homr_eval/20251226T190753JST/metrics.json.
  - Note: homr inference ran on CPU provider (CUDAExecutionProvider unavailable warning in stdout).
- Outcome summary:
  - Target FN recovery (page_004 fn_011, page_15 fn_021): NOT VERIFIED due to missing images.
  - Guard page_3 regression: degraded vs baseline (FP=30, FN=3 vs target TP=152, FP=0, FN=0). Needs investigation; may be unrelated to Approach A due to missing baseline run in same environment.
- Errors/workarounds:
  - Initial docker exec without `cd /workspace/external/homr` failed: “Poetry could not find a pyproject.toml file in /workspace”. Retried with correct working directory.
  - First run timed out at 10s; reran with extended timeout to completion.

### [Repro] Environment requirements and baseline procedure
- Source: docs/ENVIRONMENTS.md.
- homr_eval_gpu container (Dockerfile.homr, CUDA 12.1 + cuDNN 9); evals must run inside container.
- Post-create steps: `poetry install` inside `/workspace/external/homr`; GPU sanity check via `torch.cuda.is_available()` and `onnxruntime.get_device()`.
- Canonical homr eval command (page_3):
  - docker exec homr_eval_gpu bash -c "cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/evaluation/images/page_3.png --ground-truth page_3:/workspace/data/evaluation/annotations/page_003/boxes_sorted.json --output-root /workspace/logs/homr_eval --force-run-id <run_id>"
- Phase 4 baseline command (page_3 geometry note-context filter):
  - .venv_pdf/bin/python experiments/fp_reduction/analyze_staff_consistency.py --json logs/hybrid_results.json --image data/evaluation/images/page_3.png --gt data/evaluation/annotations/page_003/boxes_sorted.json --output logs/phase4_notehead_geom/<run_id>/ --no-use-ratio-tolerance --tol-top-px 5 --tol-bottom-px 5 --enable-geom-notehead-filter --geom-notehead-mode page3_known_fp --homr-context-dir logs/homr_eval_baseline/<run_id>/page_3
- Data layout: evaluation images expected under `data/evaluation/images/` with page_3.png etc; PDFs under `data/evaluation/pdfs/` (currently empty). GT under `data/evaluation/annotations/page_00x/`.

### [Repro] Dataset availability (page_004/page_15)
- `data/evaluation/pdfs/` has no PDFs; no `page_004.png` or `page_15.png` originally present.
- Used existing artifacts as a stopgap (documented source):
  - Copied `logs/phase5b_homr_recall/homr_factor_1p0/page_004/page_004.png` → `data/evaluation/images/page_004.png`.
  - Copied `logs/phase5b_homr_recall/homr_factor_1p0/page_15/page_15.png` → `data/evaluation/images/page_15.png`.
- FN-only GT used for evaluation:
  - `logs/phase6_detector_miss/gt_fix_review_full/gt_corrected/page_004/fn_only_corrected.json`
  - `logs/phase6_detector_miss/gt_fix_review_full/gt_corrected/page_15/fn_only_corrected.json`

### [Repro] Baseline reproduction results (page_3)
- Command:
  - .venv_pdf/bin/python experiments/fp_reduction/analyze_staff_consistency.py --json logs/hybrid_results.json --image data/evaluation/images/page_3.png --gt data/evaluation/annotations/page_003/boxes_sorted.json --output logs/phase4_notehead_geom/20251226T_phase4_repro/ --no-use-ratio-tolerance --tol-top-px 5 --tol-bottom-px 5 --enable-geom-notehead-filter --geom-notehead-mode page3_known_fp --homr-context-dir logs/homr_eval_baseline/baseline_verification/page_3
- Result: TP=152, FP=0, FN=0 (reproduced; stdout from script).

### [Approach A] Results and evaluation
- Environment fix for CUDAExecutionProvider:
  - `docker exec homr_eval_gpu bash -lc "nvidia-smi"` confirmed GPU visible.
  - `poetry run python -c "import onnxruntime as ort; print(ort.get_available_providers()); print(ort.get_device())"` initially showed CPU-only provider.
  - Installed `onnxruntime-gpu==1.23.2` and `opencv-python-headless==4.12.0.88` in the homr poetry env; provider now includes CUDA/TensorRT and `ort.get_device()` reports GPU.
- Commands (Approach A runs):
  - docker exec homr_eval_gpu bash -lc "cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/evaluation/images/page_004.png --ground-truth page_004:/workspace/logs/phase6_detector_miss/gt_fix_review_full/gt_corrected/page_004/fn_only_corrected.json --output-root /workspace/logs/homr_eval --force-run-id 20251226T_approachA_page004"
  - docker exec homr_eval_gpu bash -lc "cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/evaluation/images/page_15.png --ground-truth page_15:/workspace/logs/phase6_detector_miss/gt_fix_review_full/gt_corrected/page_15/fn_only_corrected.json --output-root /workspace/logs/homr_eval --force-run-id 20251226T_approachA_page15"
- Metrics:
  - page_004: TP=0, FP=170, FN=12 (logs/homr_eval/20251226T_approachA_page004/metrics.json). fn_011 not recovered.
  - page_15: TP=8, FP=141, FN=14 (logs/homr_eval/20251226T_approachA_page15/metrics.json). fn_021 not recovered (gt_index 21 not matched).
- Approach A conclusion: no recovery for target double-bar FNs; proceed to revert and test Approach B.

### [Approach B] Design / Implementation / Results
- Design: detect close parallel vertical pairs in `thin_barline_finder` and allow them through candidate selection even when near existing detections (paired double-bar recovery).
- Implementation:
  - Updated `src/common/thin_barline_finder.py` to add double-pair config (gap/overlap/height/width) and a paired-box bypass for `_is_close`.
  - Reverted Approach A changes in `src/homr_eval_scripts/homr_evaluator.py` before applying this.
- Commands (Approach B runs):
  - docker exec homr_eval_gpu bash -lc "cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/evaluation/images/page_004.png --ground-truth page_004:/workspace/logs/phase6_detector_miss/gt_fix_review_full/gt_corrected/page_004/fn_only_corrected.json --output-root /workspace/logs/homr_eval --force-run-id 20251226T_approachB_page004"
  - docker exec homr_eval_gpu bash -lc "cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/evaluation/images/page_15.png --ground-truth page_15:/workspace/logs/phase6_detector_miss/gt_fix_review_full/gt_corrected/page_15/fn_only_corrected.json --output-root /workspace/logs/homr_eval --force-run-id 20251226T_approachB_page15"
  - page_3 guard rerun: .venv_pdf/bin/python experiments/fp_reduction/analyze_staff_consistency.py ... --output logs/phase4_notehead_geom/20251226T_phase4_repro_afterB/ (TP=152, FP=0, FN=0).
- Metrics:
  - page_004: TP=0, FP=170, FN=12 (logs/homr_eval/20251226T_approachB_page004/metrics.json). fn_011 not recovered.
  - page_15: TP=8, FP=141, FN=14 (logs/homr_eval/20251226T_approachB_page15/metrics.json). fn_021 not recovered.
- Outcome: Approach B did not improve double/repeat-bar recovery in the FN-only GT checks; Phase 4 guard baseline reproduced unchanged.

### [Validation] Historical evaluation targets
- Evidence of historical image paths:
  - `tools/run_confirmed_union_eval.sh` uses `data/training/images/page_15.png` and `data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png` for FN-only evaluation pages; GT under `data/training/annotations/page_015/fn_only.json` and `data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/fn_only.json`.
  - `experiments/phase5b_b1_1_omrdln_sweep/run_omr_dln_sweep.sh` uses the same image paths for page_15/page_004.
  - `logs/homr_eval_baseline/baseline_verification/run_config.json` confirms `data/evaluation/images/page_3.png` as the canonical page_3 input.

### [Validation] Current vs historical image comparison
- Current evaluation images:
  - `data/evaluation/images/page_004.png`
  - `data/evaluation/images/page_15.png`
- Historical targets (from scripts):
  - `data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png`
  - `data/training/images/page_15.png`
- Hash/dimension comparison (sha256/dims):
  - `data/evaluation/images/page_004.png`: size=1909684, dims=3000x3900, sha256=f80b6f8b7f68edce13322733dc1145e37a7ace3af35d93a64e307874d84187c9
  - `data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png`: size=1909684, dims=3000x3900, sha256=f80b6f8b7f68edce13322733dc1145e37a7ace3af35d93a64e307874d84187c9
  - `data/evaluation/images/page_15.png`: size=721623, dims=2700x3600, sha256=20342b8afca8ac6df52e47d25031abf5994048ea0b5a50585b6596e05f38c4ee
  - `data/training/images/page_15.png`: size=721623, dims=2700x3600, sha256=20342b8afca8ac6df52e47d25031abf5994048ea0b5a50585b6596e05f38c4ee
- Conclusion: current evaluation images are byte-identical to historically used targets for page_004 and page_15.

### [Validation] GT–image alignment check
- FN-only GT boxes are in-bounds for the current images:
  - page_004: 12 GT boxes, 0 out of bounds; image dims 3000x3900.
  - page_15: 22 GT boxes, 0 out of bounds; image dims 2700x3600.
- Specific FN targets (from `logs/phase6_detector_miss/detector_miss_classification.csv`):
  - page_004 fn_011 bbox (2571,3433,2575,3498) in-bounds; crop saved to `logs/validation/20251226_target_checks/page_004_fn_011_crop.png` with marked full image `logs/validation/20251226_target_checks/page_004_fn_011_marked.png`.
  - page_15 fn_021 bbox (2395,3278,2399,3338) in-bounds; crop saved to `logs/validation/20251226_target_checks/page_15_fn_021_crop.png` with marked full image `logs/validation/20251226_target_checks/page_15_fn_021_marked.png`.

### [Validation] Corrected evaluation results
- Evaluation targets confirmed correct (images match historical targets; GT boxes in-bounds). Approach A/B conclusions remain valid under correct conditions; no re-run triggered by target mismatch.

### [Segmentation Check] GT vs predicted bbox geometry
- Source predictions: `logs/homr_eval/20251226T_approachB_page004/page_004/page_004_detections.json`, `logs/homr_eval/20251226T_approachB_page15/page_15/page_15_detections.json`.
- page_004 fn_011:
  - GT bbox: (2571,3433,2575,3498) (w=4, h=65).
  - Nearest predicted bbox (by center distance): (2432,3154,2433,3173) (w=1, h=19).
  - Center delta: dx=-140.5, dy=-302.0, dist=333.08 px.
  - Size ratios (pred/GT): w_ratio=0.25, h_ratio=0.29.
  - Interpretation: horizontally shifted left and vertically above; much smaller than GT (not oversized).
- page_15 fn_021:
  - GT bbox: (2395,3278,2399,3338) (w=4, h=60).
  - Nearest predicted bbox (by center distance): (2289,3189,2290,3209) (w=1, h=20).
  - Center delta: dx=-107.5, dy=-109.0, dist=153.09 px.
  - Size ratios (pred/GT): w_ratio=0.25, h_ratio=0.33.
  - Interpretation: shifted left/up; smaller than GT (not oversized).
- Conclusion: nearest predictions are **horizontally shifted and vertically misaligned** relative to GT; they are **smaller**, not oversized, suggesting missing/shifted candidate generation rather than NMS suppression.

### [Segmentation Check] Barline mask inspection
- Masks used (resized to original image dimensions):
  - `logs/homr_eval/20251226T_approachB_page004/page_004/page_004_debug_11_bar_lines.png`
  - `logs/homr_eval/20251226T_approachB_page15/page_15/page_15_debug_11_bar_lines.png`
- GT bbox mask occupancy (nonzero pixels within GT box after resize):
  - page_004 fn_011: mask_gt_nonzero=237
  - page_15 fn_021: mask_gt_nonzero=232
- Saved evidence (with run_id):
  - `logs/validation/20251226_target_checks/page_004_fn_011_20251226T_approachB_page004_barline_mask_crop.png`
  - `logs/validation/20251226_target_checks/page_004_fn_011_20251226T_approachB_page004_barline_mask_overlay.png`
  - `logs/validation/20251226_target_checks/page_004_fn_011_20251226T_approachB_page004_barline_mask_overlay_crop.png`
  - `logs/validation/20251226_target_checks/page_15_fn_021_20251226T_approachB_page15_barline_mask_crop.png`
  - `logs/validation/20251226_target_checks/page_15_fn_021_20251226T_approachB_page15_barline_mask_overlay.png`
  - `logs/validation/20251226_target_checks/page_15_fn_021_20251226T_approachB_page15_barline_mask_overlay_crop.png`
- Interpretation: barline mask has nonzero pixels inside the GT box for both cases, but the nearest predicted candidates are shifted/undersized; suggests segmentation evidence exists but is not converted into aligned candidates.

### [Root Cause] GT vs pred overlay confirmation
- Approach B overlays reviewed (paths in `logs/validation/20251226_target_checks/`):
  - `page_004_fn_011_20251226T_approachB_page004_gt_pred_overlay.png`
  - `page_15_fn_021_20251226T_approachB_page15_gt_pred_overlay.png`
- Nearest predicted bbox measured (also used in overlays):
  - page_004 fn_011 nearest pred: (2432,3154,2433,3173) — far above/left of GT.
  - page_15 fn_021 nearest pred: (2289,3189,2290,3209) — left/up of GT.
- Large green bbox near GT:
  - page_004 fn_011: no predicted bbox within ±200px window around GT.
  - page_15 fn_021: only a thin predicted bbox within window (2289,3189,2290,3209); no oversized bbox near GT.

### [Root Cause] CC bbox from mask near GT
- Connected-components on resized barline mask (`page_*_debug_11_bar_lines.png`), windowed around GT:
  - page_004 fn_011: 1 component intersects GT window; full-image bbox approx (2491,3353)-(2655,3578).
  - page_15 fn_021: 1 component intersects GT window; full-image bbox approx (2315,3198)-(2479,3418).
- Saved CC debug overlays:
  - `logs/validation/20251226_target_checks/page_004_fn_011_20251226T_approachB_page004_cc_mask_overlay_crop.png`
  - `logs/validation/20251226_target_checks/page_15_fn_021_20251226T_approachB_page15_cc_mask_overlay_crop.png`
- Interpretation: mask contains a large connected component spanning the GT region, but detections.json does not include a corresponding bbox. This suggests a failure in converting mask components to candidate boxes (likely in staff-level parsing or mapping), rather than NMS suppression.

### [Root Cause] Coordinate transform tracing
- Candidate generation path:
  - `run_homr_on_image()` extracts `bar_line_boxes` from homr debug symbols and creates `BarlinePrediction(pred_bbox=...)` in segmentation coordinates (see `src/homr_eval_scripts/homr_evaluator.py` around predictions list creation).
  - `compute_transform_info()` + `map_pred_to_orig()` map segmentation coords to original image coords (same file, around mapping to `orig_bbox`).
  - `metrics_predictions` later rescale for JSON export; `detections.json` stores 1x coords from `metrics_predictions`.
- Observed mismatch: segmentation mask (debug_11_bar_lines) resized to original image shows a large component overlapping GT, but no matching prediction exists near GT.
- Likely failure point: conversion from `bar_line_boxes` (symbol extraction) into `pred_bbox`, or staff parsing that drops/relocates the component before it becomes a prediction; not an NMS stage.

### [Clarification] CC mask visualization semantics
- `page_*_debug_11_bar_lines.png` is produced by `debug.write_bounding_boxes_alternating_colors("bar_lines", bar_line_boxes)` in `external/homr/homr/main.py:222-223` (homr core) and mirrored in `src/homr_eval_scripts/homr_evaluator.py:470` (eval path). These images show the **bar_line_boxes** after filtering (notehead/stem overlap + min height/max width thresholds), drawn in alternating colors; the colors are purely visual (see `external/homr/homr/debug.py:15-33,87-108`).
- In the CC overlay crops I generated (e.g., `logs/validation/20251226_target_checks/page_004_fn_011_20251226T_approachB_page004_cc_mask_overlay_crop.png`), **red vertical lines are the GT boxes** drawn by our overlay script, not segmentation detections. **Green boxes** are connected-component (CC) bboxes computed from a binarized version of `page_*_debug_11_bar_lines.png`. These CC boxes are debug-only and do **not** imply a direct detection in `detections.json`.
- Because `debug_11_bar_lines` already visualizes **filtered bar_line_boxes**, any “red/green” lines in that debug image are **candidates that should correspond to detections**, but the overlay’s colors are ours and should not be interpreted as pipeline semantics.

### [Clarification] Red-line path through pipeline
- Segmentation output flows as: `predictions.stems_rest` → `prepare_bar_line_image()` (dilate) → `create_rotated_bounding_boxes(..., skip_merging=True)` → `symbols.bar_lines` (rotated boxes) in `external/homr/homr/main.py:117-126`.
- These candidates are filtered by overlap with noteheads/stems and by size thresholds (`barline_min_height_factor`, `barline_max_width_factor`), producing `bar_line_boxes` in `src/homr_eval_scripts/homr_evaluator.py:447-470` (or `external/homr/homr/main.py:216-223` in core). These `bar_line_boxes` are what are written to `debug_11_bar_lines.png` and what become predictions in `detections.json`.
- Therefore, if a visible vertical “stroke” is only present in our CC overlay (from binarizing the debug image or mask), it is **not necessarily** a detection candidate; only `bar_line_boxes` make it into `detections.json`.

### [Clarification] Detection vs evaluation
- The assumption that “red lines in CC overlays represent detected barline strokes” is **incorrect** for our overlays; the red lines are GT. The alternating colors in `debug_11_bar_lines.png` are purely visual and represent already-filtered `bar_line_boxes`.
- A visually “correct-enough” barline could still be labeled FN if its predicted bbox is short/shifted and fails IoU/geometry matching. However, in the inspected FN cases, the nearest predicted bbox is both **much smaller** and **spatially offset** relative to GT (see `[Segmentation Check] GT vs predicted bbox geometry`), indicating that the failure is **not purely strict IoU matching** but also candidate geometry/placement.

### [Work Unit 1] Pipeline map + failure inventory (2025-12-26 22:54 JST)
- Objective / hypothesis
  - Objective: Map the exact barline pipeline stages with code references and enumerate the specific, observed failure points for fn_011/fn_021.
  - Hypothesis: The FN cases reflect a concrete failure in candidate generation or coordinate mapping, not just evaluation IoU strictness.
- What I checked / changed
  - Re-opened `README.md`, `docs/README.md`, and `docs/NEXT_SESSION_NOTES.md` to re-anchor to project goal and current phase focus.
  - Located the core segmentation → bar_line_boxes → mapping → detections.json → eval flow in `external/homr/homr/main.py` and `src/homr_eval_scripts/homr_evaluator.py`.
- Commands run
  - `sed -n '1,80p' README.md`
  - `sed -n '1,120p' docs/README.md`
  - `sed -n '1,120p' docs/NEXT_SESSION_NOTES.md`
  - `rg -n "def load_and_preprocess_predictions" -S external/homr/homr src/homr_eval_scripts/homr_evaluator.py`
  - `sed -n '60,120p' external/homr/homr/main.py`
  - `sed -n '100,260p' external/homr/homr/main.py`
  - `rg -n "bar_line" src/homr_eval_scripts/homr_evaluator.py`
  - `sed -n '420,520p' src/homr_eval_scripts/homr_evaluator.py`
  - `rg -n "map_pred_to_orig|compute_transform_info|mapped_predictions" -S src/homr_eval_scripts/homr_evaluator.py`
  - `sed -n '320,420p' src/homr_eval_scripts/homr_evaluator.py`
  - `rg -n "def compute_metrics" -S src/homr_eval_scripts/homr_evaluator.py`
  - `sed -n '1320,1405p' src/homr_eval_scripts/homr_evaluator.py`
  - `rg -n "detections.json" -S src/homr_eval_scripts/homr_evaluator.py`
  - `sed -n '1880,2005p' src/homr_eval_scripts/homr_evaluator.py`
- Key results (numbers + qualitative)
  - **Pipeline map (code-referenced)**
    - Segmentation + preprocessing: `external/homr/homr/main.py:68-116` (`load_and_preprocess_predictions` → `filter_predictions` → `make_lines_stronger`), fed by `extract(...)` in `get_predictions`.
    - Symbol extraction: `external/homr/homr/main.py:117-126` (`prepare_bar_line_image` on `predictions.stems_rest` → `create_rotated_bounding_boxes(..., skip_merging=True, min_size=(1,5))` → `symbols.bar_lines`).
    - Barline filtering (overlap + size): `external/homr/homr/main.py:216-223` and eval path `src/homr_eval_scripts/homr_evaluator.py:447-470` (exclude overlaps with noteheads/stems; apply `barline_min_height_factor` + `barline_max_width_factor`).
    - Debug output (barline candidates): `debug.write_bounding_boxes_alternating_colors("bar_lines", bar_line_boxes)` in `external/homr/homr/main.py:222-223` and `src/homr_eval_scripts/homr_evaluator.py:470`.
    - Mapping to original image coords: `compute_transform_info` and `map_pred_to_orig` in `src/homr_eval_scripts/homr_evaluator.py:344-399`.
    - Detections export: `detections.json` creation in `src/homr_eval_scripts/homr_evaluator.py:1954-1975` (writes 1x `orig_bbox`).
    - Evaluation: `compute_metrics` in `src/homr_eval_scripts/homr_evaluator.py:1349-1405` (IoU-based matching via `greedy_barline_match`).
  - **Failure inventory (fn_011 / fn_021)**
    - F1: **Nearest predicted bbox is small + offset from GT**, so evaluation reports FN even with predictions present.
      - Evidence: approach-B detections in `logs/homr_eval/20251226T_approachB_page004/page_004/page_004_detections.json` and `logs/homr_eval/20251226T_approachB_page15/page_15/page_15_detections.json` (nearest pred centers are ~333px and ~153px from GT, widths/heights ~0.25–0.33 of GT). This is visualized in `logs/validation/20251226_target_checks/page_004_fn_011_20251226T_approachB_page004_gt_pred_overlay.png` and `logs/validation/20251226_target_checks/page_15_fn_021_20251226T_approachB_page15_gt_pred_overlay.png`.
    - F2: **Unknown whether bar_line_boxes exist near GT pre-mapping** (to be resolved in Work Unit 2).
      - Evidence gap: `debug_11_bar_lines` images show bar_line_boxes after filtering, but we have not yet isolated whether any box intersects the GT region in those debug outputs or whether candidates are dropped earlier (e.g., size/overlap filter).
    - F3: **Possible coordinate mapping distortion** remains open (to be tested).
      - Evidence gap: mapping applies autocrop offsets + resize + seg scale in `compute_transform_info`/`map_pred_to_orig`, but we have not validated whether a consistent offset/scale mismatch exists for these FN cases.
- Artifacts saved (paths)
  - Existing overlays: `logs/validation/20251226_target_checks/page_004_fn_011_20251226T_approachB_page004_gt_pred_overlay.png`, `logs/validation/20251226_target_checks/page_15_fn_021_20251226T_approachB_page15_gt_pred_overlay.png`
  - Existing detections: `logs/homr_eval/20251226T_approachB_page004/page_004/page_004_detections.json`, `logs/homr_eval/20251226T_approachB_page15/page_15/page_15_detections.json`
- Conclusion / next work unit
  - Conclusion: The current pipeline stages and evidence show the FN cases are not recovered because the nearest predicted boxes are undersized and displaced relative to GT. The precise drop point (candidate generation vs filtering vs mapping) is still unverified.
  - Next work unit: Audit candidate conversion near GT (Work Unit 2) by checking `debug_11_bar_lines` boxes and reconstructing boxes from the underlying mask/CCs to identify which step drops or shifts candidates.

### [Work Unit 2] Candidate conversion audit near GT (2025-12-26 23:24 JST)
- Objective / hypothesis
  - Objective: Determine whether bar_line_boxes exist near GT pre-filter, and if/where they are dropped (overlap filter, size filter, or mapping).
  - Hypothesis: For fn_021 (page_15), candidates exist pre-filter but are removed by size thresholds; for fn_011 (page_004), candidates never overlap even at raw stage.
- Commands run
  - `docker exec -i homr_eval_gpu bash -lc 'python3 -m pip install scipy requests typing_extensions musicxml pillow scikit-image onnxruntime rapidocr_onnxruntime torch --index-url https://download.pytorch.org/whl/cpu'`
  - `docker exec -i homr_eval_gpu bash -lc 'cd /workspace && python3 - <<"PY" ... PY'` (barline stage audit; see outputs below)
  - `ls -l /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/homr_eval/20251226T_approachB_page004/page_004/page_004_debug_11_bar_lines.png /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/homr_eval/20251226T_approachB_page15/page_15/page_15_debug_11_bar_lines.png`
- Key results + decision
  - Full debug image paths (existence confirmed):
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/homr_eval/20251226T_approachB_page004/page_004/page_004_debug_11_bar_lines.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/homr_eval/20251226T_approachB_page15/page_15/page_15_debug_11_bar_lines.png`
  - **page_004 fn_011 (GT=2569,3420,2581,3506)**
    - Raw bar_line_boxes (pre-overlap filter): `max_iou=0.0`, closest dist=21.83 px, closest orig bbox=(2550,3441,2559,3470).
    - Overlap-filtered: `max_iou=0.0` (same closest box), so no overlap exists even before filtering.
    - Size-filtered: `max_iou=0.0`, closest dist=84.91 px (closest box shifts), so size filter further moves away but the miss already exists.
    - Decision: Failure is **not caused by overlap/size filters**; candidate overlap is absent at raw stage (generation/mapping mismatch).
  - **page_15 fn_021 (GT=2402,3272,2417,3348)**
    - Raw bar_line_boxes: `max_iou=0.1447`, closest dist=16.62 px, closest orig bbox=(2406,3286,2417,3301) → **overlapping candidate exists**.
    - Overlap-filtered: `max_iou=0.0421` (still overlapping but degraded).
    - Size-filtered: `max_iou=0.0`, closest dist=196.50 px, closest orig bbox=(2209,3275,2217,3346) → **size filter removes all overlap**.
    - Decision: For fn_021, the candidate is **lost at size filtering** (barline_min_height/max_width), after some overlap survives earlier filters.
  - Runtime note: onnxruntime reported no CUDA provider; inference used CPU inside container.
- Artifacts saved (full paths)
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_wu2_candidate_audit/page_004_20251226T_approachB_page004_barline_stage_boxes.json`
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_wu2_candidate_audit/page_004_20251226T_approachB_page004_barline_stage_summary.json`
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_wu2_candidate_audit/page_15_20251226T_approachB_page15_barline_stage_boxes.json`
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_wu2_candidate_audit/page_15_20251226T_approachB_page15_barline_stage_summary.json`
- Conclusion / next work unit
  - Conclusion: fn_011 (page_004) is a **pre-filter mismatch** (no raw overlap), while fn_021 (page_15) is **removed by size filtering**.
  - Next: Propose normalization ideas aligned to these confirmed drop points (Work Unit 3).

### [Work Unit 3] Normalization proposals (2025-12-26 23:24 JST)
- Objective / hypothesis
  - Objective: Propose normalization ideas targeting the confirmed drop points, then rank by impact/risk with a minimal evaluation plan.
  - Hypothesis: Geometry normalization (height/width/center adjustments) will reduce GT mismatch for fn_011 and prevent size-filter loss for fn_021 without full algorithm redesign.
- Commands run
  - None (proposal-only, based on WU2 evidence).
- Key results + decision
  - Proposal A (Size-threshold normalization before size filter):
    - Mechanism: For each raw/overlap-filtered bar_line_box, normalize height to staff-derived expected barline height and clamp width to max-width before applying `barline_min_height`/`barline_max_width` thresholds. This preserves candidates that are “nearly barline-sized” but currently fall just outside size bounds.
    - Targets: **fn_021** (page_15) where raw overlap exists but is removed at size filter.
    - Risk: May admit short vertical noise; moderate FP risk but constrained by size normalization.
    - Evaluation: Re-run page_15 and page_3; success if IoU>0.5 for fn_021 and page_3 TP=152 FP=0 FN=0 remains.
  - Proposal B (Post-mapping center/height snapping to staff metrics):
    - Mechanism: After mapping to orig coords, snap barline bbox center x to nearest strong vertical mask centroid and expand y to staff line span (or N staff spaces). This addresses near-miss offsets/short boxes without changing candidate generation.
    - Targets: **fn_011** (page_004) where raw overlap is 0 but nearest candidate is close (~22px), suggesting normalization could bridge the gap.
    - Risk: Could shift true positives into noteheads or align to wrong staff; must be constrained by staff proximity.
    - Evaluation: Page_004 fn_011 recovery check + page_3 guard. Success if overlap emerges without FP regression.
  - Proposal C (Split size filter into “strict” + “lenient if mask evidence”):
    - Mechanism: Retain size-filter thresholds for general candidates, but allow a lenient path if the candidate is supported by mask density (bar_line_img) within a local window.
    - Targets: **fn_021** (size-filter loss) and potentially **fn_011** if mask evidence is strong but box is undersized.
    - Risk: Mask-based leniency may increase FP where stems are dense; needs tight window and verticality constraints.
    - Evaluation: Same as above; additionally check FP clusters near dense chords.
  - Ranking (impact vs risk):
    - High impact / moderate risk: Proposal A (directly addresses size-filter loss for fn_021).
    - Medium impact / higher risk: Proposal B (may fix fn_011 but risks misalignment on other bars).
    - Medium impact / higher risk: Proposal C (mask-based leniency could reintroduce FPs).
- Artifacts saved (full paths)
  - None (proposal-only).
- Conclusion / next work unit
  - Conclusion: With fn_021 lost at size filtering and fn_011 missing raw overlap, normalization should focus on size normalization (fn_021) and staff-aligned snapping (fn_011) as separate experiments. Next step: choose a minimal normalization experiment and run fn_011/fn_021 + page_3 guard.

### [Work Unit 4] Proposal A implementation + eval (2025-12-26 23:45 JST)
- Objective / hypothesis
  - Objective: Apply size-threshold normalization before size filtering and test recovery for fn_021 while preserving page_3 guard.
  - Hypothesis: Clamping bar_line_box height/width to staff-derived thresholds would allow fn_021 to survive size filtering without major FP increase.
- What I changed / tested
  - Implemented normalization in `src/homr_eval_scripts/homr_evaluator.py` (clamp size before min-height/max-width checks).
  - Switched to canonical GPU environment per `docs/ENVIRONMENTS.md`: `homr_eval_gpu` + Poetry venv.
  - Installed `onnxruntime-gpu==1.22.0` in Poetry venv; verified CUDAExecutionProvider.
- Commands run
  - `docker exec -i homr_eval_gpu bash -lc 'cd /workspace/external/homr && poetry install'`
  - `docker exec -i homr_eval_gpu bash -lc 'cd /workspace/external/homr && poetry run python -m pip install onnxruntime-gpu==1.22.0'`
  - `docker exec -i homr_eval_gpu bash -lc 'cd /workspace/external/homr && poetry run python - <<"PY" ... ort.get_device() ... PY'`
  - `docker exec -i homr_eval_gpu bash -lc 'cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/evaluation/images/page_15.png --ground-truth page_15:/workspace/logs/phase6_detector_miss/gt_fix_review_full/gt_corrected/page_15/fn_only_corrected.json --output-root /workspace/logs/homr_eval --force-run-id 20251226T_wu4_normA_page15'`
  - `docker exec -i homr_eval_gpu bash -lc 'cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/evaluation/images/page_3.png --ground-truth page_3:/workspace/data/evaluation/annotations/page_003/boxes_sorted.json --output-root /workspace/logs/homr_eval --force-run-id 20251226T_wu4_normA_page3_guard'`
- Key results (quantitative + qualitative)
  - GPU provider confirmed: `onnxruntime` reports `device=GPU`, providers include `CUDAExecutionProvider`.
  - page_15 metrics (run `20251226T_wu4_normA_page15`): TP=9, FP=189, FN=13.
  - page_3 guard (run `20251226T_wu4_normA_page3_guard`): TP=149, FP=190, FN=3 — **severe regression** vs baseline (TP=152 FP=0 FN=0).
  - fn_021 recovery check: best IoU with final predictions is 0.1225 (below threshold); still FN.
- Artifacts saved (FULL paths + color legend)
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/homr_eval/20251226T_wu4_normA_page15/metrics.json`
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/homr_eval/20251226T_wu4_normA_page3_guard/metrics.json`
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_wu4_normA_visuals/page_15_fn_021_gt_red_norm_green_pred_yellow_overlay.png`
    - Color legend: Red = GT bbox, Green = nearest normalized candidate (post-overlap, pre-size filter), Yellow = nearest final prediction (post-size filter, detections.json).
- Conclusion / next step
  - Proposal A **does not recover fn_021** and **breaks the page_3 guard**; not viable as-is.

### [Work Unit 5] fn_011 diagnostic under Proposal A (2025-12-26 23:45 JST)
- Objective / hypothesis
  - Objective: Check whether Proposal A incidentally improves fn_011 geometry without adding new logic.
  - Hypothesis: Normalization might reduce the GT–candidate gap, even if fn_011 remains FN.
- What I changed / tested
  - Generated GT vs raw (overlap-filtered) vs normalized candidate overlay for fn_011 using the same normalization rule.
- Commands run
  - `docker exec -i homr_eval_gpu bash -lc 'cd /workspace/external/homr && poetry run python - <<"PY" ... overlay generation ... PY'`
- Key results (quantitative + qualitative)
  - Nearest raw candidate distance: 21.83 px (box 2550,3441,2559,3470).
  - Nearest normalized candidate distance: 21.66 px (box 2550,3424,2559,3488).
  - Improvement is marginal; fn_011 remains a miss (no IoU >= 0.5 candidate).
- Artifacts saved (FULL paths + color legend)
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_wu4_normA_visuals/page_004_fn_011_gt_red_raw_blue_norm_green_overlay.png`
    - Color legend: Red = GT bbox, Blue = nearest candidate before normalization (post-overlap filter), Green = nearest candidate after normalization (pre-size filter).
- Conclusion / next step
  - Proposal A does not meaningfully improve fn_011; still unsolved.

### [Work Unit 6] Decision checkpoint (2025-12-26 23:45 JST)
- Objective / hypothesis
  - Objective: Decide whether Proposal A is acceptable and whether Proposal B is justified.
  - Hypothesis: Given fn_021 remains FN and page_3 regresses, Proposal A should be rejected and rolled back; Proposal B is justified for fn_011 pre-filter mismatch.
- What I changed / tested
  - No further changes; decision based on Work Units 4–5 results.
- Commands run
  - None.
- Key results (quantitative + qualitative)
  - Proposal A outcome: **No fn_021 recovery** (best IoU 0.1225), **page_3 guard failed** (TP=149 FP=190 FN=3).
  - fn_011 remains pre-filter mismatch; normalization does not bridge the gap.
- Artifacts saved (FULL paths + color legend)
  - Refer to Work Units 4–5 artifacts above.
- Conclusion / next step
  - Proposal A is **not acceptable** due to severe regression and no FN recovery; change should be reverted before next experiment.
  - Proposal B (staff-aligned snapping / mapping normalization) is now justified as the next diagnostic experiment for fn_011, after rollback of Proposal A.

### [Work Unit 7] Cross-FN drop-point audit (2025-12-26 23:45 JST)
- Objective / hypothesis
  - Objective: For all 10 remaining detector-miss cases, locate the first pipeline stage where overlap is lost and quantify distribution.
  - Hypothesis: Most FN are lost pre-filter (candidate generation/segmentation), not at overlap/size filters.
- What I checked / tested
  - Used `logs/phase6_detector_miss/detector_miss_classification.csv` for GT bboxes + categories.
  - Ran stage-by-stage audit on raw, overlap-filtered, size-filtered candidates with GT IoU and center-distance; computed mask evidence using `bar_line_img`.
  - Note: `page_10.png` is absent in evaluation images; used `/workspace/data/training/images/page_10.png` as the only available image for page_10 FN audit.
- Commands run
  - `docker exec -i homr_eval_gpu bash -lc 'cd /workspace/external/homr && poetry run python - <<"PY" ... fn_stage_audit ... PY'`
- Key results (quantitative + qualitative)
  - Stage loss distribution (10 total): pre_filter=7, overlap_filter=1, size_filter=2, mapping_issue=0.
  - Per-FN summary (raw/overlap/size max IoU, mask evidence):
    - page_004 fn_000 end_barline: raw_iou=0.000 → pre_filter, mask=True
    - page_004 fn_003 text_dynamic_overlap: raw_iou=0.000 → pre_filter, mask=False
    - page_004 fn_005 dense_chord_accidental: raw_iou=0.000 → pre_filter, mask=True
    - page_004 fn_008 text_dynamic_overlap: raw_iou=0.751 → overlap_filter, mask=True
    - page_004 fn_011 double_or_repeat_bar: raw_iou=0.000 → pre_filter, mask=True
    - page_10 fn_000 end_barline: raw_iou=0.089 → size_filter, mask=True
    - page_15 fn_003 text_dynamic_overlap: raw_iou=0.295 → size_filter, mask=True
    - page_15 fn_007 notehead_overlap: raw_iou=0.000 → pre_filter, mask=False
    - page_15 fn_010 dense_chord_accidental: raw_iou=0.000 → pre_filter, mask=False
    - page_15 fn_021 double_or_repeat_bar: raw_iou=0.000 → pre_filter, mask=False
- Artifacts saved (FULL paths)
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_wu7_fn_audit/fn_stage_audit.json`
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_wu7_fn_audit/fn_stage_audit.csv`
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_wu7_fn_audit/fn_stage_audit_summary.json`
- Conclusion / implication
  - The dominant failure class is **pre-filter loss** (7/10), implying segmentation/candidate generation gaps rather than size/overlap filtering. Size-filter loss exists but is minor (2/10). No mapping issues detected.

### [Work Unit 8] Failure-class consolidation (2025-12-26 23:45 JST)
- Objective / hypothesis
  - Objective: Group FN by drop-point + category to identify scalable fixes.
  - Hypothesis: Pre-filter losses cluster across multiple categories, suggesting a single candidate-generation intervention could help several FN.
- What I checked / tested
  - Clustered FN by `stage_loss` and category using `fn_stage_audit.csv`.
- Commands run
  - `.venv_pdf/bin/python - <<'PY' ... cluster counts from fn_stage_audit.csv ... PY`
- Key results (quantitative + qualitative)
  - Dominant class: pre_filter (7 FN) spanning end_barline, dense_chord_accidental, double_or_repeat_bar, notehead_overlap, text_dynamic_overlap.
  - Secondary class: size_filter (2 FN) spanning end_barline + text_dynamic_overlap.
  - Minor class: overlap_filter (1 FN) in text_dynamic_overlap.
  - Ranked potential impact by class size:
    1) pre_filter (7)
    2) size_filter (2)
    3) overlap_filter (1)
- Artifacts saved (FULL paths)
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_wu7_fn_audit/fn_stage_audit.csv`
- Conclusion / implication
  - A single intervention that boosts **pre-filter candidate generation** is most likely to reduce FN count across multiple categories.

### [Work Unit 9] Select ONE high-impact intervention (proposal only) (2025-12-26 23:45 JST)
- Objective / hypothesis
  - Objective: Choose one minimal, high-leverage change targeting the largest FN cluster (pre-filter loss).
  - Hypothesis: Adding a lightweight, image-based vertical-run candidate generator (staff-constrained) will recover multiple pre-filter FN without major redesign.
- What I checked / tested
  - No code changes; proposal based on Work Units 7–8 audit distribution.
- Commands run
  - None.
- Key results (quantitative + qualitative)
  - **Chosen intervention**: Add a supplemental candidate path that detects thin vertical runs directly on the grayscale image (or bar_line_img) within staff-mask regions, then merges into bar_line_boxes before overlap/size filters.
    - Where: immediately after `predict_symbols()` / before overlap filtering in `src/homr_eval_scripts/homr_evaluator.py`.
    - Why: pre_filter loss suggests missing candidates; vertical-run detector can supply candidates when segmentation misses thin/occluded bars.
  - Minimal experiment plan:
    - Pages: page_004, page_10, page_15 (all remaining FN pages).
    - Guard: page_3 Phase 4 baseline (TP=152 FP=0 FN=0).
    - Success criteria:
      - At least 3/7 pre_filter FN gain non-zero IoU (>=0.1) with new candidates before final filtering.
      - No page_3 regression beyond +10 FP in raw candidates (final filtered output must remain FP=0).
- Artifacts saved (FULL paths)
  - None (proposal-only).
- Conclusion / implication
  - Next step is to implement the supplemental candidate generator and re-run the three FN pages + page_3 guard; stop if FP regression exceeds threshold.

### [Experiment Batch 1] Lightweight candidate generators (2025-12-27 00:39 JST)
- Candidate generator(s) tested
  - gen1_vertical_run: staff-constrained vertical run-length detector (dark_threshold=80, min_run=20, morphological open with (20x1) kernel).
  - gen2_barline_cc_relaxed: relaxed CC extraction on bar_line_img (min_size=(1,3)).
  - gen3_sobel_vertical: staff-constrained vertical Sobel detector (sobel_threshold=60, min_run=15, morphological open (15x1)).
- Parameters used
  - Defaults as implemented in `src/homr_eval_scripts/homr_evaluator.py` (see functions `generate_vertical_run_candidates`, `generate_barline_cc_relaxed`, `generate_sobel_vertical_candidates`).
- Pages evaluated
  - page_004, page_10 (from `/workspace/data/training/images/page_10.png`), page_15 (FN-only GT)
  - page_3 guard (Phase 4 baseline check)
- FN recovered (count + which FN)
  - gen1_vertical_run: 0 recovered; all 10 missed.
  - gen2_barline_cc_relaxed: 0 recovered; all 10 missed.
  - gen3_sobel_vertical: 0 recovered; all 10 missed.
- FP impact (raw + final)
  - gen1_vertical_run:
    - page_004: num_pred=170, FP=170, FN=12
    - page_10: num_pred=237, FP=216, FN=7
    - page_15: num_pred=154, FP=141, FN=14
    - page_3 guard: num_pred=222, FP=30, FN=0
  - gen2_barline_cc_relaxed:
    - page_004: num_pred=272, FP=272, FN=12
    - page_10: num_pred=393, FP=351, FN=7
    - page_15: num_pred=264, FP=238, FN=14
    - page_3 guard: num_pred=327, FP=31, FN=0
  - gen3_sobel_vertical:
    - page_004: num_pred=170, FP=170, FN=12
    - page_10: num_pred=237, FP=216, FN=7
    - page_15: num_pred=154, FP=141, FN=14
    - page_3 guard: num_pred=222, FP=30, FN=0
- Artifacts (FULL paths, color legends)
  - Overlay (Red=GT, Green=Pred): `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_batch1_overlays/gen1_vertical_run/20251226T_batch1_gen1_page_004_page_004_gt_red_pred_green_overlay.png`
  - Overlay (Red=GT, Green=Pred): `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_batch1_overlays/gen1_vertical_run/20251226T_batch1_gen1_page_10_page_10_gt_red_pred_green_overlay.png`
  - Overlay (Red=GT, Green=Pred): `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_batch1_overlays/gen1_vertical_run/20251226T_batch1_gen1_page_15_page_15_gt_red_pred_green_overlay.png`
  - Overlay (Red=GT, Green=Pred): `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_batch1_overlays/gen1_vertical_run/20251226T_batch1_gen1_page3_guard_page_3_gt_red_pred_green_overlay.png`
  - Overlay (Red=GT, Green=Pred): `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_batch1_overlays/gen2_barline_cc_relaxed/20251226T_batch1_gen2_page_004_page_004_gt_red_pred_green_overlay.png`
  - Overlay (Red=GT, Green=Pred): `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_batch1_overlays/gen2_barline_cc_relaxed/20251226T_batch1_gen2_page_10_page_10_gt_red_pred_green_overlay.png`
  - Overlay (Red=GT, Green=Pred): `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_batch1_overlays/gen2_barline_cc_relaxed/20251226T_batch1_gen2_page_15_page_15_gt_red_pred_green_overlay.png`
  - Overlay (Red=GT, Green=Pred): `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_batch1_overlays/gen2_barline_cc_relaxed/20251226T_batch1_gen2_page3_guard_page_3_gt_red_pred_green_overlay.png`
  - Overlay (Red=GT, Green=Pred): `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_batch1_overlays/gen3_sobel_vertical/20251226T_batch1_gen3_page_004_page_004_gt_red_pred_green_overlay.png`
  - Overlay (Red=GT, Green=Pred): `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_batch1_overlays/gen3_sobel_vertical/20251226T_batch1_gen3_page_10_page_10_gt_red_pred_green_overlay.png`
  - Overlay (Red=GT, Green=Pred): `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_batch1_overlays/gen3_sobel_vertical/20251226T_batch1_gen3_page_15_page_15_gt_red_pred_green_overlay.png`
  - Overlay (Red=GT, Green=Pred): `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_batch1_overlays/gen3_sobel_vertical/20251226T_batch1_gen3_page3_guard_page_3_gt_red_pred_green_overlay.png`
  - Summary JSON: `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_batch1_overlays/batch1_summary.json`
  - Metrics brief JSON: `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251226T_batch1_overlays/batch1_metrics_brief.json`
- Decision (keep / discard / refine)
  - All three generators failed to recover any remaining FN and added FP (especially gen2); **discard** as-is.
  - Note: initial multi-command batch timed out; remaining runs completed individually afterward.

### [Experiment Batch 2] No-staff-mask + tiny-CC variants (2025-12-27 01:19 JST)
- Objective / hypothesis: Test additional candidate generators (no staff mask and tiny CC) to increase FN recall without assuming a single FN cause.
- What I checked / tested: Ran gen4 vertical-run no staff mask, gen5 tiny CC on bar_line_img, gen6 sobel vertical no staff mask on page_004/page_10/page_15 + page_3 guard. Generated GT+pred overlays for each run.
- Commands run:
  - `docker exec homr_eval_gpu bash -lc 'cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/evaluation/images/page_3.png --ground-truth page_3:/workspace/data/evaluation/annotations/page_003/boxes_sorted.json --output-root /workspace/logs/homr_eval --force-run-id 20251227T_batch2_gen4_page3_guard --gen-vertical-run-no-staff'`
  - `docker exec homr_eval_gpu bash -lc 'cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/evaluation/images/page_15.png --ground-truth page_15:/workspace/logs/phase6_detector_miss/gt_fix_review_full/gt_corrected/page_15/fn_only_corrected.json --output-root /workspace/logs/homr_eval --force-run-id 20251227T_batch2_gen5_page_15 --gen-barline-cc-tiny'`
  - `docker exec homr_eval_gpu bash -lc 'cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/evaluation/images/page_3.png --ground-truth page_3:/workspace/data/evaluation/annotations/page_003/boxes_sorted.json --output-root /workspace/logs/homr_eval --force-run-id 20251227T_batch2_gen5_page3_guard --gen-barline-cc-tiny'`
  - `docker exec homr_eval_gpu bash -lc 'cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/evaluation/images/page_15.png --ground-truth page_15:/workspace/logs/phase6_detector_miss/gt_fix_review_full/gt_corrected/page_15/fn_only_corrected.json --output-root /workspace/logs/homr_eval --force-run-id 20251227T_batch2_gen6_page_15 --gen-sobel-no-staff'`
  - `docker exec homr_eval_gpu bash -lc 'cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/evaluation/images/page_3.png --ground-truth page_3:/workspace/data/evaluation/annotations/page_003/boxes_sorted.json --output-root /workspace/logs/homr_eval --force-run-id 20251227T_batch2_gen6_page3_guard --gen-sobel-no-staff'`
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/.venv_pdf/bin/python /tmp/summarize_batch2_metrics.py`
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/.venv_pdf/bin/python /tmp/summarize_batch2_recovered.py`
  - `bash /tmp/render_batch2_overlays.sh`
- Key results (quantitative + qualitative):
  - gen4_vertical_run_no_staff:
    - page_004: TP=0 FP=210 FN=12 (0/12 recovered)
    - page_10: TP=18 FP=340 FN=6 (18/24 recovered)
    - page_15: TP=14 FP=256 FN=8 (14/22 recovered)
    - page_3 guard: TP=152 FP=30 FN=0 (FP +30 vs baseline)
  - gen5_barline_cc_tiny:
    - page_004: TP=0 FP=272 FN=12 (0/12 recovered)
    - page_10: TP=17 FP=351 FN=7 (17/24 recovered)
    - page_15: TP=8 FP=238 FN=14 (8/22 recovered)
    - page_3 guard: TP=152 FP=31 FN=0 (FP +31 vs baseline)
  - gen6_sobel_no_staff:
    - page_004: TP=3 FP=342 FN=9 (3/12 recovered)
    - page_10: TP=19 FP=460 FN=5 (19/24 recovered)
    - page_15: TP=15 FP=354 FN=7 (15/22 recovered)
    - page_3 guard: TP=152 FP=55 FN=0 (FP +55 vs baseline)
  - Overall: no generator recovers any FN on page_004 beyond 3/12 for gen6; FP inflation increases significantly for guard page.
- Artifacts saved (FULL paths + color legend):
  - Color legend for ALL overlays: Red=GT boxes, Green=predicted boxes (from `*_detections.json`).
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch2_overlays/gen4_vertical_run_no_staff/page_004_20251227T_batch2_gen4_page_004_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch2_overlays/gen4_vertical_run_no_staff/page_10_20251227T_batch2_gen4_page_10_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch2_overlays/gen4_vertical_run_no_staff/page_15_20251227T_batch2_gen4_page_15_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch2_overlays/gen4_vertical_run_no_staff/page_3_20251227T_batch2_gen4_page3_guard_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch2_overlays/gen5_barline_cc_tiny/page_004_20251227T_batch2_gen5_page_004_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch2_overlays/gen5_barline_cc_tiny/page_10_20251227T_batch2_gen5_page_10_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch2_overlays/gen5_barline_cc_tiny/page_15_20251227T_batch2_gen5_page_15_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch2_overlays/gen5_barline_cc_tiny/page_3_20251227T_batch2_gen5_page3_guard_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch2_overlays/gen6_sobel_no_staff/page_004_20251227T_batch2_gen6_page_004_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch2_overlays/gen6_sobel_no_staff/page_10_20251227T_batch2_gen6_page_10_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch2_overlays/gen6_sobel_no_staff/page_15_20251227T_batch2_gen6_page_15_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch2_overlays/gen6_sobel_no_staff/page_3_20251227T_batch2_gen6_page3_guard_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch2_overlays/batch2_metrics_brief.json
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch2_overlays/batch2_recovered_gt_indices.json
- Conclusion / implication: Additional candidate generators (no staff mask + tiny CC + sobel no staff mask) still fail to recover page_004 FN; page_3 guard FP regressions worsen. None are suitable as-is for recall gains; next step is to inspect candidate generation quality vs GT for the persistent FN set to find a shared drop point or adjust normalization.

### [Work Unit A] Base generator selection + baseline metrics (2025-12-27 02:09 JST)
- Objective / hypothesis: Use gen4_vertical_run_no_staff as base (lower FP than gen6) and confirm baseline metrics on page_10/page_15 FN-only and page_3 guard.
- What I checked / tested: Rechecked repo docs once (README.md, docs/README.md, docs/NEXT_SESSION_NOTES.md). Ran base generator on page_10/page_15/page_3 guard with new run ids after adding staff-overlap filter option (left at default 0.0, so no change in behavior).
- Commands run:
  - `bash /tmp/run_batch3_base.sh`
  - `docker exec homr_eval_gpu bash -lc 'cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/evaluation/images/page_3.png --ground-truth page_3:/workspace/data/evaluation/annotations/page_003/boxes_sorted.json --output-root /workspace/logs/homr_eval --force-run-id 20251227T_batch3_base_page3_guard --gen-vertical-run-no-staff'`
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/.venv_pdf/bin/python /tmp/summarize_batch3_metrics.py`
- Key results (quantitative + qualitative):
  - page_10 (base): TP=18 FP=340 FN=6 (recall 0.75)
  - page_15 (base): TP=14 FP=256 FN=8 (recall 0.636)
  - page_3 guard (base): TP=152 FP=30 FN=0
- Artifacts saved (FULL paths + color legend):
  - Metrics summary JSON: /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/batch3_metrics_brief.json
- Conclusion / implication: gen4_vertical_run_no_staff remains the base; FP on page_3 still +30 vs baseline, so we proceed to FP sampling and cheap filter variants.

### [Work Unit B] FP sampling on page_3 (2025-12-27 02:09 JST)
- Objective / hypothesis: Sample FP patterns from page_3 to guide cheap geometry-based filters.
- What I checked / tested: Sampled 20 FP boxes from base generator (page_3) and generated overlay + 10 FP crops.
- Commands run:
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/.venv_pdf/bin/python /tmp/sample_fp_overlays.py --base /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/data/evaluation/images/page_3.png --gt /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/data/evaluation/annotations/page_003/boxes_sorted.json --pred /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/homr_eval/20251227T_batch3_base_page3_guard/page_3/page_3_detections.json --metrics /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/homr_eval/20251227T_batch3_base_page3_guard/metrics.json --output-overlay /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_fp_sampling/page_3_base_gt_red_pred_green_fp_blue_overlay.png --output-crops-dir /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_fp_sampling/crops`
- Key results (quantitative + qualitative):
  - Sampled FP indices: [0, 1, 4, 14, 28, 29, 31, 42, 45, 48, 63, 73, 77, 91, 105, 109, 110, 111, 112, 116]
- Artifacts saved (FULL paths + color legend):
  - Overlay legend: Red=GT boxes, Green=all predictions, Blue=sampled FP predictions.
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_fp_sampling/page_3_base_gt_red_pred_green_fp_blue_overlay.png
  - Crop legend: Blue=sampled FP prediction.
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_fp_sampling/crops/fp000_pred_blue_crop.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_fp_sampling/crops/fp001_pred_blue_crop.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_fp_sampling/crops/fp004_pred_blue_crop.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_fp_sampling/crops/fp014_pred_blue_crop.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_fp_sampling/crops/fp028_pred_blue_crop.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_fp_sampling/crops/fp029_pred_blue_crop.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_fp_sampling/crops/fp031_pred_blue_crop.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_fp_sampling/crops/fp042_pred_blue_crop.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_fp_sampling/crops/fp045_pred_blue_crop.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_fp_sampling/crops/fp048_pred_blue_crop.png
- Conclusion / implication: FP patterns are captured for filter tuning; proceed to staff-overlap filter variants.

### [Work Unit C] Staff-overlap filter variants (2025-12-27 02:09 JST)
- Objective / hypothesis: Add a cheap geometry filter (staff mask overlap ratio) to reduce FP while preserving FN-only recall.
- What I changed / tested: Implemented optional staff-overlap filter (`--barline-staff-overlap-min`) and ran 5 threshold variants (0.1–0.5) with gen4 base on page_10/page_15/page_3 guard. Generated GT+pred overlays for each variant/page.
- Commands run:
  - `docker exec homr_eval_gpu bash -lc '... --force-run-id 20251227T_batch3_v0p1_page_10 --gen-vertical-run-no-staff --barline-staff-overlap-min 0.1'`
  - `docker exec homr_eval_gpu bash -lc '... --force-run-id 20251227T_batch3_v0p1_page_15 --gen-vertical-run-no-staff --barline-staff-overlap-min 0.1'`
  - `docker exec homr_eval_gpu bash -lc '... --force-run-id 20251227T_batch3_v0p1_page3_guard --gen-vertical-run-no-staff --barline-staff-overlap-min 0.1'`
  - `docker exec homr_eval_gpu bash -lc '... --force-run-id 20251227T_batch3_v0p2_page_10 --gen-vertical-run-no-staff --barline-staff-overlap-min 0.2'`
  - `docker exec homr_eval_gpu bash -lc '... --force-run-id 20251227T_batch3_v0p2_page_15 --gen-vertical-run-no-staff --barline-staff-overlap-min 0.2'`
  - `docker exec homr_eval_gpu bash -lc '... --force-run-id 20251227T_batch3_v0p2_page3_guard --gen-vertical-run-no-staff --barline-staff-overlap-min 0.2'`
  - `docker exec homr_eval_gpu bash -lc '... --force-run-id 20251227T_batch3_v0p3_page_10 --gen-vertical-run-no-staff --barline-staff-overlap-min 0.3'`
  - `docker exec homr_eval_gpu bash -lc '... --force-run-id 20251227T_batch3_v0p3_page_15 --gen-vertical-run-no-staff --barline-staff-overlap-min 0.3'`
  - `docker exec homr_eval_gpu bash -lc '... --force-run-id 20251227T_batch3_v0p3_page3_guard --gen-vertical-run-no-staff --barline-staff-overlap-min 0.3'`
  - `docker exec homr_eval_gpu bash -lc '... --force-run-id 20251227T_batch3_v0p4_page_10 --gen-vertical-run-no-staff --barline-staff-overlap-min 0.4'`
  - `docker exec homr_eval_gpu bash -lc '... --force-run-id 20251227T_batch3_v0p4_page_15 --gen-vertical-run-no-staff --barline-staff-overlap-min 0.4'`
  - `docker exec homr_eval_gpu bash -lc '... --force-run-id 20251227T_batch3_v0p4_page3_guard --gen-vertical-run-no-staff --barline-staff-overlap-min 0.4'`
  - `docker exec homr_eval_gpu bash -lc '... --force-run-id 20251227T_batch3_v0p5_page_10 --gen-vertical-run-no-staff --barline-staff-overlap-min 0.5'`
  - `docker exec homr_eval_gpu bash -lc '... --force-run-id 20251227T_batch3_v0p5_page_15 --gen-vertical-run-no-staff --barline-staff-overlap-min 0.5'`
  - `docker exec homr_eval_gpu bash -lc '... --force-run-id 20251227T_batch3_v0p5_page3_guard --gen-vertical-run-no-staff --barline-staff-overlap-min 0.5'`
  - `bash /tmp/render_batch3_variant_overlays.sh`
  - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/.venv_pdf/bin/python /tmp/summarize_batch3_metrics.py`
- Key results (quantitative + qualitative):
  - v0p1 (min overlap 0.1): page_10 TP=18 FP=332 FN=6; page_15 TP=14 FP=238 FN=8; page_3 TP=152 FP=30 FN=0 (no guard improvement)
  - v0p2 (0.2): page_10 TP=17 FP=328 FN=7; page_15 TP=12 FP=231 FN=10; page_3 TP=150 FP=29 FN=2 (guard FN regression)
  - v0p3 (0.3): page_10 TP=13 FP=265 FN=11; page_15 TP=6 FP=179 FN=16; page_3 TP=120 FP=29 FN=32 (major recall regression)
  - v0p4 (0.4): page_10 TP=0 FP=81 FN=24; page_15 TP=2 FP=44 FN=20; page_3 TP=120 FP=29 FN=32 (collapse)
  - v0p5 (0.5): page_10 TP=0 FP=81 FN=24; page_15 TP=0 FP=44 FN=22; page_3 TP=120 FP=29 FN=32 (collapse)
- Artifacts saved (FULL paths + color legend):
  - Color legend for ALL overlays: Red=GT boxes, Green=predicted boxes (from `*_detections.json`).
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/overlays/20251227T_batch3_v0p1_page_10/page_10_20251227T_batch3_v0p1_page_10_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/overlays/20251227T_batch3_v0p1_page_15/page_15_20251227T_batch3_v0p1_page_15_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/overlays/20251227T_batch3_v0p1_page3_guard/page_3_20251227T_batch3_v0p1_page3_guard_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/overlays/20251227T_batch3_v0p2_page_10/page_10_20251227T_batch3_v0p2_page_10_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/overlays/20251227T_batch3_v0p2_page_15/page_15_20251227T_batch3_v0p2_page_15_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/overlays/20251227T_batch3_v0p2_page3_guard/page_3_20251227T_batch3_v0p2_page3_guard_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/overlays/20251227T_batch3_v0p3_page_10/page_10_20251227T_batch3_v0p3_page_10_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/overlays/20251227T_batch3_v0p3_page_15/page_15_20251227T_batch3_v0p3_page_15_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/overlays/20251227T_batch3_v0p3_page3_guard/page_3_20251227T_batch3_v0p3_page3_guard_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/overlays/20251227T_batch3_v0p4_page_10/page_10_20251227T_batch3_v0p4_page_10_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/overlays/20251227T_batch3_v0p4_page_15/page_15_20251227T_batch3_v0p4_page_15_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/overlays/20251227T_batch3_v0p4_page3_guard/page_3_20251227T_batch3_v0p4_page3_guard_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/overlays/20251227T_batch3_v0p5_page_10/page_10_20251227T_batch3_v0p5_page_10_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/overlays/20251227T_batch3_v0p5_page_15/page_15_20251227T_batch3_v0p5_page_15_gt_red_pred_green_overlay.png
  - /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/overlays/20251227T_batch3_v0p5_page3_guard/page_3_20251227T_batch3_v0p5_page3_guard_gt_red_pred_green_overlay.png
  - Metrics summary JSON: /home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch3_variants/batch3_metrics_brief.json
- Conclusion / implication: Staff-overlap filter reduces FP modestly at 0.1 but does not improve page_3 FP (still +30) and higher thresholds rapidly destroy recall and staff detection. This filter alone is not sufficient for aggressive FP reduction without major recall loss.

### [Experiment Batch 4] Weak vertical-run/sobel + dilated CC generators (GPU) (2025-12-27 06:30 JST)
- Objective / hypothesis: expand candidate generation (Lane A) with weaker vertical-run + weaker Sobel + dilated CC on bar_line_img to recover FN across multiple pages without focusing on single FN.
- What I checked / tested:
  - Re-opened `README.md`, `docs/README.md`, `docs/NEXT_SESSION_NOTES.md` to confirm phase goals and constraints.
  - Verified CUDA provider in `homr_eval_gpu` via `poetry run` (torch.cuda True, ort device GPU).
  - Implemented new candidate generators in `src/homr_eval_scripts/homr_evaluator.py`:
    - `--gen-vertical-run-weak` (min_run=10, dark_threshold=130)
    - `--gen-sobel-vertical-weak` (sobel_threshold=40, min_run=10)
    - `--gen-barline-cc-dilated` (vertical dilation kernel 5x1)
  - Ran GPU evaluations with `poetry run` (CUDAExecutionProvider) on page_10/page_15/page_004 (FN-only GT) and page_3 guard.
  - Generated GT vs pred overlays for every run (Red=GT, Green=pred).
- Commands run:
  - GPU sanity check: `docker exec -i homr_eval_gpu bash -lc "cd /workspace/external/homr && poetry run python -c 'import torch, onnxruntime as ort; print(torch.cuda.is_available()); print(ort.get_device())'"`
  - Example eval (all runs listed below in run_ids):
    - `docker exec -i homr_eval_gpu bash -lc "cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/training/images/page_10.png --ground-truth page_10:/workspace/logs/phase6_detector_miss/gt_fix_review_full/gt_corrected/page_10/fn_only_corrected.json --output-root /workspace/logs/homr_eval --force-run-id 20251227T_batch4b_vrunweak_page_10 --gen-vertical-run-weak"`
  - Overlay generation (container, GT+pred): `docker exec -i homr_eval_gpu bash -lc "cd /workspace/external/homr && poetry run python /workspace/tmp/render_gt_pred_overlay.py --base <base> --gt <gt> --pred <pred_json> --output <overlay>"`
- Key results (quantitative + qualitative):
  - No FN recovery observed; FN counts are same or worse vs previous gen4 baseline.
  - `20251227T_batch4b_vrunweak_*`:
    - page_10: TP=17 FP=216 FN=7
    - page_15: TP=8 FP=141 FN=14
    - page_004: TP=0 FP=170 FN=12
    - page_3: TP=152 FP=30 FN=0
  - `20251227T_batch4b_sobelweak_*`:
    - page_10: TP=17 FP=216 FN=7
    - page_15: TP=8 FP=141 FN=14
    - page_004: TP=0 FP=170 FN=12
    - page_3: TP=152 FP=30 FN=0
  - `20251227T_batch4b_ccdilated_*`:
    - page_10: TP=17 FP=352 FN=7
    - page_15: TP=8 FP=239 FN=14
    - page_004: TP=0 FP=274 FN=12
    - page_3: TP=152 FP=32 FN=0
- Artifacts saved (FULL paths + color legend):
  - Metrics summary: `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch4b_metrics_summary.json`
  - Overlays (Red=GT, Green=pred):
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch4b_overlays/20251227T_batch4b_vrunweak_page_10/page_10_20251227T_batch4b_vrunweak_page_10_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch4b_overlays/20251227T_batch4b_vrunweak_page_15/page_15_20251227T_batch4b_vrunweak_page_15_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch4b_overlays/20251227T_batch4b_vrunweak_page_004/page_004_20251227T_batch4b_vrunweak_page_004_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch4b_overlays/20251227T_batch4b_vrunweak_page3_guard/page_3_20251227T_batch4b_vrunweak_page3_guard_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch4b_overlays/20251227T_batch4b_sobelweak_page_10/page_10_20251227T_batch4b_sobelweak_page_10_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch4b_overlays/20251227T_batch4b_sobelweak_page_15/page_15_20251227T_batch4b_sobelweak_page_15_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch4b_overlays/20251227T_batch4b_sobelweak_page_004/page_004_20251227T_batch4b_sobelweak_page_004_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch4b_overlays/20251227T_batch4b_sobelweak_page3_guard/page_3_20251227T_batch4b_sobelweak_page3_guard_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch4b_overlays/20251227T_batch4b_ccdilated_page_10/page_10_20251227T_batch4b_ccdilated_page_10_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch4b_overlays/20251227T_batch4b_ccdilated_page_15/page_15_20251227T_batch4b_ccdilated_page_15_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch4b_overlays/20251227T_batch4b_ccdilated_page_004/page_004_20251227T_batch4b_ccdilated_page_004_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch4b_overlays/20251227T_batch4b_ccdilated_page3_guard/page_3_20251227T_batch4b_ccdilated_page3_guard_gt_red_pred_green_overlay.png`
- Decision (keep / discard / next):
  - Discard these three weak/dilated generators for FN recovery (no FN gains; FP increases). Next step should try a different candidate-generation family (Lane A) rather than FP compression on failed candidates.

### [Experiment Batch 5] Column-sum candidate generators (staff/no-staff) (2025-12-27 07:10 JST)
- Objective / hypothesis: test a different candidate-generation family (column-sum projection of dark pixels) to increase recall across FN pages.
- What I checked / tested:
  - Implemented column-sum candidates in `src/homr_eval_scripts/homr_evaluator.py` with three toggles:
    - `--gen-column-sum-staff` (min_column_sum=20, dark_threshold=120)
    - `--gen-column-sum-weak` (min_column_sum=12, dark_threshold=140)
    - `--gen-column-sum-no-staff` (min_column_sum=20, dark_threshold=120)
  - Ran GPU evaluations on page_10/page_15/page_004 FN-only GT and page_3 guard for each variant.
  - Generated GT vs pred overlays (Red=GT, Green=pred).
- Commands run:
  - Example eval: `docker exec -i homr_eval_gpu bash -lc "cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/training/images/page_10.png --ground-truth page_10:/workspace/logs/phase6_detector_miss/gt_fix_review_full/gt_corrected/page_10/fn_only_corrected.json --output-root /workspace/logs/homr_eval --force-run-id 20251227T_batch5_colsumstaff_page_10 --gen-column-sum-staff"`
  - Overlay generation: `docker exec -i homr_eval_gpu bash -lc "cd /workspace/external/homr && poetry run python /workspace/tmp/render_gt_pred_overlay.py --base <base> --gt <gt> --pred <pred_json> --output <overlay>"`
- Key results (quantitative + qualitative):
  - No FN recovery; results match batch4 patterns.
  - `20251227T_batch5_colsumstaff_*`:
    - page_10: TP=17 FP=216 FN=7
    - page_15: TP=8 FP=141 FN=14
    - page_004: TP=0 FP=170 FN=12
    - page_3: TP=152 FP=30 FN=0
  - `20251227T_batch5_colsumweak_*`:
    - page_10: TP=17 FP=216 FN=7
    - page_15: TP=8 FP=141 FN=14
    - page_004: TP=0 FP=170 FN=12
    - page_3: TP=152 FP=30 FN=0
  - `20251227T_batch5_colsum_nostaff_*`:
    - page_10: TP=17 FP=222 FN=7
    - page_15: TP=8 FP=146 FN=14
    - page_004: TP=0 FP=171 FN=12
    - page_3: TP=152 FP=33 FN=0
- Artifacts saved (FULL paths + color legend):
  - Metrics summary: `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch5_metrics_summary.json`
  - Overlays (Red=GT, Green=pred):
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch5_overlays/20251227T_batch5_colsumstaff_page_10/page_10_20251227T_batch5_colsumstaff_page_10_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch5_overlays/20251227T_batch5_colsumstaff_page_15/page_15_20251227T_batch5_colsumstaff_page_15_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch5_overlays/20251227T_batch5_colsumstaff_page_004/page_004_20251227T_batch5_colsumstaff_page_004_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch5_overlays/20251227T_batch5_colsumstaff_page3_guard/page_3_20251227T_batch5_colsumstaff_page3_guard_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch5_overlays/20251227T_batch5_colsumweak_page_10/page_10_20251227T_batch5_colsumweak_page_10_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch5_overlays/20251227T_batch5_colsumweak_page_15/page_15_20251227T_batch5_colsumweak_page_15_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch5_overlays/20251227T_batch5_colsumweak_page_004/page_004_20251227T_batch5_colsumweak_page_004_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch5_overlays/20251227T_batch5_colsumweak_page3_guard/page_3_20251227T_batch5_colsumweak_page3_guard_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch5_overlays/20251227T_batch5_colsum_nostaff_page_10/page_10_20251227T_batch5_colsum_nostaff_page_10_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch5_overlays/20251227T_batch5_colsum_nostaff_page_15/page_15_20251227T_batch5_colsum_nostaff_page_15_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch5_overlays/20251227T_batch5_colsum_nostaff_page_004/page_004_20251227T_batch5_colsum_nostaff_page_004_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch5_overlays/20251227T_batch5_colsum_nostaff_page3_guard/page_3_20251227T_batch5_colsum_nostaff_page3_guard_gt_red_pred_green_overlay.png`
- Decision (keep / discard / next):
  - Discard column-sum generators for FN recovery (no FN gains, FP rises). Next: switch to a new candidate family (e.g., staff-height normalized vertical CC on stems_rest or stem-mask-subtracted detector) rather than further FP compression on these failed candidates.

### [Experiment Batch 6] Hough vertical line candidates (staff-masked) (2025-12-27 07:30 JST)
- Objective / hypothesis: try Hough-based vertical line extraction to introduce a new candidate family with different sensitivity to faint/fragmented bars.
- What I checked / tested:
  - Implemented `generate_hough_vertical_candidates` in `src/homr_eval_scripts/homr_evaluator.py`.
  - Added flags:
    - `--gen-hough-vertical`
    - `--gen-hough-vertical-weak` (lower thresholds, shorter min length)
  - Ran GPU evaluations on page_10/page_15/page_004 FN-only GT and page_3 guard for both variants.
  - Generated GT vs pred overlays (Red=GT, Green=pred).
- Commands run:
  - Example eval: `docker exec -i homr_eval_gpu bash -lc "cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/training/images/page_10.png --ground-truth page_10:/workspace/logs/phase6_detector_miss/gt_fix_review_full/gt_corrected/page_10/fn_only_corrected.json --output-root /workspace/logs/homr_eval --force-run-id 20251227T_batch6_hough_page_10 --gen-hough-vertical"`
  - Overlay generation: `docker exec -i homr_eval_gpu bash -lc "cd /workspace/external/homr && poetry run python /workspace/tmp/render_gt_pred_overlay.py --base <base> --gt <gt> --pred <pred_json> --output <overlay>"`
- Key results (quantitative + qualitative):
  - No FN recovery observed (metrics essentially identical to previous candidate generators).
  - `20251227T_batch6_hough_*`:
    - page_10: TP=17 FP=216 FN=7
    - page_15: TP=8 FP=141 FN=14
    - page_004: TP=0 FP=170 FN=12
    - page_3: TP=152 FP=30 FN=0
  - `20251227T_batch6_houghweak_*`:
    - page_10: TP=17 FP=216 FN=7
    - page_15: TP=8 FP=142 FN=14
    - page_004: TP=0 FP=170 FN=12
    - page_3: TP=152 FP=30 FN=0
- Artifacts saved (FULL paths + color legend):
  - Metrics summary: `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch6_metrics_summary.json`
  - Overlays (Red=GT, Green=pred):
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch6_overlays/20251227T_batch6_hough_page_10/page_10_20251227T_batch6_hough_page_10_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch6_overlays/20251227T_batch6_hough_page_15/page_15_20251227T_batch6_hough_page_15_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch6_overlays/20251227T_batch6_hough_page_004/page_004_20251227T_batch6_hough_page_004_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch6_overlays/20251227T_batch6_hough_page3_guard/page_3_20251227T_batch6_hough_page3_guard_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch6_overlays/20251227T_batch6_houghweak_page_10/page_10_20251227T_batch6_houghweak_page_10_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch6_overlays/20251227T_batch6_houghweak_page_15/page_15_20251227T_batch6_houghweak_page_15_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch6_overlays/20251227T_batch6_houghweak_page_004/page_004_20251227T_batch6_houghweak_page_004_gt_red_pred_green_overlay.png`
    - `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/logs/validation/20251227T_batch6_overlays/20251227T_batch6_houghweak_page3_guard/page_3_20251227T_batch6_houghweak_page3_guard_gt_red_pred_green_overlay.png`
- Decision (keep / discard / next):
  - Discard Hough candidates (no FN recovery, FP unchanged). Next: move to a different candidate family using segmentation masks directly (e.g., stem-mask-subtracted vertical CC or staff-height normalized mask dilation) rather than further edge-based detectors.
