"""Filesystem helpers for pipeline outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def write_manifest(path: Path, manifest: Dict[str, Any]) -> None:
    write_json(path, manifest)


def score_to_dict(score) -> dict:
    """Converts the Score object tree into a serializable dictionary."""
    data = {"pages": []}
    for p in score.pages:
        page_data = {
            "page_number": p.page_number,
            "width": p.width,
            "height": p.height,
            "systems": [],
        }
        for s in p.systems:
            sys_data = {
                "staves": [
                    {"bbox": [st.bbox.x1, st.bbox.y1, st.bbox.x2, st.bbox.y2]} for st in s.staves
                ],
                "measures": [],
            }
            for m in s.measures:
                m_data = {"number": m.number, "bbox": [m.bbox.x1, m.bbox.y1, m.bbox.x2, m.bbox.y2]}
                sys_data["measures"].append(m_data)
            page_data["systems"].append(sys_data)
        data["pages"].append(page_data)
    return data
