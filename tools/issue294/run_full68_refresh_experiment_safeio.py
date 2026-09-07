#!/usr/bin/env python3
"""Run the Issue #294 full68 experiment without root writes to the bind mount.

Temporary experiment-only compatibility wrapper.  The profiling container's
/workspace is a live bind mount of the Issue #294 worktree.  Once the driver's
round-trip check has passed, tracked source synchronization must therefore be
read-only: compare host/container hashes rather than extracting a tar archive as
container root.  Likewise, make the Real-ESRGAN weight bind-visible from the host
instead of copying it into /workspace with docker cp.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from tools.issue294 import run_full68_refresh_experiment as driver
from tools.issue294.run_full68_refresh_experiment_hosttests import _host_tests_step


def _read_only_source_sync_step() -> dict[str, object]:
    paths = [
        "tools/issue294/run_full68_refresh_experiment.py",
        "tools/issue294/run_full68_refresh_experiment_hosttests.py",
        "tools/issue294/run_full68_refresh_experiment_safeio.py",
        "tools/issue294/run_fixed_support_smoke.py",
        "tools/issue294/run_downstream_candidate_matrix.py",
        "tools/issue294/run_downstream_candidate_matrix_full68_host.py",
        "tools/issue294/run_full68_mmr_audit.py",
    ]
    hashes: dict[str, dict[str, str]] = {}
    for relative in paths:
        host_path = driver.PROJECT_ROOT / relative
        if not host_path.is_file():
            raise FileNotFoundError(host_path)
        host_hash = driver._sha256(host_path)
        container_hash = driver._docker_capture(
            ["exec", driver.CONTAINER, "sha256sum", f"/workspace/{relative}"]
        ).split()[0]
        if host_hash != container_hash:
            raise RuntimeError(
                f"Bind-visible source SHA mismatch for {relative}: "
                f"host={host_hash} container={container_hash}"
            )
        hashes[relative] = {"host": host_hash, "container": container_hash}
    return {
        "mode": "read_only_bind_verification",
        "verified_files": hashes,
    }


def _bind_visible_weight_step() -> dict[str, object]:
    source = driver._find_weight()
    target = (driver.PROJECT_ROOT / driver.WEIGHT_RELATIVE).resolve()
    if source != target:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    if not target.is_file():
        raise FileNotFoundError(target)
    if target.stat().st_size != driver.EXPECTED_WEIGHT_SIZE:
        raise RuntimeError(
            f"Real-ESRGAN weight size mismatch: {target.stat().st_size}"
        )
    host_hash = driver._sha256(target)
    if host_hash != driver.EXPECTED_WEIGHT_SHA256:
        raise RuntimeError(f"Host Real-ESRGAN weight SHA mismatch: {host_hash}")

    container_path = "/workspace/external/realesrgan/weights/RealESRGAN_x4plus.pth"
    container_hash = driver._docker_capture(
        ["exec", driver.CONTAINER, "sha256sum", container_path]
    ).split()[0]
    if container_hash != driver.EXPECTED_WEIGHT_SHA256:
        raise RuntimeError(
            "Bind-visible Real-ESRGAN weight SHA mismatch: "
            f"host={host_hash} container={container_hash}"
        )
    return {
        "mode": "host_write_bind_read_only_container",
        "host_weight": str(target),
        "size": target.stat().st_size,
        "sha256": host_hash,
    }


def main() -> int:
    driver._sync_source_step = _read_only_source_sync_step
    driver._weight_step = _bind_visible_weight_step
    driver._tests_step = _host_tests_step
    return driver.main()


if __name__ == "__main__":
    raise SystemExit(main())
