"""Check translation references and provenance using only the Python standard library."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

RECORD = re.compile(r"<!-- translation:\s*(.*?)\s*-->", re.DOTALL)
LINK = re.compile(r"\[[^\]]*\]\(([^\s)]+)\)")
STATES = {"draft", "reviewed", "update required"}


def prose(path: Path) -> str:
    """Exclude fenced examples so sample metadata is not treated as a real record."""
    lines = []
    fence = None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if match:
            marker, rest = match.groups()
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence) and not rest.strip():
                fence = None
            continue
        if fence is None:
            lines.append(line)
    return "\n".join(lines)


def local_links(path: Path) -> set[Path]:
    return {
        (path.parent / target.split("#", 1)[0]).resolve()
        for target in LINK.findall(prose(path))
        if ":" not in target and not target.startswith("#")
    }


def check(root: Path) -> tuple[list[str], list[str]]:
    """Return errors and provenance observations; observations never certify meaning."""
    root = root.resolve()
    errors, observations = [], []
    candidates = set()
    for pattern in ("*.ja.md", "*.en.md"):
        candidates.update(root.glob(pattern))
        candidates.update((root / "docs").rglob(pattern))
    for translated in sorted(candidates):
        name = translated.relative_to(root).as_posix()
        try:
            records = RECORD.findall(prose(translated))
            if len(records) != 1:
                raise ValueError("expected exactly one translation metadata record")
            record = json.loads(records[0])
            if not isinstance(record, dict) or set(record) != {"original", "source", "state"}:
                raise ValueError("metadata requires original, source and state only")
            if not isinstance(record["state"], str) or record["state"] not in STATES:
                raise ValueError("invalid translation state")
            original_name = record["original"]
            if (
                not isinstance(original_name, str)
                or not original_name
                or Path(original_name).is_absolute()
            ):
                raise ValueError("original must be a relative file path")
            original = (translated.parent / original_name).resolve()
            if (
                not original.is_relative_to(root)
                or original == translated.resolve()
                or not original.is_file()
            ):
                raise ValueError(
                    "original must be an existing different file inside the repository"
                )
            if original not in local_links(translated) or translated.resolve() not in local_links(
                original
            ):
                raise ValueError("missing reciprocal Markdown language links")
            source = record["source"]
            if not isinstance(source, dict) or len(source) != 1:
                raise ValueError("source must contain exactly one sha256 or commit identity")
            if "sha256" in source:
                digest = source["sha256"]
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ValueError("same PR source requires a lowercase SHA-256")
                if hashlib.sha256(original.read_bytes()).hexdigest() != digest:
                    raise ValueError("same PR original SHA-256 mismatch")
                observations.append(
                    f"{name}: original bytes match recorded SHA-256; state={record['state']}"
                )
            elif "commit" in source:
                commit = source["commit"]
                if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
                    raise ValueError("commit source requires a full lowercase 40-hex Git identity")
                relative = original.relative_to(root).as_posix()
                result = subprocess.run(
                    ["git", "-C", str(root), "show", f"{commit}:{relative}"],
                    capture_output=True,
                    check=False,
                )
                if result.returncode:
                    observations.append(
                        f"UNKNOWN {name}: source commit/path unavailable; synchronization not determined"
                    )
                elif result.stdout == original.read_bytes():
                    observations.append(
                        f"{name}: original bytes unchanged since source commit; state={record['state']}"
                    )
                elif record["state"] != "update required":
                    raise ValueError(
                        "original changed since source commit; mark translation 'update required'"
                    )
                else:
                    observations.append(
                        f"STALE {name}: original changed; explicitly marked update required"
                    )
            else:
                raise ValueError("unknown source identity type")
        except (ValueError, OSError) as exc:
            errors.append(f"{name}: {exc}")
    observations.append(
        f"Checked {len(candidates)} translation file(s); semantic fidelity and language quality require review"
    )
    return errors, observations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    errors, observations = check(args.root)
    for message in observations:
        print(message)
    for message in errors:
        print(f"ERROR {message}")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
