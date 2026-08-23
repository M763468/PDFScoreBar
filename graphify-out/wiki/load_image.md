# load_image

> 21 nodes · cohesion 0.21

## Key Concepts

- **load_image()** (21 connections) — `src/pipeline/utils/images.py`
- **images.py** (18 connections) — `src/pipeline/utils/images.py`
- **collect_images()** (13 connections) — `src/pipeline/utils/images.py`
- **test_issue236_review_package_source_images.py** (7 connections) — `tests/test_issue236_review_package_source_images.py`
- **load_image_size()** (6 connections) — `src/pipeline/utils/images.py`
- **Path** (6 connections)
- **resolve_page_ids()** (6 connections) — `src/pipeline/utils/images.py`
- **get_image_cache()** (5 connections) — `src/pipeline/utils/images.py`
- **_config()** (5 connections) — `tests/test_issue236_review_package_source_images.py`
- **_write_text()** (5 connections) — `tests/test_issue236_review_package_source_images.py`
- **ndarray** (4 connections)
- **_review_package_enabled()** (4 connections) — `src/pipeline/utils/images.py`
- **_stage_external_review_images()** (4 connections) — `src/pipeline/utils/images.py`
- **test_collect_images_keeps_external_source_images_without_review_package()** (4 connections) — `tests/test_issue236_review_package_source_images.py`
- **test_collect_images_keeps_run_dir_source_images_for_review_package()** (4 connections) — `tests/test_issue236_review_package_source_images.py`
- **test_collect_images_stages_external_source_images_for_review_package()** (4 connections) — `tests/test_issue236_review_package_source_images.py`
- **_path_is_inside()** (3 connections) — `src/pipeline/utils/images.py`
- **Any** (3 connections)
- **Path** (2 connections)
- **Image collection and page id helpers.** (1 connections) — `src/pipeline/utils/images.py`
- **Loads an image, checking the in-memory cache first. If the file exists on disk,…** (1 connections) — `src/pipeline/utils/images.py`

## Relationships

- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (8 shared connections)
- [get_nested](get_nested.md) (6 shared connections)
- [.run](run.md) (6 shared connections)
- [apply_advanced_sr](apply_advanced_sr.md) (3 shared connections)
- [phase_b_page001_acceptance.py](phase_b_page001_acceptance.py.md) (3 shared connections)
- [probe_scan.py](probe_scan.py.md) (3 shared connections)
- [load_yaml](load_yaml.md) (2 shared connections)
- [hybrid.py](hybrid.py.md) (2 shared connections)
- [Staff](Staff.md) (1 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (1 shared connections)
- [main](main.md) (1 shared connections)

## Source Files

- `src/pipeline/utils/images.py`
- `tests/test_issue236_review_package_source_images.py`

## Audit Trail

- EXTRACTED: 80 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*