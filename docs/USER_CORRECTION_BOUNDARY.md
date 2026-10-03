# User correction and GT tooling boundary (Issue #393)

The supported user correction application is `tools/review_correction/server.py`. It opens one
validated `review/manual_correction_input.json` package. The handoff selects the pages, readable
artifacts, and correction outputs. Its server exposes only the manual review UI and routes needed
by that UI. It listens on `127.0.0.1`, accepts that local address as the HTTP host, and requires
same-origin JSON requests for writes. It rechecks resolved paths, including symlinks, on each file
request and write. Recorded correction outputs remain in that package's `review/corrections/` directory. Application
attempts and copied inputs are isolated under `review/application_runs/`; the corrected final PDF
stays in each attempt's `corrected/final/` directory.

`tools/gt_relabel_gui/server.py` is the separate developer entrypoint. Its `gt`, `rest`, and
`relabel` modes may edit canonical GT/evaluation data or relabel templates. Its legacy `manual`
mode and arbitrary config/root options are developer-only compatibility surfaces; they are not
the supported way to open a user correction session. GT editor behavior is unchanged here.

| Surface | Responsibility |
| --- | --- |
| `tools/review_correction/application.py` | Package-bound engine invocation, immutable recorded-input copies, collision/concurrency safeguards, and verified final PDF discovery |
| `tools/review_correction/state.py` | Page/type state and content identities for recorded corrections and successful corrected results |
| `tools/review_correction/server.py` | User application entry, HTTP route allowlist, and package-local persistence boundary |
| `tools/review_correction/index.html`, `app.js`, `strings.js` | Dedicated user review presentation and controlled copy |
| `src/pipeline/review/manual_correction_handoff.py` | Shared handoff validation and GUI page configuration |
| `src/pipeline/review/movement_boundary_review.py` | Shared review evidence and resolved-output helper |
| `tools/gt_relabel_gui/server.py` | GT/evaluation editing, relabeling, developer probe, and legacy manual compatibility entry |
| `tools/gt_relabel_gui/index_gt.html`, `app_gt.js`, `index_rest.html`, `app_rest.js`, `index.html`, `app.js` | GT/rest/relabel developer UI assets |
| `tools/gt_relabel_gui/*config*.json`, `build_*config.py`, `prepare_rebuild_eval2.py` | GT/evaluation setup data and developer config builders |

The two applications share low-level handoff/rendering concepts, but their entrypoints, route
sets, and save sinks are separate. The user server never calls the GT handler. This boundary
does not change correction payloads or detector, MMR, grouping, or canonical GT data.

### Recording responsibility

`ReviewPackage.record_correction` owns the common package-bound recording operation for every
correction type: validate the declared sink and item shape, preserve other pages in a shared file,
replace the correction file atomically, then clear that page/type's pending edit and recording
error. A failed write preserves the previous recorded content and the pending edit.

MMR/measure/barline explicit Save and movement confirmation differ only in their UI trigger.
Both call `/api/save` and the same recording operation. Movement finalization remains a separate
engine-derived input step; it does not introduce a second correction persistence model.

State summary counts are independent axes: a page/type may be both recorded and pending.
`recorded_identity` hashes the recorded page items and is `null` whenever that page/type has no
recorded correction, even if a shared file exists for another page. Error counts count each
page/type once, including failed apply combined with a recording error.

The user state adapter compares save completion with its captured page/type draft. Edits made
while a save is in flight remain pending; page navigation stops if its automatic save leaves newer
edits unsaved. Movement finalization refreshes state after the actual request settles, including
failure, rather than inferring completion from button state. These adapters are user-only and do
not change GT/developer handlers or correction payloads.

The authoritative apply engine records the exact finalized reviewed movement payload in
`corrected_pipeline_config.json`, including an explicitly empty boundary set. This consumed-input
provenance belongs to the apply integration (#395); the acceptance gate (#397) verifies it on real
artifacts without owning a second movement-input interpretation.
