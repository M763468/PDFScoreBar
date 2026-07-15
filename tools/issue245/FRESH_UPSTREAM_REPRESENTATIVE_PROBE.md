# Fresh upstream HOMR representative-page probe

## Preconditions

The public-upstream page-001 probe must already have completed with:

```text
retained historical=87
fresh candidate=87
matched=87
historical-only=0
candidate-only=0
semantic_equal=true
```

The verified Docker image must have been retained with `--keep-image`:

```text
pdfscorebar-issue245-fresh-upstream-homr:864e2882f7a4
```

## Page set

The manifest `fresh_upstream_representative_pages.json` fixes three pages:

- `page_001`: corrected-final row-start smoke and the source/model/runtime boundary page;
- `page_033`: post-Issue-213 one-bar MMR veto guard from `Sibelius-Violin_Concerto-Viola_page_002`;
- `page_060`: known current-GT detector residual from Issue #202, `Va__Prokofiev_Symphony5_page_015`.

The retained comparison batch is pinned to date `20260131`. Individual page runs have different clock timestamps, so the runner discovers each run by normalizing the score-directory name and page stem across underscore/hyphen variants. It requires exactly one matching baseline detection for each page and records the resolved run path. Retained files are comparison evidence only and are not detector inputs.

## Run

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar_issue245

git fetch origin
git reset --hard \
  origin/investigate/issue245-fresh-upstream-detector-route

python3 -m py_compile \
  tools/issue245/run_fresh_upstream_representative_probe.py

PYTHONPATH=. python3 -m pytest \
  tests/test_issue245_fresh_upstream_representative_probe.py

bash tools/issue245/run_fresh_upstream_representative_probe.sh \
  --force
```

This probe reuses the already verified public-upstream image. It does not rebuild or download models again.

## Output

```text
logs/issue245_fresh_upstream_representative_probe/
  fresh_upstream_representative_probe_report.json
  pdfscore_source_snapshot/...
  pages/
    page_001/evaluator.log
    page_001/evaluator/...
    page_033/evaluator.log
    page_033/evaluator/...
    page_060/evaluator.log
    page_060/evaluator/...
```

## Decision gate

- `all_semantic_equal=true`: the fresh baseline HOMR route generalizes across the three focused score/layout guards; proceed to the full-68 baseline regeneration plan.
- Any page with historical-only or candidate-only records: stop before full-68 and inspect that page's evaluator log, input hash, and box examples.
- Ambiguous or missing retained matches stop the probe; do not guess which historical run belongs to the accepted batch.
- Do not change the production default from this representative baseline-only probe. Full-68 detector, physical-measure, MMR, and corrected-final gates remain required.
