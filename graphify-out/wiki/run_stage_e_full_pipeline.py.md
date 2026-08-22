# run_stage_e_full_pipeline.py

> 21 nodes · cohesion 0.19

## Key Concepts

- **run_stage_e_full_pipeline.py** (25 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **main()** (13 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **_suppress_low_value_external_raw_log()** (8 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **_filter_default_console_log()** (7 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **Path** (7 connections)
- **_summarize_console_log()** (5 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **_is_low_value_external_line()** (4 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **_is_progress_line()** (4 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **_is_warning_or_error_line()** (4 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **_load_optional_json()** (4 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **_redirect_stdout_stderr_to_file()** (4 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **_is_real_esrgan_tile_line()** (3 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **_low_value_marker_keys()** (3 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **_strip_low_value_suffix_from_progress_line()** (3 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **_temporary_env()** (3 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **_env_flag_enabled()** (2 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **Rewrite raw stdout/stderr with known low-value external chatter removed.** (1 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **Write a bounded default console log while preserving raw stdout/stderr…** (1 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **Redirect fd-level stdout/stderr so subprocess-heavy logs are kept in a file.** (1 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **Temporarily set environment variables and restore their previous values.** (1 connections) — `tools/issue120/run_stage_e_full_pipeline.py`
- **Summarize captured stdout/stderr without loading the whole file into memory.** (1 connections) — `tools/issue120/run_stage_e_full_pipeline.py`

## Relationships

- [Any](Any.md) (10 shared connections)
- [load_yaml](load_yaml.md) (6 shared connections)
- [CapturedProgressMirror](CapturedProgressMirror.md) (5 shared connections)
- [dense_full_pipeline.py](dense_full_pipeline.py.md) (3 shared connections)

## Source Files

- `tools/issue120/run_stage_e_full_pipeline.py`

## Audit Trail

- EXTRACTED: 64 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*