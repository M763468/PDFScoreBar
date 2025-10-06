#!/usr/bin/env python3
"""CLI helper to generate vertical closing blends for one or more images."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.preprocessing import vertical_closing_blend_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="Input image files")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory to store processed images",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="_vclose",
        help="Suffix appended before the file extension",
    )
    parser.add_argument(
        "--kernel-height",
        type=int,
        default=7,
        help="Height of the vertical structuring element",
    )
    parser.add_argument(
        "--closing-blend",
        type=float,
        default=0.4,
        help="Blend weight for the closed image (0..1)",
    )
    return parser.parse_args()


def resolve_output_path(output_dir: Path, input_path: Path, suffix: str) -> Path:
    stem = input_path.stem + suffix
    return output_dir / f"{stem}{input_path.suffix}"


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for raw_input in args.inputs:
        input_path = Path(raw_input)
        if not input_path.exists():
            raise FileNotFoundError(f"Input not found: {input_path}")
        output_path = resolve_output_path(args.output_dir, input_path, args.suffix)
        vertical_closing_blend_file(
            input_path,
            output_path,
            kernel_height=args.kernel_height,
            closing_blend=args.closing_blend,
        )
        print(f"Saved {output_path}")


if __name__ == "__main__":
    main()

