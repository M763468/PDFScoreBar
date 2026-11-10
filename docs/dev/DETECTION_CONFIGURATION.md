# Detection configuration contract

New detection settings are validated before execution by
`validate_detection_config` in `src/pipeline/detection/config.py`.
`DETECTION_KEYS` explicitly lists supported keys and incorporates the shared probe
keyword list. Unknown keys raise `ValueError` with the complete `detection.<key>`
path, regardless of whether their value is false, null or an empty string. Typos,
outdated keys and settings for removed features follow the same rule.

The CLI validates after reading configuration and before creating run outputs.
Pipeline construction (including validate-only), direct detector dispatch, input
contracts and model selection share this validation. Runtime `probe_skip_existing`
and production/exploration/comparison settings remain supported. There is no OMR
specific denylist. All shipped detection configurations are covered by a test.

Saved manifests and review packages describe historical executions. Reading them,
or applying corrections without rerunning detection, does not validate their
recorded detection settings as a new run. This preserves standard-route review
packages. Only `dense_full_pipeline` and `maintained_original` can be selected for
new detection runs.

Other sections use heterogeneous step-specific contracts and dynamic dictionaries
(e.g. per-page overrides). This change does not impose a root schema on those
sections: a broader schema requires a separate migration and caller audit.

Historical Stage-E execution and Docker extension builds, and the retired OMR
hybrid evaluation algorithms, can be reproduced from commit `f6bbd1c0` using a
separate worktree. Retained manifests, history documents and saved evaluation
outputs remain evidence. `tools/probe_evaluation_helpers.py` preserves only shared
probe functions and prediction loading used by current datasets and visualization.
