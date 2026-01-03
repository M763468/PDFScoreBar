# Measure Numbering: Issue Drafts (Issue-Ready)

## 1) Measure Numbering: Spec Draft + Open Questions
**Labels**: docs, planning

**Goal**
Define the measure-numbering rules and list open questions in a single place so future decisions are explicit and traceable.

**Context**
We need a spec skeleton before coding. Several rules (upbeat, movement boundaries, multi-measure rests, divisi) are undecided.

**Scope**
- Create a rules list with short explanations.
- List open questions and possible approaches.
- Define a small decision log format.

**Out of Scope**
- Implementing any detection logic.
- Reviewing real score data.

**Deliverables**
- `docs/DEVLOG_MEASURE_NUMBERING.md` updated with:
  - Rules list
  - Open questions list
  - Decision log template

**Acceptance Criteria**
- Rules list and open-questions list exist and are easy to extend.
- Decision log template exists and includes date, rationale, examples, and affected code paths.

---

## 2) Define I/O JSON Schemas for Measure Numbering
**Labels**: docs, schema

**Goal**
Propose JSON schemas for barline input and measure-numbering output so implementation can proceed without real data.

**Context**
We need a contract for the traversal + numbering logic. Actual detector logs will be wired later.

**Scope**
- Draft input schema (barlines) with minimal required fields.
- Draft output schema (measures) with numbering and references to input barlines.
- Provide example JSON blocks.

**Out of Scope**
- Binding to actual log files or concrete detector outputs.

**Deliverables**
- New doc: `docs/measure_numbering_schema.md`
  - Input schema (fields + types)
  - Output schema (fields + types)
  - Example JSON snippets

**Acceptance Criteria**
- Example input/output JSON is provided and consistent with the field definitions.
- Schema can support multiple pages and staff systems.

---

## 3) Measure Numbering Data Structures
**Labels**: implementation, core

**Goal**
Define core data structures for measure numbering in code, independent of detector specifics.

**Context**
We want stable internal models before wiring to real data.

**Scope**
- Create `src/measure_numbering/`.
- Define minimal classes (e.g., `Page`, `StaffSystem`, `Barline`, `Measure`).
- Include small constructors and type annotations.

**Out of Scope**
- Any real detector log parsing.
- Any drawing/rendering.

**Deliverables**
- New module(s) under `src/measure_numbering/`.
- Simple usage example (docstring or small helper).

**Acceptance Criteria**
- Classes exist with clear responsibilities.
- Unit tests can construct objects from dummy data.

---

## 4) Traversal + Numbering Core (No Real Data)
**Labels**: implementation, algorithm

**Goal**
Implement the core numbering algorithm using abstracted barline inputs.

**Context**
We need a conservative baseline that assigns sequential numbers and supports reset hooks.

**Scope**
- Implement a traversal function that orders barlines by system and x-position.
- Assign measure numbers sequentially starting from 1.
- Provide reset hooks for movement boundaries (API only).

**Out of Scope**
- Auto-detection of upbeat/movement/multi-measure rests.
- Real data ingestion.

**Deliverables**
- New module: `src/measure_numbering/assign_numbers.py` (or similar).
- A small API that accepts dummy data structures and returns numbered measures.

**Acceptance Criteria**
- Deterministic numbering for synthetic test fixtures.
- Reset hooks can be injected (even as a stub callback).

---

## 5) Unit Test Scaffold for Measure Numbering
**Labels**: tests

**Goal**
Create a minimal test suite for traversal + numbering without real data.

**Context**
We need fast feedback when core logic evolves.

**Scope**
- Add test fixtures with 1–2 pages and multiple systems.
- Add at least three tests (simple, multi-system, reset hook).

**Out of Scope**
- Tests based on real logs.

**Deliverables**
- `tests/measure_numbering/` with fixtures and tests.

**Acceptance Criteria**
- Tests run locally without any external data.
- Tests cover traversal order and numbering reset hook behavior.
