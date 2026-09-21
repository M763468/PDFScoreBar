#!/usr/bin/env python3
"""Resolve reusable PDFScoreBar Docker runtime images across worktrees."""

from __future__ import annotations

import argparse
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
RUNTIME_SCOPE = (
    "Dockerfile",
    "pyproject.toml",
    "docker/patch_homr_onnx_provider.py",
    "models/barline_cnn/manifest.json",
)


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


def working_tree_source_fingerprint(repo_root: Path) -> str:
    return _load_runtime_contract(repo_root).source_fingerprint(repo_root)


def working_tree_fingerprint(repo_root: Path) -> str:
    """Return the image/runtime compatibility fingerprint for the active checkout."""
    return _load_runtime_contract(repo_root).runtime_fingerprint(repo_root)


def git_ref_fingerprint(repo_root: Path, ref: str) -> str:
    runtime_contract = _load_runtime_contract(repo_root)
    entries: dict[str, bytes | None] = {}
    for relative in RUNTIME_SCOPE:
        blob = subprocess.run(
            ["git", "show", f"{ref}:{relative}"],
            cwd=repo_root,
            check=False,
            capture_output=True,
        )
        if blob.returncode == 0:
            entries[relative] = blob.stdout
        else:
            entries[relative] = None
    return runtime_contract.runtime_fingerprint_entries(entries)


def _find_develop_ref(repo_root: Path) -> str | None:
    for ref in ("refs/remotes/origin/develop", "develop"):
        result = _run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=repo_root)
        if result.returncode == 0:
            return ref
    return None


def _topic_has_runtime_diff(repo_root: Path, develop_ref: str) -> bool | None:
    merge_base = _run(["git", "merge-base", develop_ref, "HEAD"], cwd=repo_root)
    if merge_base.returncode != 0:
        return None
    base = merge_base.stdout.strip()
    if not base:
        return None
    try:
        return git_ref_fingerprint(repo_root, base) != git_ref_fingerprint(repo_root, "HEAD")
    except RuntimeError:
        return None


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


RUNTIME_FINGERPRINT_SCRIPT = r"""
from pathlib import Path
import hashlib

root = Path("/workspace")
files = (
    Path("Dockerfile"),
    Path("pyproject.toml"),
    Path("docker/patch_homr_onnx_provider.py"),
    Path("models/barline_cnn/manifest.json"),
)


def dockerfile_runtime_contract(payload):
    lines = payload.decode("utf-8").splitlines()
    normalized = []
    skipping_source_check = False
    skipping_legacy_source_write = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("ARG PDFSCORE_SOURCE_"):
            continue
        if stripped.startswith("LABEL pdfscore.runtime.source_"):
            continue

        if "ACTUAL_SOURCE_FINGERPRINT=$(" in stripped:
            skipping_source_check = True
            continue
        if skipping_source_check:
            if stripped == "fi && \\":
                skipping_source_check = False
            continue

        if stripped.startswith(
            "/opt/venv_pipeline/bin/python "
            "/opt/pdfscore-runtime/runtime_contract.py fingerprint /workspace"
        ):
            skipping_legacy_source_write = True
            continue
        if skipping_legacy_source_write:
            if "/opt/pdfscore-runtime/source_fingerprint.txt" in stripped:
                skipping_legacy_source_write = False
            continue

        if not stripped or stripped.startswith("#"):
            continue
        normalized.append(line.rstrip())

    return ("\n".join(normalized) + "\n").encode("utf-8")


digest = hashlib.sha256()
for relative in files:
    path = root / relative
    payload = path.read_bytes() if path.is_file() else b"<missing>"
    if relative == Path("Dockerfile") and payload != b"<missing>":
        payload = dockerfile_runtime_contract(payload)
    digest.update(relative.as_posix().encode("utf-8"))
    digest.update(b"\0")
    digest.update(payload)
    digest.update(b"\0")
print(digest.hexdigest())
"""


def _embedded_runtime_fingerprint(info: ImageInfo) -> str | None:
    if info.asset_contract != EXPECTED_ASSET_CONTRACT:
        return None
    result = _run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/opt/venv_pipeline/bin/python",
            info.image_id,
            "-c",
            RUNTIME_FINGERPRINT_SCRIPT,
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
    asset_contract = _label(labels, ASSET_CONTRACT_LABEL)
    if fingerprint is None and asset_contract == EXPECTED_ASSET_CONTRACT:
        fingerprint = _embedded_fingerprint(image_id)
    created = payload.get("Created")
    return ImageInfo(
        image_id=image_id,
        tags=tags,
        created=created if isinstance(created, str) else None,
        asset_contract=asset_contract,
        source_fingerprint=fingerprint,
        source_commit=_label(labels, SOURCE_COMMIT_LABEL),
        source_branch=_label(labels, SOURCE_BRANCH_LABEL),
    )


def list_runtime_images() -> list[ImageInfo]:
    result = _run(
        [
            "docker",
            "image",
            "ls",
            "--no-trunc",
            "--quiet",
            "--filter",
            f"label={ASSET_CONTRACT_LABEL}={EXPECTED_ASSET_CONTRACT}",
        ],
        check=True,
    )
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
        return "compatible", "The selected image matches the active runtime environment contract."

    if active_fingerprint != head_fingerprint:
        return (
            "working_tree_runtime_change",
            "The active checkout has uncommitted or untracked image/environment-defining changes. "
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
            "The image matches current develop's runtime environment, while this topic has no "
            "image/environment-defining changes of its own. Refresh the topic branch onto current "
            "develop and retry; "
            "do not rebuild solely for this mismatch.",
        )

    if topic_has_runtime_diff is True:
        return (
            "topic_runtime_change",
            "This topic changes image/environment-defining inputs relative to current develop. "
            "Reuse a matching local image or build a runtime image for this source state with "
            "make docker-build DOCKER_IMAGE=pdfscore-topic:<tag>.",
        )

    if (
        image_fingerprint is not None
        and develop_fingerprint is not None
        and image_fingerprint != develop_fingerprint
    ):
        return (
            "stale_image",
            "The selected image does not match current develop's runtime environment contract. "
            "Build the canonical image from the intended current target source.",
        )

    if image_fingerprint is None:
        return (
            "runtime_contract_unavailable",
            "The image runtime compatibility fingerprint could not be derived. Rebuild it once "
            "with the current canonical build path so compatibility can be verified.",
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
        f"source_fingerprint={info.source_fingerprint or '<missing>'} "
        f"commit={info.source_commit or '<legacy/unknown>'} "
        f"branch={info.source_branch or '<legacy/unknown>'}"
    )


def _resolve(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    requested = image_info(args.image_ref)
    if requested is None:
        if not args.explicit:
            active_fingerprint = working_tree_fingerprint(repo_root)
            for candidate in list_runtime_images():
                if candidate.source_fingerprint is None:
                    continue
                if _embedded_runtime_fingerprint(candidate) == active_fingerprint:
                    print(_format_info(candidate), file=sys.stderr)
                    print(candidate.image_id)
                    return 0
        print(
            f"Docker image reference is not available locally: {args.image_ref}. "
            f"Build the intended source with 'make docker-build DOCKER_IMAGE={args.image_ref}'.",
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

    active_source_fingerprint = working_tree_source_fingerprint(repo_root)
    if requested.source_fingerprint is None:
        print(
            "Docker image source provenance is missing; refusing compatibility-only reuse.",
            file=sys.stderr,
        )
        return 2

    active_fingerprint = working_tree_fingerprint(repo_root)
    requested_runtime_fingerprint = _embedded_runtime_fingerprint(requested)
    if requested_runtime_fingerprint == active_fingerprint:
        if requested.source_fingerprint == active_source_fingerprint:
            print(
                "Image source provenance and runtime environment contract both match.",
                file=sys.stderr,
            )
        else:
            print(
                "Image build source differs, but the image/runtime environment contract matches "
                "the active checkout; reusing the image with bind-mounted application source.",
                file=sys.stderr,
            )
        print(_format_info(requested), file=sys.stderr)
        print(f"  image_runtime_fingerprint={requested_runtime_fingerprint}", file=sys.stderr)
        print(f"  active_source_fingerprint={active_source_fingerprint}", file=sys.stderr)
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
        image_fingerprint=requested_runtime_fingerprint,
        head_fingerprint=head_fingerprint,
        develop_fingerprint=develop_fingerprint,
        topic_has_runtime_diff=topic_diff,
    )

    # A topic that is merely behind current develop's environment contract should refresh its
    # base instead of falling back to an older image. Bind-mounted source-only changes are
    # compatible and return above; genuine environment changes can reuse a matching local image.
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
            if candidate.source_fingerprint is None:
                continue
            candidate_runtime_fingerprint = _embedded_runtime_fingerprint(candidate)
            if candidate_runtime_fingerprint == active_fingerprint:
                print(
                    "Canonical tag points to a different build source; reusing a local "
                    "PDFScoreBar image with a matching runtime environment contract.",
                    file=sys.stderr,
                )
                print(_format_info(candidate), file=sys.stderr)
                print(
                    f"  image_runtime_fingerprint={candidate_runtime_fingerprint}",
                    file=sys.stderr,
                )
                print(candidate.image_id)
                return 0

    print("Docker runtime compatibility mismatch:", file=sys.stderr)
    print(f"  category: {category}", file=sys.stderr)
    print(f"  image_ref: {args.image_ref}", file=sys.stderr)
    print(f"  {_format_info(requested)}", file=sys.stderr)
    print(f"  active_runtime_fingerprint: {active_fingerprint}", file=sys.stderr)
    print(f"  active_source_fingerprint: {active_source_fingerprint}", file=sys.stderr)
    print(
        f"  image_runtime_fingerprint: {requested_runtime_fingerprint or '<unavailable>'}",
        file=sys.stderr,
    )
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
