"""Utilities for configuring ONNX Runtime sessions and providers via environment variables."""

from __future__ import annotations

import json
import os
from typing import Dict, Optional

try:
    import onnxruntime as ort
except ImportError:  # pragma: no cover
    ort = None  # type: ignore


def _parse_json(value: str) -> Optional[Dict[str, str]]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    result: Dict[str, str] = {}
    for key, val in data.items():
        if val is None:
            continue
        result[str(key)] = str(val)
    return result


def create_session_options_from_env(prefix: str) -> "ort.SessionOptions":
    """Create SessionOptions and apply common configuration entries from the environment.

    Supported variables (with *prefix*):
      - ``<prefix>ORT_LOG_SEVERITY_LEVEL``: integer 0–4.
      - ``<prefix>ORT_LOG_VERBOSITY_LEVEL``: integer 0–4.
      - ``<prefix>ORT_SESSION_CONFIG_JSON``: JSON object mapping config keys to values.
    """

    if ort is None:  # pragma: no cover
        raise RuntimeError("onnxruntime is not available")

    options = ort.SessionOptions()

    severity_env = os.environ.get(f"{prefix}ORT_LOG_SEVERITY_LEVEL")
    if severity_env:
        try:
            options.log_severity_level = int(severity_env)
        except ValueError:
            pass

    verbosity_env = os.environ.get(f"{prefix}ORT_LOG_VERBOSITY_LEVEL")
    if verbosity_env:
        try:
            options.log_verbosity_level = int(verbosity_env)
        except ValueError:
            pass

    config_env = os.environ.get(f"{prefix}ORT_SESSION_CONFIG_JSON")
    if config_env:
        config_pairs = _parse_json(config_env)
        if config_pairs:
            for key, value in config_pairs.items():
                try:
                    options.add_session_config_entry(key, value)
                except Exception:  # pragma: no cover - defensive, ORT may reject invalid keys
                    continue

    return options


def build_cuda_provider_options_from_env(
    prefix: str,
    base: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Merge CUDAExecutionProvider options from environment variables (all coerced to strings).

    Supported variables (with *prefix*):
      - ``<prefix>CUDA_ENABLE_CUDA_GRAPH``: ``0``/``1`` or boolean string.
      - ``<prefix>CUDA_DO_COPY_IN_DEFAULT_STREAM``: ``0``/``1``.
      - ``<prefix>CUDA_PROVIDER_OPTIONS_JSON``: JSON object merged verbatim.
    """

    options: Dict[str, str] = {}
    if base:
        options.update({key: str(value) for key, value in base.items()})

    json_env = os.environ.get(f"{prefix}CUDA_PROVIDER_OPTIONS_JSON")
    if json_env:
        parsed = _parse_json(json_env)
        if parsed:
            options.update(parsed)

    def _set_bool(flag: str, env_key: str) -> None:
        raw = os.environ.get(env_key)
        if raw is None:
            return
        truthy = {"1", "true", "True", "yes", "YES"}
        falsy = {"0", "false", "False", "no", "NO"}
        if raw in truthy:
            options[flag] = "1"
        elif raw in falsy:
            options[flag] = "0"

    _set_bool("enable_cuda_graph", f"{prefix}CUDA_ENABLE_CUDA_GRAPH")
    _set_bool("do_copy_in_default_stream", f"{prefix}CUDA_DO_COPY_IN_DEFAULT_STREAM")

    return options


__all__ = [
    "create_session_options_from_env",
    "build_cuda_provider_options_from_env",
]
