#!/usr/bin/env python3
"""Temporary #221 v10 windowed RapidOCR evaluation.

This diagnostic consumes v9 mask-repair variant images and tests whether
restricting the horizontal OCR window can suppress edge/neighbor contamination:

- page_001: boxed 2 near the image edge
- page_009: right-side vertical element causing 31-like readings
- page_004: horizontal masking can recover 3, but must remain safe globally

The script is not production code. It evaluates proxy safety using the same
RapidOCR path and numeric candidate selection as `src.measure_numbering.mmr`.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
import traceback
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from src.measure_numbering.mmr import MMROCREngine

TARGETS = {
    "page_001": {"key": [0, 2, 2], "expected_num": 4},
    "page_004": {"key": [3, 2, 2], "expected_num": 3},
    "page_009": {"key": [8, 0, 0], "expected_num": 3},
}
RISKY_DIGITS = {2, 3, 4}
DEFAULT_VARIANTS = {
    "baseline_binary",
    "mask_horizontal_dilate1",
    "mask_horizontal_dilate2",
    "mask_horizontal_vertical_dilate1",
    "mask_horizontal_edge_dilate1",
    "mask_horizontal_vertical_edge_dilate1",
}
OCR_INPUT_MODES = ("direct", "production_standard")


@dataclass(frozen=True)
class WindowSpec:
    name: str
    left_frac: float
    right_frac: float


WINDOWS = (
    WindowSpec("full", 0.0, 1.0),
    WindowSpec("center50", 0.25, 0.75),
    WindowSpec("center60", 0.20, 0.80),
    WindowSpec("center70", 0.15, 0.85),
    WindowSpec("center80", 0.10, 0.90),
    WindowSpec("trim_right10", 0.0, 0.90),
    WindowSpec("trim_right15", 0.0, 0.85),
    WindowSpec("trim_right20", 0.0, 0.80),
    WindowSpec("trim_lr10", 0.10, 0.90),
    WindowSpec("trim_lr15", 0.15, 0.85),
)


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


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)[:180]


def raw_len(value: Any) -> int | None:
    try:
        return len(value)  # type: ignore[arg-type]
    except Exception:
        return None


def short_repr(value: Any, limit: int = 500) -> str:
    return repr(value).replace("\n", " ")[:limit]


def unwrap_rapidocr_result(raw: Any) -> tuple[Any, float | None]:
    if isinstance(raw, tuple) and len(raw) == 2:
        try:
            return raw[0], float(raw[1]) if raw[1] is not None else None
        except Exception:
            return raw[0], None
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


def make_engine() -> tuple[RapidOCR, MMROCREngine, dict[str, Any]]:
    rapid = RapidOCR()
    mmr_ocr = MMROCREngine(ocr_engine=rapid)
    status = {
        "available": True,
        "module": "rapidocr_onnxruntime",
        "selection": "src.measure_numbering.mmr.MMROCREngine.select_best_candidate",
    }
    return rapid, mmr_ocr, status


def apply_window(image: np.ndarray, spec: WindowSpec, pad: int = 20) -> tuple[np.ndarray | None, dict[str, Any]]:
    h, w = image.shape[:2]
    x1 = int(round(w * spec.left_frac))
    x2 = int(round(w * spec.right_frac))
    x1 = max(0, min(w - 1, x1))
    x2 = max(x1 + 1, min(w, x2))
    cropped = image[:, x1:x2]
    if cropped.size == 0 or cropped.shape[1] < 8 or cropped.shape[0] < 8:
        return None, {"window_x1": x1, "window_x2": x2, "window_error": "too_small"}
    padded = cv2.copyMakeBorder(cropped, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    return padded, {
        "window_x1": x1,
        "window_x2": x2,
        "window_width": x2 - x1,
        "source_width": w,
        "source_height": h,
    }


def prepare_input_image(mmr_ocr: MMROCREngine, image: np.ndarray, mode: str) -> tuple[np.ndarray | None, str | None]:
    if mode == "direct":
        return image, None
    if mode == "production_standard":
        try:
            return mmr_ocr.preprocess_variant(image, mode="standard", angle=0), None
        except Exception as exc:
            return None, f"preprocess_failed:{type(exc).__name__}: {exc}"
    return None, f"unknown_ocr_input_mode:{mode}"


def run_ocr(mmr_ocr: MMROCREngine, image: np.ndarray, input_mode: str) -> dict[str, Any]:
    ocr_input, prep_error = prepare_input_image(mmr_ocr, image, input_mode)
    if prep_error:
        return {"error": prep_error}
    if ocr_input is None or ocr_input.size == 0:
        return {"error": "empty_ocr_input"}
    h, w = ocr_input.shape[:2]
    try:
        raw = mmr_ocr.ocr_engine(ocr_input)
        ocr_result, elapsed = unwrap_rapidocr_result(raw)
        texts = collect_texts(ocr_result)
        selected_num, selected_score, selected_debug = mmr_ocr.select_best_candidate(ocr_result, w, h)
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


def should_save_review(row: dict[str, Any]) -> bool:
    return bool(
        row.get("is_exact") is True
        or row.get("is_wrong") is True
        or row.get("is_risky_global") is True
        or row.get("parsed_num") is not None
    )


def eval_rows(
    v9_rows: list[dict[str, str]],
    mmr_ocr: MMROCREngine,
    output_dir: Path,
    save_review_limit: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    review_dir = output_dir / "review_windows"
    review_saved = 0

    for base_idx, row in enumerate(v9_rows):
        image_path = Path(row.get("variant_path") or "")
        image = cv2.imread(str(image_path))
        if image is None:
            for spec in WINDOWS:
                for input_mode in OCR_INPUT_MODES:
                    out.append({
                        "sample_id": row.get("sample_id"),
                        "group": row.get("group"),
                        "page_key": row.get("page_key") or None,
                        "expected_num": norm_expected(row.get("expected_num")),
                        "variant": row.get("variant"),
                        "window": spec.name,
                        "ocr_input_mode": input_mode,
                        "variant_path": row.get("variant_path"),
                        "source_path": row.get("source_path"),
                        "error": f"cv2_imread_failed:{image_path}",
                    })
            continue

        group = row.get("group") or ""
        page_key = row.get("page_key") or None
        expected = norm_expected(row.get("expected_num"))

        for spec in WINDOWS:
            window_img, window_info = apply_window(image, spec)
            if window_img is None:
                for input_mode in OCR_INPUT_MODES:
                    out.append({
                        "sample_id": row.get("sample_id"),
                        "group": group,
                        "page_key": page_key,
                        "expected_num": expected,
                        "variant": row.get("variant"),
                        "window": spec.name,
                        "ocr_input_mode": input_mode,
                        "variant_path": row.get("variant_path"),
                        "source_path": row.get("source_path"),
                        **window_info,
                        "error": window_info.get("window_error") or "window_failed",
                    })
                continue

            for input_mode in OCR_INPUT_MODES:
                result = run_ocr(mmr_ocr, window_img, input_mode)
                parsed = result.get("parsed_num")
                is_exact = None
                is_wrong = None
                if group == "residual" and expected is not None and parsed is not None:
                    is_exact = parsed == expected
                    is_wrong = parsed != expected
                is_risky_global = group == "global" and parsed in RISKY_DIGITS
                eval_row = {
                    "sample_id": row.get("sample_id"),
                    "group": group,
                    "page_key": page_key,
                    "expected_num": expected,
                    "variant": row.get("variant"),
                    "window": spec.name,
                    "ocr_input_mode": input_mode,
                    "variant_path": row.get("variant_path"),
                    "source_path": row.get("source_path"),
                    **window_info,
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
                    "review_image": None,
                }
                if review_saved < save_review_limit and should_save_review(eval_row):
                    review_dir.mkdir(parents=True, exist_ok=True)
                    label = "exact" if is_exact else "wrong" if is_wrong else "risky" if is_risky_global else "parsed"
                    fname = safe_name(
                        f"{review_saved:04d}_{label}_{group}_{page_key}_{row.get('variant')}_{spec.name}_{input_mode}_{parsed}.png"
                    )
                    review_path = review_dir / fname
                    cv2.imwrite(str(review_path), window_img)
                    eval_row["review_image"] = str(review_path)
                    review_saved += 1
                out.append(eval_row)
    return out


def summarize_scope(rows: list[dict[str, Any]], variant: str, window: str, input_mode: str) -> dict[str, Any]:
    scoped = [r for r in rows if r["variant"] == variant and r["window"] == window and r["ocr_input_mode"] == input_mode]
    residual = [r for r in scoped if r["group"] == "residual"]
    global_rows = [r for r in scoped if r["group"] == "global"]
    recovered = sorted({r["page_key"] for r in residual if r.get("is_exact") is True})
    wrong = sum(1 for r in residual if r.get("is_wrong") is True)
    risky = sum(1 for r in global_rows if r.get("is_risky_global") is True)
    by_target = {}
    for page_key, target in TARGETS.items():
        subset = [r for r in residual if r["page_key"] == page_key]
        by_target[page_key] = {
            "expected_num": target["expected_num"],
            "rows": len(subset),
            "raw_text_rows": sum(1 for r in subset if r.get("raw_text_count") or 0),
            "exact_rows": sum(1 for r in subset if r.get("is_exact") is True),
            "wrong_rows": sum(1 for r in subset if r.get("is_wrong") is True),
            "parsed_counts": dict(Counter(str(r.get("parsed_num")) for r in subset if r.get("parsed_num") is not None)),
        }
    return {
        "variant": variant,
        "window": window,
        "ocr_input_mode": input_mode,
        "rows": len(scoped),
        "raw_text_rows": sum(1 for r in scoped if r.get("raw_text_count") or 0),
        "parsed_rows": sum(1 for r in scoped if r.get("parsed_num") is not None),
        "residual_exact_rows": sum(1 for r in residual if r.get("is_exact") is True),
        "residual_wrong_rows": wrong,
        "global_risky_rows": risky,
        "global_risky_counts": dict(Counter(str(r.get("parsed_num")) for r in global_rows if r.get("is_risky_global") is True)),
        "recovered_pages": recovered,
        "recovered_count": len(recovered),
        "candidate_like": bool(recovered and wrong == 0 and risky == 0),
        "by_target": by_target,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    variants = sorted({str(r["variant"]) for r in rows})
    windows = sorted({str(r["window"]) for r in rows})
    modes = sorted({str(r["ocr_input_mode"]) for r in rows})
    scope_summaries = [
        summarize_scope(rows, variant, window, mode)
        for variant in variants
        for window in windows
        for mode in modes
    ]
    candidate_like = [s for s in scope_summaries if s["candidate_like"]]
    residual = [r for r in rows if r["group"] == "residual"]
    global_rows = [r for r in rows if r["group"] == "global"]
    by_target = []
    for page_key, target in TARGETS.items():
        subset = [r for r in residual if r["page_key"] == page_key]
        by_target.append({
            "page_key": page_key,
            "key": target["key"],
            "expected_num": target["expected_num"],
            "rows": len(subset),
            "raw_text_rows": sum(1 for r in subset if r.get("raw_text_count") or 0),
            "exact_rows": sum(1 for r in subset if r.get("is_exact") is True),
            "wrong_rows": sum(1 for r in subset if r.get("is_wrong") is True),
            "parsed_counts": dict(Counter(str(r.get("parsed_num")) for r in subset if r.get("parsed_num") is not None)),
        })
    return {
        "rows": len(rows),
        "error_rows": sum(1 for r in rows if r.get("error")),
        "raw_text_rows": sum(1 for r in rows if r.get("raw_text_count") or 0),
        "parsed_rows": sum(1 for r in rows if r.get("parsed_num") is not None),
        "residual_rows": len(residual),
        "global_rows": len(global_rows),
        "residual_exact_rows": sum(1 for r in residual if r.get("is_exact") is True),
        "residual_wrong_rows": sum(1 for r in residual if r.get("is_wrong") is True),
        "global_risky_rows": sum(1 for r in global_rows if r.get("is_risky_global") is True),
        "global_risky_counts": dict(Counter(str(r.get("parsed_num")) for r in global_rows if r.get("is_risky_global") is True)),
        "by_target": by_target,
        "scope_summaries": scope_summaries,
        "candidate_like_scopes": candidate_like,
        "top_candidate_like_scopes": candidate_like[:20],
    }


def write_decision(path: Path, summary: dict[str, Any]) -> None:
    s = summary["rapidocr_summary"]
    lines = [
        "# Issue #221 v10 windowed RapidOCR evaluation",
        "",
        "This diagnostic applies horizontal OCR-window restrictions to v9 mask-repair images and evaluates them with the production RapidOCR path.",
        "",
        "## Aggregate",
        f"- rows: `{s['rows']}`",
        f"- error_rows: `{s['error_rows']}`",
        f"- raw_text_rows: `{s['raw_text_rows']}`",
        f"- parsed_rows: `{s['parsed_rows']}`",
        f"- residual_exact_rows: `{s['residual_exact_rows']}`",
        f"- residual_wrong_rows: `{s['residual_wrong_rows']}`",
        f"- global_risky_rows: `{s['global_risky_rows']}`",
        f"- candidate_like_scopes: `{len(s['candidate_like_scopes'])}`",
        "",
        "## Targets",
    ]
    for target in s["by_target"]:
        lines.append(
            f"- `{target['page_key']}` expected={target['expected_num']} raw_text_rows={target['raw_text_rows']} exact={target['exact_rows']} wrong={target['wrong_rows']} parsed={target['parsed_counts']}"
        )
    lines.extend(["", "## Candidate-like scopes"])
    if s["candidate_like_scopes"]:
        for scope in s["candidate_like_scopes"][:30]:
            lines.append(
                f"- variant=`{scope['variant']}` window=`{scope['window']}` mode=`{scope['ocr_input_mode']}` recovered={scope['recovered_pages']} exact={scope['residual_exact_rows']} wrong={scope['residual_wrong_rows']} risky={scope['global_risky_rows']}"
            )
    else:
        lines.append("No candidate-like scope was found under the proxy rule.")
    lines.extend([
        "",
        "## Decision guide",
        "A candidate-like scope is not a production candidate. It only means a narrow geometry condition may deserve a production follow-up and full 68-page evaluation.",
        "If scopes recover only page_004, prioritize staff-line-aware horizontal masking. If scopes recover page_001/page_009 without wrong/global risk, inspect review_windows for whether boxed/right-edge contamination was actually removed.",
    ])
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
    parser.add_argument("--output-dir", default="logs/issue221_component_ocr/v10_windowed_rapidocr_eval")
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--variants", default=",".join(sorted(DEFAULT_VARIANTS)))
    parser.add_argument("--review-limit", type=int, default=500)
    args = parser.parse_args()

    started = time.time()
    v9_dir = Path(args.v9_dir)
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    variant_csv = v9_dir / "variant_rows.csv"
    if not variant_csv.exists():
        raise SystemExit(f"Missing {variant_csv}; run v9_mask_repair_probe.py first")

    selected_variants = {item.strip() for item in args.variants.split(",") if item.strip()}
    v9_rows = [r for r in read_csv(variant_csv) if (r.get("variant") or "") in selected_variants]
    if args.max_rows:
        v9_rows = v9_rows[: args.max_rows]

    _rapid, mmr_ocr, status = make_engine()
    rows = eval_rows(v9_rows, mmr_ocr, output_dir, args.review_limit)

    fields = [
        "sample_id", "group", "page_key", "expected_num", "variant", "window", "ocr_input_mode",
        "variant_path", "source_path", "window_x1", "window_x2", "window_width", "source_width", "source_height",
        "ocr_input_width", "ocr_input_height", "raw_type", "raw_len", "raw_repr_head", "ocr_result_type",
        "ocr_result_len", "ocr_result_repr_head", "ocr_elapsed", "raw_texts", "raw_text_count", "parsed_num",
        "selected_score", "selected_debug", "one_bar_evidence_count", "is_exact", "is_wrong", "is_risky_global",
        "error", "traceback_head", "review_image",
    ]
    write_csv(output_dir / "ocr_rows.csv", rows, fields)

    parsed_rows = [r for r in rows if r.get("parsed_num") is not None]
    write_csv(output_dir / "parsed_rows.csv", parsed_rows, fields)
    candidate_rows = [r for r in rows if r.get("is_exact") is True or r.get("is_wrong") is True or r.get("is_risky_global") is True]
    write_csv(output_dir / "candidate_rows.csv", candidate_rows, fields)

    summary = {
        "experiment": "v10_windowed_rapidocr_eval",
        "production_code_changed": False,
        "production_candidate": False,
        "v9_dir": str(v9_dir),
        "output_dir": str(output_dir),
        "selected_variants": sorted(selected_variants),
        "windows": [spec.__dict__ for spec in WINDOWS],
        "ocr_input_modes": list(OCR_INPUT_MODES),
        "v9_rows_evaluated": len(v9_rows),
        "rapidocr_status": status,
        "rapidocr_summary": summarize(rows),
        "candidate_rule": "candidate_like requires recovered_count>=1, residual_wrong_rows=0, global_risky_rows=0 within the same variant/window/ocr_input_mode scope",
        "elapsed_sec": round(time.time() - started, 3),
        "cwd": os.getcwd(),
        "python": sys.version,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_decision(output_dir / "decision.md", summary)

    zip_path = output_dir.parent / "issue221_windowed_rapidocr_v10_pack.zip"
    zip_dir(output_dir, zip_path)
    print(json.dumps({
        "zip_path": str(zip_path),
        "summary_path": str(output_dir / "summary.json"),
        "rows": len(rows),
        "candidate_like_scopes": len(summary["rapidocr_summary"]["candidate_like_scopes"]),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
