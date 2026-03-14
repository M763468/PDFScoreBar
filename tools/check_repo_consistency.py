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
INVENTORY_PATH = Path("docs/DOCUMENT_INVENTORY.md")
EXPERIMENTS_INVENTORY_PATH = Path("docs/EXPERIMENTS_INVENTORY.md")
TOOLS_INVENTORY_PATH = Path("docs/TOOLS_INVENTORY.md")

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
    matches = re.findall(r"`([^`\s]+)`", content)
    path_candidates = (p.strip(".,;:()") for p in matches if "(Container)" not in p)
    paths = {p for p in path_candidates if "/" in p or "." in p}
    return sorted(list(paths))


def parse_document_inventory(inventory_path: Path) -> dict[str, dict]:
    """Parses DOCUMENT_INVENTORY.md tables for file metadata."""
    if not inventory_path.exists():
        return {}

    inventory = {}
    current_category = "Unknown"
    content = inventory_path.read_text()

    # Simple state machine to parse markdown categories and tables
    lines = content.splitlines()
    updated_col_idx = -1

    for line in lines:
        # Detect Category from Headers
        cat_match = re.search(r"## \d+\. \[(.*?)\]", line)
        if cat_match:
            current_category = cat_match.group(1)
            updated_col_idx = -1  # Reset column index for new category table
            continue

        # Detect Table Header to find '最終更新' column
        if "|" in line and "最終更新" in line:
            header_parts = [p.strip() for p in line.split("|")]
            for idx, part in enumerate(header_parts):
                if "最終更新" in part:
                    updated_col_idx = idx
            continue

        # Parse Table Row
        if "|" in line and "`" in line and not line.strip().startswith("|-"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue

            # Extract path from backticks
            path_match = re.search(r"`([^`]+)`", line)
            if not path_match:
                continue

            path_str = path_match.group(1)
            # Handle root files (strip labels outside backticks)
            # path_str is already just the backticked content.

            # Extract Updated date from specific column
            updated_date = "Unknown"
            if updated_col_idx != -1 and updated_col_idx < len(parts):
                date_match = re.search(r"(\d{4}-\d{2}-\d{2})", parts[updated_col_idx])
                if date_match:
                    updated_date = date_match.group(1)

            inventory[path_str] = {"category": current_category, "stated_updated": updated_date}

    return inventory


def extract_dirs_from_inventory(inventory_path: Path) -> list[str]:
    """Extracts experiment directory names from EXPERIMENTS_INVENTORY.md."""
    if not inventory_path.exists():
        return []
    content = inventory_path.read_text()
    matches = re.findall(r"`([^`\s]+)`", content)
    dirs = {m for m in matches if "." not in m and "/" not in m}
    complex_dirs = {m for m in matches if "/" in m and "." not in m}
    return sorted(list(dirs.union(complex_dirs)))


def extract_paths_from_inventory(inventory_path: Path) -> list[str]:
    """Extracts backticked file-like strings from TOOLS_INVENTORY.md."""
    if not inventory_path.exists():
        return []
    content = inventory_path.read_text()
    matches = re.findall(r"`([^`\s]+)`", content)
    paths = {p.strip("/") for p in matches if "/" in p}
    return sorted(list(paths))


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

    print(f"\n--- 2. Document Inventory & Freshness Check (Threshold: {stale_days} days) ---")
    inventory = parse_document_inventory(INVENTORY_PATH)
    actual_docs = sorted(list(Path("docs").rglob("*.md")) + [Path("README.md"), Path("AGENTS.md")])
    now = datetime.now()

    for doc in actual_docs:
        doc_str = str(doc)
        inv_key = doc.name if doc.parent == Path(".") else doc_str
        info = inventory.get(inv_key) or inventory.get(doc_str)
        category = info["category"] if info else "Unclassified"

        ts = get_git_timestamp(doc)
        dt = datetime.fromtimestamp(ts) if ts > 0 else None
        git_date_str = str(dt.date()) if dt else "Unknown"
        status_tag = f"[{category}]"

        if not info and doc.parent == Path("docs") and doc.name != "DOCUMENT_INVENTORY.md":
            is_sub_covered = False
            for inv_path in inventory:
                if inv_path.endswith("/") and doc_str.startswith(inv_path):
                    is_sub_covered = True
                    break
            if not is_sub_covered:
                print(f"[ORPHAN]   {doc_str:40} (Not listed in DOCUMENT_INVENTORY.md)")

        if info and info["stated_updated"] != "Unknown" and git_date_str != "Unknown":
            if info["stated_updated"] < git_date_str:
                status_tag += " [DESYNC]"

        if dt:
            diff = now - dt
            is_stale = diff.days > stale_days
            if category == "Legacy":
                print(
                    f"[LEGACY]   {doc_str:40} (Last updated {diff.days} days ago: {git_date_str})"
                )
            elif is_stale:
                if category == "Current":
                    print(
                        f"[STALE!!]  {doc_str:40} {status_tag} (CRITICAL: Current doc is {diff.days} days old!)"
                    )
                else:
                    print(f"[STALE]    {doc_str:40} {status_tag} ({diff.days} days ago)")
            else:
                print(f"[FRESH]    {doc_str:40} {status_tag} ({git_date_str})")
        else:
            print(f"[UNKNOWN]  {doc_str:40} {status_tag} (No git history)")

    for inv_path in inventory:
        if not Path(inv_path).exists() and not (Path("docs") / inv_path).exists():
            if inv_path.endswith("/") and (
                Path(inv_path).is_dir() or (Path("docs") / inv_path).is_dir()
            ):
                continue
            print(f"[BROKEN]   {inv_path:40} (Listed in inventory but NOT found on disk)")
            all_ok = False

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

    print(f"\n--- 4. Experiments Inventory Check (from {EXPERIMENTS_INVENTORY_PATH}) ---")
    inventory_dirs = extract_dirs_from_inventory(EXPERIMENTS_INVENTORY_PATH)
    exp_dir = Path("experiments")
    actual_dirs = []
    if exp_dir.exists():
        for path in exp_dir.rglob("*"):
            if path.is_dir() and path != exp_dir:
                actual_dirs.append(str(path.relative_to(exp_dir)))
        for d in sorted(actual_dirs):
            if d.startswith("legacy"):
                continue
            if d not in inventory_dirs:
                print(f"[UNTRACKED] {d:40} (Not listed in {EXPERIMENTS_INVENTORY_PATH.name})")
            else:
                print(f"[TRACKED]   {d}")

    print(f"\n--- 5. Tools Inventory Coverage Check (from {TOOLS_INVENTORY_PATH}) ---")
    inventory_paths = extract_paths_from_inventory(TOOLS_INVENTORY_PATH)
    inventory_set = {str(Path(p)) for p in inventory_paths}
    missing_from_inventory = []
    tools_dir = Path("tools")
    if tools_dir.exists():
        for f in list(tools_dir.glob("*.py")) + list(tools_dir.glob("*.sh")):
            if f.name == "__init__.py":
                continue
            f_str = str(f)
            if f_str not in inventory_set:
                missing_from_inventory.append(f_str)
    if not missing_from_inventory:
        print(f"[OK] All scripts in tools/ root are documented in {TOOLS_INVENTORY_PATH.name}.")
    else:
        for f_str in sorted(missing_from_inventory):
            print(f"[MISSING]  {f_str:40} (Not in {TOOLS_INVENTORY_PATH.name})")

    print("\n--- 6. Orphan Asset Check (Untracked Mainline Candidates) ---")
    norm_tracked = {str(Path(p)) for p in paths}
    found_any_orphan = False
    for core_dir in CORE_DIRS:
        d = Path(core_dir)
        if not d.exists():
            continue
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
