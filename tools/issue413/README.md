# Issue #413: retained Phase-C replay

This tool checks recognition-to-application identity on the five scores / 68 pages
retained by [Issue #409](https://github.com/M763468/PDFScoreBar/issues/409). It does
not run SR, HOMR, detector/CNN inference, MMR classification, or OCR. It reconstructs
Phase-C pages from the original images, barlines, staff masks and connector masks,
copies retained base numbering and MMR predictions, and executes the real
orchestrator's final-numbering and combined-output paths.

The retained input root is local ignored data, not included in a fresh checkout:
`logs/issue409/full68-numbering-20261009/`. Its source revision is
`a65d9541777ae492137c24b6ce0f5f5692881945`, and the canonical dense configuration
SHA-256 is `0edfdfda89ed50be6d0dafbf28fccc80840ef6330f193d19823a94f934cb2209`.
All original results remain intact. The runner requires a fresh output directory.

From the checkout root, in the maintained pipeline environment:

```bash
PYTHONPATH=. /opt/venv_pipeline/bin/python tools/issue413/replay_phase_c.py \
  --retained-root logs/issue409/full68-numbering-20261009 \
  --output logs/issue413/phase-c-replay/new-run
```

The execution-only configuration disables upstream execution and selects standard
input resolution, bypassing preparation of new Phase-B support. Recognition files
are copied unchanged and reused through `skip_existing`. Model/config/threshold
selection in the original experiment is unchanged. This narrowly scoped auditor
rejects retained configurations with manual overrides, movement boundaries or
barline overrides; those precedence/reset contracts have separate model-free tests.

The gates are fixed before interpreting the results:

- Reproduce the same 104 baseline application mismatches and resolve all of them.
- Compare recognized skips with actual increments at **every** physical measure,
  including zero-skip locations, cross-page successors and the final measure.
- Preserve geometry, source images, retained OCR/recognition and upstream artifacts.
- Preserve page continuity and per-page/combined JSON agreement.
- Match all final PDF row-label values to the corrected JSON and compare actual
  embedded PDF image pixels with the same expected page after JPEG encoding.
  This last check uses exact decoded RGB equality, without a tolerance.

The initial retained replay (`logs/issue413/phase-c-replay/run-01/`) passed across
3,287 physical measures: 104 application mismatches became zero, and 2,315 measure
numbers changed. All 68 final PDF pages and their 637 row-start labels matched.
The original-image audit inspected all 104 physical sites on 13 contact sheets.
The seven-measure rest in Festival Overture/page_001 is still recognized as 37;
the corrected consumer now applies that retained prediction to the intended
measure. This is application correctness, not an absolute-number or OCR-accuracy
claim. Remaining recognition/GT work belongs to #414 / #415.

Outputs include the predeclared contract, input hashes, all physical-measure
records, all 104 resolved mismatches, every number delta, per-page/combined JSON,
five final PDFs and their pixel-verification records. The original-image contact
sheets and review record for the initial run are also retained under its
`visual-audit/` directory. Generated artifacts stay out of Git.
