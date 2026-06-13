#!/usr/bin/env python3
"""Run the issue #206 context-FOV comparison workflow.

The script orchestrates the local experiment only. It writes generated datasets,
models, scores, reports, previews, and a zip archive under logs/ by default.
It does not modify tracked source files at runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

CURRENT_LIKE = {
    "name": "current_like",
    "crop_width": 128,
    "crop_height": 256,
    "crop_scale": 3.0,
    "min_crop_height": 48,
    "max_crop_height": 256,
}
WIDER_X = {
    "name": "wider_x",
    "crop_width": 384,
    "crop_height": 256,
    "crop_scale": 3.0,
    "min_crop_height": 48,
    "max_crop_height": 256,
}
VARIANTS = {"current_like": CURRENT_LIKE, "wider_x": WIDER_X}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run_command(cmd: list[str], log_path: Path, *, env: dict[str, str] | None = None, dry_run: bool = False) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    display = " ".join(cmd)
    print(f"\n$ {display}")
    if dry_run:
        log_path.write_text(display + "\n")
        return
    with log_path.open("w") as f:
        f.write("$ " + display + "\n\n")
        proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, text=True, env=env)
    if proc.returncode != 0:
        print(f"FAILED: {display}")
        print(f"See log: {log_path}")
        raise SystemExit(proc.returncode)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def candidate_path(args: argparse.Namespace, phase: str) -> Path:
    return (
        args.phase_root
        / phase
        / "scoring"
        / f"eval2_{args.score_name}_{args.page_name}"
        / args.candidate_filename
    )


def candidate_root(args: argparse.Namespace, phase: str) -> Path:
    return args.phase_root / phase / "scoring"


def normalize_lr(value: float) -> str:
    return str(value).replace(".", "p").replace("-", "m")


def dataset_dir(args: argparse.Namespace, phase: str, variant: str) -> Path:
    return args.run_root / "datasets" / f"{phase}_{variant}_e{args.epochs}_lr{normalize_lr(args.learning_rate)}"


def train_dir(args: argparse.Namespace, phase: str, variant: str) -> Path:
    return args.run_root / "training" / f"{phase}_{variant}_e{args.epochs}_lr{normalize_lr(args.learning_rate)}"


def score_dir(args: argparse.Namespace, train_phase: str, score_phase: str, variant: str) -> Path:
    return (
        args.run_root
        / "scoring"
        / f"train_{train_phase}__score_{score_phase}__{variant}_e{args.epochs}_lr{normalize_lr(args.learning_rate)}"
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def load_gt_boxes(gt_dir: Path) -> tuple[Path, list[list[int]]]:
    paths = sorted(gt_dir.glob("boxes_sorted*.json"), key=lambda p: p.name, reverse=True)
    if not paths:
        raise FileNotFoundError(f"No boxes_sorted*.json under {gt_dir}")
    path = paths[0]
    data = load_json(path)
    if isinstance(data, list):
        if not data:
            return path, []
        first = data[0]
        if isinstance(first, dict):
            if "barline_location" in first:
                return path, [x["barline_location"] for x in data]
            if "bbox" in first:
                return path, [x["bbox"] for x in data]
        return path, data
    if isinstance(data, dict):
        if "boxes" in data:
            return path, data["boxes"]
        if "annotations" in data:
            return path, [x["barline_location"] for x in data["annotations"] if "barline_location" in x]
    raise ValueError(f"Unknown GT format: {path}")


def iou(a: list[int], b: list[int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 < ix1 or iy2 < iy1:
        return 0.0
    inter = (ix2 - ix1 + 1) * (iy2 - iy1 + 1)
    area_a = (ax2 - ax1 + 1) * (ay2 - ay1 + 1)
    area_b = (bx2 - bx1 + 1) * (by2 - by1 + 1)
    return inter / float(area_a + area_b - inter)


def evaluate_rows(rows: list[dict[str, Any]], gt_boxes: list[list[int]], threshold: float, iou_threshold: float):
    filtered = [r for r in rows if r["score"] >= threshold]
    matched_gt = set()
    tp = []
    fp = []
    for r in filtered:
        box = r["bbox"]
        best_i = None
        best_iou = 0.0
        for idx, gt in enumerate(gt_boxes):
            value = iou(box, gt)
            if value > best_iou:
                best_i = idx
                best_iou = value
        if best_i is not None and best_iou >= iou_threshold:
            matched_gt.add(best_i)
            tp.append({"bbox": box, "score": r["score"], "gt_index": best_i, "iou": best_iou})
        else:
            fp.append({"bbox": box, "score": r["score"], "best_iou": best_iou})
    fn = [gt for idx, gt in enumerate(gt_boxes) if idx not in matched_gt]
    return filtered, tp, fp, fn


def build_dataset(args: argparse.Namespace, phase: str, variant: str, commands_dir: Path) -> None:
    spec = VARIANTS[variant]
    out = dataset_dir(args, phase, variant)
    train_tp = out / "splits" / "train" / "tp"
    train_fp = out / "splits" / "train" / "fp"
    if train_tp.exists() and train_fp.exists() and not args.force:
        print(f"Dataset exists, skip: {out}")
        return
    cmd = [
        sys.executable,
        "tools/cnn_classifier/build_cnn_dataset.py",
        "--output-root",
        str(out),
        "--skip-local",
        "--skip-deepscores",
        "--eval2-candidates-root",
        str(candidate_root(args, phase)),
        "--eval2-candidate-file",
        args.candidate_filename,
        "--crop-width",
        str(spec["crop_width"]),
        "--crop-height",
        str(spec["crop_height"]),
        "--crop-scale",
        str(spec["crop_scale"]),
        "--min-crop-height",
        str(spec["min_crop_height"]),
        "--max-crop-height",
        str(spec["max_crop_height"]),
        "--seed",
        str(args.seed),
    ]
    run_command(cmd, commands_dir / f"build_dataset_{phase}_{variant}.log", dry_run=args.dry_run)


def train_model(args: argparse.Namespace, phase: str, variant: str, commands_dir: Path) -> Path:
    ds = dataset_dir(args, phase, variant)
    work = train_dir(args, phase, variant)
    model_path = work / "cnn_classifier_best.pth"
    if model_path.exists() and not args.force:
        print(f"Model exists, skip training: {model_path}")
        return model_path
    cmd = [
        sys.executable,
        "experiments/cnn_classifier/train.py",
        "--work-dir",
        str(work),
        "--epochs",
        str(args.epochs),
        "--batch-size",
        str(args.batch_size),
        "--learning-rate",
        str(args.learning_rate),
        "--img-size",
        "256",
        "128",
        "--seed",
        str(args.seed),
        "--model-name",
        args.model_name,
        "--imbalance",
        "sampler",
        "--optimize-threshold",
        "--num-workers",
        str(args.num_workers),
        "--prefetch-factor",
        str(args.prefetch_factor),
    ]
    if args.amp:
        cmd.append("--amp")
    env = os.environ.copy()
    env["CNN_DATASET_ROOT"] = str(ds)
    run_command(cmd, commands_dir / f"train_{phase}_{variant}.log", env=env, dry_run=args.dry_run)
    return model_path


def score_candidates(args: argparse.Namespace, train_phase: str, score_phase: str, variant: str, model_path: Path, commands_dir: Path) -> Path:
    out = score_dir(args, train_phase, score_phase, variant)
    scored = out / f"{variant}_scored.json"
    if scored.exists() and not args.force:
        print(f"Scores exist, skip: {scored}")
        return scored
    cmd = [
        sys.executable,
        "tools/cnn_classifier/score_context_fov_candidates.py",
        "--image",
        str(args.image),
        "--candidates",
        str(candidate_path(args, score_phase)),
        "--model",
        str(model_path),
        "--output-dir",
        str(out),
        "--variant",
        variant,
        "--threshold",
        str(args.threshold),
    ]
    run_command(cmd, commands_dir / f"score_train_{train_phase}_score_{score_phase}_{variant}.log", dry_run=args.dry_run)
    return scored


def write_diff_preview_manifest(args: argparse.Namespace, phase_report_dir: Path, current_only: set[tuple[int, ...]], wider_only: set[tuple[int, ...]]) -> Path:
    manifest = []
    for box in sorted(current_only):
        manifest.append(
            {
                "case_id": "current_only_" + "_".join(map(str, box)),
                "case_type": "current_only",
                "raw_image_path": str(args.image),
                "bbox": list(box),
                "notes": "current_like passes, wider_x suppresses",
            }
        )
    for box in sorted(wider_only):
        manifest.append(
            {
                "case_id": "wider_only_" + "_".join(map(str, box)),
                "case_type": "wider_only",
                "raw_image_path": str(args.image),
                "bbox": list(box),
                "notes": "wider_x passes, current_like suppresses",
            }
        )
    path = phase_report_dir / "diff_preview_manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def compare_phase(args: argparse.Namespace, train_phase: str, score_phase: str, report_dir: Path, commands_dir: Path) -> dict[str, Any]:
    gt_path, gt_boxes = load_gt_boxes(args.gt_dir)
    phase_report_dir = report_dir / f"train_{train_phase}__score_{score_phase}"
    phase_report_dir.mkdir(parents=True, exist_ok=True)

    rows_by_variant = {}
    summary = {
        "train_phase": train_phase,
        "score_phase": score_phase,
        "gt_path": str(gt_path),
        "gt_count": len(gt_boxes),
        "candidate_path": str(candidate_path(args, score_phase)),
        "candidate_sha256": sha256_file(candidate_path(args, score_phase)),
        "variants": {},
    }

    for variant in ("current_like", "wider_x"):
        scored = score_dir(args, train_phase, score_phase, variant) / f"{variant}_scored.json"
        rows = load_json(scored)
        rows_by_variant[variant] = rows
        filtered, tp, fp, fn = evaluate_rows(rows, gt_boxes, args.threshold, args.iou_threshold)
        by_box = {tuple(r["bbox"]): r["score"] for r in rows}
        summary["variants"][variant] = {
            "scored_path": str(scored),
            "filtered_count": len(filtered),
            "tp": len(tp),
            "fp": len(fp),
            "fn": len(fn),
            "target_fp_score": by_box.get(tuple(args.target_fp)),
            "target_fp_filtered": tuple(args.target_fp) in {tuple(r["bbox"]) for r in filtered},
            "true_barline_score": by_box.get(tuple(args.true_barline)),
            "true_barline_filtered": tuple(args.true_barline) in {tuple(r["bbox"]) for r in filtered},
        }

    cur_by = {tuple(r["bbox"]): r["score"] for r in rows_by_variant["current_like"]}
    wid_by = {tuple(r["bbox"]): r["score"] for r in rows_by_variant["wider_x"]}
    cur_set = {tuple(r["bbox"]) for r in rows_by_variant["current_like"] if r["score"] >= args.threshold}
    wid_set = {tuple(r["bbox"]) for r in rows_by_variant["wider_x"] if r["score"] >= args.threshold}
    current_only = cur_set - wid_set
    wider_only = wid_set - cur_set
    summary["filtered_set_diff"] = {
        "current_only_count": len(current_only),
        "wider_only_count": len(wider_only),
        "current_only": [list(b) for b in sorted(current_only)],
        "wider_only": [list(b) for b in sorted(wider_only)],
    }

    common = sorted(set(cur_by) & set(wid_by))
    movement = [
        {"bbox": list(b), "current_like": cur_by[b], "wider_x": wid_by[b], "delta": wid_by[b] - cur_by[b]}
        for b in common
    ]
    movement_up = sorted(movement, key=lambda x: x["delta"], reverse=True)[:30]
    movement_down = sorted(movement, key=lambda x: x["delta"])[:30]

    (phase_report_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (phase_report_dir / "score_movement_top30.json").write_text(
        json.dumps({"increases": movement_up, "decreases": movement_down}, indent=2) + "\n"
    )
    lines = [
        f"# train={train_phase} score={score_phase}",
        "",
        json.dumps(summary, indent=2),
    ]
    (phase_report_dir / "summary.md").write_text("\n".join(lines) + "\n")

    manifest_path = write_diff_preview_manifest(args, phase_report_dir, current_only, wider_only)
    if (current_only or wider_only) and not args.no_previews:
        cmd = [
            sys.executable,
            "tools/cnn_classifier/preview_context_crops.py",
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(phase_report_dir / "diff_previews"),
            "--variant",
            "current_like",
            "--variant",
            "wider_x",
            "--variant",
            "square_context",
            "--max-crops",
            str(args.max_preview_crops),
        ]
        run_command(cmd, commands_dir / f"preview_train_{train_phase}_score_{score_phase}.log", dry_run=args.dry_run)

    return summary


def zip_outputs(args: argparse.Namespace, report_dir: Path) -> Path:
    zip_path = args.run_root / f"issue206_context_fov_auto_{args.train_phase}_e{args.epochs}_lr{normalize_lr(args.learning_rate)}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for base in [report_dir, args.run_root / "scoring"]:
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(args.run_root.parent))
    return zip_path


def print_console_summary(all_summaries: list[dict[str, Any]], zip_path: Path) -> None:
    print("\n=== Issue #206 context-FOV summary ===")
    for summary in all_summaries:
        cur = summary["variants"]["current_like"]
        wid = summary["variants"]["wider_x"]
        diff = summary["filtered_set_diff"]
        print(f"\ntrain={summary['train_phase']} score={summary['score_phase']}")
        print(f"candidate_sha256={summary['candidate_sha256']}")
        print(f"current_like: filtered={cur['filtered_count']} tp={cur['tp']} fp={cur['fp']} fn={cur['fn']} target={cur['target_fp_score']} true={cur['true_barline_score']}")
        print(f"wider_x:      filtered={wid['filtered_count']} tp={wid['tp']} fp={wid['fp']} fn={wid['fn']} target={wid['target_fp_score']} true={wid['true_barline_score']}")
        print(f"diff: current_only={diff['current_only_count']} wider_only={diff['wider_only_count']}")
    print(f"\nZIP: {zip_path}")


def parse_args() -> argparse.Namespace:
    root = repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=Path("logs/issue206_context_fov_auto"))
    parser.add_argument("--phase-root", type=Path, default=Path("logs/issue202_fp0_search/phase5_eval"))
    parser.add_argument("--train-phase", default="B200")
    parser.add_argument("--score-phases", nargs="+", default=["B200", "C100", "D100"])
    parser.add_argument("--score-name", default="Va_Prokofiev_Symphony1")
    parser.add_argument("--page-name", default="page_004")
    parser.add_argument("--candidate-filename", default="pipeline2_no_peak_candidates.json")
    parser.add_argument("--image", type=Path, default=Path("data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png"))
    parser.add_argument("--gt-dir", type=Path, default=Path("data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004"))
    parser.add_argument("--target-fp", type=int, nargs=4, default=[2613, 4110, 2617, 4208])
    parser.add_argument("--true-barline", type=int, nargs=4, default=[2404, 4107, 2412, 4208])
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--learning-rate", type=float, default=3e-5)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--seed", type=int, default=44)
    parser.add_argument("--model-name", default="resnet18")
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--prefetch-factor", type=int, default=2)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--max-preview-crops", type=int, default=60)
    parser.add_argument("--amp", action="store_true", default=True)
    parser.add_argument("--no-amp", action="store_false", dest="amp")
    parser.add_argument("--force", action="store_true", help="Rebuild datasets, retrain, and rescore even when outputs exist.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-previews", action="store_true")
    args = parser.parse_args()

    os.chdir(root)
    args.run_root = args.run_root.resolve()
    args.phase_root = args.phase_root.resolve()
    args.image = args.image.resolve()
    args.gt_dir = args.gt_dir.resolve()
    return args


def main() -> int:
    args = parse_args()
    args.run_root.mkdir(parents=True, exist_ok=True)
    commands_dir = args.run_root / "command_logs"
    report_dir = args.run_root / "reports"

    for phase in [args.train_phase] + list(args.score_phases):
        path = candidate_path(args, phase)
        if not path.exists():
            raise FileNotFoundError(f"Candidate file not found for {phase}: {path}")

    for variant in ("current_like", "wider_x"):
        build_dataset(args, args.train_phase, variant, commands_dir)
    models = {variant: train_model(args, args.train_phase, variant, commands_dir) for variant in ("current_like", "wider_x")}

    for phase in args.score_phases:
        for variant in ("current_like", "wider_x"):
            score_candidates(args, args.train_phase, phase, variant, models[variant], commands_dir)

    summaries = [compare_phase(args, args.train_phase, phase, report_dir, commands_dir) for phase in args.score_phases]
    aggregate_path = report_dir / "aggregate_summary.json"
    aggregate_path.parent.mkdir(parents=True, exist_ok=True)
    aggregate_path.write_text(json.dumps(summaries, indent=2) + "\n")
    zip_path = zip_outputs(args, report_dir)
    print_console_summary(summaries, zip_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
