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
            time.sleep(1)

        process.wait()
        end_time = time.perf_counter()

    duration = end_time - start_time
    peak_vram = max(vram_samples) if vram_samples else 0
    return duration, peak_vram


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=str, required=True)
    parser.add_argument("--gt", type=str, required=True)
    parser.add_argument("--output-tag", type=str, default="sr_only_test")
    args = parser.parse_args()

    image_path = Path(args.image).resolve()
    gt_path = Path(args.gt).resolve()
    rel_image = f"/workspace/{image_path.relative_to(PROJECT_ROOT)}"
    rel_gt = f"/workspace/{gt_path.relative_to(PROJECT_ROOT)}"

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

    print(f"\n--- Running with SR (Real-ESRGAN x4) for {image_path.name} ---")
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

    result = {"duration": dur_sr, "peak_vram": vram_sr, "f1": f1_sr}
    print(f"\nResult: Duration={dur_sr:.2f}s, Peak VRAM={vram_sr} MiB, F1={f1_sr:.4f}")

    with open(ARTIFACTS_DIR / f"{args.output_tag}_results.json", "w") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
