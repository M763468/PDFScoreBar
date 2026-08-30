# Issue #291 temporary investigation tools

The helpers in this directory are temporary investigation/review tooling for Issue #291.
They must be removed before the production PR unless a helper is deliberately promoted to a general validator/test surface.

Current gate:

1. `audit_gt_duplicate_pairs.py` reproduces the historical P1/P3 inventory without writing GT.
2. `render_p1_duplicate_review.py` renders the 12 historical P1 candidates on original score images.
3. `review_retained_numbering_boundaries.py` checks P1 #12 and a genuine double-bar control against retained final numbering artifacts, without rerunning inference/numbering.

Do not edit canonical GT until the visual and retained-numbering gates are complete.
