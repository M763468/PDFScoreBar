# Issue #333 movement-boundary investigation result

This document records the bounded evidence and production disposition for
movement-boundary detection. The resolved numbering consumer remains
[`MOVEMENT_BOUNDARY_CONTRACT.md`](MOVEMENT_BOUNDARY_CONTRACT.md).

## Evidence gap and fixture

The current pipeline reconstructs page/system/measure geometry but does not
retain general heading OCR, PDF outline/text evidence, or semantic
final/double/repeat barline types in the numbering artifact. MMR OCR is scoped
to printed measure numbers and was not changed or reused as a movement
detector. Five local evaluation PDFs also had no native PDF outline entries or
extractable text, so native PDF evidence produced no candidates in this set.

Fresh current-pipeline runs at commit
`862a9833e2a349106107ed7709c597ba07b18a01` rendered selected source pages at
360 dpi and regenerated detector/system artifacts. Exact source-PDF page and
fresh system ground truth is retained in
`tests/fixtures/movement_boundaries/issue333_representative.json`:

| Score | Movement | Zero-based page/system | Placement |
| --- | --- | --- | --- |
| Prokofiev Symphony 1 | II | `2 / 3` | mid-page |
| Prokofiev Symphony 1 | III | `3 / 3` | mid-page |
| Prokofiev Symphony 1 | IV | `3 / 8` | mid-page; second start on page |
| Prokofiev Symphony 5 | II | `6 / 0` | page start |
| Prokofiev Symphony 5 | III | `12 / 0` | page start |
| Prokofiev Symphony 5 | IV | `15 / 5` | mid-page |
| Shostakovich Symphony 5 | II | `7 / 5` | mid-page |
| Sibelius Violin Concerto | II | `5 / 0` | page start |
| Sibelius Violin Concerto | III | `6 / 0` | page start |

All nine observed movement starts align with the start of a reconstructed
system. The set includes page starts, mid-page starts, and two starts on one
page. No real example required a movement start inside a system, so extending
the consumer to measure granularity is not justified.

Reviewed negatives include ordinary and multi-page continuations, large
inter-system whitespace, a `Più Lento`/tempo heading within a movement, and a
final/end-like barline at the end of a single-movement score. These remain
`no_boundary`; page breaks, tempo text, spacing, and end-like barlines are not
individually reset instructions.

## Bounded strategy comparison

The fixed comparison covered 168 reconstructed system starts: 9 true movement
starts and 159 negatives. False reset and missed boundary were scored
separately. Experiment cutoffs were fixed for the comparison but are not a
calibrated confidence model:

- layout candidate: left indent at least 2% of page width relative to the page
  median, or preceding whitespace at least 1.75 times the page median gap;
- heading candidate: OCR movement/tempo token mapped to the following system;
- conservative consensus: intersection of those two candidate sets.

| Strategy | True positive | False reset | Missed boundary | Precision | Recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| explicit/manual/configured | 9 | 0 | 0 | 1.0000 | 1.0000 |
| native PDF TOC/text | 0 | 0 | 9 | n/a | 0.0000 |
| heading-like image OCR | 8 | 6 | 1 | 0.5714 | 0.8889 |
| geometry/layout candidate | 9 | 2 | 0 | 0.8182 | 1.0000 |
| heading + geometry consensus | 8 | 0 | 1 | 1.0000 | 0.8889 |

Heading-only confused ordinary tempo/layout changes with movement starts and
also mapped one heading to the wrong following system when the OCR box
overlapped the target staff band. Geometry-only proposed large-whitespace
continuations as resets. Their intersection avoided false resets in this
bounded set but missed one true boundary.

## Production disposition

Automatic resolution is not enabled. The perfect observed precision of the
consensus is based on only nine positives from related orchestral-part source
styles, its cutoffs are not independently calibrated, and one boundary was
missed. It is useful as candidate/review evidence, not yet safe as a silent
numbering reset.

Production therefore keeps the existing deterministic
`issue268.movement_boundaries.v1` manual/configured input. Candidate generators
may emit the separate `issue333.movement_boundary_evidence.v1` contract
documented in `MOVEMENT_BOUNDARY_CONTRACT.md`; ambiguous candidates require
review and only resolved records are exported to the consumer. No numeric
confidence is defined by this investigation.

No detector threshold, barline threshold, MMR OCR/CNN, HOMR recognition,
grouping behavior, pipeline routing, or numbering consumer semantics changed.
The investigation did not add a production detector because the evidence does
not justify one.

## Reproduction artifacts

Generated artifacts are intentionally ignored under `logs/issue333/fresh/`:

- `configs/*.yaml` — selected-page current-pipeline configs;
- `runs/*/manifest.json`, `pipeline.log`, and
  `intermediate/page_*/numbering_base.json` — fresh run provenance/geometry;
- `heading_ocr.json` — investigation-only full-page OCR evidence;
- `strategy_evaluation.json` — locations, separate false-reset/missed-boundary
  metrics, and raw geometry evidence;
- `run_heading_ocr.py` and `evaluate_strategies.py` — reproduction helpers.

The source PDFs/images remain local-only and are not committed. Their SHA-256
identities are retained in the fixture.
