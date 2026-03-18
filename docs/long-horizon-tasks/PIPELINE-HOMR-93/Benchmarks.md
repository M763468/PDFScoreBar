# Benchmarks

| Milestone | Metric A (Accuracy F1) | Metric B (Latency per page) | Notes |
| :--- | :--- | :--- | :--- |
| **M0 Baseline** | - | ~130s | Subprocess execution |
| **Final** | 0.9919 | ~120s (Homr) / ~150s (Total) | In-process execution, model loaded once. VRAM stable at ~600 MiB. |

## Verification Command
```bash
docker exec -it pdfscore_pipeline_gpu bash -c "export PYTHONPATH=. ; /opt/venv_pipeline/bin/python src/pipeline/main.py --config configs/evaluation2_e2e_verification_refactor_test.yaml --run-id refactor_test_prokofiev_batch --page-limit 3"
```