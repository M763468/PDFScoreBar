#!/usr/bin/env python3
"""Score fixed Issue #218 outputs against independently authored scan annotations."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GT = ROOT / "tests/fixtures/system_grouping/issue218_measure_gt.json"


def validate_gt(annotation: dict) -> None:
    if annotation["schema_version"] != "pdfscore.manual_measure_gt.v1":
        raise ValueError("Unsupported annotation schema")
    works = annotation["works"]
    if len({work["id"] for work in works}) != len(works) or not works:
        raise ValueError("Unique, nonempty annotated works are required")
    for work in works:
        number = 1
        if len({page["page_id"] for page in work["pages"]}) != len(work["pages"]):
            raise ValueError("Duplicate annotated page")
        for page in work["pages"]:
            local_number = 1
            width, height = page["image_size"]
            for i, system in enumerate(page["systems"]):
                unit = system["staff_spacing"]
                centers = system["staff_center_y"]
                boundaries = system["shared_boundaries_x"]
                if system["index_0based"] != i or not math.isfinite(unit) or unit <= 0:
                    raise ValueError("Invalid system index or staff spacing")
                if (
                    not centers
                    or centers != sorted(set(centers))
                    or not all(0 <= y < height for y in centers)
                ):
                    raise ValueError("Invalid annotated staff centers")
                if len(boundaries) != len(system["measures"]) + 1 or not all(
                    0 <= a < b <= width for a, b in zip(boundaries, boundaries[1:])
                ):
                    raise ValueError("Invalid annotated measure boundaries")
                for j, measure in enumerate(system["measures"]):
                    duration = measure["duration_bars"]
                    if (
                        measure["index_0based"] != j
                        or measure["x_interval"] != boundaries[j : j + 2]
                        or not isinstance(duration, int)
                        or duration < 1
                        or measure["printed_rest_count"] not in (None, duration)
                        or (duration > 1 and measure["printed_rest_count"] != duration)
                    ):
                        raise ValueError("Invalid annotated duration or interval")
                    if (
                        measure["expected_run_number"] != number
                        or measure["expected_page_local_number"] != local_number
                    ):
                        raise ValueError("Annotated numbering disagrees with durations")
                    number += duration
                    local_number += duration
        if number - 1 != work["musical_bar_total"] or work["displayed_intervals"] != sum(
            len(s["measures"]) for p in work["pages"] for s in p["systems"]
        ):
            raise ValueError("Annotated totals disagree with intervals")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def interval_iou(a: list[int], b: list[int]) -> float:
    intersection = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    return intersection / max(1, max(a[1], b[1]) - min(a[0], b[0]))


def align_intervals(predicted: list[list[int]], expected: list[list[int]]) -> list[tuple[int, int]]:
    """Ordered, geometry-only matching; never align indices by predicted counts."""
    table = [[(0, 0.0, []) for _ in range(len(expected) + 1)] for _ in range(len(predicted) + 1)]
    for i, pred in enumerate(predicted, 1):
        for j, gt in enumerate(expected, 1):
            options = [table[i - 1][j], table[i][j - 1]]
            overlap = interval_iou(pred, gt)
            if overlap >= 0.8:
                count, total, pairs = table[i - 1][j - 1]
                options.append((count + 1, total + overlap, pairs + [(i - 1, j - 1)]))
            table[i][j] = max(options, key=lambda item: item[:2])
    return table[-1][-1][2]


def boundary_matches(predicted: list[float], expected: list[int], tolerance: float) -> int:
    pairs = sorted(
        (abs(p - g), i, j)
        for i, p in enumerate(predicted)
        for j, g in enumerate(expected)
        if abs(p - g) <= tolerance
    )
    used_pred, used_gt = set(), set()
    for _, i, j in pairs:
        if i not in used_pred and j not in used_gt:
            used_pred.add(i)
            used_gt.add(j)
    return len(used_gt)


def score_page(page: dict, expected: dict, overrides: dict, *, page_index: int = 0) -> dict:
    pred_systems = page["systems"]
    durations = {}
    for item in overrides["measure_overrides"]:
        key = (item["system"], item["measure"])
        if item.get("page", page_index) != page_index or key in durations or item["skip"] < 0:
            raise ValueError(f"Invalid or duplicate MMR override: {item}")
        if not (0 <= key[0] < len(pred_systems)) or not (
            0 <= key[1] < len(pred_systems[key[0]]["measures"])
        ):
            raise ValueError(f"MMR override points outside the numbering page: {item}")
        durations[key] = item["skip"] + 1
    pred_mmr = {key: value for key, value in durations.items() if value >= 2}
    gt_mmr = {
        (i, j): measure["duration_bars"]
        for i, system in enumerate(expected["systems"])
        for j, measure in enumerate(system["measures"])
        if measure["duration_bars"] >= 2
    }
    first_number = next((m["number"] for s in pred_systems for m in s["measures"]), 1)
    results, mmr_pairs = [], []
    for i, gt_system in enumerate(expected["systems"]):
        pred_system = pred_systems[i] if i < len(pred_systems) else {"staves": [], "measures": []}
        pred = pred_system["measures"]
        gt = gt_system["measures"]
        centers = gt_system["staff_center_y"]
        unit = gt_system["staff_spacing"]
        core = [min(centers) - 2 * unit, max(centers) + 2 * unit]
        # Reject unrelated vertical geometry before horizontal matching.
        intervals = []
        for measure in pred:
            x1, y1, x2, y2 = measure["bbox"]
            overlap = max(0, min(y2, core[1]) - max(y1, core[0]))
            vov = overlap / max(1, min(y2 - y1, core[1] - core[0]))
            intervals.append([x1, x2] if vov >= 0.5 else [0, 0])
        pairs = align_intervals(intervals, [m["x_interval"] for m in gt])
        matched_pred, matched_gt = {p for p, _ in pairs}, {g for _, g in pairs}
        details = []
        for p, g in pairs:
            details.append(
                {
                    "pred_index": p,
                    "gt_index": g,
                    "pred_interval": intervals[p],
                    "gt_interval": gt[g]["x_interval"],
                    "pred_number": pred[p]["number"],
                    "gt_number": gt[g]["expected_run_number"],
                    "number_correct": pred[p]["number"] == gt[g]["expected_run_number"],
                    "page_local_number_correct": pred[p]["number"] - first_number + 1
                    == gt[g]["expected_page_local_number"],
                    "pred_duration": durations.get((i, p), 1),
                    "gt_duration": gt[g]["duration_bars"],
                }
            )
            if (i, p) in pred_mmr and (i, g) in gt_mmr:
                mmr_pairs.append(((i, p), (i, g)))
        boundaries = [(a["bbox"][2] + b["bbox"][0]) / 2 for a, b in zip(pred, pred[1:])]
        gt_boundaries = gt_system["shared_boundaries_x"][1:-1]
        boundary_tp = boundary_matches(boundaries, gt_boundaries, 0.5 * unit)
        staff_membership = len(pred_system["staves"]) == len(centers) and all(
            staff["bbox"][1] <= y <= staff["bbox"][3]
            for staff, y in zip(pred_system["staves"], centers)
        )
        results.append(
            {
                "system": i,
                "staff_membership_correct": staff_membership,
                "displayed_counts": {"pred": len(pred), "gt": len(gt)},
                "count_correct": len(pred) == len(gt),
                "matched_intervals": len(pairs),
                "unmatched_pred": sorted(set(range(len(pred))) - matched_pred),
                "unmatched_gt": sorted(set(range(len(gt))) - matched_gt),
                "numbers_correct": sum(d["number_correct"] for d in details),
                "page_local_numbers_correct": sum(d["page_local_number_correct"] for d in details),
                "boundary": {
                    "tp": boundary_tp,
                    "fp": len(boundaries) - boundary_tp,
                    "fn": len(gt_boundaries) - boundary_tp,
                },
                "matches": details,
            }
        )
    paired_pred = {p for p, _ in mmr_pairs}
    paired_gt = {g for _, g in mmr_pairs}
    count_errors = [
        {"pred": list(p), "gt": list(g), "pred_count": pred_mmr[p], "gt_count": gt_mmr[g]}
        for p, g in mmr_pairs
        if pred_mmr[p] != gt_mmr[g]
    ]
    return {
        "page_id": expected["page_id"],
        "pred_intervals_total": sum(len(s["measures"]) for s in pred_systems),
        "systems": results,
        "extra_systems": len(pred_systems) - min(len(pred_systems), len(expected["systems"])),
        "missing_systems": max(0, len(expected["systems"]) - len(pred_systems)),
        "empty_systems": len(page.get("empty_systems", [])),
        "mmr": {
            "gt": len(gt_mmr),
            "pred": len(pred_mmr),
            "detected": len(mmr_pairs),
            "exact_count": len(mmr_pairs) - len(count_errors),
            "count_errors": count_errors,
            "missed": [list(key) for key in sorted(set(gt_mmr) - paired_gt)],
            "false_positive": [list(key) for key in sorted(set(pred_mmr) - paired_pred)],
        },
    }


def evaluate(gt_path: Path, runs: dict[str, Path]) -> dict:
    gt = json.loads(gt_path.read_text())
    validate_gt(gt)
    if set(runs) != {work["id"] for work in gt["works"]}:
        raise ValueError("Every annotated work is required; extra/omitted works are invalid")
    results = []
    for work in gt["works"]:
        run = runs[work["id"]]
        manifest_path = run / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        if [p["page_id"] for p in manifest["pages"]] != [p["page_id"] for p in work["pages"]]:
            raise ValueError("Input set or order changed")
        pages = []
        for page_index, (source, expected) in enumerate(zip(manifest["pages"], work["pages"])):
            image = resolve(source["image_path"])
            if digest(image) != expected["image_sha256"]:
                raise ValueError(f"Input SHA mismatch: {image}")
            page_id = expected["page_id"]
            numbering = run / "outputs" / page_id / "numbering_final.json"
            overrides = run / "intermediate" / page_id / "overrides_mmr.json"
            payload = json.loads(numbering.read_text())
            if len(payload["pages"]) != 1:
                raise ValueError("Expected one page in each final numbering payload")
            page = payload["pages"][0]
            if [page["width"], page["height"]] != expected["image_size"]:
                raise ValueError("Input coordinate frame changed")
            if page["page_number"] != page_index + 1:
                raise ValueError("Page numbering differs from the configured input order")
            result = score_page(
                page, expected, json.loads(overrides.read_text()), page_index=page_index
            )
            result["artifact_sha256"] = {
                "image": digest(image),
                "numbering": digest(numbering),
                "mmr_overrides": digest(overrides),
            }
            pages.append(result)
        results.append(
            {
                "work": work["id"],
                "run_dir": str(run),
                "manifest_sha256": digest(manifest_path),
                "pages": pages,
            }
        )
    pages = [p for work in results for p in work["pages"]]
    systems = [s for page in pages for s in page["systems"]]
    totals = {
        "gt_intervals": sum(s["displayed_counts"]["gt"] for s in systems),
        "pred_intervals": sum(p["pred_intervals_total"] for p in pages),
        "matched_intervals": sum(s["matched_intervals"] for s in systems),
        "correct_numbers": sum(s["numbers_correct"] for s in systems),
        "correct_page_local_numbers": sum(s["page_local_numbers_correct"] for s in systems),
        "count_correct_systems": sum(s["count_correct"] for s in systems),
        "total_systems": len(systems),
        "mmr_gt": sum(p["mmr"]["gt"] for p in pages),
        "mmr_pred": sum(p["mmr"]["pred"] for p in pages),
        "mmr_exact": sum(p["mmr"]["exact_count"] for p in pages),
    }
    topology = all(s["staff_membership_correct"] for s in systems) and not any(
        p["extra_systems"] or p["missing_systems"] or p["empty_systems"] for p in pages
    )
    gates = {
        "staff_membership": topology,
        "displayed_counts": totals["count_correct_systems"] == len(systems)
        and not any(p["extra_systems"] or p["missing_systems"] for p in pages),
        "mmr_exact": totals["mmr_exact"] == totals["mmr_gt"] == totals["mmr_pred"],
        "final_numbers_and_coverage": totals["correct_numbers"]
        == totals["gt_intervals"]
        == totals["pred_intervals"],
    }
    return {
        "status": "passed" if all(gates.values()) else "failed",
        "gates": gates,
        "annotation_sha256": digest(gt_path),
        "evaluation_contract": gt["evaluation_contract"],
        "annotation_provenance": gt["annotation_provenance"],
        "totals": totals,
        "works": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gt", type=Path, default=GT)
    parser.add_argument(
        "--run", action="append", required=True, help="WORK=RUN_DIR (every work required)"
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    runs = {}
    for item in args.run:
        work, path = item.split("=", 1)
        if work in runs:
            raise ValueError(f"Duplicate work: {work}")
        runs[work] = resolve(path)
    report = evaluate(resolve(args.gt), runs)
    report["evaluator_sha256"] = digest(Path(__file__))
    report["checkout_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    output = resolve(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "gates", "totals")}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
