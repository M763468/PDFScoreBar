import inspect
from src.pipeline.probe_detector import detect_probe_scan
from src.pipeline.steps.candidate_filters import filter_probe_candidates
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch

print("## detect_probe_scan Parameters")
sig_probe = inspect.signature(detect_probe_scan)
for k, v in sig_probe.parameters.items():
    if k not in ('base_img', 'staff_mask', 'existing_boxes', 'row_stats', 'debug_path'):
        default_val = v.default if v.default is not inspect.Parameter.empty else "N/A"
        print(f"| {k} | {default_val} | |")

print("\n## filter_probe_candidates Parameters")
sig_filter = inspect.signature(filter_probe_candidates)
for k, v in sig_filter.parameters.items():
    if k not in ('candidates', 'image', 'existing_boxes', 'staff_mask', 'clef_mask'):
        default_val = v.default if v.default is not inspect.Parameter.empty else "N/A"
        print(f"| {k} | {default_val} | |")

print("\n## run_cnn_scoring_batch Parameters")
sig_cnn = inspect.signature(run_cnn_scoring_batch)
for k, v in sig_cnn.parameters.items():
    if k not in ('probe_output_root', 'images', 'model_path', 'in_memory_images', 'bands_from', 'staff_mask_dir'):
        default_val = v.default if v.default is not inspect.Parameter.empty else "N/A"
        print(f"| {k} | {default_val} | |")
