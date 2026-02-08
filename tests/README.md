# tests directory policy

- `tests/` contains actively maintained, lightweight tests for current pipeline code.
- These tests should run in the default development environment without special GPU/image dependencies.
- Current minimum pre-PR target: `tests/test_pipeline_detection.py`.

If a test requires heavy external dependencies (e.g. OpenCV runtime setup, GUI server/network, large real data),
move it out of `tests/` and track it as integration/legacy until it is reworked.
