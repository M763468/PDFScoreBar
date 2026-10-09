# Issue #218: 3div./4div. connector grouping fixtures

These are original synthetic score excerpts, authored for
[Issue #218](https://github.com/M763468/PDFScoreBar/issues/218). They contain
five-line staves, simple notes, aligned barlines, a left/system-start connector
chain for three or four divisi staves, and a separate following system. They
are not scans of published music or retained detector/model outputs.

| Fixture | Expected staff membership (top-to-bottom, zero-based) | Measure numbers |
| --- | --- | --- |
| [3div. score](issue218_3div_score.png) | `[[0, 1, 2], [3]]` | `[[1, 2], [3, 4]]` |
| [4div. score](issue218_4div_score.png) | `[[0, 1, 2, 3], [4]]` | `[[1, 2], [3, 4]]` |

Each excerpt has a JSON file with page coordinates, staff-line spacing,
barline boxes, expected connector presence, system membership, and numbering.
The `*_staff.png` masks contain only the five staff lines; `*_symbols.png`
contains only the left connectors, as a controlled semantic-mask input.
The score PNG includes a deliberate non-left ink bridge at the rightmost
barline between the last divisi staff and the independent following system.
That bridge tests the false-merge guard; it is not a musical connector.

The original staff height is 80 pixels (`unit_size=20`). Adjacent gaps within
the divisi chain are 72, 123, and (for 4div.) 72 pixels. The 123-pixel gap
lies above the ordinary `1.5 * height` grouping limit and below the
`1.56 * height` connector-rescue limit. Three aligned barlines provide the
required rescue support. The independent following system has a 72-pixel
gap and no left connector, so proximity and aligned ink alone cannot explain
the expected split.

Regenerate the committed assets from the repository root:

```bash
python3 tests/fixtures/system_grouping/generate_issue218.py
```

Run the regression tests:

```bash
python3 -m pytest -q tests/test_issue218_multistaff_system_grouping.py
```

The tests use the current connector extractor and `ConnectorAwareSystemBuilder`
without explicit system indices. They verify complete staff membership,
transitive merging, independent-neighbor separation, each missing chain link,
half/normal/double resolution, reversed staff input, and score/blank/no image
paths. They also exercise `MeasureNumberingPipeline.process_page` using the
retained staff mask and either the symbols or brace-dot semantic-mask input,
then verify shared measure progression. The builder tests exercise connector
rescue with the original boxes; staff extraction expands boxes, so the
pipeline test establishes integration rather than the exact rescue-distance
boundary.

These fixtures establish grouping and numbering regression behavior under
controlled inputs. They do not establish real-score 3div./4div. detector
accuracy, mask-production quality, or full-pipeline/GPU performance. No
production thresholds, detector settings, or accepted evaluation contract
are changed by this addition.
