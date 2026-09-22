# Issue #372 retained detector regression triage

This directory contains investigation-only tooling for the detector regression
tracked by Issue #372. Production behavior is unchanged.

## First retained-only comparison

The first gate compares:

- accepted Issue #296 D27 full68 summary;
- saved current-production output from the Issue #43 full68 run;
- historical fixed-12px matcher used by D27;
- current staff-unit matcher.

It does **not** run HOMR, SR, OMR-DLN, or CNN inference.

Expected D27 summary:

```text
logs/issue296/diagnostic_27_current_candidate_aligned/full68/clean_full68_summary.json
```

Expected Issue #43 run:

```text
logs/issue43/full68_x_domain_ab/issue43_full68_20260922T121216Z/
```

The Issue #43 run directory may be root-owned because it was created through
Docker. Do not write into that retained tree. Instead, copy only the saved
detector JSON artifacts into the writable Issue #372 worktree:

```bash
(
  set -euo pipefail

  MAIN=/home/masaki_muramatsu/ws_PDFScoreBar
  I43=/home/masaki_muramatsu/ws_PDFScoreBar_issue43
  I372=/home/masaki_muramatsu/ws_PDFScoreBar_issue372
  RUN=issue43_full68_20260922T121216Z
  REPORT="$I43/logs/issue43/full68_x_domain_ab/$RUN/issue43_full68_x_domain_ab_report.json"
  DEST="$I372/logs/issue372/current_production_probe_output"

  "$MAIN/.venv_pdf/bin/python" \
    "$I372/experiments/issue372/materialize_issue43_production_outputs.py" \
    --report "$REPORT" \
    --source-repo-root "$I43" \
    --destination "$DEST"
)
```

This is retained-only file copying: it does not rerun HOMR, SR, OMR-DLN, or CNN.

Then, from a checkout of `fix/issue372-detector-regression`:

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar
git fetch origin
git switch fix/issue372-detector-regression
git pull --ff-only

/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python \
  experiments/issue372/compare_retained_detector_contracts.py \
  --d27-summary logs/issue296/diagnostic_27_current_candidate_aligned/full68/clean_full68_summary.json \
  --current-root /home/masaki_muramatsu/ws_PDFScoreBar_issue372/logs/issue372/current_production_probe_output \
  --image-root /home/masaki_muramatsu/ws_PDFScoreBar/data/evaluation2/images \
  --output logs/issue372/retained_detector_comparison.json
```

The report records:

- D27 vs current aggregate/page-level detector metrics under the same legacy
  matcher;
- current legacy-vs-staff-unit matcher deltas;
- each newly missing GT bbox relative to D27;
- whether each new FN is already absent from current candidates
  (`stage=detector`) or present before CNN (`stage=cnn`);
- exact-bbox hard-FP additions/removals;
- hashes of all current saved candidate/final files consumed by the comparison.

## Missing-artifact preflight

Before running the comparison, these checks are sufficient:

```bash
test -f /home/masaki_muramatsu/ws_PDFScoreBar/logs/issue296/diagnostic_27_current_candidate_aligned/full68/clean_full68_summary.json
test -f /home/masaki_muramatsu/ws_PDFScoreBar_issue43/logs/issue43/full68_x_domain_ab/issue43_full68_20260922T121216Z/issue43_full68_x_domain_ab_report.json
find /home/masaki_muramatsu/ws_PDFScoreBar_issue372/logs/issue372/current_production_probe_output \
  -name pipeline2_no_peak_filtered_cnn.json | wc -l
```

The final count should be 68. If the first D27 path is absent, do not rerun
training; locate retained D27 summaries first:

```bash
find /home/masaki_muramatsu/ws_PDFScoreBar/logs/issue296 \
  -type f -name clean_full68_summary.json -print
```
