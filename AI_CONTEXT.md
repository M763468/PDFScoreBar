# AI Context for PDFScoreBar (Homr/Oemer)

## Current Project Status
**Active Phase**: Maintenance / Future Planning
**Completed Project**: Barline FP Reduction (Dec 2025)

## Key Components
- **Pipeline**: PDF -> [Oemer/Homr] -> MusicXML
- **Critical Path**: Barline Detection (finding measure lines)

## Recent Achievements (FP Reduction)
We aimed to reduce False Positives (FPs) in barline detection on `page_3`.
- **Outcome**: **Optimization Complete**.
- **Stable Heuristic**: `Heuristic 1` (Safe Notehead Proximity Filter) is **ENABLED**.
  - Logic: Reject if near notehead AND small AND overlapped.
  - Metrics: 152 TP, 30 FP, 0 FN.
- **Failures**: Staff Crossing (H2), Cluster Resolution (H3), Tight Duplicates (H4), Measure Grid (H5) all **FAILED** due to fragmented True Positives.
- **Conclusion**: Visual heuristics are exhausted. Remaining FPs are indistinguishable from TPs locally.

## Next Steps / Future Work
1. **Interactive Verification (GUI)**:
   - Build a tool to let humans quickly accept/reject "Warning" candidates.
   - Do NOT try more automatic removal logic for now.
2. **Model Improvement**:
   - Retrain the segmentation model to produce cleaner, non-fragmented barlines.
   - Investigate external OMR models (Transformer-based).

## Documentation
- **Detailed History**: `docs/fp_reduction/development_log.md`
- **Final Summary**: `docs/fp_reduction/FINAL_SUMMARY.md`
- **Future Roadmap**: `docs/future/roadmap.md`

## Agents
See `docs/AGENTS.md` for specific agent roles.