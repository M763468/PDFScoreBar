# Next steps after exact page-001 reconstruction

1. Run the fresh public-upstream HOMR probe and require:
   - public source checkout at `864e288`;
   - public model downloads through that revision's `download_weights()` route;
   - exact model SHA-256 matches;
   - page-001 `87/87`, with zero retained-only and zero candidate-only records.
2. If the public-upstream gate passes, select a small representative page set from existing Issue #244 page-level evidence. Include page-001 plus detector FP/FN extremes and one guard page. Do not guess page IDs manually.
3. Regenerate baseline HOMR only for that set, keeping SR, OMR, consensus, dense, CNN, MMR, and numbering unchanged.
4. If the focused set preserves historical baseline behavior, construct the fresh baseline-HOMR production route behind an explicit non-default configuration.
5. Run full-68 detector metrics, physical measure signatures, post-#221 MMR gates, page-033 guard, and corrected-final page-001 row starts.
6. Change no production default until all gates pass.

The investigation branch history contains many temporary compatibility and archaeology commits. Squash and retain only the final reproduction tooling, provenance record, and accepted implementation before opening the PR.
