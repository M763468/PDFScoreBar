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
