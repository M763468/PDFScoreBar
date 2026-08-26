"""Compare canonical Torch with an isolated PyTorch preview stack for Issue #284.

The canonical container is read-only from this tool's perspective.  A temporary
container is created from the same production image, Torch/torchvision are upgraded
from the PyTorch preview index there, and both environments run the same capability
and full-page SR probe.  Results are written by the host runner and bundled into one
ZIP for sharing.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCORE = "Shostakovich-Sym5-Va"
PAGE = "page_013"
CANONICAL_CONTAINER = "pdfscore_pipeline_pytest_dev"
PRODUCTION_IMAGE = "pdfscore_pipeline_gpu"
PYTHON = "/opt/venv_pipeline/bin/python"
PROBE = "/workspace/tools/issue284/probe_torch_runtime_capabilities.py"


def _run(command: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _load_json_from_output(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        raise ValueError("Probe output does not contain JSON")
    payload = json.loads(text[start:])
    if not isinstance(payload, dict):
        raise ValueError("Probe payload must be an object")
    return payload


def _reference_image(candidate_summary: Path, project_root: Path) -> tuple[Path, str]:
    summary = json.loads(candidate_summary.read_text(encoding="utf-8"))
    score = next(item for item in summary["scores"] if item["score"] == SCORE)
    support_container = score["page_artifacts"][PAGE]["current_support"]
    prefix = "/workspace/"
    if not support_container.startswith(prefix):
        raise RuntimeError(f"Unexpected support path: {support_container}")
    support_host = project_root / support_container[len(prefix) :]
    support = json.loads(support_host.read_text(encoding="utf-8"))
    sr_container = str(support["sr_image"])
    if not sr_container.startswith(prefix):
        raise RuntimeError(f"Unexpected SR path: {sr_container}")
    sr_host = project_root / sr_container[len(prefix) :]
    if not sr_host.is_file():
        raise FileNotFoundError(sr_host)
    return sr_host, sr_container


def _probe_container(container: str, reference_container: str, timeout: float) -> tuple[dict[str, Any] | None, str, int]:
    command = [
        "docker",
        "exec",
        "-w",
        "/workspace",
        container,
        PYTHON,
        PROBE,
        "--reference-image",
        reference_container,
    ]
    result = _run(command, timeout=timeout)
    payload: dict[str, Any] | None = None
    try:
        payload = _load_json_from_output(result.stdout)
    except Exception:
        pass
    return payload, result.stdout, result.returncode


def _bundle(output: Path, paths: list[Path]) -> Path:
    bundle = output / "issue284_torch_version_compat_audit_bundle.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            if path.is_file():
                archive.write(path, arcname=path.name)
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--candidate-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--preview-index-url",
        default="https://download.pytorch.org/whl/test/cu130",
    )
    parser.add_argument("--probe-timeout-sec", type=float, default=180.0)
    parser.add_argument("--install-timeout-sec", type=float, default=900.0)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    if project_root != ROOT.resolve():
        raise RuntimeError(f"Runner must execute from canonical checkout {ROOT}, got {project_root}")
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output must be fresh and empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    candidate_summary = args.candidate_summary.resolve()
    reference_host, reference_container = _reference_image(candidate_summary, project_root)
    records: dict[str, Any] = {
        "schema_version": "issue284.torch_version_compat_audit.v1",
        "candidate_summary": str(candidate_summary),
        "reference_host": str(reference_host),
        "reference_container": reference_container,
        "preview_index_url": args.preview_index_url,
    }
    share_paths: list[Path] = []

    current_payload, current_log, current_rc = _probe_container(
        CANONICAL_CONTAINER,
        reference_container,
        args.probe_timeout_sec,
    )
    current_log_path = output / "current_probe.log"
    _write(current_log_path, current_log)
    share_paths.append(current_log_path)
    records["current"] = {
        "returncode": current_rc,
        "payload": current_payload,
    }

    temp_name = f"issue284_torch_preview_{os.getpid()}_{int(time.time())}"
    preview_log_path = output / "preview_install.log"
    preview_probe_log_path = output / "preview_probe.log"
    pip_check_path = output / "preview_pip_check.log"
    share_paths.extend([preview_log_path, preview_probe_log_path, pip_check_path])

    preview_record: dict[str, Any] = {"container": temp_name, "status": "started"}
    records["preview"] = preview_record
    try:
        start = _run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                temp_name,
                "--gpus",
                "all",
                "-v",
                f"{project_root}:/workspace",
                "-w",
                "/workspace",
                PRODUCTION_IMAGE,
                "sleep",
                "infinity",
            ],
            timeout=60,
        )
        preview_record["container_start_returncode"] = start.returncode
        preview_record["container_start_output"] = start.stdout.strip()
        if start.returncode != 0:
            preview_record["status"] = "container_start_failed"
        else:
            install_command = [
                "docker",
                "exec",
                temp_name,
                PYTHON,
                "-m",
                "pip",
                "install",
                "--pre",
                "--upgrade",
                "torch",
                "torchvision",
                "--index-url",
                args.preview_index_url,
            ]
            install = _run(install_command, timeout=args.install_timeout_sec)
            _write(preview_log_path, "$ " + shlex.join(install_command) + "\n" + install.stdout)
            preview_record["install_returncode"] = install.returncode
            if install.returncode != 0:
                preview_record["status"] = "install_failed"
            else:
                pip_check = _run(
                    ["docker", "exec", temp_name, PYTHON, "-m", "pip", "check"],
                    timeout=120,
                )
                _write(pip_check_path, pip_check.stdout)
                preview_record["pip_check_returncode"] = pip_check.returncode

                preview_payload, preview_log, preview_rc = _probe_container(
                    temp_name,
                    reference_container,
                    args.probe_timeout_sec,
                )
                _write(preview_probe_log_path, preview_log)
                preview_record.update(
                    {
                        "status": "completed" if preview_payload else "probe_failed",
                        "probe_returncode": preview_rc,
                        "payload": preview_payload,
                    }
                )
    except subprocess.TimeoutExpired as error:
        preview_record.update(
            {
                "status": "timeout",
                "timeout_command": error.cmd,
                "timeout_sec": error.timeout,
            }
        )
    finally:
        _run(["docker", "rm", "-f", temp_name], timeout=60)

    current_sr = ((current_payload or {}).get("sr_probe") or {})
    preview_payload = preview_record.get("payload") or {}
    preview_sr = (preview_payload.get("sr_probe") or {}) if isinstance(preview_payload, dict) else {}
    summary = {
        **records,
        "comparison": {
            "current_torch": ((current_payload or {}).get("torch") or {}).get("version"),
            "preview_torch": ((preview_payload or {}).get("torch") or {}).get("version")
            if isinstance(preview_payload, dict)
            else None,
            "current_wall_sec": current_sr.get("wall_sec"),
            "preview_wall_sec": preview_sr.get("wall_sec"),
            "current_array_equal": (current_sr.get("comparison") or {}).get("array_equal"),
            "preview_array_equal": (preview_sr.get("comparison") or {}).get("array_equal"),
            "preview_imports_ok": (
                all(item.get("ok") for item in (preview_payload.get("imports") or {}).values())
                if isinstance(preview_payload, dict) and preview_payload.get("imports")
                else None
            ),
        },
    }
    summary_path = output / "torch_version_compat_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    share_paths.append(summary_path)
    bundle = _bundle(output, share_paths)
    print(json.dumps(summary["comparison"], indent=2))
    print(f"share_bundle={bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
