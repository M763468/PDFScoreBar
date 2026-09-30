# User correction and GT tooling boundary (Issue #393)

The supported user correction application is `tools/review_correction/server.py`. It opens one
validated `review/manual_correction_input.json` package. The handoff selects the pages, readable
artifacts, and correction outputs. Its server exposes only the manual review UI and routes needed
by that UI. It listens on loopback and rechecks resolved paths, including symlinks, on each file
request and write. Outputs must remain in that package's `review/corrections/` directory.

`tools/gt_relabel_gui/server.py` is the separate developer entrypoint. Its `gt`, `rest`, and
`relabel` modes may edit canonical GT/evaluation data or relabel templates. Its legacy `manual`
mode and arbitrary config/root options are developer-only compatibility surfaces; they are not
the supported way to open a user correction session. GT editor behavior is unchanged here.

| Surface | Responsibility |
| --- | --- |
| `tools/review_correction/server.py` | User application entry, HTTP route allowlist, and package-local persistence boundary |
| `tools/gt_relabel_gui/index_manual.html`, `app_manual.js` | Shared manual review presentation assets served by the user application |
| `src/pipeline/review/manual_correction_handoff.py` | Shared handoff validation and GUI page configuration |
| `src/pipeline/review/movement_boundary_review.py` | Shared review evidence and resolved-output helper |
| `tools/gt_relabel_gui/server.py` | GT/evaluation editing, relabeling, developer probe, and legacy manual compatibility entry |
| `tools/gt_relabel_gui/index_gt.html`, `app_gt.js`, `index_rest.html`, `app_rest.js`, `index.html`, `app.js` | GT/rest/relabel developer UI assets |
| `tools/gt_relabel_gui/*config*.json`, `build_*config.py`, `prepare_rebuild_eval2.py` | GT/evaluation setup data and developer config builders |

The two applications share low-level handoff/rendering concepts, but their entrypoints, route
sets, and save sinks are separate. The user server never calls the GT handler. This boundary
does not change correction payloads or detector, MMR, grouping, or canonical GT data.
