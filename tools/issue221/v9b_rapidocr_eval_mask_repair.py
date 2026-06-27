#!/usr/bin/env python3
"""Temporary #221 v9b RapidOCR evaluation for v9 mask-repair outputs.

Run v9 first to generate variant images, then run this script to evaluate the
same images with RapidOCR, the production-relevant OCR backend.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import re
import sys
import time
import traceback
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore[assignment]

try:
    from PIL import Image
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"Pillow is required: {exc}") from exc

TARGETS = {
    "page_001": {"key": [0, 2, 2], "expected_num": 4},
    "page_004": {"key": [3, 2, 2], "expected_num": 3},
    "page_009": {"key": [8, 0, 0], "expected_num": 3},
}
RISKY_DIGITS = {2, 3, 4}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_num(text: str | None) -> int | None:
    if not text:
        return None
    digits = "".join(ch for ch in str(text) if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def norm_expected(value: str | None) -> int | None:
    if not value or value == "None":
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def flatten(obj: Any) -> list[Any]:
    if obj is None:
        return []
    if isinstance(obj, (str, int, float)):
        return [obj]
    if isinstance(obj, dict):
        out: list[Any] = []
        for key in ("text", "rec_text", "label", "content", "contents"):
            if key in obj:
                out.append(obj[key])
        for key in ("result", "results", "res", "data"):
            if key in obj:
                out.extend(flatten(obj[key]))
        return out
    if isinstance(obj, (tuple, list)):
        if len(obj) >= 2 and isinstance(obj[1], str):
            return [obj]
        out = []
        for item in obj:
            out.extend(flatten(item))
        return out
    return []


def extract_text_score(raw: Any) -> tuple[str | None, float | None]:
    candidates: list[tuple[str, float | None]] = []
    for item in flatten(raw):
        if isinstance(item, str):
            text = item.strip()
            if text:
                candidates.append((text, None))
        elif isinstance(item, dict):
            text = None
            for key in ("text", "rec_text", "label", "content", "contents"):
                if key in item and item[key] is not None:
                    text = str(item[key]).strip()
                    break
            score = None
            for key in ("score", "confidence", "conf", "rec_score"):
                if key in item:
                    try:
                        score = float(item[key])
                    except Exception:
                        score = None
                    break
            if text:
                candidates.append((text, score))
        elif isinstance(item, (tuple, list)) and len(item) >= 2 and isinstance(item[1], str):
            score = None
            if len(item) >= 3:
                try:
                    score = float(item[2])
                except Exception:
                    score = None
            candidates.append((item[1].strip(), score))
    if not candidates:
        return None, None
    candidates.sort(key=lambda x: (not any(ch.isdigit() for ch in x[0]), -(x[1] or -1.0), len(x[0])))
    return candidates[0]


def make_rapidocr_engine() -> tuple[Any | None, dict[str, Any]]:
    attempts: list[str] = []
    for module_name in ("rapidocr", "rapidocr_onnxruntime", "rapidocr_openvino"):
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            attempts.append(f"{module_name}: import failed: {type(exc).__name__}: {exc}")
            continue
        cls = getattr(module, "RapidOCR", None)
        if cls is None:
            attempts.append(f"{module_name}: RapidOCR class not found")
            continue
        try:
            return cls(), {"available": True, "module": module_name, "class": "RapidOCR"}
        except Exception as exc:
            attempts.append(f"{module_name}: init failed: {type(exc).__name__}: {exc}")
    return None, {"available": False, "attempts": attempts}


def run_rapidocr(engine: Any, path: Path) -> tuple[str | None, float | None, str | None]:
    try:
        raw = engine(str(path))
        text, score = extract_text_score(raw)
        return text, score, None
    except Exception as exc1:
        if np is None:
            return None, None, f"path call failed and numpy unavailable: {type(exc1).__name__}: {exc1}"
        try:
            arr = np.asarray(Image.open(path).convert("RGB"))
            raw = engine(arr)
            text, score = extract_text_score(raw)
            return text, score, None
        except Exception as exc2:
            return None, None, f"path failed {type(exc1).__name__}: {exc1}; array failed {type(exc2).__name__}: {exc2}"


def eval_rows(v9_rows: list[dict[str, str]], engine: Any | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in v9_rows:
        path = Path(row.get("variant_path") or "")
        text = None
        score = None
        error = None
        if engine is None:
            error = "rapidocr_unavailable"
        elif not path.exists():
            error = f"missing_variant_path:{path}"
        else:
            text, score, error = run_rapidocr(engine, path)
        parsed = parse_num(text)
        group = row.get("group") or ""
        page_key = row.get("page_key") or None
        expected = norm_expected(row.get("expected_num"))
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
                "variant_path": row.get("variant_path"),
                "source_path": row.get("source_path"),
                "ocr_text": text,
                "ocr_score": score,
                "parsed_num": parsed,
                "is_exact": is_exact,
                "is_wrong": is_wrong,
                "is_risky_global": is_risky_global,
                "error": error,
            }
        )
    return out


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    residual = [r for r in rows if r["group"] == "residual"]
    global_rows = [r for r in rows if r["group"] == "global"]
    by_target = []
    for page_key, target in TARGETS.items():
        subset = [r for r in residual if r["page_key"] == page_key]
        by_target.append(
            {
                "page_key": page_key,
                "key": target["key"],
                "expected_num": target["expected_num"],
                "rows": len(subset),
                "exact_rows": sum(1 for r in subset if r["is_exact"] is True),
                "wrong_rows": sum(1 for r in subset if r["is_wrong"] is True),
                "parsed_counts": dict(Counter(str(r["parsed_num"]) for r in subset if r["parsed_num"] is not None)),
                "exact_variants": dict(Counter(r["variant"] for r in subset if r["is_exact"] is True)),
                "wrong_variants": dict(Counter(r["variant"] for r in subset if r["is_wrong"] is True)),
            }
        )
    variants = []
    for variant in sorted({str(r["variant"]) for r in rows}):
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
                "global_parsed_counts": dict(Counter(str(r["parsed_num"]) for r in glob_v if r["parsed_num"] is not None)),
                "candidate_like": bool(recovered and wrong == 0 and risky == 0),
            }
        )
    return {
        "rows": len(rows),
        "error_rows": sum(1 for r in rows if r["error"]),
        "parsed_rows": sum(1 for r in rows if r["parsed_num"] is not None),
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


def write_decision(path: Path, summary: dict[str, Any]) -> None:
    rapid = summary["rapidocr_summary"]
    lines = [
        "# Issue #221 v9b RapidOCR mask-repair evaluation",
        "",
        "RapidOCR is the primary backend for this diagnostic because it is the production-relevant OCR path.",
        "",
        "## RapidOCR status",
        f"`{summary['rapidocr_status']}`",
        "",
        "## Aggregate",
        f"- rows: `{rapid['rows']}`",
        f"- error_rows: `{rapid['error_rows']}`",
        f"- residual_exact_rows: `{rapid['residual_exact_rows']}`",
        f"- residual_wrong_rows: `{rapid['residual_wrong_rows']}`",
        f"- global_risky_rows: `{rapid['global_risky_rows']}`",
        f"- candidate_like_variants: `{rapid['candidate_like_variants']}`",
        "",
        "## Targets",
    ]
    for target in rapid["by_target"]:
        lines.append(
            f"- `{target['page_key']}` expected={target['expected_num']} "
            f"exact={target['exact_rows']} wrong={target['wrong_rows']} parsed={target['parsed_counts']}"
        )
    lines.extend(["", "## Decision"])
    if rapid["error_rows"] == rapid["rows"]:
        lines.append("RapidOCR did not run successfully. Re-run in the environment where the production OCR backend is installed.")
    elif rapid["candidate_like_variants"]:
        lines.append("At least one mask-repair variant is candidate-like under the proxy rule. Inspect `ocr_rows.csv` and review images before deciding whether to create a production follow-up issue.")
    else:
        lines.append("No RapidOCR candidate-like variant was found under the proxy rule. The current mask-repair variants are not sufficient as a production fallback.")
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

    engine, status = make_rapidocr_engine()
    rows = eval_rows(v9_rows, engine)
    fields = [
        "sample_id", "group", "page_key", "expected_num", "variant", "variant_path",
        "source_path", "ocr_text", "ocr_score", "parsed_num", "is_exact", "is_wrong",
        "is_risky_global", "error",
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
        "candidate_rule": "candidate_like requires recovered_count>=1, residual_wrong_rows=0, global_risky_rows=0 in this proxy sample",
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
