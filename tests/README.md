# tests directory policy

- `tests/` contains actively maintained, lightweight tests for current pipeline code.
- These tests should run in the default development environment without GPU, network services, or
  large real-data requirements.
- Current minimum pre-PR target: `tests/test_pipeline_detection.py`.
- OpenCV-backed unit tests are acceptable when they use synthetic/tmp-path inputs and remain
  deterministic and lightweight.

If a test requires a server/network dependency, GPU/model runtime, or large real data, first reduce it
to a deterministic unit/contract test where possible. Otherwise track it as an explicit integration
test with documented environment requirements; do not create a second `tests_legacy/` surface.
