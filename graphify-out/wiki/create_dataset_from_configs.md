# create_dataset_from_configs

> 8 nodes · cohesion 0.43

## Key Concepts

- **create_dataset_from_configs()** (6 connections) — `tools/mmr_training/create_mmr_train_data.py`
- **create_mmr_train_data.py** (5 connections) — `tools/mmr_training/create_mmr_train_data.py`
- **build_staff_mask_index()** (3 connections) — `tools/mmr_training/create_mmr_train_data.py`
- **extract_page_token()** (3 connections) — `tools/mmr_training/create_mmr_train_data.py`
- **map_global_index_to_bbox()** (3 connections) — `tools/mmr_training/create_mmr_train_data.py`
- **load_staff_mask_from_segmentation()** (2 connections) — `tools/mmr_training/create_mmr_train_data.py`
- **Returns a list mapping global_index -> bbox [x1, y1, x2, y2]** (1 connections) — `tools/mmr_training/create_mmr_train_data.py`
- **Iterates over pages defined in the provided config files and creates training…** (1 connections) — `tools/mmr_training/create_mmr_train_data.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `tools/mmr_training/create_mmr_train_data.py`

## Audit Trail

- EXTRACTED: 12 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*