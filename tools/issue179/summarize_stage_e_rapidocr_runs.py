#!/usr/bin/env python3
"""Summarize default-vs-CUDA Stage E RapidOCR experiment runs for Issue #179."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any


def _load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _stage_e_root(path: Path) -> Path:
    if (path / "stage_e_runtime_summary.json").exists():
        return path
    candidate = path / "stage_e_full_pipeline"
    if (candidate / "stage_e_runtime_summary.json").exists():
        return candidate
    raise FileNotFoundError(f"Could not find Stage E run root under {path}")


def _max_dict_value(d: Any) -> int | float | None:
    if not isinstance(d, dict) or not d:
        return None
    values = [v for v in d.values() if isinstance(v, (int, float))]
    if not values:
        return None
    return max(values)


def _provider_lines(provider_summary: dict[str, Any] | None) -> list[str]:
    if not provider_summary:
        return []
    lines: list[str] = []
    for instance in provider_summary.get("instances", []):
        component = instance.get("component", "<unknown>")
        providers_by_path = instance.get("providers_by_path", {})
        if not providers_by_path:
            lines.append(f"{component}: <no provider sessions found>")
            continue
        for path, providers in providers_by_path.items():
            lines.append(f"{component}:{path}={providers}")
    return lines


def collect_run(label: str, path: Path) -> dict[str, Any]:
    root = _stage_e_root(path)
    runtime = _load_json(root / "stage_e_runtime_summary.json") or {}
    resource = runtime.get("resource_monitor") or _load_json(
        root / "stage_e_resource_samples.summary.json"
    )
    pipeline = runtime.get("pipeline", {})
    console_summary = pipeline.get("stdout_stderr_low_value_raw_suppression_summary", {})
    marker_counts = console_summary.get("low_value_marker_counts", {})
    provider_summary = _load_json(root / "rapidocr_provider_summary.json")
    eval_contract = _load_json(root / "eval_detector" / "evaluation_contract.json")
    if eval_contract is None:
        eval_contract = _load_json(root / "eval_detector_smoke" / "evaluation_contract.json")

    return {
        "label": label,
        "root": str(root),
        "total_duration_sec": runtime.get("total_duration_sec"),
        "pipeline_duration_sec": pipeline.get("duration_sec"),
        "dense_route_duration_sec": (runtime.get("dense_route_execution_summary") or {}).get(
            "total_duration_sec"
        ),
        "sample_count": (resource or {}).get("sample_count"),
        "peak_gpu_memory_mb": _max_dict_value((resource or {}).get("peak_gpu_memory_mb_by_uuid")),
        "peak_gpu_utilization_pct": _max_dict_value(
            (resource or {}).get("peak_gpu_utilization_pct_by_uuid")
        ),
        "peak_process_tree_rss_bytes": (resource or {}).get("peak_process_tree_rss_bytes"),
        "peak_process_tree_cpu_percent": (resource or {}).get(
            "peak_process_tree_cpu_percent"
        ),
        "rapidocr_cuda_enabled": ((provider_summary or {}).get("env") or {}).get(
            "cuda_enabled"
        ),
        "rapidocr_instance_count": len((provider_summary or {}).get("instances", [])),
        "rapidocr_provider_lines": _provider_lines(provider_summary),
        "rapidocr_info_marker_count": marker_counts.get("rapidocr_info"),
        "onnxruntime_warning_marker_count": marker_counts.get("onnxruntime_warning"),
        "onnxruntime_fallback_marker_count": marker_counts.get("onnxruntime_fallback"),
        "eval_contract": eval_contract,
    }


def parse_run_arg(value: str) -> tuple[str, Path]:
    if ":" not in value:
        raise argparse.ArgumentTypeError("--run must use label:path format")
    label, path = value.split(":", 1)
    if not label:
        raise argparse.ArgumentTypeError("--run label must not be empty")
    return label, Path(path)


def _format_float(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, int):
        return str(value)
    return ""


def _mode_from_label(label: str) -> str:
    return label.rsplit("_run", 1)[0] if "_run" in label else label


def _duration_means(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[float]] = {}
    for run in runs:
        duration = run.get("pipeline_duration_sec")
        if isinstance(duration, (int, float)):
            grouped.setdefault(_mode_from_label(str(run["label"])), []).append(float(duration))
    return {
        mode: {"count": len(values), "pipeline_duration_mean_sec": mean(values)}
        for mode, values in sorted(grouped.items())
    }


def _comparison_from_means(means: dict[str, dict[str, Any]]) -> dict[str, Any]:
    default_key = next((key for key in means if key.startswith("default")), None)
    cuda_key = next((key for key in means if key.startswith("cuda")), None)
    if default_key is None or cuda_key is None:
        return {}
    default_mean = means[default_key]["pipeline_duration_mean_sec"]
    cuda_mean = means[cuda_key]["pipeline_duration_mean_sec"]
    if not isinstance(default_mean, (int, float)) or not isinstance(cuda_mean, (int, float)):
        return {}
    return {
        "default_mode": default_key,
        "cuda_mode": cuda_key,
        "default_pipeline_duration_mean_sec": default_mean,
        "cuda_pipeline_duration_mean_sec": cuda_mean,
        "delta_sec": cuda_mean - default_mean,
        "speedup_ratio_default_over_cuda": (default_mean / cuda_mean) if cuda_mean else None,
        "cuda_faster": cuda_mean < default_mean,
    }


def _write_markdown(runs: list[dict[str, Any]], path: Path) -> None:
    lines = [
        "# Issue #179 RapidOCR CUDA comparison",
        "",
        "| label | total_sec | pipeline_sec | peak_gpu_mb | peak_gpu_util_pct | rapidocr_cuda | rapidocr_instances |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for run in runs:
        lines.append(
            "| {label} | {total} | {pipeline} | {gpu_mb} | {gpu_util} | {cuda} | {instances} |".format(
                label=run["label"],
                total=_format_float(run.get("total_duration_sec")),
                pipeline=_format_float(run.get("pipeline_duration_sec")),
                gpu_mb=_format_float(run.get("peak_gpu_memory_mb")),
                gpu_util=_format_float(run.get("peak_gpu_utilization_pct")),
                cuda=run.get("rapidocr_cuda_enabled"),
                instances=run.get("rapidocr_instance_count"),
            )
        )

    duration_means = _duration_means(runs)
    if duration_means:
        lines += ["", "## Pipeline duration means", ""]
        for mode, item in duration_means.items():
            lines.append(
                f"- `{mode}`: {item['pipeline_duration_mean_sec']:.3f} sec "
                f"over {item['count']} run(s)"
            )

    comparison = _comparison_from_means(duration_means)
    if comparison:
        lines += ["", "## Default vs CUDA", ""]
        lines.append(f"- default mode: `{comparison['default_mode']}`")
        lines.append(f"- CUDA mode: `{comparison['cuda_mode']}`")
        lines.append(f"- delta: {comparison['delta_sec']:.3f} sec (CUDA - default)")
        ratio = comparison.get("speedup_ratio_default_over_cuda")
        if isinstance(ratio, (int, float)):
            lines.append(f"- speedup ratio default/CUDA: {ratio:.4f}x")
        lines.append(f"- CUDA faster: {comparison['cuda_faster']}")

    lines += ["", "## RapidOCR provider details", ""]
    for run in runs:
        lines.append(f"### {run['label']}")
        provider_lines = run.get("rapidocr_provider_lines") or []
        if provider_lines:
            for provider_line in provider_lines:
                lines.append(f"- `{provider_line}`")
        else:
            lines.append("- No RapidOCR provider detail file found.")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        type=parse_run_arg,
        action="append",
        required=True,
        metavar="LABEL:PATH",
        help="Run output root or stage_e_full_pipeline path.",
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runs = [collect_run(label, path) for label, path in args.run]
    duration_means = _duration_means(runs)
    output = {
        "schema_version": "tools.issue179.rapidocr_comparison_summary.v1",
        "duration_means": duration_means,
        "default_vs_cuda": _comparison_from_means(duration_means),
        "runs": runs,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_markdown(runs, args.output_md)
    print(f"Wrote JSON summary: {args.output_json}")
    print(f"Wrote Markdown summary: {args.output_md}")


if __name__ == "__main__":
    main()
