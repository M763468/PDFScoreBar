"""Run the Issue #283 full-68 gate against retained copied source images.

Issue #274's accepted fresh full-68 run staged canonical evaluation images under
its retained ``inputs/<score>/<page>.png`` tree.  The generic Issue #283 gate is
intentionally strict about source-image identity; this wrapper changes only that
preflight check from path equality to SHA-256 equality while preserving the
retained copied image as the actual replay input.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.issue283 import validate_full68_current_homr as base


def _preflight_retained_copy(
    key: tuple[str, str],
    result_path: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    score, page = key
    image = base._visible_path(payload.get("image"))  # noqa: SLF001
    sr_image = base._visible_path(payload.get("sr_image"))  # noqa: SLF001
    canonical_image = (base.ROOT / "data/evaluation2/images" / score / f"{page}.png").resolve()

    if not image.is_file():
        raise FileNotFoundError(image)
    if not canonical_image.is_file():
        raise FileNotFoundError(canonical_image)
    if not sr_image.is_file():
        raise FileNotFoundError(sr_image)

    image_sha256 = base._sha256(image)  # noqa: SLF001
    canonical_sha256 = base._sha256(canonical_image)  # noqa: SLF001
    if image_sha256 != canonical_sha256:
        raise RuntimeError(
            f"{score}/{page}: retained source bytes differ from canonical evaluation image: "
            f"{image} ({image_sha256}) != {canonical_image} ({canonical_sha256})"
        )

    if payload.get("connector_complete") is not True:
        raise RuntimeError(f"{score}/{page}: connector_complete is not true")

    hashes = base._artifact_hashes(payload)  # noqa: SLF001
    return {
        "score": score,
        "page": page,
        "baseline_result": str(result_path),
        "image": str(image),
        "canonical_image": str(canonical_image),
        "image_sha256": image_sha256,
        "canonical_image_sha256": canonical_sha256,
        "source_image_bytes_equal": True,
        "sr_image": str(sr_image),
        "sr_sha256": base._sha256(sr_image),  # noqa: SLF001
        "baseline_artifact_hashes": hashes,
    }


def main() -> int:
    base._preflight_entry = _preflight_retained_copy  # noqa: SLF001
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
