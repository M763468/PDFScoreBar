#!/usr/bin/env python3
"""Resolve reusable PDFScoreBar Docker runtime images across worktrees."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ASSET_CONTRACT_LABEL = "pdfscore.runtime.asset_contract"
SOURCE_FINGERPRINT_LABEL = "pdfscore.runtime.source_fingerprint"
SOURCE_COMMIT_LABEL = "pdfscore.runtime.source_commit"
SOURCE_BRANCH_LABEL = "pdfscore.runtime.source_branch"
EXPECTED_ASSET_CONTRACT = "v1"
EMBEDDED_FINGERPRINT_PATH = "/opt/pdfscore-runtime/source_fingerprint.txt"
RUNTIME_SCOPE = ("src", "experiments/models", "docker", "Dockerfile", "pyproject.toml")
RUNTIME_ROOTS = ("src/", "experiments/models/", "docker/")
RUNTIME_FILES = frozenset({"Dockerfile", "pyproject.toml"})
RUNTIME_SUFFIXES = frozenset({".py", ".toml"})


@dataclass(frozen=True)
class ImageInfo:
    image_id: str
    tags: tuple[str, ...]
    created: str | None
    asset_contract: str | None
    source_fingerprint: str | None
    source_commit: str | None
    source_branch: str | None


def _run(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(args),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args)}\n{detail}")
    return result


def _load_runtime_contract(repo_root: Path):
    module_path = repo_root / "docker" / "runtime_contract.py"
    spec = importlib.util.spec_from_file_location("pdfscore_runtime_contract_host", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load runtime contract: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def working_tree_fingerprint(repo_root: Path) -> str:
    return _load_runtime_contract(repo_root).source_fingerprint(repo_root)


def _eligible_git_path(path: str) -> bool:
    if path in RUNTIME_FILES:
        return True
    return path.startswith(RUNTIME_ROOTS) and Path(path).suffix in RUNTIME_SUFFIXES


def git_ref_fingerprint(repo_root: Path, ref: str) -> str:
    listing = _run(
        ["git", "ls-tree", "-r", "--name-only", ref, "--", *RUNTIME_SCOPE],
        cwd=repo_root,
        check=True,
    )
    paths = sorted(path for path in listing.stdout.splitlines() if _eligible_git_path(path))

    digest = hashlib.sha256()
    for relative in paths:
        blob = subprocess.run(
            ["git", "show", f"{ref}:{relative}"],
            cwd=repo_root,
            check=False,
            capture_output=True,
        )
        if blob.returncode != 0:
            detail = blob.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Unable to read {ref}:{relative}: {detail}")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(blob.stdout)
        digest.update(b"\0")
    return digest.hexdigest()


def _find_develop_ref(repo_root: Path) -> str | None:
    for ref in ("refs/remotes/origin/develop", "develop"):
        result = _run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=repo_root)
        if result.returncode == 0:
            return ref
    return None


def _topic_has_runtime_diff(repo_root: Path, develop_ref: str) -> bool | None:
    result = _run(
        ["git", "diff", "--name-only", f"{develop_ref}...HEAD", "--", *RUNTIME_SCOPE],
        cwd=repo_root,
    )
    if result.returncode != 0:
        return None
    return any(_eligible_git_path(path) for path in result.stdout.splitlines())


def _inspect_image(image_ref: str) -> dict[str, object] | None:
    result = _run(["docker", "image", "inspect", image_ref])
    if result.returncode != 0:
        return None
    payload = json.loads(result.stdout)
    if not isinstance(payload, list) or not payload:
        return None
    item = payload[0]
    return item if isinstance(item, dict) else None


def _label(labels: object, key: str) -> str | None:
    if not isinstance(labels, dict):
        return None
    value = labels.get(key)
    return value if isinstance(value, str) and value else None


def _embedded_fingerprint(image_id: str) -> str | None:
    result = _run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "cat",
            image_id,
            EMBEDDED_FINGERPRINT_PATH,
        ]
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    if len(value) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in value):
        return value.lower()
    return None


def image_info(image_ref: str) -> ImageInfo | None:
    payload = _inspect_image(image_ref)
    if payload is None:
        return None
    image_id = payload.get("Id")
    if not isinstance(image_id, str) or not image_id:
        return None
    config = payload.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    tags_raw = payload.get("RepoTags")
    tags = (
        tuple(tag for tag in tags_raw if isinstance(tag, str)) if isinstance(tags_raw, list) else ()
    )
    fingerprint = _label(labels, SOURCE_FINGERPRINT_LABEL)
    if fingerprint is None:
        fingerprint = _embedded_fingerprint(image_id)
    created = payload.get("Created")
    return ImageInfo(
        image_id=image_id,
        tags=tags,
        created=created if isinstance(created, str) else None,
        asset_contract=_label(labels, ASSET_CONTRACT_LABEL),
        source_fingerprint=fingerprint,
        source_commit=_label(labels, SOURCE_COMMIT_LABEL),
        source_branch=_label(labels, SOURCE_BRANCH_LABEL),
    )


def list_runtime_images() -> list[ImageInfo]:
    result = _run(["docker", "image", "ls", "--no-trunc", "--quiet"], check=True)
    images: list[ImageInfo] = []
    seen: set[str] = set()
    for image_id in result.stdout.splitlines():
        if not image_id or image_id in seen:
            continue
        seen.add(image_id)
        info = image_info(image_id)
        if info is not None and info.asset_contract == EXPECTED_ASSET_CONTRACT:
            images.append(info)
    return images


def classify_mismatch(
    *,
    active_fingerprint: str,
    image_fingerprint: str | None,
    head_fingerprint: str,
    develop_fingerprint: str | None,
    topic_has_runtime_diff: bool | None,
) -> tuple[str, str]:
    if image_fingerprint == active_fingerprint:
        return "compatible", "The selected image matches the active runtime-sensitive source."

    if active_fingerprint != head_fingerprint:
        return (
            "working_tree_runtime_change",
            "The active checkout has uncommitted or untracked runtime-sensitive changes. "
            "Resolve those changes before deciding whether an image rebuild is required.",
        )

    if (
        image_fingerprint is not None
        and develop_fingerprint is not None
        and image_fingerprint == develop_fingerprint
        and topic_has_runtime_diff is False
    ):
        return (
            "stale_topic_base",
            "The image matches current develop, while this topic has no runtime-sensitive "
            "changes of its own. Refresh the topic branch onto current develop and retry; "
            "do not rebuild solely for this mismatch.",
        )

    if topic_has_runtime_diff is True:
        return (
            "topic_runtime_change",
            "This topic changes runtime-sensitive files relative to current develop. "
            "After refreshing the base, build a runtime image for this source state.",
        )

    if (
        image_fingerprint is not None
        and develop_fingerprint is not None
        and image_fingerprint != develop_fingerprint
    ):
        return (
            "stale_image",
            "The selected image does not match current develop runtime source. "
            "Build the canonical image from the intended current target source.",
        )

    if image_fingerprint is None:
        return (
            "image_provenance_missing",
            "The image does not expose a source fingerprint. Rebuild it once with the "
            "current canonical build path so compatibility can be verified.",
        )

    return (
        "unclassified_mismatch",
        "The image and checkout fingerprints differ, but the available Git provenance is "
        "insufficient to classify the mismatch safely. Inspect the source/base before rebuilding.",
    )


def _format_info(info: ImageInfo) -> str:
    tags = ",".join(info.tags) if info.tags else "<untagged>"
    return (
        f"id={info.image_id} tags={tags} created={info.created or '<unknown>'} "
        f"fingerprint={info.source_fingerprint or '<missing>'} "
        f"commit={info.source_commit or '<legacy/unknown>'} "
        f"branch={info.source_branch or '<legacy/unknown>'}"
    )


def _resolve(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    requested = image_info(args.image_ref)
    if requested is None:
        print(
            f"Docker image reference is not available locally: {args.image_ref}. "
            "Run 'make docker-build' first.",
            file=sys.stderr,
        )
        return 2
    if requested.asset_contract != EXPECTED_ASSET_CONTRACT:
        print(
            "Docker image does not expose the expected PDFScoreBar runtime contract label.\n"
            f"  image_ref: {args.image_ref}\n"
            f"  image_id: {requested.image_id}\n"
            f"  asset_contract: {requested.asset_contract or '<missing>'}",
            file=sys.stderr,
        )
        return 2

    active_fingerprint = working_tree_fingerprint(repo_root)
    if requested.source_fingerprint == active_fingerprint:
        print(_format_info(requested), file=sys.stderr)
        print(requested.image_id)
        return 0

    head_fingerprint = git_ref_fingerprint(repo_root, "HEAD")
    develop_ref = _find_develop_ref(repo_root)
    develop_fingerprint = (
        git_ref_fingerprint(repo_root, develop_ref) if develop_ref is not None else None
    )
    topic_diff = (
        _topic_has_runtime_diff(repo_root, develop_ref) if develop_ref is not None else None
    )
    category, guidance = classify_mismatch(
        active_fingerprint=active_fingerprint,
        image_fingerprint=requested.source_fingerprint,
        head_fingerprint=head_fingerprint,
        develop_fingerprint=develop_fingerprint,
        topic_has_runtime_diff=topic_diff,
    )

    # A docs/non-runtime topic that is merely behind current develop should refresh its
    # base instead of falling back to an older image that happens to match stale source.
    # For genuine topic runtime changes or a stale canonical tag, however, reuse an
    # already-built compatible image before asking for another build.
    reusable_categories = {
        "topic_runtime_change",
        "stale_image",
        "image_provenance_missing",
        "unclassified_mismatch",
    }
    if not args.explicit and category in reusable_categories:
        for candidate in list_runtime_images():
            if candidate.image_id == requested.image_id:
                continue
            if candidate.source_fingerprint == active_fingerprint:
                print(
                    "Canonical tag points to different source; reusing a compatible local "
                    "PDFScoreBar runtime image.",
                    file=sys.stderr,
                )
                print(_format_info(candidate), file=sys.stderr)
                print(candidate.image_id)
                return 0

    print("Docker runtime source mismatch:", file=sys.stderr)
    print(f"  category: {category}", file=sys.stderr)
    print(f"  image_ref: {args.image_ref}", file=sys.stderr)
    print(f"  {_format_info(requested)}", file=sys.stderr)
    print(f"  active_fingerprint: {active_fingerprint}", file=sys.stderr)
    print(f"  head_fingerprint: {head_fingerprint}", file=sys.stderr)
    print(f"  develop_ref: {develop_ref or '<unavailable>'}", file=sys.stderr)
    print(f"  develop_fingerprint: {develop_fingerprint or '<unavailable>'}", file=sys.stderr)
    print(f"  guidance: {guidance}", file=sys.stderr)
    if args.explicit:
        print(
            "  note: DOCKER_IMAGE is explicit, so no alternate image was selected.", file=sys.stderr
        )
    return 2


def _list_images(_args: argparse.Namespace) -> int:
    images = list_runtime_images()
    if not images:
        print("No local PDFScoreBar runtime images with asset contract v1 were found.")
        return 0
    for info in images:
        print(_format_info(info))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--repo-root", type=Path, required=True)
    resolve.add_argument("--image-ref", default="pdfscore_pipeline_gpu")
    resolve.add_argument(
        "--explicit",
        action="store_true",
        help="Honor the requested image exactly instead of searching compatible local images.",
    )
    resolve.set_defaults(func=_resolve)

    images = subparsers.add_parser("list")
    images.set_defaults(func=_list_images)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
