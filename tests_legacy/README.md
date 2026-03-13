# Legacy tests (temporarily separated)

This directory stores tests that are currently not part of the default pre-PR test set.

## Why separated
- `test_thin_barline_finder.py`: depends on `cv2` in the runtime where default unit tests are executed.
- `test_gt_gui_server.py`: depends on GUI/server/network style behavior and extra runtime setup.

## Re-activation policy
- Rework and move tests back to `tests/` when the related issue is being handled.
- Add clear environment requirements and deterministic execution steps before re-adding.
