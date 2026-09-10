# Legacy Development Milestone Ledger

> [!IMPORTANT]
> This file is **historical navigation**, not a current source of truth.
> For current behavior, use current source/tests/config plus `docs/PIPELINE_ARCHITECTURE.md` and the active Issue/PR.

## Why this file is compact

The former `DEVELOPMENT_LOG.md` accumulated thousands of lines of dated run notes, local paths,
commands, temporary blockers, and `next step` state from before the project adopted mature
Issue/PR post-mortems. Under Issue #308 that execution diary was compressed to the durable
project-origin milestones below.

Exact old prose and run-by-run chronology remain recoverable from Git history. Historical
numbers below must not be interpreted as current production baselines.

## Milestones

### 1. Early OMR / OpenCV / Gemini prototypes — superseded

Early work explored broad OMR, hand-tuned OpenCV geometry, and Gemini-assisted classification.
These approaches did not become a reliable standalone barline detector. The durable outcome was
a shift toward specialized detector/evaluation tooling rather than increasingly broad heuristic
or prompt-based classification.

### 2. HOMR evaluation and manual-GT foundation

The project established a dedicated HOMR evaluation path with reproducible page-level runs,
overlays, and manually reviewed ground truth. This became the foundation for later detector
comparison and reconstruction work.

Old environment names, absolute paths, thresholds, and then-current run directories from this
period are historical only.

### 3. Repository restructuring and manual inspection tooling — Dec 2025

The repository was reorganized so experimental code moved away from production paths, and a
lightweight GUI helper was used for manual inspection of difficult detections. These were workflow
transitions, not permanent architecture contracts.

Current placement/lifecycle rules are in `docs/SCRIPT_MANAGEMENT.md` and current user-facing
review flows should be resolved from current docs/source rather than this history.

### 4. Geometry-only FP reduction reached a safety boundary

Focused experiments showed that several apparently reasonable local geometry filters could remove
fragmented true barlines together with false positives. Conservative note-context ideas could help
on focused cases, but staff-crossing, local-cluster winner selection, aggressive duplicate merging,
and similar geometric rejection rules were not generally safe.

The reusable rule is preserved in `docs/ai-workflow/LESSONS.md`: detector/filter changes that can
remove fragmented true barlines require explicit recall and downstream-semantic validation.
Detailed sweep chronology and local run directories belong to Git history / retained experiment
tooling, not active documentation.

### 5. External-model survey favored complementary signals over replacement

Historical model experiments found that zero-shot YOLO-World and GroundingDINO did not transfer
reliably to this barline task. Direct morphology and lightweight FSRCNN-style preprocessing also
degraded important detector behavior in the tested paths. OMR-DLN measure-related detections were
more useful as a complementary signal than as a wholesale replacement for the high-recall HOMR
path.

See retained experiment tooling/READMEs and Git history when exact old commands or measurements are
needed. The two historical PDFs under `docs/model_experiments/` remain separately audit-gated.

### 6. Real-ESRGAN and hybrid-consensus experiments changed the architecture direction

Dec-2025 experiments established that combining a high-recall HOMR path with complementary
SR/OMR evidence could reduce false positives on focused pages while preserving recall. This was an
important transition toward the later hybrid detector lineage.

Focused-page values from that period are historical evidence only; later accepted detector
contracts are indexed in `docs/HISTORY_INDEX.md`.

### 7. GT cleanup and detector-probe reconstruction improved reproducibility

Late-Dec-2025 and early-Jan-2026 work rebuilt ground truth, investigated detector misses, and
iterated probe-scan/end-bar recovery on a broader page set. Many individual parameter sweeps were
negative or superseded, and several recorded runs were later shown to depend on exact historical
code/input provenance.

The durable lesson is to preserve provenance and distinguish accepted, rejected, invalidated, and
superseded runs. Current detector-input provenance rules are documented in
`docs/PIPELINE_ARCHITECTURE.md` and the relevant Issue lineages.

### 8. Transition to Issue/PR-driven durable history — Jan 2026 onward

As development moved into structured Issues and PRs, the global diary stopped being the right
place for authoritative state. Issue #6 / PR #11 standardized the Makefile/ruff development
workflow, and later investigation history is better recovered from its specific Issue, PR, commit,
source, tests, and retained reproduction contract.

## Recovery map

| Topic | Preferred historical/current entry |
| --- | --- |
| Detector reconstruction / Stage E | `docs/HISTORY_INDEX.md` → Issues #117–#163 and later accepted milestones |
| CNN classifier history | Issue #44; current verified CNN lineage #296 / PR #310 |
| Measure numbering / MMR | Issue #94 and `docs/refactors/issue94/MMR_CURRENT_STATE.md` |
| Early performance work | Issues #25 / #60 / #70 / #78 |
| Recent performance work | Issues #281–#294 as applicable to the active task |
| FP-filter safety lesson | `docs/ai-workflow/LESSONS.md` |
| Current architecture | `docs/PIPELINE_ARCHITECTURE.md`, current source/tests/config |

## Historical-state rule

Do not treat any old branch name, worktree/container path, local artifact directory, blocker,
`Current Focus`, `Next Steps`, threshold recommendation, or production label recovered from the
former diary as current without revalidation.

For archaeology requiring the exact former `DEVELOPMENT_LOG.md`, use Git history before the #308
compression change rather than expanding this ledger again.
