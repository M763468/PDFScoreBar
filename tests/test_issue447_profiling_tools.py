"""Geometry guards for the isolated tile-batching experiment, without GPU/model I/O."""

import json
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from tools.issue447.analyze import proc_summary
from tools.issue447.component_poc import batched_enhance, pixel_difference


@pytest.mark.parametrize("batch_size", [1, 2])
@pytest.mark.parametrize("fp32", [True, False])
def test_batched_tiles_preserve_edge_padding_channel_order_and_cpu_stitch(batch_size, fp32):
    image = np.arange(10 * 14 * 3, dtype=np.uint8).reshape(10, 14, 3)
    seen_batches = []

    def model(tensor):
        seen_batches.append(tensor.shape[0])
        return tensor.repeat_interleave(4, dim=2).repeat_interleave(4, dim=3)

    runtime = SimpleNamespace(
        torch=torch,
        device=torch.device("cpu"),
        fp32=fp32,
        channels_last=True,
        scale=4,
        tile_pad=1,
        model=model,
        _effective_tile=lambda _: 4,
    )
    result = batched_enhance(runtime, image, batch_size)
    expected = np.repeat(np.repeat(image, 4, axis=0), 4, axis=1)
    np.testing.assert_array_equal(result, expected)
    assert max(seen_batches) == batch_size


def test_pixel_comparison_reports_channel_differences_and_shape_mismatch():
    baseline = np.zeros((70, 2, 3), dtype=np.uint8)
    candidate = baseline.copy()
    candidate[65, 1, 2] = 3
    assert pixel_difference(candidate, baseline) == {
        "shape_equal": True,
        "changed_channel_values": 1,
        "max_abs_difference": 3,
    }
    assert pixel_difference(candidate[:2], baseline) == {"shape_equal": False}


def test_process_summary_keeps_nested_residencies_and_cumulative_io_separate(tmp_path):
    samples = []
    for second in range(3):
        processes = [
            {
                "pid": 1,
                "start_ticks": 1,
                "command": "parent",
                "cpu_seconds": second,
                "rss_bytes": 10,
                "io": {"rchar": 100 * second},
            }
        ]
        if second < 2:
            processes.append(
                {
                    "pid": 2,
                    "start_ticks": 2,
                    "command": "child",
                    "cpu_seconds": second,
                    "rss_bytes": 20,
                    "io": {"rchar": 50 * second},
                }
            )
        samples.append(
            {
                "monotonic": second,
                "observer_pid": 99,
                "processes": processes,
                "cgroup": {
                    "cpu.stat": f"usage_usec {1000 * second}\n",
                    "memory.peak": "40\n",
                    "io.stat": f"8:0 rbytes={100 * second} wbytes=0 rios=1 wios=0\n",
                },
            }
        )
    path = tmp_path / "proc.jsonl"
    path.write_text("\n".join(json.dumps(s) for s in samples) + "\n")
    summary = proc_summary(path)
    assert summary["cgroup_cpu_cumulative"]["usage_usec"] == 2000
    assert summary["cgroup_physical_io_cumulative"]["rbytes"] == 200
    assert summary["sampled_peak_sum_rss_bytes"] == 30
    assert [p["observed_residency_seconds"] for p in summary["process_residency_not_additive"]] == [
        2,
        1,
    ]
    assert summary["process_residency_not_additive"][0]["right_censored"]
