#!/usr/bin/env python3
import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

# --- Configuration ---
MANIFEST_PATH = Path("docs/MANIFEST.md")
INVENTORY_PATH = Path("docs/EXPERIMENTS_INVENTORY.md")
# Scan these directories for untracked (orphan) files
CORE_DIRS = ["configs", "src/pipeline", "src/measure_numbering", "tools"]


def get_git_timestamp(path: Path) -> int:
    """Gets the unix timestamp of the last commit for a path."""
    try:
        cmd = ["git", "log", "-n", "1", "--format=%ct", "--", str(path)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return int(result.stdout.strip()) if result.stdout.strip() else 0
    except (subprocess.CalledProcessError, ValueError):
        return 0


def extract_paths_from_manifest(manifest_path: Path) -> list[str]:
    """Extracts backticked file-like strings from MANIFEST.md."""
    if not manifest_path.exists():
        return []
    content = manifest_path.read_text()
    # A simpler regex to find any non-whitespace string in backticks, then filter.
    # This is more robust than a complex regex trying to validate paths.
    matches = re.findall(r"`([^`\s]+)`", content)

    # Filter out container placeholders and clean paths.
    path_candidates = (p.strip(".,;:()") for p in matches if "(Container)" not in p)

    # Heuristic to filter out non-path-like strings (e.g. single words without extension).
    paths = {p for p in path_candidates if "/" in p or "." in p}

    return sorted(list(paths))


def extract_dirs_from_inventory(inventory_path: Path) -> list[str]:
    """Extracts experiment directory names from EXPERIMENTS_INVENTORY.md."""
    if not inventory_path.exists():
        return []
    content = inventory_path.read_text()
    # Find `name` in backticks
    matches = re.findall(r"`([^`\s]+)`", content)
    # Filter for directory names (not ending with extension)
    dirs = {m for m in matches if "." not in m and "/" not in m}
    # Also handle paths like models/omr_dln
    complex_dirs = {m for m in matches if "/" in m and "." not in m}
    return sorted(list(dirs.union(complex_dirs)))


def check_consistency(stale_days: int):
    all_ok = True

    print(f"--- 1. Asset Existence Check (from {MANIFEST_PATH}) ---")
    paths = extract_paths_from_manifest(MANIFEST_PATH)
    if not paths:
        print(f"[WARN] No paths extracted from {MANIFEST_PATH} or file missing.")

    for p_str in paths:
        p = Path(p_str)
        is_ignored = any(part in ["datasets", "logs", "external", "models"] for part in p.parts)

        if p.exists():
            print(f"[OK]       {p_str}")
        else:
            if is_ignored:
                print(f"[WARN]     {p_str} (Missing, but it is gitignored/external)")
            else:
                print(f"[CRITICAL] {p_str} (Missing and NOT ignored!)")
                all_ok = False

    print(f"\n--- 2. Document Freshness Check (Threshold: {stale_days} days) ---")
    docs = sorted(list(Path("docs").glob("*.md")) + [Path("README.md"), Path("AGENTS.md")])
    now = datetime.now()
    for doc in docs:
        ts = get_git_timestamp(doc)
        if ts == 0:
            print(f"[UNKNOWN]  {doc} (No git history)")
            continue
        dt = datetime.fromtimestamp(ts)
        diff = now - dt
        if diff.days > stale_days:
            print(f"[STALE]    {doc} (Last updated {diff.days} days ago: {dt.date()})")
        else:
            print(f"[FRESH]    {doc} (Last updated {diff.days} days ago: {dt.date()})")

    print("\n--- 3. Configuration Integrity Check ---")
    key_configs = [Path("configs/evaluation2_e2e_verification_full.yaml")]
    for cfg in key_configs:
        if not cfg.exists():
            print(f"[MISSING]  {cfg}")
            continue
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                yaml.safe_load(f)
            print(f"[VALID]    {cfg}")
        except Exception as e:
            print(f"[INVALID]  {cfg}: {e}")
            all_ok = False

    print(f"\n--- 4. Experiments Inventory Check (from {INVENTORY_PATH}) ---")
    inventory_dirs = extract_dirs_from_inventory(INVENTORY_PATH)
    exp_dir = Path("experiments")
    if exp_dir.exists():
        actual_dirs = [d.name for d in exp_dir.iterdir() if d.is_dir()]
        # Also handle sub-subdirs like models/omr_dln
        for d in actual_dirs:
            p = exp_dir / d
            for sub in p.iterdir():
                if sub.is_dir():
                    actual_dirs.append(f"{d}/{sub.name}")

        for d in sorted(actual_dirs):
            if d in ["legacy", "legacy/archive", "legacy/scripts", "legacy/tmp_archive", "legacy/tools_archive", "legacy/investigation_20260102"]:
                # Ignore legacy nested dirs if needed, but let's check top-level legacy
                continue
            if d not in inventory_dirs:
                print(f"[UNTRACKED] {d:40} (Not listed in {INVENTORY_PATH.name})")
            else:
                print(f"[TRACKED]   {d}")

    print("\n--- 5. Orphan Asset Check (Untracked Mainline Candidates) ---")
    norm_tracked = {str(Path(p)) for p in paths}
    found_any_orphan = False

    for core_dir in CORE_DIRS:
        d = Path(core_dir)
        if not d.exists():
            continue

        # Collect all files recursively
        for f in d.rglob("*"):
            if f.is_dir() or "__pycache__" in str(f) or f.name == "__init__.py":
                continue

            f_str = str(f)
            if f_str not in norm_tracked:
                ts = get_git_timestamp(f)
                dt = datetime.fromtimestamp(ts).date() if ts else "No history"
                print(f"[UNTRACKED] {f_str:40} (Last updated: {dt})")
                found_any_orphan = True

    if not found_any_orphan:
        print("[OK] All assets in core directories are tracked in MANIFEST.md.")
    else:
        print(
            "\nNote: [UNTRACKED] files are either legacy, experimental, or missing in MANIFEST.md."
        )

    return all_ok


def main():
    parser = argparse.ArgumentParser(description="Check repository consistency.")
    parser.add_argument(
        "--stale-days", type=int, default=30, help="Days until a document is considered stale."
    )
    args = parser.parse_args()

    success = check_consistency(args.stale_days)
    if not success:
        print("\n[RESULT] Consistency check FAILED. Please fix the critical issues above.")
        sys.exit(1)
    else:
        print("\n[RESULT] Consistency check PASSED (Critical issues only).")


if __name__ == "__main__":
    main()
