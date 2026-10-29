"""Explicit trusted local compiler cache; fail closed, never migrate or delete entries."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
from contextlib import contextmanager
from pathlib import Path


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Cache symlink rejected: {path}")
        if path.is_file():
            result[str(path.relative_to(root))] = digest(path)
    return result


def _private(path):
    if path.is_symlink():
        raise ValueError(f"Cache symlink rejected: {path}")
    path.mkdir(mode=0o700, exist_ok=True)
    stat = path.stat()
    if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
        raise PermissionError(f"Cache must be private and owned by executing UID: {path}")


@contextmanager
def lease(root: Path, identity: dict):
    """Single writer for entire SR process; dirty leases require a new operator root.

    The root is trusted executable storage, provisioned by the operator. flock
    requires a local filesystem and must be shared by every participating writer.
    """
    if not root.is_absolute():
        raise ValueError("Cache root must be absolute")
    root = root.absolute()
    # Reject symlinked ancestors, including an operator root redirected after setup.
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("Cache ancestors must not be symlinks")
    if not root.is_dir():
        raise FileNotFoundError(f"Provision private cache root first: {root}")
    _private(root)
    identity = json.loads(
        json.dumps(dict(identity, uid=os.getuid(), gid=os.getgid(), schema=1), sort_keys=True)
    )
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    entry = root / key
    _private(entry)
    lock_path = entry / "lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        info = os.fstat(lock.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise PermissionError("Cache lock must be private and owned by executing UID")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = entry / "manifest.json"
        dirty = entry / "dirty"
        for name in ("manifest.json", "dirty", "inductor", "triton"):
            if (entry / name).is_symlink():
                raise ValueError("Cache symlink rejected")
        if dirty.exists():
            raise ValueError("Interrupted cache writer; select a new empty operator root")
        previous = None
        if manifest.exists():
            previous = json.loads(manifest.read_text())
            if previous["identity"] != identity:
                raise ValueError("Cache identity mismatch")
        elif set(p.name for p in entry.iterdir()) != {"lock"}:
            raise ValueError("Unattributed cache contents")
        for name in ("inductor", "triton"):
            _private(entry / name)
        before = {name: inventory(entry / name) for name in ("inductor", "triton")}
        if previous and previous["inventory"] != before:
            raise ValueError("Cache inventory integrity mismatch")
        provenance = {
            "identity": identity,
            "key": key,
            "entry": str(entry),
            "state": "verified-reuse" if previous else "empty",
            "hit_status": "not inferred from directory reuse",
            "before": before,
        }
        dirty.write_text(json.dumps(identity, sort_keys=True))
        keys = ("TORCHINDUCTOR_CACHE_DIR", "TRITON_CACHE_DIR")
        old = {key: os.environ.get(key) for key in keys}
        try:
            for key, name in zip(keys, ("inductor", "triton")):
                os.environ[key] = str(entry / name)
            yield provenance
            after = {name: inventory(entry / name) for name in ("inductor", "triton")}
            provenance["after"] = after
            temporary = entry / "manifest.pending"
            temporary.write_text(
                json.dumps({"identity": identity, "inventory": after}, sort_keys=True)
            )
            temporary.replace(manifest)
            dirty.unlink()
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def runtime_identity(detection):
    """Resolve actual runtime, source, weight and visible device before compilation."""
    if any(os.environ.get(key) for key in ("TORCHINDUCTOR_CACHE_DIR", "TRITON_CACHE_DIR")):
        raise ValueError("Managed cache conflicts with explicit compiler-cache environment")
    import importlib.metadata
    import subprocess

    import torch

    from src.common.model_artifacts import resolve_realesrgan_weight

    if torch._dynamo.config.suppress_errors:
        raise ValueError("Managed cache forbids compiler error suppression")
    image = os.environ.get("PDFSCORE_DOCKER_IMAGE_ID", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("Managed cache requires immutable launcher image provenance")
    from src.pipeline.detection.current_sr_runtime import normalize_compile_mode

    if normalize_compile_mode(detection.get("sr_compile_mode")) is None:
        raise ValueError("Managed SR cache requires an enabled compile mode")
    root = Path(__file__).resolve().parents[3]
    weights = resolve_realesrgan_weight("RealESRGAN_x4plus", project_root=root)
    device = torch.cuda.current_device()
    driver = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=uuid,driver_version", "--format=csv,noheader"], text=True
    ).strip()
    return {
        "image": image,
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "cudnn": torch.backends.cudnn.version(),
        "triton": importlib.metadata.version("triton"),
        "device": torch.cuda.get_device_name(device),
        "capability": list(torch.cuda.get_device_capability(device)),
        "visible_device": device,
        "driver_devices": driver,
        "weights_sha256": digest(weights),
        "detection": {k: v for k, v in detection.items() if k.startswith("sr_")},
        "source": {
            str(p.relative_to(root)): digest(p) for p in sorted((root / "src").rglob("*.py"))
        },
        "compiler_env": {
            k: v
            for k, v in sorted(os.environ.items())
            if (
                k.startswith(("TORCH", "TRITON", "CUDA", "CUBLAS"))
                or k in {"CC", "CXX", "CFLAGS", "CXXFLAGS", "LDFLAGS", "LD_LIBRARY_PATH"}
            )
            and k not in ("TORCHINDUCTOR_CACHE_DIR", "TRITON_CACHE_DIR")
        },
    }
