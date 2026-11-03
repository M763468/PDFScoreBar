"""Check local Markdown links and fragments using only the Python standard library.

Every tracked Markdown file is scanned. A relative link must point to an existing file or
directory, and a ``#fragment`` pointing into a Markdown file must match a heading slug
(GitHub style) or an explicit ``<a id="...">`` / ``<a name="...">`` anchor. External URLs,
links inside fenced code blocks and inline code spans are ignored. This checks link
integrity only; it does not judge whether the linked content is current or correct.

Parsing approximates GitHub-flavored Markdown (inline and reference links, escapes,
fenced/indented code, ATX/Setext headings) without a Markdown dependency. If an unusual
construct is misread, add an explicit ``<a id="...">`` anchor or extend the fixtures in
``tests/test_doc_links.py`` rather than disabling the check.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
INLINE_CODE = re.compile(r"(`+)(?:(?!\1)(?!\n[ \t]*\n).)+?\1", re.DOTALL)
SETEXT = re.compile(r"^ {0,3}(?:=+|-+)\s*$")
HEADING = re.compile(r"^ {0,3}#{1,6}\s+(.*?)\s*#*\s*$")
ANCHOR = re.compile(r"<a\s+(?:id|name)=\"([^\"]+)\"", re.IGNORECASE)
REFERENCE = re.compile(r"^ {0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)")
ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")
LIST_ITEM = re.compile(r"^ {0,3}(?:[-*+]|\d+[.)])\s")
EMPHASIS = re.compile(r"(\*{1,3}|(?<!\w)_{1,3})(?=\S)(.+?)(?<=\S)\1(?!\w)")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:|^//")


def prose_lines(text: str) -> list[str]:
    """Return lines outside fenced and indented code blocks (blank lines kept)."""
    lines: list[str] = []
    fence = None
    previous_blank = True
    in_list = False
    in_code = False
    for line in text.splitlines():
        match = FENCE.match(line)
        if match:
            marker, rest = match.groups()
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence) and not rest.strip():
                fence = None
            in_code = False
            previous_blank = False
            continue
        if fence is not None:
            continue
        if not line.strip():
            # Blank lines neither open nor close an indented code block.
            lines.append("")
            previous_blank = True
            continue
        indented = line.startswith(("    ", "\t"))
        if indented and in_code:
            # Later line of an indented code block (including after blank lines).
            previous_blank = False
            continue
        if indented and (in_list or not previous_blank):
            # List continuation or paragraph continuation: keep it as prose.
            lines.append(line)
        elif indented:
            # An indented code block opened after a blank line outside a list.
            in_code = True
            previous_blank = False
            continue
        else:
            in_code = False
            in_list = bool(LIST_ITEM.match(line))
            lines.append(line)
        previous_blank = False
    return lines


def slugify(heading: str) -> str:
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = re.sub(r"<[^>]+>", "", text).replace("`", "")
    previous = None
    while previous != text:
        previous, text = text, EMPHASIS.sub(r"\2", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(text: str) -> set[str]:
    found = set(ANCHOR.findall(text))
    seen: dict[str, int] = {}
    lines = prose_lines(text)
    for index, line in enumerate(lines):
        match = HEADING.match(line)
        if match:
            heading = match.group(1)
        elif (
            index + 1 < len(lines)
            and SETEXT.match(lines[index + 1])
            and line.strip()
            and not line.lstrip().startswith(("|", "-", "*", "+", ">"))
            and not HEADING.match(line)
        ):
            heading = line
        else:
            continue
        slug = slugify(heading)
        count = seen.get(slug, 0)
        found.add(slug if count == 0 else f"{slug}-{count}")
        seen[slug] = count + 1
    return found


def destinations(line: str) -> list[str]:
    """Extract inline link destinations, allowing balanced parentheses inside them."""
    targets: list[str] = []
    start = line.find("](")
    while start != -1:
        index = start + 2
        while index < len(line) and line[index] in " \t":
            index += 1
        if line.startswith("<", index):
            end = line.find(">", index)
            if end != -1:
                targets.append(line[index + 1 : end])
            start = line.find("](", index)
            continue
        depth = 0
        begin = index
        while index < len(line):
            char = line[index]
            if char == "\\" and index + 1 < len(line):
                index += 2
                continue
            if char.isspace():
                break
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
            index += 1
        if index > begin:
            targets.append(line[begin:index])
        start = line.find("](", index)
    return targets


def links(text: str) -> list[str]:
    """Return inline and reference-definition destinations with Markdown escapes decoded."""
    targets: list[str] = []
    prose = "\n".join(prose_lines(text))
    prose = INLINE_CODE.sub(lambda match: "\n" * match.group(0).count("\n"), prose)
    for line in prose.split("\n"):
        reference = REFERENCE.match(line)
        if reference:
            target = reference.group(1)
            targets.append(target[1:-1] if target.startswith("<") else target)
            continue
        targets.extend(destinations(line))
    return [ESCAPE.sub(r"\1", target) for target in targets]


def check(root: Path, files: list[Path]) -> list[str]:
    errors: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}
    root = root.resolve()
    for path in (item.resolve() for item in files):
        text = path.read_text(encoding="utf-8", errors="replace")
        for target in links(text):
            if SCHEME.match(target):
                continue
            location, _, fragment = target.partition("#")
            raw_path = location.partition("?")[0]
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
    root = args.root.resolve()
    files = tracked_markdown(root)
    errors = check(root, files)
    for error in errors:
        print(error)
    print(f"Checked local links in {len(files)} Markdown file(s); {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
