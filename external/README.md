# External Repositories

This directory contains third-party repositories used in the project.

## Contents
- **`grounding_dino/`**: Clone of the [Grounding DINO](https://github.com/IDEA-Research/GroundingDINO) repository (Open-Set Object Detection).
- **`homr/`**: Clone of the [homr](https://github.com/liebharc/homr) repository (Baseline OMR barline detector).
- **`oemer/`**: Git submodule for the [oemer](https://github.com/BreezeWhite/oemer) repository (General OMR library).
- **`omr_dln/`**: Code related to the [OMR-DLN](https://github.com/dmgonzalez8/OMR) experiments (YOLOv8-based).
- **`yolo_world/`**: Clone of the [YOLO-World](https://github.com/ultralytics/ultralytics) model from Ultralytics.

## Usage Note
- **`oemer/`**: Managed as a Git submodule. It tracks a specific commit of the upstream repository.
- **`homr/`**: Plain clone (Untracked). It is a nested repository, not a submodule. Used for running the baseline evaluation.
- Docker environments may mount their own internal copies of these libraries.
- Use these local copies primarily for reference, debugging, or experimental modifications.
