#!/usr/bin/env python3
"""Generate proxy-free context crop previews for CNN candidate boxes.

This is an issue #206 design/experiment helper. It does not train, retrain,
score, or modify tracked data. It reads a manifest with raw image paths and
bbox entries, then writes small crop previews plus a preview manifest under a
log/output directory.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import cv2
import yaml

from tools.cnn_classifier.crop_contract import crop_candidate, resolve_contracts


DEFAULT_VARIANTS = ["current_like", "wider_x", "square_context"]


def load_mapping(path: Path) -> Any:
    with path.open("r") as f:
        if path.suffix.lower() in {".yaml", ".yml"}:
            return yaml.safe_load(f)
        return json.load(f)


def load_manifest(path: Path) -> list[dict[str, Any]]:
    data = load_mapping(path)
    if data is None:
        return []
    if isinstance(data, dict):
        if "cases" in data:
            data = data["cases"]
        elif "items" in data:
            data = data["items"]
    if not isinstance(data, list):
        raise ValueError(f"manifest must be a list or a mapping with cases/items: {path}")
    return [dict(item) for item in data]


def resolve_image_path(entry: dict[str, Any], repo_root: Path) -> Path | None:
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


def resolve_bbox(entry: dict[str, Any]) -> list[float] | None:
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
    fieldnames = [
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
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def run_preview(
    *,
    manifest_path: Path,
    output_dir: Path,
    repo_root: Path,
    variants: list[str],
    max_crops: int,
) -> int:
    cases = load_manifest(manifest_path)
    contracts = resolve_contracts(variants)
    crops_dir = output_dir / "preview_crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    preview_rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for entry in cases:
        case_id = str(entry.get("case_id") or entry.get("id") or f"case_{len(preview_rows):05d}")
        image_path = resolve_image_path(entry, repo_root)
        bbox = resolve_bbox(entry)
        if image_path is None or bbox is None:
            skipped.append(
                {
                    "case_id": case_id,
                    "reason": "missing_raw_image" if image_path is None else "missing_bbox",
                    "entry": entry,
                }
            )
            continue

        img = cv2.imread(str(image_path))
        if img is None:
            skipped.append({"case_id": case_id, "reason": "image_load_failed", "entry": entry})
            continue

        for contract in contracts:
            if len(preview_rows) >= max_crops:
                break
            result = crop_candidate(img, bbox, contract)
            rel_crop_path = Path("preview_crops") / f"{safe_stem(case_id)}__{contract.name}.png"
            crop_path = output_dir / rel_crop_path
            cv2.imwrite(str(crop_path), result.crop)
            preview_rows.append(
                {
                    "case_id": case_id,
                    "variant": contract.name,
                    "image_path": str(image_path.relative_to(repo_root) if image_path.is_relative_to(repo_root) else image_path),
                    "bbox": [int(round(v)) for v in bbox],
                    "crop_path": str(rel_crop_path),
                    "crop_box": list(result.crop_box),
                    "padding_applied": result.padding_applied,
                    "padding": list(result.padding),
                    "contract": contract.as_dict(),
                    "notes": entry.get("notes", ""),
                }
            )
        if len(preview_rows) >= max_crops:
            break

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_out = output_dir / "preview_manifest.json"
    with manifest_out.open("w") as f:
        json.dump(preview_rows, f, indent=2, ensure_ascii=False)
    with (output_dir / "skipped_cases.json").open("w") as f:
        json.dump(skipped, f, indent=2, ensure_ascii=False)
    write_csv(output_dir / "preview_manifest.csv", preview_rows)

    summary = [
        "# Context-FOV preview summary",
        "",
        f"Input manifest: `{manifest_path}`",
        f"Output dir: `{output_dir}`",
        f"Variants: {', '.join(variants)}",
        f"Generated crops: {len(preview_rows)}",
        f"Skipped cases: {len(skipped)}",
        "",
        "This helper generates crop previews only. It does not train, retrain, score, or modify tracked files.",
    ]
    (output_dir / "summary.md").write_text("\n".join(summary) + "\n")
    return len(preview_rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="JSON/YAML case manifest")
    parser.add_argument(
        "--output-dir",
        default=Path("logs/issue206_context_fov_preview/latest"),
        type=Path,
        help="Output directory for preview crops and manifests",
    )
    parser.add_argument("--repo-root", default=Path("."), type=Path)
    parser.add_argument("--variant", action="append", dest="variants", help="Crop variant name")
    parser.add_argument("--max-crops", type=int, default=40)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
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
