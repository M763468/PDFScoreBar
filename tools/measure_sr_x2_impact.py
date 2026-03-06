import json
import subprocess
import sys
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

        # Monitor VRAM
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
            except Exception as e:
                print(f"Warning: Failed to get VRAM usage: {e}", file=sys.stderr)
                pass
            time.sleep(0.5)

        process.wait()
        end_time = time.perf_counter()

    duration = end_time - start_time
    peak_vram = max(vram_samples) if vram_samples else 0
    return duration, peak_vram


def main():
    image_path = PROJECT_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png"
    gt_path = (
        PROJECT_ROOT
        / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/boxes_sorted.json"
    )

    # Paths for container
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

    results = {}

    # Case 1: SR x4 (Reference)
    print("\n--- Running SR x4 ---")
    output_x4 = ARTIFACTS_DIR / "prokofiev_p1_sr_x4_v2"
    rel_output_x4 = "/workspace/artifacts/prokofiev_p1_sr_x4_v2"
    cmd_x4 = docker_prefix + [
        "src/homr_eval_scripts/homr_evaluator.py",
        "--images",
        rel_image,
        "--output-root",
        rel_output_x4,
        "--force-run-id",
        "sr4",
        "--enable-sr",
        "--sr-scale",
        "4",
        "--ground-truth",
        f"page_001:{rel_gt}",
    ]
    dur_x4, vram_x4 = run_command(cmd_x4, ARTIFACTS_DIR / "prokofiev_p1_sr_x4_v2.log")
    results["sr_x4"] = {"duration": dur_x4, "peak_vram": vram_x4}

    # Case 2: SR x2 (Native)
    print("\n--- Running SR x2 (Native) ---")
    output_x2 = ARTIFACTS_DIR / "prokofiev_p1_sr_x2_v2"
    rel_output_x2 = "/workspace/artifacts/prokofiev_p1_sr_x2_v2"
    cmd_x2 = docker_prefix + [
        "src/homr_eval_scripts/homr_evaluator.py",
        "--images",
        rel_image,
        "--output-root",
        rel_output_x2,
        "--force-run-id",
        "sr2",
        "--enable-sr",
        "--sr-scale",
        "2",
        "--ground-truth",
        f"page_001:{rel_gt}",
    ]
    dur_x2, vram_x2 = run_command(cmd_x2, ARTIFACTS_DIR / "prokofiev_p1_sr_x2_v2.log")
    results["sr_x2"] = {"duration": dur_x2, "peak_vram": vram_x2}

    # Extract metrics
    def get_f1(path):
        m_file = Path(path) / "metrics.json"
        if m_file.exists():
            with open(m_file) as f:
                return json.load(f)["aggregate"]["f1"]
        return 0

    results["sr_x4"]["f1"] = get_f1(output_x4 / "sr4")
    results["sr_x2"]["f1"] = get_f1(output_x2 / "sr2")

    print("\n" + "=" * 50)
    print(f"{'Metric':<15} | {'SR x4':<10} | {'SR x2':<10} | {'Diff'}")
    print("-" * 50)
    print(
        f"{'Duration (s)':<15} | {results['sr_x4']['duration']:>10.2f} | {results['sr_x2']['duration']:>10.2f} | {results['sr_x2']['duration'] - results['sr_x4']['duration']:.2f}"
    )
    print(
        f"{'Peak VRAM (MiB)':<15} | {results['sr_x4']['peak_vram']:>10} | {results['sr_x2']['peak_vram']:>10} | {results['sr_x2']['peak_vram'] - results['sr_x4']['peak_vram']}"
    )
    print(
        f"{'F1 Score':<15} | {results['sr_x4']['f1']:>10.4f} | {results['sr_x2']['f1']:>10.4f} | {results['sr_x2']['f1'] - results['sr_x4']['f1']:.4f}"
    )
    print("=" * 50)


if __name__ == "__main__":
    main()
