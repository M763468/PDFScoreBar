#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import cv2
import yaml

from crop_contract import crop_candidate, resolve_contracts

DEFAULT_VARIANTS = ["current_like", "wider_x", "square_context"]


def load_data(path: Path) -> Any:
    with path.open("r") as f:
        if path.suffix.lower() in {".yaml", ".yml"}:
            return yaml.safe_load(f)
        return json.load(f)


def load_cases(path: Path) -> list[dict[str, Any]]:
    data = load_data(path)
    if data is None:
        return []
    if isinstance(data, dict):
        data = data.get("cases", data.get("items", data))
    if not isinstance(data, list):
        raise ValueError(f"manifest must be a list or contain cases/items: {path}")
    return [dict(item) for item in data]


def image_path_for(entry: dict[str, Any], repo_root: Path) -> Path | None:
    for key in ("raw_image_path", "image_path"):
        value = entry.get(key)
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute():
            path = repo_root / path
        if path.exists():
            return path
    return None


def bbox_for(entry: dict[str, Any]) -> list[float] | None:
    bbox = entry.get("bbox") or entry.get("box")
    if not isinstance(bbox, list | tuple) or len(bbox) != 4:
        return None
    try:
        return [float(v) for v in bbox]
    except (TypeError, ValueError):
        return None


def safe_stem(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "case_id",
        "variant",
        "image_path",
        "bbox",
        "crop_path",
        "crop_box",
        "padding_applied",
        "padding",
        "contract",
        "notes",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def run_preview(
    *,
    manifest_path: Path,
    output_dir: Path,
    repo_root: Path,
    variants: list[str],
    max_crops: int,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = output_dir / "preview_crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    contracts = resolve_contracts(variants)
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for entry in load_cases(manifest_path):
        case_id = str(entry.get("case_id") or entry.get("id") or f"case_{len(rows):05d}")
        image_path = image_path_for(entry, repo_root)
        bbox = bbox_for(entry)
        if image_path is None or bbox is None:
            skipped.append({"case_id": case_id, "reason": "missing_image_or_bbox", "entry": entry})
            continue
        img = cv2.imread(str(image_path))
        if img is None:
            skipped.append({"case_id": case_id, "reason": "image_load_failed", "entry": entry})
            continue
        for contract in contracts:
            if len(rows) >= max_crops:
                break
            result = crop_candidate(img, bbox, contract)
            rel_path = Path("preview_crops") / f"{safe_stem(case_id)}__{contract.name}.png"
            cv2.imwrite(str(output_dir / rel_path), result.crop)
            rows.append(
                {
                    "case_id": case_id,
                    "variant": contract.name,
                    "image_path": str(image_path.relative_to(repo_root) if image_path.is_relative_to(repo_root) else image_path),
                    "bbox": [int(round(v)) for v in bbox],
                    "crop_path": str(rel_path),
                    "crop_box": list(result.crop_box),
                    "padding_applied": result.padding_applied,
                    "padding": list(result.padding),
                    "contract": contract.as_dict(),
                    "notes": entry.get("notes", ""),
                }
            )
        if len(rows) >= max_crops:
            break

    (output_dir / "preview_manifest.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    (output_dir / "skipped_cases.json").write_text(json.dumps(skipped, indent=2, ensure_ascii=False) + "\n")
    write_csv(output_dir / "preview_manifest.csv", rows)
    (output_dir / "summary.md").write_text(
        "\n".join(
            [
                "# Context-FOV preview summary",
                "",
                f"Input manifest: `{manifest_path}`",
                f"Output dir: `{output_dir}`",
                f"Variants: {', '.join(variants)}",
                f"Generated crops: {len(rows)}",
                f"Skipped cases: {len(skipped)}",
            ]
        )
        + "\n"
    )
    return len(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", default=Path("logs/issue206_context_fov_preview/latest"), type=Path)
    parser.add_argument("--repo-root", default=Path("."), type=Path)
    parser.add_argument("--variant", action="append", dest="variants")
    parser.add_argument("--max-crops", type=int, default=40)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    variants = args.variants or DEFAULT_VARIANTS
    generated = run_preview(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        repo_root=args.repo_root.resolve(),
        variants=variants,
        max_crops=args.max_crops,
    )
    print(f"Generated {generated} preview crops under {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
