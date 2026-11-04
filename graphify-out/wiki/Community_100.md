# Community 100

> 24 nodes · cohesion 0.17

## Key Concepts

- **detect_probe_scan()** (34 connections) — `src/pipeline/probe_detector/__init__.py`
- **probe_detector/__init__.py** (24 connections) — `src/pipeline/probe_detector/__init__.py`
- **probe_detector/types.py** (13 connections) — `src/pipeline/probe_detector/types.py`
- **ExistingBarlines** (8 connections) — `src/pipeline/probe_detector/existing.py`
- **apply_gap_rescue()** (8 connections) — `src/pipeline/probe_detector/rescue.py`
- **build_divisi_map()** (7 connections) — `src/pipeline/probe_detector/bands.py`
- **rescue.py** (7 connections) — `src/pipeline/probe_detector/rescue.py`
- **apply_rightmost_rescue()** (7 connections) — `src/pipeline/probe_detector/rescue.py`
- **existing.py** (5 connections) — `src/pipeline/probe_detector/existing.py`
- **BandSelectionConfig** (5 connections) — `src/pipeline/probe_detector/types.py`
- **DivisiRescueConfig** (5 connections) — `src/pipeline/probe_detector/types.py`
- **GapRescueConfig** (5 connections) — `src/pipeline/probe_detector/types.py`
- **RightmostRescueConfig** (5 connections) — `src/pipeline/probe_detector/types.py`
- **.closest_existing_band()** (3 connections) — `src/pipeline/probe_detector/existing.py`
- **.has_existing_for_suppression()** (3 connections) — `src/pipeline/probe_detector/existing.py`
- **Any** (2 connections)
- **test_existing_suppression_requires_vertical_overlap_and_preserves_nearest_band()** (2 connections) — `tests/test_probe_helpers.py`
- **Lookup and suppression against existing barlines in a staff band.** (1 connections) — `src/pipeline/probe_detector/existing.py`
- **ndarray** (1 connections)
- **Path** (1 connections)
- **Core probe scan detection logic orchestrating submodules.** (1 connections) — `src/pipeline/probe_detector/__init__.py`
- **Rescue logic for probe detection.** (1 connections) — `src/pipeline/probe_detector/rescue.py`
- **Rescue barlines in large gaps between detected barlines using relaxed threshold.** (1 connections) — `src/pipeline/probe_detector/rescue.py`
- **Shared types/config for probe detector modules.** (1 connections) — `src/pipeline/probe_detector/types.py`

## Relationships

- [Community 105](Community_105.md) (20 shared connections)
- [Community 259](Community_259.md) (9 shared connections)
- [Community 7](Community_7.md) (5 shared connections)
- [Community 87](Community_87.md) (4 shared connections)
- [Community 31](Community_31.md) (4 shared connections)
- [Community 235](Community_235.md) (3 shared connections)
- [Community 192](Community_192.md) (2 shared connections)
- [Community 154](Community_154.md) (2 shared connections)
- [Community 37](Community_37.md) (2 shared connections)
- [Community 151](Community_151.md) (2 shared connections)
- [Community 207](Community_207.md) (1 shared connections)

## Source Files

- `src/pipeline/probe_detector/__init__.py`
- `src/pipeline/probe_detector/bands.py`
- `src/pipeline/probe_detector/existing.py`
- `src/pipeline/probe_detector/rescue.py`
- `src/pipeline/probe_detector/types.py`
- `tests/test_probe_helpers.py`

## Audit Trail

- EXTRACTED: 99 (97%)
- INFERRED: 3 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*