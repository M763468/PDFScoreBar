"""Check local Markdown links and fragments using only the Python standard library.

Every tracked Markdown file is scanned. A relative link must point to an existing file or
directory, and a ``#fragment`` pointing into a Markdown file must match a heading slug
(GitHub style) or an explicit ``<a id="...">`` / ``<a name="...">`` anchor. External URLs,
links inside fenced code blocks and inline code spans are ignored. This checks link
integrity only; it does not judge whether the linked content is current or correct.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)+?\1")
LINK = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*(<[^>]*>|[^\s)]+)(?:\s+\"[^\"]*\")?\s*\)")
HEADING = re.compile(r"^ {0,3}#{1,6}\s+(.*?)\s*#*\s*$")
ANCHOR = re.compile(r"<a\s+(?:id|name)=\"([^\"]+)\"", re.IGNORECASE)
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:|^//")


def prose_lines(text: str) -> list[str]:
    """Return lines outside fenced code blocks."""
    lines: list[str] = []
    fence = None
    for line in text.splitlines():
        match = FENCE.match(line)
        if match:
            marker, rest = match.groups()
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence) and not rest.strip():
                fence = None
            continue
        if fence is None:
            lines.append(line)
    return lines


def slugify(heading: str) -> str:
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = re.sub(r"<[^>]+>", "", text).replace("`", "").strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(text: str) -> set[str]:
    found = set(ANCHOR.findall(text))
    seen: dict[str, int] = {}
    for line in prose_lines(text):
        match = HEADING.match(line)
        if not match:
            continue
        slug = slugify(match.group(1))
        count = seen.get(slug, 0)
        found.add(slug if count == 0 else f"{slug}-{count}")
        seen[slug] = count + 1
    return found


def links(text: str) -> list[str]:
    targets: list[str] = []
    for line in prose_lines(text):
        for target in LINK.findall(INLINE_CODE.sub("", line)):
            targets.append(target[1:-1] if target.startswith("<") else target)
    return targets


def check(root: Path, files: list[Path]) -> list[str]:
    errors: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}
    root = root.resolve()
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for target in links(text):
            if SCHEME.match(target):
                continue
            raw_path, _, fragment = target.partition("#")
            destination = (path.parent / unquote(raw_path)).resolve() if raw_path else path
            label = f"{path.relative_to(root)}: {target}"
            if not destination.exists():
                errors.append(f"missing target: {label}")
                continue
            if fragment and destination.suffix.lower() == ".md":
                if destination not in anchor_cache:
                    anchor_cache[destination] = anchors(
                        destination.read_text(encoding="utf-8", errors="replace")
                    )
                wanted = unquote(fragment)
                known = anchor_cache[destination]
                if wanted not in known and wanted.lower() not in known:
                    errors.append(f"missing fragment: {label}")
    return errors


def tracked_markdown(root: Path) -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    return [root / name for name in output.split("\0") if name and (root / name).is_file()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    files = tracked_markdown(args.root)
    errors = check(args.root, files)
    for error in errors:
        print(error)
    print(f"Checked local links in {len(files)} Markdown file(s); {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
