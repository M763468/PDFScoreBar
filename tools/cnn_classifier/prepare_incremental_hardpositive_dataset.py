import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Dict

import yaml


def load_config_file(config_path: Path) -> Dict:
    with config_path.open("r") as f:
        if config_path.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(f)
        else:
            data = json.load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping/dict: {config_path}")
    return data


def _copytree_hardlink(src: Path, dst: Path):
    shutil.copytree(src, dst, copy_function=os.link, dirs_exist_ok=True)


def _copytree_copy(src: Path, dst: Path):
    shutil.copytree(src, dst, dirs_exist_ok=True)


def main():
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", type=Path, help="YAML/JSON config path")
    pre_args, _ = pre_parser.parse_known_args()

    parser = argparse.ArgumentParser(parents=[pre_parser])
    parser.add_argument("--baseline-dataset-root")
    parser.add_argument("--hard-positive-dir")
    parser.add_argument("--output-dataset-root")
    parser.add_argument("--split", default="train")
    parser.add_argument("--copy-mode", choices=["hardlink", "copy"], default="hardlink")
    parser.add_argument("--name-prefix", default="hcfn")
    parser.add_argument("--dedup", action="store_true")
    parser.add_argument(
        "--copy-subdirs",
        default="splits",
        help="Comma-separated subdirs to copy from baseline root (default: splits)",
    )

    if pre_args.config:
        cfg = load_config_file(pre_args.config)
        parser.set_defaults(**{k.replace("-", "_"): v for k, v in cfg.items() if k != "config"})

    args = parser.parse_args()
    missing = [
        k
        for k in ("baseline_dataset_root", "hard_positive_dir", "output_dataset_root")
        if not getattr(args, k, None)
    ]
    if missing:
        parser.error(
            "Missing required arguments (provide via CLI or --config): "
            + ", ".join(f"--{k.replace('_', '-')}" for k in missing)
        )

    baseline_root = Path(args.baseline_dataset_root)
    hard_positive_dir = Path(args.hard_positive_dir)
    output_root = Path(args.output_dataset_root)
    if not baseline_root.exists():
        raise FileNotFoundError(f"Baseline dataset root not found: {baseline_root}")
    if not hard_positive_dir.exists():
        raise FileNotFoundError(f"Hard positive dir not found: {hard_positive_dir}")

    print(f"Preparing incremental dataset: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    subdirs = [s.strip() for s in str(args.copy_subdirs).split(",") if s.strip()]
    for sub in subdirs:
        src_sub = baseline_root / sub
        if not src_sub.exists():
            continue
        dst_sub = output_root / sub
        if args.copy_mode == "hardlink":
            _copytree_hardlink(src_sub, dst_sub)
        else:
            _copytree_copy(src_sub, dst_sub)

    target_tp_dir = output_root / "splits" / args.split / "tp"
    target_tp_dir.mkdir(parents=True, exist_ok=True)

    added = 0
    skipped = 0
    hard_positive_files = sorted(hard_positive_dir.glob("*.png"))
    for idx, src in enumerate(hard_positive_files):
        stem = src.stem
        name = f"{args.name_prefix}_{idx:04d}_{stem}.png"
        dst = target_tp_dir / name
        if dst.exists():
            skipped += 1
            continue
        if args.dedup:
            duplicate = next(target_tp_dir.glob(f"*{stem}.png"), None)
            if duplicate is not None:
                skipped += 1
                continue
        shutil.copy2(src, dst)
        added += 1

    summary = {
        "baseline_dataset_root": str(baseline_root),
        "hard_positive_dir": str(hard_positive_dir),
        "output_dataset_root": str(output_root),
        "split": args.split,
        "copy_mode": args.copy_mode,
        "hard_positive_files": len(hard_positive_files),
        "added_to_split_tp": added,
        "skipped": skipped,
    }
    with (output_root / "incremental_hardpositive_summary.json").open("w") as f:
        json.dump(summary, f, indent=2)

    print(f"Done. hard_positive_files={len(hard_positive_files)} added={added} skipped={skipped}")


if __name__ == "__main__":
    main()
