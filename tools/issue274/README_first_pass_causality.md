# Issue #274 first-pass causal split

This note records the interpretation of
`issue274.stage_e_first_pass_context_causality.v1` before any production change.

## Sanity

The focused first-pass replay is valid: production control and current-x4 candidate
raw sets are exact for all three structural pages.

The experiment reruns only the PDFScoreBar first dense probe pass.  It does not
rerun HOMR, SR, OMR-DLN, filtering, CNN, MMR, or numbering.

## Ownership

Upstream HOMR supplies the underlying A/B/C barline and segmentation evidence.
The following causal mechanisms tested here are PDFScoreBar-owned:

- hybrid support policy (`hybrid_consensus`);
- row construction from hybrid/existing boxes;
- dense probe generation;
- existing-box suppression;
- merging accepted hybrid seeds with generated dense candidates.

The current broad thin-line recovery is also a PDFScoreBar extension.  It must not
be conflated with upstream HOMR inference.

## Two different structural failure classes

### Sym5 page_013 and Sibelius page_004

Current-x4 B supports an A baseline box that pinned-x4 C did not support.  Feeding
that supported A box into the Stage-E first pass changes two independent pieces of
PDFScoreBar state:

1. row context collapses locally (control has two target rows; candidate has one);
2. the same B-supported A box becomes an existing-box suppression seed.

Disabling suppression restores matching *capacity*, but with candidate-derived row
context the second prediction can still be geometrically near-duplicate evidence
rather than the second control row.  Supplying control rows and disabling
suppression restores the actual two control-style generated boxes (plus the B seed).
Therefore these pages must not be summarized as "suppression alone".

A particularly strong ablation is `candidate_context_control_merge`: candidate
context suppresses/removes the target generated boxes even when the final merge is
switched back to control.  Conversely `control_context_candidate_merge` preserves
capacity while merging the B seed.  The failure is therefore in the *use of hybrid
boxes as dense context*, not merely in the final set union.

### Sym5 page_015

This case has the opposite sign.  Control keeps one A baseline seed that the current
B IoU policy drops.  Neither suppression removal nor control row context recreates
that missing identity.  Capacity is restored only when the control hybrid seed is
merged back.

Prior retained analysis showed that current B's long thin-line evidence can support
this A box under the directional staff-slot relation even though symmetric IoU
fails.  This case is therefore a support-relation / thin-evidence-contract problem,
not a row/suppression problem.

## Design consequence

One threshold cannot solve both classes.

The next architecture should separate at least four concepts:

1. **A structural geometry / row context** — original-image baseline geometry used
   to define structural rows independently of x4 support acceptance;
2. **x4 evidence support** — current x4 HOMR evidence may support an A geometry
   candidate without owning its identity/topology;
3. **suppression ownership** — a kept A candidate may suppress dense reconstruction
   only in its assigned structural row, not every overlapping row;
4. **supplemental thin evidence** — PDFScoreBar thin-line observations are evidence
   and must not destructively replace upstream primary geometry before support is
   evaluated.

This structure is compatible with the Issue #274 target of one original HOMR plus
one x4 HOMR execution per page.  It does not yet select the final canonical HOMR
version; runtime/version unification remains a later gate.

## Visual gate

Coordinates alone do not prove whether each two-box component represents separate
staff/system rows, double-bar strokes, or another physical structure.  The
structural crop renderer is therefore required before turning these focused cases
into a generic identity rule.
