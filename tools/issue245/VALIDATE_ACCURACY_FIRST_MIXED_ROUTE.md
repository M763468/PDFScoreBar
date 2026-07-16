# Validate the Issue #245 accuracy-first mixed route

The mixed-route preparation step writes historical and mixed hybrid predictions as top-level box arrays. The evaluator-probe comparison loader accepts only `{"predictions": ...}` payloads, so the initial report could incorrectly classify 0-versus-0 as a successful equality check.

Run the validator after the mixed artifacts exist:

```bash
PYTHONPATH=. \
ISSUE245_MAIN_REPO_ROOT=/home/masaki_muramatsu/ws_PDFScoreBar \
python3 -m tools.issue245.validate_accuracy_first_mixed_route
```

The validator:

- reads both hybrid files with `src.pipeline.steps.hybrid_consensus.load_json_boxes`;
- recomputes all 68 tolerant comparisons;
- requires the retained historical hybrid total to be exactly 3,312;
- rejects empty mixed output;
- overwrites `accuracy_first_mixed_route_report.json` with validated nonzero counts.

A report is usable for the next Stage E gate only when:

```text
status=completed
comparison_validation.status=validated
aggregate_comparison_to_historical_hybrid.historical_count=3312
aggregate_comparison_to_historical_hybrid.mixed_count>0
```
