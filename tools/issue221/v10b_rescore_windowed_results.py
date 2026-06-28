#!/usr/bin/env python3
"""Temporary #221 v10b rescore for windowed RapidOCR results.

This script does not run OCR. It reads v10 `ocr_rows.csv` and recomputes
summary metrics with clearer separation between:

- v10's original proxy risky definition: global parsed number in {2, 3, 4}
- stricter production-review indicator: any global parsed number >= 2

The output is a diagnostic artifact only. It is not production code.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

TARGETS = {
    "page_001": {"key": [0, 2, 2], "expected_num": 4},
    "page_004": {"key": [3, 2, 2], "expected_num": 3},
    "page_009": {"key": [8, 0, 0], "expected_num": 3},
}
V10_GLOBAL_RISKY_DIGITS = {2, 3, 4}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "None":
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def to_row(raw: dict[str, str]) -> dict[str, Any]:
    row: dict[str, Any] = dict(raw)
    row["expected_num_i"] = parse_int(raw.get("expected_num"))
    row["parsed_num_i"] = parse_int(raw.get("parsed_num"))
    row["raw_text_count_i"] = parse_int(raw.get("raw_text_count")) or 0
    row["is_exact_b"] = parse_bool(raw.get("is_exact"))
    row["is_wrong_b"] = parse_bool(raw.get("is_wrong"))
    row["is_v10_global_risky_b"] = row.get("group") == "global" and row["parsed_num_i"] in V10_GLOBAL_RISKY_DIGITS
    row["is_global_parsed_ge2_b"] = row.get("group") == "global" and row["parsed_num_i"] is not None and row["parsed_num_i"] >= 2
    return row


def source_bucket(path: str | None) -> str:
    if not path:
        return "unknown"
    if "/attempt" in path or "attempt" in path:
        return "diagnostic_attempt_artifact"
    if "v9_mask_repair_probe" in path:
        return "v9_variant_artifact"
    if "logs/" in path:
        return "log_artifact"
    return "other"


def summarize_scope(rows: list[dict[str, Any]], variant: str, window: str, mode: str) -> dict[str, Any]:
    scoped = [r for r in rows if r.get("variant") == variant and r.get("window") == window and r.get("ocr_input_mode") == mode]
    residual = [r for r in scoped if r.get("group") == "residual"]
    global_rows = [r for r in scoped if r.get("group") == "global"]
    recovered_pages = sorted({r.get("page_key") for r in residual if r["is_exact_b"]})
    residual_wrong_rows = sum(1 for r in residual if r["is_wrong_b"])
    global_v10_risky_rows = sum(1 for r in global_rows if r["is_v10_global_risky_b"])
    global_parsed_rows = sum(1 for r in global_rows if r["parsed_num_i"] is not None)
    global_parsed_ge2_rows = sum(1 for r in global_rows if r["is_global_parsed_ge2_b"])
    parsed_counts = Counter(str(r["parsed_num_i"]) for r in scoped if r["parsed_num_i"] is not None)
    global_parsed_counts = Counter(str(r["parsed_num_i"]) for r in global_rows if r["parsed_num_i"] is not None)
    residual_parsed_counts = Counter(str(r["parsed_num_i"]) for r in residual if r["parsed_num_i"] is not None)
    by_target: dict[str, Any] = {}
    for page_key, target in TARGETS.items():
        subset = [r for r in residual if r.get("page_key") == page_key]
        by_target[page_key] = {
            "expected_num": target["expected_num"],
            "rows": len(subset),
            "raw_text_rows": sum(1 for r in subset if r["raw_text_count_i"] > 0),
            "parsed_rows": sum(1 for r in subset if r["parsed_num_i"] is not None),
            "exact_rows": sum(1 for r in subset if r["is_exact_b"]),
            "wrong_rows": sum(1 for r in subset if r["is_wrong_b"]),
            "parsed_counts": dict(Counter(str(r["parsed_num_i"]) for r in subset if r["parsed_num_i"] is not None)),
        }
    source_buckets = Counter(source_bucket(r.get("source_path")) for r in scoped)
    return {
        "variant": variant,
        "window": window,
        "ocr_input_mode": mode,
        "rows": len(scoped),
        "raw_text_rows": sum(1 for r in scoped if r["raw_text_count_i"] > 0),
        "parsed_rows": sum(1 for r in scoped if r["parsed_num_i"] is not None),
        "residual_rows": len(residual),
        "global_rows": len(global_rows),
        "residual_exact_rows": sum(1 for r in residual if r["is_exact_b"]),
        "residual_wrong_rows": residual_wrong_rows,
        "global_v10_risky_rows": global_v10_risky_rows,
        "global_parsed_rows": global_parsed_rows,
        "global_parsed_ge2_rows": global_parsed_ge2_rows,
        "recovered_pages": recovered_pages,
        "recovered_count": len(recovered_pages),
        "candidate_like_v10": bool(recovered_pages and residual_wrong_rows == 0 and global_v10_risky_rows == 0),
        "candidate_like_strict": bool(recovered_pages and residual_wrong_rows == 0 and global_parsed_ge2_rows == 0),
        "parsed_counts": dict(parsed_counts),
        "residual_parsed_counts": dict(residual_parsed_counts),
        "global_parsed_counts": dict(global_parsed_counts),
        "source_buckets": dict(source_buckets),
        "by_target": by_target,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    variants = sorted({str(r.get("variant")) for r in rows})
    windows = sorted({str(r.get("window")) for r in rows})
    modes = sorted({str(r.get("ocr_input_mode")) for r in rows})
    scopes = [summarize_scope(rows, variant, window, mode) for variant in variants for window in windows for mode in modes]
    residual = [r for r in rows if r.get("group") == "residual"]
    global_rows = [r for r in rows if r.get("group") == "global"]
    by_target = []
    for page_key, target in TARGETS.items():
        subset = [r for r in residual if r.get("page_key") == page_key]
        by_target.append({
            "page_key": page_key,
            "key": target["key"],
            "expected_num": target["expected_num"],
            "rows": len(subset),
            "raw_text_rows": sum(1 for r in subset if r["raw_text_count_i"] > 0),
            "parsed_rows": sum(1 for r in subset if r["parsed_num_i"] is not None),
            "exact_rows": sum(1 for r in subset if r["is_exact_b"]),
            "wrong_rows": sum(1 for r in subset if r["is_wrong_b"]),
            "parsed_counts": dict(Counter(str(r["parsed_num_i"]) for r in subset if r["parsed_num_i"] is not None)),
        })
    return {
        "rows": len(rows),
        "raw_text_rows": sum(1 for r in rows if r["raw_text_count_i"] > 0),
        "parsed_rows": sum(1 for r in rows if r["parsed_num_i"] is not None),
        "residual_rows": len(residual),
        "global_rows": len(global_rows),
        "residual_exact_rows": sum(1 for r in residual if r["is_exact_b"]),
        "residual_wrong_rows": sum(1 for r in residual if r["is_wrong_b"]),
        "global_v10_risky_rows": sum(1 for r in global_rows if r["is_v10_global_risky_b"]),
        "global_parsed_rows": sum(1 for r in global_rows if r["parsed_num_i"] is not None),
        "global_parsed_ge2_rows": sum(1 for r in global_rows if r["is_global_parsed_ge2_b"]),
        "global_parsed_counts": dict(Counter(str(r["parsed_num_i"]) for r in global_rows if r["parsed_num_i"] is not None)),
        "by_target": by_target,
        "scope_summaries": scopes,
        "candidate_like_v10_scopes": [s for s in scopes if s["candidate_like_v10"]],
        "candidate_like_strict_scopes": [s for s in scopes if s["candidate_like_strict"]],
    }


def write_scope_csv(path: Path, scopes: list[dict[str, Any]]) -> None:
    fieldnames = [
        "variant",
        "window",
        "ocr_input_mode",
        "rows",
        "raw_text_rows",
        "parsed_rows",
        "residual_exact_rows",
        "residual_wrong_rows",
        "global_v10_risky_rows",
        "global_parsed_rows",
        "global_parsed_ge2_rows",
        "recovered_pages",
        "recovered_count",
        "candidate_like_v10",
        "candidate_like_strict",
        "residual_parsed_counts",
        "global_parsed_counts",
        "source_buckets",
    ]
    flat = []
    for scope in scopes:
        flat.append({
            key: json.dumps(scope[key], ensure_ascii=False) if isinstance(scope.get(key), (dict, list)) else scope.get(key)
            for key in fieldnames
        })
    write_csv(path, flat, fieldnames)


def write_decision(path: Path, summary: dict[str, Any]) -> None:
    s = summary["rescore_summary"]
    lines = [
        "# Issue #221 v10b windowed result rescore",
        "",
        "This is a post-processing pass over v10 `ocr_rows.csv`. It does not run OCR.",
        "",
        "## Metric separation",
        "",
        "- `global_v10_risky_rows`: global rows where parsed number is in `{2, 3, 4}`. This matches the original v10 proxy-risk definition.",
        "- `global_parsed_rows`: global rows where any number was selected by `MMROCREngine.select_best_candidate()`.",
        "- `global_parsed_ge2_rows`: global rows where the selected number is `>= 2`. This is an additional production-review indicator, not the original v10 proxy metric.",
        "- `candidate_like_v10`: exact residual recovery exists, residual wrong is 0, and `global_v10_risky_rows` is 0 in the same scope.",
        "- `candidate_like_strict`: exact residual recovery exists, residual wrong is 0, and `global_parsed_ge2_rows` is 0 in the same scope.",
        "",
        "## Aggregate",
        f"- rows: `{s['rows']}`",
        f"- raw_text_rows: `{s['raw_text_rows']}`",
        f"- parsed_rows: `{s['parsed_rows']}`",
        f"- residual_exact_rows: `{s['residual_exact_rows']}`",
        f"- residual_wrong_rows: `{s['residual_wrong_rows']}`",
        f"- global_v10_risky_rows: `{s['global_v10_risky_rows']}`",
        f"- global_parsed_rows: `{s['global_parsed_rows']}`",
        f"- global_parsed_ge2_rows: `{s['global_parsed_ge2_rows']}`",
        f"- candidate_like_v10_scopes: `{len(s['candidate_like_v10_scopes'])}`",
        f"- candidate_like_strict_scopes: `{len(s['candidate_like_strict_scopes'])}`",
        "",
        "## Targets",
    ]
    for target in s["by_target"]:
        lines.append(
            f"- `{target['page_key']}` expected={target['expected_num']} "
            f"exact={target['exact_rows']} wrong={target['wrong_rows']} "
            f"parsed={target['parsed_counts']}"
        )
    lines.extend(["", "## candidate_like_v10 scopes"])
    if s["candidate_like_v10_scopes"]:
        for scope in s["candidate_like_v10_scopes"]:
            lines.append(
                f"- variant=`{scope['variant']}` window=`{scope['window']}` mode=`{scope['ocr_input_mode']}` "
                f"recovered={scope['recovered_pages']} exact={scope['residual_exact_rows']} wrong={scope['residual_wrong_rows']} "
                f"global_v10_risky={scope['global_v10_risky_rows']} global_parsed_ge2={scope['global_parsed_ge2_rows']} "
                f"global_parsed={scope['global_parsed_counts']}"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## candidate_like_strict scopes"])
    if s["candidate_like_strict_scopes"]:
        for scope in s["candidate_like_strict_scopes"]:
            lines.append(
                f"- variant=`{scope['variant']}` window=`{scope['window']}` mode=`{scope['ocr_input_mode']}` "
                f"recovered={scope['recovered_pages']} exact={scope['residual_exact_rows']} wrong={scope['residual_wrong_rows']} "
                f"global_parsed_ge2={scope['global_parsed_ge2_rows']}"
            )
    else:
        lines.append("- none")
    lines.extend([
        "",
        "## Decision guide",
        "",
        "If `candidate_like_v10` exists but `candidate_like_strict` is empty, the original v10 proxy is too weak for production judgment. Treat the scope as diagnostic evidence only.",
        "If `candidate_like_strict` exists, inspect corresponding v10 `review_windows/` images and source paths before considering any production follow-up.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def zip_dir(output_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(output_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(output_dir.parent))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v10-dir", default="logs/issue221_component_ocr/v10_windowed_rapidocr_eval")
    parser.add_argument("--output-dir", default="logs/issue221_component_ocr/v10b_windowed_result_rescore")
    args = parser.parse_args()

    started = time.time()
    v10_dir = Path(args.v10_dir)
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ocr_csv = v10_dir / "ocr_rows.csv"
    if not ocr_csv.exists():
        raise SystemExit(f"Missing {ocr_csv}; run v10_windowed_rapidocr_eval.py first")

    rows = [to_row(r) for r in read_csv(ocr_csv)]
    rescore = summarize(rows)
    summary = {
        "experiment": "v10b_windowed_result_rescore",
        "production_code_changed": False,
        "production_candidate": False,
        "v10_dir": str(v10_dir),
        "output_dir": str(output_dir),
        "metric_note": "This post-processes existing v10 OCR rows and separates original v10 proxy risk from additional production-review parsed-number indicators.",
        "rescore_summary": rescore,
        "elapsed_sec": round(time.time() - started, 3),
        "cwd": os.getcwd(),
        "python": sys.version,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_scope_csv(output_dir / "scope_summary.csv", rescore["scope_summaries"])
    write_scope_csv(output_dir / "candidate_like_v10_scopes.csv", rescore["candidate_like_v10_scopes"])
    write_scope_csv(output_dir / "candidate_like_strict_scopes.csv", rescore["candidate_like_strict_scopes"])
    write_decision(output_dir / "decision.md", summary)

    zip_path = output_dir.parent / "issue221_windowed_rescore_v10b_pack.zip"
    zip_dir(output_dir, zip_path)
    print(json.dumps({
        "zip_path": str(zip_path),
        "summary_path": str(output_dir / "summary.json"),
        "candidate_like_v10_scopes": len(rescore["candidate_like_v10_scopes"]),
        "candidate_like_strict_scopes": len(rescore["candidate_like_strict_scopes"]),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
