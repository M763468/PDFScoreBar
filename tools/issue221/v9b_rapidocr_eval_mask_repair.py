#!/usr/bin/env python3
"""Temporary #221 v9b RapidOCR evaluation for v9 mask-repair outputs.

Run v9 first to generate variant images, then run this script to evaluate the
same images with the production-relevant RapidOCR path:

- import `RapidOCR` from `rapidocr_onnxruntime`, matching src.measure_numbering.mmr
- use `MMROCREngine.select_best_candidate()` for numeric candidate selection
- record raw OCR result diagnostics so all-empty runs can be distinguished from
  result-parsing bugs.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import traceback
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import cv2

try:
    from rapidocr_onnxruntime import RapidOCR
except Exception as exc:  # pragma: no cover - local diagnostic guard
    RapidOCR = None  # type: ignore[assignment]
    RAPIDOCR_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    RAPIDOCR_IMPORT_ERROR = None

from src.measure_numbering.mmr import MMROCREngine

TARGETS = {
    "page_001": {"key": [0, 2, 2], "expected_num": 4},
    "page_004": {"key": [3, 2, 2], "expected_num": 3},
    "page_009": {"key": [8, 0, 0], "expected_num": 3},
}
RISKY_DIGITS = {2, 3, 4}
OCR_INPUT_MODES = ("direct", "production_standard")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def norm_expected(value: str | None) -> int | None:
    if not value or value == "None":
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def raw_len(value: Any) -> int | None:
    try:
        return len(value)  # type: ignore[arg-type]
    except Exception:
        return None


def short_repr(value: Any, limit: int = 700) -> str:
    text = repr(value)
    text = text.replace("\n", " ")
    return text[:limit]


def unwrap_rapidocr_result(raw: Any) -> tuple[Any, float | None]:
    """Return `(ocr_result, elapsed)` from common RapidOCR return shapes."""
    if isinstance(raw, tuple) and len(raw) == 2:
        elapsed = raw[1]
        try:
            elapsed_float = float(elapsed) if elapsed is not None else None
        except Exception:
            elapsed_float = None
        return raw[0], elapsed_float
    return raw, None


def collect_texts(ocr_result: Any) -> list[str]:
    texts: list[str] = []
    if not ocr_result:
        return texts
    if isinstance(ocr_result, dict):
        for key in ("text", "rec_text", "label", "content", "contents"):
            value = ocr_result.get(key)
            if value:
                texts.append(str(value))
        for key in ("result", "results", "res", "data"):
            if key in ocr_result:
                texts.extend(collect_texts(ocr_result[key]))
        return texts
    if isinstance(ocr_result, (list, tuple)):
        if len(ocr_result) >= 2 and isinstance(ocr_result[1], str):
            text = ocr_result[1].strip()
            return [text] if text else []
        for item in ocr_result:
            texts.extend(collect_texts(item))
    return texts


def make_engine() -> tuple[RapidOCR | None, MMROCREngine | None, dict[str, Any]]:
    if RapidOCR is None:
        return None, None, {
            "available": False,
            "module": "rapidocr_onnxruntime",
            "import_error": RAPIDOCR_IMPORT_ERROR,
        }
    try:
        rapid = RapidOCR()
        mmr_ocr = MMROCREngine(ocr_engine=rapid)
        return rapid, mmr_ocr, {
            "available": True,
            "module": "rapidocr_onnxruntime",
            "class": "RapidOCR",
            "selection": "src.measure_numbering.mmr.MMROCREngine.select_best_candidate",
        }
    except Exception as exc:
        return None, None, {
            "available": False,
            "module": "rapidocr_onnxruntime",
            "init_error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=5),
        }


def prepare_input_image(mmr_ocr: MMROCREngine, image: Any, mode: str) -> tuple[Any | None, str | None]:
    if mode == "direct":
        return image, None
    if mode == "production_standard":
        try:
            return mmr_ocr.preprocess_variant(image, mode="standard", angle=0), None
        except Exception as exc:
            return None, f"preprocess_failed:{type(exc).__name__}: {exc}"
    return None, f"unknown_ocr_input_mode:{mode}"


def run_one(
    mmr_ocr: MMROCREngine | None,
    image_path: Path,
    input_mode: str,
) -> dict[str, Any]:
    if mmr_ocr is None:
        return {"error": "rapidocr_engine_unavailable"}
    image = cv2.imread(str(image_path))
    if image is None:
        return {"error": f"cv2_imread_failed:{image_path}"}

    ocr_input, prep_error = prepare_input_image(mmr_ocr, image, input_mode)
    if prep_error:
        return {"error": prep_error}
    if ocr_input is None:
        return {"error": "empty_ocr_input"}

    h, w = ocr_input.shape[:2]
    try:
        raw = mmr_ocr.ocr_engine(ocr_input)
        ocr_result, elapsed = unwrap_rapidocr_result(raw)
        texts = collect_texts(ocr_result)
        selected_num, selected_score, selected_debug = mmr_ocr.select_best_candidate(
            ocr_result, w, h
        )
        one_bar_evidence = mmr_ocr.collect_one_bar_evidence(ocr_result)
        return {
            "ocr_input_width": w,
            "ocr_input_height": h,
            "raw_type": type(raw).__name__,
            "raw_len": raw_len(raw),
            "raw_repr_head": short_repr(raw),
            "ocr_result_type": type(ocr_result).__name__,
            "ocr_result_len": raw_len(ocr_result),
            "ocr_result_repr_head": short_repr(ocr_result),
            "ocr_elapsed": elapsed,
            "raw_texts": " | ".join(texts),
            "raw_text_count": len(texts),
            "parsed_num": selected_num,
            "selected_score": selected_score,
            "selected_debug": selected_debug,
            "one_bar_evidence_count": len(one_bar_evidence),
            "error": None,
        }
    except Exception as exc:
        return {
            "ocr_input_width": w,
            "ocr_input_height": h,
            "error": f"ocr_failed:{type(exc).__name__}: {exc}",
            "traceback_head": traceback.format_exc(limit=5),
        }


def eval_rows(v9_rows: list[dict[str, str]], mmr_ocr: MMROCREngine | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in v9_rows:
        path = Path(row.get("variant_path") or "")
        group = row.get("group") or ""
        page_key = row.get("page_key") or None
        expected = norm_expected(row.get("expected_num"))
        for input_mode in OCR_INPUT_MODES:
            result = run_one(mmr_ocr, path, input_mode)
            parsed = result.get("parsed_num")
            is_exact = None
            is_wrong = None
            if group == "residual" and expected is not None and parsed is not None:
                is_exact = parsed == expected
                is_wrong = parsed != expected
            is_risky_global = group == "global" and parsed in RISKY_DIGITS
            out.append(
                {
                    "sample_id": row.get("sample_id"),
                    "group": group,
                    "page_key": page_key,
                    "expected_num": expected,
                    "variant": row.get("variant"),
                    "ocr_input_mode": input_mode,
                    "variant_path": row.get("variant_path"),
                    "source_path": row.get("source_path"),
                    "ocr_input_width": result.get("ocr_input_width"),
                    "ocr_input_height": result.get("ocr_input_height"),
                    "raw_type": result.get("raw_type"),
                    "raw_len": result.get("raw_len"),
                    "raw_repr_head": result.get("raw_repr_head"),
                    "ocr_result_type": result.get("ocr_result_type"),
                    "ocr_result_len": result.get("ocr_result_len"),
                    "ocr_result_repr_head": result.get("ocr_result_repr_head"),
                    "ocr_elapsed": result.get("ocr_elapsed"),
                    "raw_texts": result.get("raw_texts"),
                    "raw_text_count": result.get("raw_text_count"),
                    "parsed_num": parsed,
                    "selected_score": result.get("selected_score"),
                    "selected_debug": result.get("selected_debug"),
                    "one_bar_evidence_count": result.get("one_bar_evidence_count"),
                    "is_exact": is_exact,
                    "is_wrong": is_wrong,
                    "is_risky_global": is_risky_global,
                    "error": result.get("error"),
                    "traceback_head": result.get("traceback_head"),
                }
            )
    return out


def summarize_mode(rows: list[dict[str, Any]], input_mode: str) -> dict[str, Any]:
    mode_rows = [r for r in rows if r["ocr_input_mode"] == input_mode]
    residual = [r for r in mode_rows if r["group"] == "residual"]
    global_rows = [r for r in mode_rows if r["group"] == "global"]
    by_target = []
    for page_key, target in TARGETS.items():
        subset = [r for r in residual if r["page_key"] == page_key]
        by_target.append(
            {
                "page_key": page_key,
                "key": target["key"],
                "expected_num": target["expected_num"],
                "rows": len(subset),
                "raw_text_rows": sum(1 for r in subset if r.get("raw_text_count") or 0),
                "exact_rows": sum(1 for r in subset if r["is_exact"] is True),
                "wrong_rows": sum(1 for r in subset if r["is_wrong"] is True),
                "parsed_counts": dict(Counter(str(r["parsed_num"]) for r in subset if r["parsed_num"] is not None)),
                "exact_variants": dict(Counter(r["variant"] for r in subset if r["is_exact"] is True)),
                "wrong_variants": dict(Counter(r["variant"] for r in subset if r["is_wrong"] is True)),
            }
        )
    variants = []
    for variant in sorted({str(r["variant"]) for r in mode_rows}):
        res_v = [r for r in residual if r["variant"] == variant]
        glob_v = [r for r in global_rows if r["variant"] == variant]
        recovered = sorted({r["page_key"] for r in res_v if r["is_exact"] is True})
        wrong = sum(1 for r in res_v if r["is_wrong"] is True)
        risky = sum(1 for r in glob_v if r["is_risky_global"] is True)
        variants.append(
            {
                "variant": variant,
                "recovered_pages": recovered,
                "recovered_count": len(recovered),
                "residual_exact_rows": sum(1 for r in res_v if r["is_exact"] is True),
                "residual_wrong_rows": wrong,
                "global_risky_rows": risky,
                "raw_text_rows": sum(1 for r in res_v + glob_v if r.get("raw_text_count") or 0),
                "candidate_like": bool(recovered and wrong == 0 and risky == 0),
            }
        )
    return {
        "ocr_input_mode": input_mode,
        "rows": len(mode_rows),
        "error_rows": sum(1 for r in mode_rows if r["error"]),
        "raw_text_rows": sum(1 for r in mode_rows if r.get("raw_text_count") or 0),
        "parsed_rows": sum(1 for r in mode_rows if r["parsed_num"] is not None),
        "residual_rows": len(residual),
        "global_rows": len(global_rows),
        "residual_exact_rows": sum(1 for r in residual if r["is_exact"] is True),
        "residual_wrong_rows": sum(1 for r in residual if r["is_wrong"] is True),
        "global_risky_rows": sum(1 for r in global_rows if r["is_risky_global"] is True),
        "global_risky_counts": dict(Counter(str(r["parsed_num"]) for r in global_rows if r["is_risky_global"] is True)),
        "by_target": by_target,
        "variants": variants,
        "candidate_like_variants": [v for v in variants if v["candidate_like"]],
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    mode_summaries = [summarize_mode(rows, mode) for mode in OCR_INPUT_MODES]
    return {
        "rows": len(rows),
        "error_rows": sum(1 for r in rows if r["error"]),
        "raw_text_rows": sum(1 for r in rows if r.get("raw_text_count") or 0),
        "parsed_rows": sum(1 for r in rows if r["parsed_num"] is not None),
        "mode_summaries": mode_summaries,
        "extraction_suspect": all((m["raw_text_rows"] == 0 and m["parsed_rows"] == 0 and m["error_rows"] == 0) for m in mode_summaries),
    }


def write_decision(path: Path, summary: dict[str, Any]) -> None:
    rapid = summary["rapidocr_summary"]
    lines = [
        "# Issue #221 v9b RapidOCR mask-repair evaluation",
        "",
        "RapidOCR is fixed to `rapidocr_onnxruntime.RapidOCR`, matching `src.measure_numbering.mmr`.",
        "Numeric selection uses `MMROCREngine.select_best_candidate()` rather than an ad-hoc text flattener.",
        "",
        "## RapidOCR status",
        f"`{summary['rapidocr_status']}`",
        "",
        "## Aggregate",
        f"- rows: `{rapid['rows']}`",
        f"- error_rows: `{rapid['error_rows']}`",
        f"- raw_text_rows: `{rapid['raw_text_rows']}`",
        f"- parsed_rows: `{rapid['parsed_rows']}`",
        f"- extraction_suspect: `{rapid['extraction_suspect']}`",
        "",
    ]
    for mode_summary in rapid["mode_summaries"]:
        lines.extend(
            [
                f"## Mode: {mode_summary['ocr_input_mode']}",
                f"- rows: `{mode_summary['rows']}`",
                f"- error_rows: `{mode_summary['error_rows']}`",
                f"- raw_text_rows: `{mode_summary['raw_text_rows']}`",
                f"- parsed_rows: `{mode_summary['parsed_rows']}`",
                f"- residual_exact_rows: `{mode_summary['residual_exact_rows']}`",
                f"- residual_wrong_rows: `{mode_summary['residual_wrong_rows']}`",
                f"- global_risky_rows: `{mode_summary['global_risky_rows']}`",
                f"- candidate_like_variants: `{mode_summary['candidate_like_variants']}`",
                "",
                "Targets:",
            ]
        )
        for target in mode_summary["by_target"]:
            lines.append(
                f"- `{target['page_key']}` expected={target['expected_num']} "
                f"raw_text_rows={target['raw_text_rows']} exact={target['exact_rows']} "
                f"wrong={target['wrong_rows']} parsed={target['parsed_counts']}"
            )
        lines.append("")
    lines.append("## Decision")
    if rapid["extraction_suspect"]:
        lines.append("No raw OCR text or selected numeric candidate was produced in any row despite no errors. Treat this as inconclusive and inspect `raw_repr_head` / `ocr_result_repr_head` in `ocr_rows.csv` before making a #221 decision.")
    elif any(m["candidate_like_variants"] for m in rapid["mode_summaries"]):
        lines.append("At least one mask-repair variant is candidate-like under the proxy rule. Inspect rows and review images before considering a production follow-up issue.")
    else:
        lines.append("No candidate-like variant was found in this proxy run. This is a meaningful negative result only if raw OCR diagnostics confirm extraction is working.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def zip_dir(output_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(output_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(output_dir.parent))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v9-dir", default="logs/issue221_component_ocr/v9_mask_repair_probe")
    parser.add_argument("--output-dir", default="logs/issue221_component_ocr/v9b_rapidocr_mask_repair_eval")
    parser.add_argument("--max-rows", type=int, default=None)
    args = parser.parse_args()

    started = time.time()
    v9_dir = Path(args.v9_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    variant_csv = v9_dir / "variant_rows.csv"
    if not variant_csv.exists():
        raise SystemExit(f"Missing {variant_csv}; run v9_mask_repair_probe.py first")
    v9_rows = read_csv(variant_csv)
    if args.max_rows:
        v9_rows = v9_rows[: args.max_rows]

    _rapid, mmr_ocr, status = make_engine()
    rows = eval_rows(v9_rows, mmr_ocr)
    fields = [
        "sample_id", "group", "page_key", "expected_num", "variant", "ocr_input_mode",
        "variant_path", "source_path", "ocr_input_width", "ocr_input_height",
        "raw_type", "raw_len", "raw_repr_head", "ocr_result_type", "ocr_result_len",
        "ocr_result_repr_head", "ocr_elapsed", "raw_texts", "raw_text_count",
        "parsed_num", "selected_score", "selected_debug", "one_bar_evidence_count",
        "is_exact", "is_wrong", "is_risky_global", "error", "traceback_head",
    ]
    write_csv(output_dir / "ocr_rows.csv", rows, fields)
    summary = {
        "experiment": "v9b_rapidocr_mask_repair_eval",
        "production_code_changed": False,
        "production_candidate": False,
        "v9_dir": str(v9_dir),
        "output_dir": str(output_dir),
        "v9_rows": len(v9_rows),
        "rapidocr_status": status,
        "rapidocr_summary": summarize(rows),
        "candidate_rule": "candidate_like requires recovered_count>=1, residual_wrong_rows=0, global_risky_rows=0 in the same ocr_input_mode proxy sample",
        "elapsed_sec": round(time.time() - started, 3),
        "cwd": os.getcwd(),
        "python": sys.version,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_decision(output_dir / "decision.md", summary)
    zip_path = output_dir.parent / "issue221_mask_repair_rapidocr_v9b_pack.zip"
    zip_dir(output_dir, zip_path)
    print(json.dumps({"zip_path": str(zip_path), "summary_path": str(output_dir / "summary.json"), "rapidocr_available": status.get("available")}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
