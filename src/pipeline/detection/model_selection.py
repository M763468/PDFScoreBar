"""Model paths for exploration, fixed comparisons, and production selection.

Exploration observes current bytes; comparison checks caller-recorded hashes;
production keeps the selected artifact manifests authoritative.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Mapping

from src.common.model_artifacts import (
    get_model_cache_root,
    resolve_model_artifact,
    sha256_file,
    verify_model_artifact,
)


def model_validation_mode(detection: Mapping[str, Any]) -> str:
    mode = detection.get("model_validation", "production")
    if mode not in ("production", "exploration", "comparison"):
        raise ValueError(f"Unknown detection.model_validation: {mode!r}")
    if mode != "production":
        from .config import resolve_detector_route

        resolve_detector_route(detection)
        for key in ("cnn_device",):
            if detection.get(key, "cuda") not in ("cpu", "cuda"):
                raise ValueError(f"Unsupported detection.{key}; use cpu or cuda")
    return str(mode)


def _file(value: Any, root: Path) -> Path:
    if not isinstance(value, (str, Path)) or not str(value):
        raise ValueError("An explicit model path is required")
    path = Path(value).expanduser()
    path = path if path.is_absolute() else root / path
    if not path.is_file():
        raise FileNotFoundError(f"Model file not found: {path}")
    return path


def _comparison_check(path: Path, detection: Mapping[str, Any], role: str) -> Path:
    if model_validation_mode(detection) == "comparison":
        hashes = detection.get("model_sha256") or {}
        expected = hashes.get(role) if isinstance(hashes, Mapping) else None
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError(f"Comparison requires detection.model_sha256.{role}")
        verify_model_artifact(path, expected_sha256=expected)
    return path


def resolve_cnn_candidate(detection: Mapping[str, Any], root: Path) -> Path:
    if model_validation_mode(detection) == "production":
        raise ValueError("Production CNN selection requires its artifact manifest")
    if detection.get("cnn_model_path"):
        # An explicit checkpoint takes precedence over the copied production config.
        path = _file(detection["cnn_model_path"], root)
    elif detection.get("cnn_model_manifest"):
        manifest = _file(detection["cnn_model_manifest"], root)
        path = resolve_model_artifact(manifest, project_root=root)
    else:
        raise ValueError("Configure detection.cnn_model_path or cnn_model_manifest")
    return _comparison_check(path, detection, "cnn")


def model_observation(detection: Mapping[str, Any], root: Path) -> dict[str, Any]:
    """Observe selected files without requiring exploration users to register them."""
    paths = {
        "cnn": resolve_cnn_candidate(detection, root),
    }
    return {role: {"path": str(path), "sha256": sha256_file(path)} for role, path in paths.items()}


def main() -> int:
    # Internal host-launcher helper, not a separate experiment runner.
    import yaml

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--role", choices=("mode", "cnn", "cache"), required=True)
    parser.add_argument("--container-path", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    detection = (yaml.safe_load(args.config.read_text()) or {}).get("detection") or {}
    mode = model_validation_mode(detection)
    if args.role == "mode":
        print(mode)
    elif args.role == "cache":
        print(get_model_cache_root(project_root=root))
    else:
        path = resolve_cnn_candidate(detection, root)
        if args.container_path:
            # Preserve explicit absolute config paths; map checkout-relative ones.
            value = detection.get("cnn_model_path")
            if value and Path(value).expanduser().is_absolute():
                path = Path(value).expanduser()
            else:
                path = (
                    Path("/workspace") / path.relative_to(root)
                    if path.is_relative_to(root)
                    else path
                )
        print(path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc
