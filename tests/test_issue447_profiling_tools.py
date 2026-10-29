"""Geometry guards for the isolated tile-batching experiment, without GPU/model I/O."""

import json
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from tools.issue447.analyze import proc_summary, select_process_samples
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


def test_process_sample_selection_prefers_run_local_over_legacy(tmp_path):
    run = tmp_path / "multi-off-warm"
    run.mkdir()
    local = run / "proc-samples.jsonl"
    local.write_text("new attempt\n")
    legacy = tmp_path / "old.jsonl"
    legacy.write_text("old attempt\n")
    assert select_process_samples(run, legacy) == (local, "run-local")


def test_legacy_process_samples_require_explicit_matching_run(tmp_path):
    legacy = tmp_path / "old.jsonl"
    legacy.write_text("old attempt\n")
    run = tmp_path / "multi-off-warm"
    assert select_process_samples(run) == (None, "no-run-local-samples")
    assert select_process_samples(run, legacy) == (legacy, "explicit-legacy-fallback")
    assert select_process_samples(tmp_path / "another-attempt", legacy) == (
        None,
        "no-run-local-samples",
    )
    with pytest.raises(FileNotFoundError):
        select_process_samples(run, tmp_path / "missing.jsonl")


def test_host_timeline_does_not_correlate_unaligned_gpu_or_epoch_clocks(tmp_path):
    from tools.issue447.deepening_analyze import timeline

    samples = [
        {
            "epoch": epoch,
            "monotonic": second,
            "cgroup": {"cpu.stat": f"usage_usec {second * 1000000}\n"},
            "processes": [],
        }
        for second, epoch in ((0, 100), (1, 200))
    ]
    (tmp_path / "proc-samples.jsonl").write_text("\n".join(json.dumps(s) for s in samples))
    result = timeline(tmp_path)
    assert result["host_phase_samples_not_exclusive_stages"]["other"] == {
        "sampled_seconds": 1.0,
        "cgroup_cpu_seconds": 1.0,
    }
    assert result["gpu_cpu_clock_correlation"].startswith("Blocked:")


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("python -m src.pipeline.detection.maintained_source_page_worker --request a", True),
        ("python -m tools.issue447.omr_reuse_poc --request a --result b", True),
        ("python -m tools.issue447.omr_reuse_poc --request /tmp/--support.json", True),
        ("python -m tools.issue447.omr_reuse_poc --support --request a", False),
        ("python -m src.pipeline.detection.current_support_worker --request a", False),
        ("python -m tools.issue447.omr_reuse_poc_other --request a", False),
        ("python -m other --request /tmp/maintained_source_page_worker.json", False),
        ("python /tmp/tools.issue447.omr_reuse_poc --request a", False),
        ("python -m", False),
    ],
)
def test_source_worker_entrypoint_distinguishes_reuse_parent_and_support(command, expected):
    from tools.issue447.deepening_analyze import is_source_worker

    assert is_source_worker(command) is expected


@pytest.mark.parametrize("reuse", [False, True])
@pytest.mark.parametrize("workers", [1, 2])
def test_host_timeline_assigns_same_source_intervals_for_both_entrypoints(tmp_path, reuse, workers):
    from tools.issue447.deepening_analyze import timeline

    module = (
        "tools.issue447.omr_reuse_poc"
        if reuse
        else "src.pipeline.detection.maintained_source_page_worker"
    )
    parents = [
        {"pid": pid, "start_ticks": pid, "command": f"python -m {module} --request page_{pid}"}
        for pid in range(1, workers + 1)
    ]
    support = {
        "pid": 10,
        "start_ticks": 10,
        "command": "python -m tools.issue447.omr_reuse_poc --support --request a",
    }
    sr = {"pid": 11, "start_ticks": 11, "command": "python -m current_sr_batch_worker"}
    # A support-only sample must not invent a top-level source worker. Parallel
    # parents and nested support must not multiply an observed interval or CPU.
    samples = [
        {"monotonic": second, "cgroup": {"cpu.stat": f"usage_usec {cpu}\n"}, "processes": procs}
        for second, cpu, procs in [
            (0, 0, []),
            (1, 1000000, parents + [support]),
            (2, 3000000, parents + [support]),
            (3, 4000000, [support]),
            (4, 5000000, parents + [sr]),
        ]
    ]
    (tmp_path / "proc-samples.jsonl").write_text("\n".join(json.dumps(s) for s in samples))
    result = timeline(tmp_path)["host_phase_samples_not_exclusive_stages"]
    assert result == {
        "source": {"sampled_seconds": 2.0, "cgroup_cpu_seconds": 3.0},
        "other": {"sampled_seconds": 1.0, "cgroup_cpu_seconds": 1.0},
        "SR": {"sampled_seconds": 1.0, "cgroup_cpu_seconds": 1.0},
    }
