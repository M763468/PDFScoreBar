import argparse
import json
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
ARTIFACTS_DIR.mkdir(exist_ok=True)


def run_command(cmd, log_file=None):
    print(f"Executing: {' '.join(cmd)}")
    with open(log_file, "w") if log_file else subprocess.DEVNULL as f:
        start_time = time.perf_counter()
        process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, text=True)

        # Monitor VRAM in background
        vram_samples = []
        while process.poll() is None:
            try:
                res = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                vram_samples.append(int(res.stdout.strip()))
            except Exception:
                pass
            time.sleep(0.5)

        process.wait()
        end_time = time.perf_counter()

    duration = end_time - start_time
    peak_vram = max(vram_samples) if vram_samples else 0
    return duration, peak_vram


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=str, required=True)
    parser.add_argument("--gt", type=str, required=True)
    parser.add_argument("--output-tag", type=str, default="sr_impact_test")
    args = parser.parse_args()

    image_path = Path(args.image).resolve()
    gt_path = Path(args.gt).resolve()

    # We need to use paths relative to PROJECT_ROOT for the container (which mounts it at /workspace)
    rel_image = f"/workspace/{image_path.relative_to(PROJECT_ROOT)}"
    rel_gt = f"/workspace/{gt_path.relative_to(PROJECT_ROOT)}"

    # Base command prefix for Docker
    docker_prefix = [
        "docker",
        "exec",
        "-w",
        "/workspace",
        "-e",
        "PYTHONPATH=/workspace:/workspace/external/homr",
        "sr_eval_gpu",
        "/opt/venv_sr/bin/python",
    ]

    results = {}

    # 1. No SR (Baseline)
    print("\n--- Running Baseline (No SR) ---")
    output_no_sr = ARTIFACTS_DIR / f"{args.output_tag}_no_sr"
    rel_output_no_sr = f"/workspace/artifacts/{args.output_tag}_no_sr"

    cmd_no_sr = docker_prefix + [
        "src/homr_eval_scripts/homr_evaluator.py",
        "--images",
        rel_image,
        "--output-root",
        rel_output_no_sr,
        "--force-run-id",
        "baseline",
        "--ground-truth",
        f"page_001:{rel_gt}",
    ]

    dur_no_sr, vram_no_sr = run_command(cmd_no_sr, ARTIFACTS_DIR / f"{args.output_tag}_no_sr.log")

    # Read metrics
    metrics_no_sr_file = output_no_sr / "baseline" / "metrics.json"
    f1_no_sr = 0
    if metrics_no_sr_file.exists():
        with open(metrics_no_sr_file) as f:
            m = json.load(f)
            f1_no_sr = m["aggregate"]["f1"]

    results["no_sr"] = {"duration": dur_no_sr, "peak_vram": vram_no_sr, "f1": f1_no_sr}

    # 2. With SR
    print("\n--- Running with SR (Real-ESRGAN x4) ---")
    output_sr = ARTIFACTS_DIR / f"{args.output_tag}_with_sr"
    rel_output_sr = f"/workspace/artifacts/{args.output_tag}_with_sr"

    cmd_sr = docker_prefix + [
        "src/homr_eval_scripts/homr_evaluator.py",
        "--images",
        rel_image,
        "--output-root",
        rel_output_sr,
        "--force-run-id",
        "sr",
        "--enable-sr",
        "--ground-truth",
        f"page_001:{rel_gt}",
    ]

    dur_sr, vram_sr = run_command(cmd_sr, ARTIFACTS_DIR / f"{args.output_tag}_with_sr.log")

    # Read metrics
    metrics_sr_file = output_sr / "sr" / "metrics.json"
    f1_sr = 0
    if metrics_sr_file.exists():
        with open(metrics_sr_file) as f:
            m = json.load(f)
            f1_sr = m["aggregate"]["f1"]

    results["with_sr"] = {"duration": dur_sr, "peak_vram": vram_sr, "f1": f1_sr}

    # Summary
    print("\n" + "=" * 40)
    print("SR IMPACT SUMMARY")
    print("=" * 40)
    print(f"{'Metric':<15} | {'No SR':<10} | {'With SR':<10} | {'Diff':<10}")
    print("-" * 40)
    print(
        f"{'Duration (s)':<15} | {dur_no_sr:>10.2f} | {dur_sr:>10.2f} | {dur_sr - dur_no_sr:>10.2f}"
    )
    print(
        f"{'Peak VRAM (MiB)':<15} | {vram_no_sr:>10} | {vram_sr:>10} | {vram_sr - vram_no_sr:>10}"
    )
    print(f"{'F1 Score':<15} | {f1_no_sr:>10.4f} | {f1_sr:>10.4f} | {f1_sr - f1_no_sr:>10.4f}")
    print("=" * 40)

    with open(ARTIFACTS_DIR / f"{args.output_tag}_results.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
