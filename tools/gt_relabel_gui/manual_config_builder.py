#!/usr/bin/env python3
"""Build one-page config JSON for the manual GUI.

Usage:
  python3 tools/gt_relabel_gui/manual_config_builder.py \
    IMAGE NUMBERING NAME PAGE OUTPUT [MMR] [BARLINES]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) not in {6, 7, 8}:
        raise SystemExit(
            "usage: manual_config_builder.py IMAGE NUMBERING NAME PAGE OUTPUT [MMR] [BARLINES]"
        )
    image, numbering, name, page, output = sys.argv[1:6]
    mmr = sys.argv[6] if len(sys.argv) >= 7 else None
    barlines = sys.argv[7] if len(sys.argv) >= 8 else None
    page_config = {
        "name": name,
        "page": int(page),
        "image": image,
        "numbering": numbering,
    }
    if mmr:
        page_config["mmr"] = mmr
    if barlines:
        page_config["barlines"] = barlines
    payload = {"pages": [page_config]}
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
