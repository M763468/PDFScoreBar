#!/usr/bin/env python3
"""Grid-search wrapper around homr_evaluator.py."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python <3.9 fallback
    from backports.zoneinfo import ZoneInfo  # type: ignore

DEFAULT_TARGET_BARCNT = 150
VENV_PYTHON = Path("homr/.venv/bin/python")
EVALUATOR = Path("src/homr/homr_evaluator.py")
NIGHT_RUN_STEPS = Path("logs/night_run/steps.ndjson")
JST = ZoneInfo("Asia/Tokyo")


@dataclass
class TrialResult:
    trial_id: str
    min_factor: float
    max_factor: float
    num_predictions: int
    score: float
    metrics_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", nargs="+", required=True, help="Images to evaluate")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("logs/homr_eval"),
        help="Root directory for evaluator outputs",
    )
    parser.add_argument(
        "--run-root",
        type=str,
        help="Run identifier prefix (default: autotune-<timestamp>)",
    )
    parser.add_argument(
        "--min-factors",
        type=float,
        nargs="+",
        default=[0.9, 1.0, 1.1],
        help="Grid values for barline min-height scaling",
    )
    parser.add_argument(
        "--max-factors",
        type=float,
        nargs="+",
        default=[1.0, 1.2],
        help="Grid values for barline max-width scaling",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=DEFAULT_TARGET_BARCNT,
        help="Desired barline count for heuristic scoring",
    )
    return parser.parse_args()


def ensure_python() -> None:
    if not VENV_PYTHON.exists():
        raise SystemExit(f"Python interpreter not found at {VENV_PYTHON}")


def current_jst() -> datetime:
    return datetime.now(JST)


def timestamp() -> str:
    return current_jst().strftime("%Y-%m-%dT%H:%M:%S") + "JST"


def run_trial(
    images: Iterable[str],
    output_root: Path,
    run_id: str,
    min_factor: float,
    max_factor: float,
) -> Path:
    cmd = [
        str(VENV_PYTHON),
        str(EVALUATOR),
        "--output-root",
        str(output_root),
        "--force-run-id",
        run_id,
        "--barline-min-height-factor",
        str(min_factor),
        "--barline-max-width-factor",
        str(max_factor),
    ]
    for image in images:
        cmd.extend(["--images", image])

    result = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        raise SystemExit(f"Trial {run_id} failed with return code {result.returncode}")
    metrics_path = output_root / run_id / "metrics.json"
    if not metrics_path.exists():
        raise SystemExit(f"metrics.json not found for trial {run_id}")
    return metrics_path


def load_num_predictions(metrics_path: Path) -> int:
    with metrics_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    images = data.get("images", [])
    if not images:
        return 0
    return int(images[0].get("num_predictions", 0))


def append_step_log(trial: TrialResult) -> None:
    NIGHT_RUN_STEPS.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": timestamp(),
        "step": "autotune_trial",
        "status": "completed",
        "trial_id": trial.trial_id,
        "params": {
            "barline_min_height_factor": trial.min_factor,
            "barline_max_width_factor": trial.max_factor,
        },
        "metrics": {
            "num_predictions": trial.num_predictions,
            "score": trial.score,
        },
        "metrics_path": str(trial.metrics_path),
    }
    with NIGHT_RUN_STEPS.open("a", encoding="utf-8") as fh:
        json.dump(payload, fh)
        fh.write("\n")


def main() -> None:
    args = parse_args()
    ensure_python()

    run_root = args.run_root or (current_jst().strftime("%Y%m%dT%H%M%S") + "JST_autotune")
    trials: List[TrialResult] = []
    best_score = float("-inf")
    recent_no_improve = 0

    for idx, min_factor in enumerate(args.min_factors, start=1):
        for jdx, max_factor in enumerate(args.max_factors, start=1):
            trial_idx = len(trials) + 1
            trial_id = f"{run_root}/trials/trial-{trial_idx:03d}"
            metrics_path = run_trial(args.images, args.output_root, trial_id, min_factor, max_factor)
            num_predictions = load_num_predictions(metrics_path)
            score = -abs(num_predictions - args.target)
            trial = TrialResult(trial_id, min_factor, max_factor, num_predictions, score, metrics_path)
            trials.append(trial)
            append_step_log(trial)

            if score > best_score + 0.5:
                best_score = score
                recent_no_improve = 0
            else:
                recent_no_improve += 1

            if recent_no_improve >= 5:
                break
        if recent_no_improve >= 5:
            break

    summary_dir = args.output_root / run_root
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / "trials_summary.json"
    best_trial = max(trials, key=lambda t: t.score) if trials else None
    best_payload = (
        {
            "trial_id": best_trial.trial_id,
            "barline_min_height_factor": best_trial.min_factor,
            "barline_max_width_factor": best_trial.max_factor,
            "num_predictions": best_trial.num_predictions,
            "score": best_trial.score,
            "metrics_path": str(best_trial.metrics_path),
        }
        if best_trial
        else None
    )

    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "target": args.target,
                "trials": [
                    {
                        "trial_id": t.trial_id,
                        "barline_min_height_factor": t.min_factor,
                        "barline_max_width_factor": t.max_factor,
                        "num_predictions": t.num_predictions,
                        "score": t.score,
                        "metrics_path": str(t.metrics_path),
                    }
                    for t in trials
                ],
                "best_trial": best_payload,
            },
            fh,
            indent=2,
        )


if __name__ == "__main__":
    main()
