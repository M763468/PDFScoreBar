# Issue #244 temporary investigation helpers

These scripts are temporary diagnostics for Issue #244 and must be removed before the final PR.

The accepted production detector route has **not** been established yet. The current investigation compares retained Stage E artifacts with fresh full-68 pipeline output and isolates upstream hybrid prediction drift.

Current sequence:

1. `analyze_full68_route_drift.sh`
2. `run_full68_hybrid_mask_cross.sh`
3. `evaluate_full68_hybrid_mask_cross.sh`
4. `analyze_full68_hybrid_sources.sh`

Do not treat any generated candidate profile as a production default until the full-68 detector, numbering, and MMR regression gates pass.
