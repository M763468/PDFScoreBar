# Session Log (Measure Numbering Track)

**Last Updated**: 2026-01-03
**Context**: This log tracks the design and implementation of the "Measure Numbering" system (Plan A) in the `feature/measure_numbering` branch.

---

## 2026-01-03 Task Planning & Architecture Design

**Goal**: Establish a robust system to convert a list of detected barlines (and other symbols) into a structured, numbered score representation.

### 1. Core Requirements
- **Input**:
  - Detected Barlines (bbox, type?)
  - Detected Staves (bbox of staff lines)
  - (Optional/Future) Detected Systems (group of staves)
  - (Optional/Future) Detected Measure Numbers/Multi-measure Rests
- **Output**:
  - A structured object (e.g., `Score`) containing `Page` -> `System` -> `Measure` hierarchy.
  - Each `Measure` has a `number` (int) and `bbox` (visual region).
- **Key Challenges**:
  - **Incomplete Detection**: Handling FPs (extra lines) and FNs (missing lines). Logic should be robust or interactive.
  - **Structure Inference**: Inferring "Systems" from "Staves" (which staves are grouped together?).
  - **Anomalies**: Upbeats (pickup measures), Repeats (1st/2nd endings), Coda/Segno jumps.
  - **Multi-measure Rests**: Recognizing "4" above a rest and incrementing the count by 4.

### 2. Proposed Architecture (Draft)

#### Directory Structure
```
src/
  measure_numbering/
    __init__.py
    types.py          # Data classes (Measure, System, Page, Score)
    builder.py        # Logic to build structure from raw detections
    numbering.py      # Logic to assign numbers (handling rests, repeats)
    recognizers/      # OCR/Template matching for numbers/rests
      __init__.py
      rest_recognizer.py
```

#### Data Structures (types.py)
- `Barline`: `{bbox: [x1, y1, x2, y2], type: "SINGLE"|"DOUBLE"|"END"}`
- `Staff`: `{bbox: [...], barlines: List[Barline]}`
- `System`: `{staves: List[Staff], measures: List[Measure]}`
  - *Logic*: Barlines in a system effectively define the measures for all staves in that system.
- `Measure`: `{number: int, start_bar: Barline, end_bar: Barline, bounding_regions: List[BBox]}`

### 3. Immediate Task List

1.  **Scaffolding**: Create directory structure and `types.py`.
2.  **System Inference Logic**:
    - Implement a simple heuristic to group staves into systems (e.g., based on vertical proximity and left-side bracket alignment if available, or just uniform spacing).
3.  **Basic Numbering Logic**:
    - Implement a "Linear Numbering" strategy: Sort systems, sort barlines x-wise, increment counter.
    - *Constraint*: Assume 1 measure = 1 interval between barlines (for now).
4.  **Multi-measure Rest Recognition (Prototype)**:
    - Focus on recognizing the "H-bar" shape and the number above it.
    - Input: A measure image crop.
    - Output: `rest_count` (int) or `None`.

### 4. Discussion Points (Self-Correction/Refinement)
- *Question*: Should we rely on `homr` output for system detection?
- *Answer*: Yes, `homr` provides `system_index` in its JSON. We should leverage that if available, but keep a fallback logic for raw bbox inputs.
- *Refinement*: The `builder.py` should accept a generic "DetectionResult" object and normalize it.

### Next Action
- Implement `src/measure_numbering/types.py` and `src/measure_numbering/__init__.py`.