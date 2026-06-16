#!/usr/bin/env python3
"""Build one-page config JSON for the manual GUI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--numbering", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--page", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = {
        "pages": [
            {
                "name": args.name,
                "page": args.page,
                "image": str(args.image),
                "numbering": str(args.numbering),
            }
        ]
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
