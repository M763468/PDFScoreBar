# Benchmarks

| Milestone | Metric A (Accuracy) | Metric B (Latency) | Notes |
| :--- | :--- | :--- | :--- |
| **M0 Baseline (CPU Fallback)** | - | ~9s / page | Recorded on `main` branch (SHA: dc35656ece5c9245188e9fdc089d2a84472cb1de) |
| **Final (GPU Fixed)** | - | ~1.6s / page | Verified on this PR's branch |

## Verification Command
```bash
docker exec -e PYTHONPATH=/workspace:/workspace/external/homr sr_eval_gpu /opt/venv_sr/bin/python -u src/pipeline/main.py --config configs/issue90_repro_test.yaml
```
