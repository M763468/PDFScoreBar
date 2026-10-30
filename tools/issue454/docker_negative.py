"""CPU-only Docker ownership, integrity, crash and cross-container flock checks."""

import json
import subprocess
import time
import uuid
from pathlib import Path

IMAGE = "sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a"


def main():
    source = Path.cwd()
    root = source / "logs/issue454/final/negative"
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    rows = []
    base = [
        "docker",
        "run",
        "--rm",
        "--mount",
        f"type=bind,source={source},target=/workspace,readonly",
        "--mount",
        f"type=bind,source={root},target=/negative",
        "-w",
        "/workspace",
        "-e",
        "PYTHONPATH=/workspace",
        "--entrypoint",
        "/opt/venv_pipeline/bin/python",
    ]
    prelude = (
        "from pathlib import Path; from src.pipeline.detection.sr_compiler_cache import lease; "
    )

    def check(name, uid, code, expected=0):
        command = base + ["--user", uid, IMAGE, "-c", prelude + code]
        result = subprocess.run(command, text=True, capture_output=True, timeout=60)
        rows.append(
            dict(
                name=name,
                command=command,
                expected=expected,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        )
        (root / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
        assert result.returncode == expected, rows[-1]

    check(
        "nonroot-owner",
        "1000:1001",
        "Path('/negative/nonroot').mkdir(mode=0o700);\nwith lease(Path('/negative/nonroot'), {}) as p:\n print(p['state'])",
    )
    check("mixed-uid-rejected", "0:0", "\nwith lease(Path('/negative/nonroot'), {}): pass", 1)
    check(
        "root-owner",
        "0:0",
        "Path('/negative/root').mkdir(mode=0o700);\nwith lease(Path('/negative/root'), {}) as p:\n print(p['state'])",
    )
    check(
        "corrupt-inventory-rejected",
        "1000:1001",
        "p=next(Path('/negative/nonroot').glob('*/manifest.json')); p.write_text('{}');\nwith lease(Path('/negative/nonroot'), {}): pass",
        1,
    )
    check(
        "interrupted-writer",
        "1000:1001",
        "import os; Path('/negative/crash').mkdir(mode=0o700);\nwith lease(Path('/negative/crash'), {}): os._exit(7)",
        7,
    )
    check("dirty-cache-rejected", "1000:1001", "\nwith lease(Path('/negative/crash'), {}): pass", 1)
    concurrent = root / "concurrent"
    concurrent.mkdir(mode=0o700)
    ready, release = root / "ready", root / "release"
    code = (
        prelude
        + "import time;\nwith lease(Path('/negative/concurrent'), {}):\n Path('/negative/ready').touch()\n for i in range(450):\n  if Path('/negative/release').exists(): break\n  time.sleep(.1)\n else: raise TimeoutError('contender not released')"
    )
    command = base + [
        "--user",
        "1000:1001",
        "--name",
        "pdfscore-issue454-lock-" + uuid.uuid4().hex[:8],
        IMAGE,
        "-c",
        code,
    ]
    writer = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 30
        while not ready.exists():
            if writer.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("writer did not acquire lock")
            time.sleep(0.1)
        check(
            "cross-container-busy",
            "1000:1001",
            "\nwith lease(Path('/negative/concurrent'), {}): pass",
            1,
        )
    finally:
        release.touch()
        stdout, stderr = writer.communicate(timeout=60)
        rows.append(
            dict(
                name="exclusive-writer",
                command=command,
                exit_code=writer.returncode,
                stdout=stdout,
                stderr=stderr,
            )
        )
        (root / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
    assert writer.returncode == 0
    assert "BlockingIOError" in rows[-2]["stderr"]
    check(
        "reuse-after-release",
        "1000:1001",
        "\nwith lease(Path('/negative/concurrent'), {}) as p: print(p['state'])",
    )
    print("Docker negative checks passed; existing caches untouched")


if __name__ == "__main__":
    main()
