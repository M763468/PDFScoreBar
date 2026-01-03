# Development Log (Measure Numbering)

Active log for 'feature/measure_numbering' branch.
See 'docs/DEVELOPMENT_LOG.md' for historical logs prior to 2026-01-03.

## Measure Numbering Specification Draft

### Goal
Define the measure-numbering rules and list open questions in a single place so future decisions are explicit and traceable.

### Context
We assume barline detection information is already available.

### Rules List (Draft)

1.  **Sequential Numbering**: Measures are numbered sequentially starting from 1 (typically).
2.  **Barline Dependency**: Measure numbers are incremented at each barline.

*(Placeholder for future rules)*

### Open Questions & Possible Approaches

1.  **Upbeat (Anacrusis)**
    *   *Question*: How should the initial partial measure be numbered?
    *   *Approaches*:
        *   Count as 0.
        *   Count as 1.
        *   Do not count (first full measure is 1).

2.  **Movement Boundaries**
    *   *Question*: Does the measure count reset at new movements or sections?
    *   *Approaches*:
        *   Reset to 1.
        *   Continue cumulatively.

3.  **Multi-measure Rests**
    *   *Question*: How to handle multi-measure rests in numbering?
    *   *Approaches*:
        *   Treat as single measure for numbering (incorrect for musical context usually).
        *   Increment by the number of measures indicated in the rest.

4.  **Divisi / Multiple Staves**
    *   *Question*: How to handle cases where barlines might not align perfectly or when processing individual parts vs score?
    *   *Approaches*:
        *   Use global system barlines.
        *   Handle per-part.

5.  **Repeats / Endings (Volta)**
    *   *Question*: How does numbering handle repeats (1st/2nd endings)?
    *   *Approaches*:
        *   Strict linear numbering of the printed score (ignoring execution flow).
        *   Numbering reflecting execution flow (unlikely for standard score marking).

### Decision Log Template

When a decision is made regarding the rules above, record it here.

#### [YYYY-MM-DD] Decision Title
*   **Status**: [Proposed | Decided | Rejected]
*   **Rationale**: Why we chose this approach.
*   **Examples**:
    *   *Input*: Description or snippet.
    *   *Output*: Expected numbering.
*   **Affected Code Paths**: List modules or functions that need updates.
