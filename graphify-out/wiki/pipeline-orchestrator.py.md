# pipeline/orchestrator.py

> 25 nodes · cohesion 0.18

## Key Concepts

- **pipeline/orchestrator.py** (47 connections) — `src/pipeline/orchestrator.py`
- **load_image()** (23 connections) — `src/pipeline/utils/images.py`
- **images.py** (19 connections) — `src/pipeline/utils/images.py`
- **collect_images()** (13 connections) — `src/pipeline/utils/images.py`
- **empty_numbering_payload()** (7 connections) — `src/pipeline/steps/numbering.py`
- **test_issue236_review_package_source_images.py** (7 connections) — `tests/test_issue236_review_package_source_images.py`
- **_ReviewPackageConfig** (6 connections) — `src/pipeline/orchestrator.py`
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
- **Pipeline orchestration for end-to-end processing.** (1 connections) — `src/pipeline/orchestrator.py`
- **Image collection and page id helpers.** (1 connections) — `src/pipeline/utils/images.py`
- **Loads an image, checking the in-memory cache first. If the file exists on disk,…** (1 connections) — `src/pipeline/utils/images.py`

## Relationships

- [get_nested](get_nested.md) (15 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (9 shared connections)
- [run_mmr_batch](run_mmr_batch.md) (8 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (6 shared connections)
- [filters.py](filters.py.md) (5 shared connections)
- [pdf_to_images.py](pdf_to_images.py.md) (4 shared connections)
- [load_yaml](load_yaml.md) (4 shared connections)
- [Score](Score.md) (3 shared connections)
- [test_issue284_sr_batch_contract.py](test_issue284_sr_batch_contract.py.md) (3 shared connections)
- [span](span.md) (3 shared connections)
- [materialize_manual_correction_review_package](materialize_manual_correction_review_package.md) (2 shared connections)
- [load_json](load_json.md) (2 shared connections)

## Source Files

- `src/pipeline/orchestrator.py`
- `src/pipeline/steps/numbering.py`
- `src/pipeline/utils/images.py`
- `tests/test_issue236_review_package_source_images.py`

## Audit Trail

- EXTRACTED: 131 (96%)
- INFERRED: 5 (4%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*