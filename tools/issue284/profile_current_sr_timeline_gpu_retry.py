"""Retry Issue #284 SR timeline profiling with reliable nvidia-smi fields only.

The original timeline profiler samples optional power/clock fields as well as GPU
utilization. On this environment one or more optional fields can report N/A,
causing the original parser to discard the whole sample row. This wrapper keeps
the exact SR/tile timing implementation and narrows sampling to fields already
verified on the target system.
"""

from tools.issue284 import profile_current_sr_timeline as timeline

# Keep only fields known to return numeric values on the target RTX 4060 setup.
timeline.GPU_QUERY_FIELDS = (
    "utilization.gpu",
    "memory.used",
    "memory.free",
)


if __name__ == "__main__":
    raise SystemExit(timeline.main())
