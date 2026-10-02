"""Runtime output directories, timestamps and HOMR logging."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import homr.simple_logging

logger = logging.getLogger("homr_evaluator")
JST = ZoneInfo("Asia/Tokyo")


def _redirect_eprint_to_logger(*args, **kwargs) -> None:
    logger.info(" ".join(map(str, args)))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def current_jst() -> datetime:
    return datetime.now(JST)


def timestamp_jst() -> str:
    return current_jst().strftime("%Y-%m-%dT%H:%M:%S") + "JST"


homr.simple_logging.eprint = _redirect_eprint_to_logger
eprint = _redirect_eprint_to_logger
