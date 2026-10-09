"""Shared configuration, run identifiers, subprocess logging and output I/O."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.measure_numbering.types import score_to_dict as score_to_dict


def load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise SystemExit("PyYAML is required. Install it in the current environment.") from exc
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("Config root must be a mapping.")
    return data


def write_yaml(path: Path, data: Dict[str, Any]) -> None:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise SystemExit("PyYAML is required. Install it in the current environment.") from exc
    path.write_text(yaml.dump(data, sort_keys=False))


def get_nested(config: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = config
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def build_probe_run_id_from_parts(score_name: str, stem: str) -> str:
    return f"eval2_{score_name}_{stem}"


def build_probe_run_id(image_path: Path, score_name: Optional[str] = None) -> str:
    """Build run id used by probe_scan/cnn_scoring page directories."""
    resolved_score_name = score_name or image_path.parent.name
    return build_probe_run_id_from_parts(resolved_score_name, image_path.stem)


def split_score_page_from_composite_stem(stem: str) -> tuple[str, str] | None:
    """Split composite stems like ``Score_page_001`` into score and page.

    Regular page stems such as ``page_001`` return ``None``. This keeps the
    default pipeline path unchanged while supporting composite benchmark image names.
    """
    marker = "_page_"
    idx = stem.rfind(marker)
    if idx < 0:
        return None
    score = stem[:idx]
    page = f"page_{stem[idx + len(marker) :]}"
    return score, page


logger = logging.getLogger(__name__)


def run_with_logging(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    log_level: int = logging.DEBUG,
) -> None:
    """
    Run a command and capture its stdout/stderr line-by-line,
    forwarding it to the Python logging system.
    """
    cmd_str = " ".join(cmd)
    logger.debug(f"Starting subprocess: {cmd_str}")

    with subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as p:
        if p.stdout:
            for line in p.stdout:
                line = line.rstrip("\n")
                logger.log(log_level, f"|> {line}")

        p.wait()
        if check and p.returncode != 0:
            logger.error(f"Subprocess failed with exit code {p.returncode}: {cmd_str}")
            raise subprocess.CalledProcessError(p.returncode, cmd)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def write_manifest(path: Path, manifest: Dict[str, Any]) -> None:
    write_json(path, manifest)
