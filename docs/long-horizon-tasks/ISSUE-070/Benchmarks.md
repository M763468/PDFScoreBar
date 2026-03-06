# Benchmarks

| Milestone | Metric A (Peak VRAM) | Metric B (Latency) | Notes |
| :--- | :--- | :--- | :--- |
| **M0 Baseline** | - | 19.22s (pytest) / 3.05s (dry-run) | Recorded on host host. |
| **M1** | 7.85 GB | ~8m (Full pipeline, 1 page) | Peak VRAM usage reaches 96% of 8GB. |
| **M2** | 7.62 GB | 7m 53s | SR tile size reduced to 400, thread limits (4) applied. |
| **Final** | | | |

## Verification Command
```bash
./tools/run_eval_experiment.py --config configs/eval.yaml
```
