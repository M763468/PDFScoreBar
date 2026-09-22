"""Movement-boundary review and resolved-export helpers.

This module keeps Issue #333 evidence separate from the Issue #268 consumer.
Only explicit review actions can produce resolved numbering boundaries.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

EVIDENCE_SCHEMA_VERSION = "issue333.movement_boundary_evidence.v1"
RESOLVED_SCHEMA_VERSION = "issue268.movement_boundaries.v1"
REVIEW_SCHEMA_VERSION = 1
REVIEW_CORRECTION_TYPE = "movement_boundary"
DEFAULT_REVIEW_FILENAME = "movement_boundaries_review.json"
DEFAULT_RESOLVED_FILENAME = "movement_boundaries.json"
DEFAULT_EVIDENCE_FILENAME = "movement_boundary_evidence.json"

_ALLOWED_EVIDENCE_STATES = {
    "confirmed_automatic",
    "explicit_manual_configured",
    "ambiguous_review_required",
    "no_boundary",
}
_ALLOWED_REVIEW_OPS = {"boundary", "no_boundary"}


class MovementBoundaryReviewError(ValueError):
    """Raised when movement-boundary review data is malformed or unsafe."""


def _nonnegative_int(value: Any, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise MovementBoundaryReviewError(f"{field} must be a nonnegative integer")
    return value


def _load_json_object(path: Path, *, description: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MovementBoundaryReviewError(f"{description} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise MovementBoundaryReviewError(f"{description} must be a JSON object: {path}")
    return payload


def validate_movement_boundary_evidence(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the review-only Issue #333 evidence contract used by the GUI."""

    if not isinstance(payload, Mapping):
        raise MovementBoundaryReviewError("movement boundary evidence must be a JSON object")
    if payload.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        raise MovementBoundaryReviewError(
            f"Unsupported movement boundary evidence schema_version: {payload.get('schema_version')}"
        )
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise MovementBoundaryReviewError("movement boundary evidence candidates must be a list")

    normalized = deepcopy(dict(payload))
    normalized_candidates: list[dict[str, Any]] = []
    seen_locations: set[tuple[int, int]] = set()
    seen_ids: set[str] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            raise MovementBoundaryReviewError(f"candidates[{index}] must be an object")
        page = _nonnegative_int(candidate.get("page"), field=f"candidates[{index}].page")
        system = _nonnegative_int(candidate.get("system"), field=f"candidates[{index}].system")
        state = candidate.get("state")
        if state not in _ALLOWED_EVIDENCE_STATES:
            raise MovementBoundaryReviewError(
                f"candidates[{index}].state must be one of {sorted(_ALLOWED_EVIDENCE_STATES)}"
            )
        location = (page, system)
        if location in seen_locations:
            raise MovementBoundaryReviewError(
                f"duplicate movement evidence location: page={page}, system={system}"
            )
        seen_locations.add(location)

        candidate_id = candidate.get("id")
        if candidate_id is None:
            candidate_id = f"page:{page}:system:{system}"
        if not isinstance(candidate_id, str) or not candidate_id:
            raise MovementBoundaryReviewError(f"candidates[{index}].id must be a non-empty string")
        if candidate_id in seen_ids:
            raise MovementBoundaryReviewError(f"duplicate movement evidence id: {candidate_id}")
        seen_ids.add(candidate_id)

        normalized_candidate = deepcopy(dict(candidate))
        normalized_candidate["id"] = candidate_id
        normalized_candidate["page"] = page
        normalized_candidate["system"] = system
        normalized_candidates.append(normalized_candidate)

    normalized["candidates"] = normalized_candidates
    return normalized


def validate_movement_boundary_review(
    payload: Mapping[str, Any],
    *,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate explicit review actions against one evidence artifact."""

    if not isinstance(payload, Mapping):
        raise MovementBoundaryReviewError("movement boundary review must be a JSON object")
    schema_version = payload.get("schema_version")
    if schema_version != REVIEW_SCHEMA_VERSION:
        raise MovementBoundaryReviewError(
            f"movement boundary review schema_version must be {REVIEW_SCHEMA_VERSION}"
        )
    if payload.get("correction_type") != REVIEW_CORRECTION_TYPE:
        raise MovementBoundaryReviewError(
            f"movement boundary review correction_type must be {REVIEW_CORRECTION_TYPE}"
        )
    items = payload.get("items")
    if not isinstance(items, list):
        raise MovementBoundaryReviewError("movement boundary review items must be a list")

    normalized_evidence = validate_movement_boundary_evidence(evidence)
    unresolved_candidates = {
        (item["page"], item["system"]): item
        for item in normalized_evidence["candidates"]
        if item["state"] == "ambiguous_review_required"
    }

    normalized_items: list[dict[str, Any]] = []
    seen_locations: set[tuple[int, int]] = set()
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise MovementBoundaryReviewError(f"review items[{index}] must be an object")
        op = item.get("op")
        if op not in _ALLOWED_REVIEW_OPS:
            raise MovementBoundaryReviewError(
                f"review items[{index}].op must be boundary or no_boundary"
            )
        page = _nonnegative_int(item.get("page"), field=f"review items[{index}].page")
        system = _nonnegative_int(item.get("system"), field=f"review items[{index}].system")
        location = (page, system)
        if location in seen_locations:
            raise MovementBoundaryReviewError(
                f"duplicate movement review location: page={page}, system={system}"
            )
        seen_locations.add(location)

        candidate = unresolved_candidates.get(location)
        if op == "no_boundary" and candidate is None:
            raise MovementBoundaryReviewError(
                "no_boundary review is only valid for an explicit unresolved candidate; "
                "candidate absence is not a reviewed negative"
            )

        normalized_item = deepcopy(dict(item))
        normalized_item["page"] = page
        normalized_item["system"] = system
        reason = normalized_item.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise MovementBoundaryReviewError(f"review items[{index}].reason must be a string")
        if candidate is not None:
            normalized_item["evidence_candidate_id"] = candidate["id"]
            normalized_item["review_kind"] = (
                "accepted_candidate" if op == "boundary" else "rejected_candidate"
            )
        else:
            normalized_item["evidence_candidate_id"] = None
            normalized_item["review_kind"] = "manual_boundary"
        normalized_items.append(normalized_item)

    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "correction_type": REVIEW_CORRECTION_TYPE,
        "items": normalized_items,
    }


def build_resolved_movement_boundaries(
    *,
    evidence: Mapping[str, Any],
    review: Mapping[str, Any],
    evidence_artifact: str,
    evidence_sha256: str,
) -> dict[str, Any]:
    """Export only explicit boundary decisions to the Issue #268 schema."""

    if not isinstance(evidence_artifact, str) or not evidence_artifact:
        raise MovementBoundaryReviewError("evidence_artifact must be a non-empty path string")
    if (
        not isinstance(evidence_sha256, str)
        or len(evidence_sha256) != 64
        or any(ch not in "0123456789abcdefABCDEF" for ch in evidence_sha256)
    ):
        raise MovementBoundaryReviewError(
            "evidence_sha256 must be a 64-character hexadecimal digest"
        )

    normalized_evidence = validate_movement_boundary_evidence(evidence)
    normalized_review = validate_movement_boundary_review(review, evidence=normalized_evidence)
    candidates = {
        (item["page"], item["system"]): item for item in normalized_evidence["candidates"]
    }
    required_review_locations = {
        (item["page"], item["system"])
        for item in normalized_evidence["candidates"]
        if item["state"] == "ambiguous_review_required"
    }
    reviewed_locations = {
        (item["page"], item["system"]) for item in normalized_review["items"]
    }
    unresolved_locations = sorted(required_review_locations - reviewed_locations)
    if unresolved_locations:
        formatted = ", ".join(
            f"(page={page}, system={system})" for page, system in unresolved_locations
        )
        raise MovementBoundaryReviewError(
            "cannot export movement boundaries while review-required candidates remain "
            f"unresolved: {formatted}"
        )

    boundaries: list[dict[str, Any]] = []
    for item in normalized_review["items"]:
        if item["op"] != "boundary":
            continue
        location = (item["page"], item["system"])
        candidate = candidates.get(location)
        reviewed_candidate = (
            candidate is not None and candidate["state"] == "ambiguous_review_required"
        )
        review_action = "accepted_candidate" if reviewed_candidate else "manual_boundary"
        source = "reviewed_candidate" if reviewed_candidate else "manual"
        boundaries.append(
            {
                "page": item["page"],
                "system": item["system"],
                "reset_number": 1,
                "source": source,
                "provenance": {
                    "kind": "movement_boundary_review",
                    "evidence": {
                        "schema_version": EVIDENCE_SCHEMA_VERSION,
                        "artifact": evidence_artifact,
                        "sha256": evidence_sha256.lower(),
                        "candidate_id": candidate.get("id") if reviewed_candidate else None,
                    },
                    "review": {
                        "action": review_action,
                        "reason": item.get("reason") or "manual movement-boundary review",
                    },
                },
            }
        )

    boundaries.sort(key=lambda item: (item["page"], item["system"]))
    return {
        "schema_version": RESOLVED_SCHEMA_VERSION,
        "boundaries": boundaries,
    }


def write_resolved_movement_boundaries(
    *,
    evidence_path: str | Path,
    review_path: str | Path,
    output_path: str | Path,
    evidence_artifact: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Load review artifacts and write the resolved Issue #268 payload."""

    evidence_file = Path(evidence_path)
    review_file = Path(review_path)
    output_file = Path(output_path)
    if output_file.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite resolved movement boundaries: {output_file}")

    evidence_bytes = evidence_file.read_bytes()
    evidence = json.loads(evidence_bytes.decode("utf-8"))
    review = _load_json_object(review_file, description="movement boundary review")
    artifact_name = evidence_artifact or evidence_file.as_posix()
    resolved = build_resolved_movement_boundaries(
        evidence=evidence,
        review=review,
        evidence_artifact=artifact_name,
        evidence_sha256=hashlib.sha256(evidence_bytes).hexdigest(),
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(resolved, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return resolved


def attach_movement_boundary_evidence(
    *,
    handoff_path: str | Path,
    evidence_path: str | Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Attach one Issue #333 evidence artifact to an existing review package.

    The evidence bytes are copied into the review package, and the handoff is
    updated so the existing manual GUI can review it without arbitrary external
    file paths.
    """

    handoff_file = Path(handoff_path).resolve()
    package_root = handoff_file.parent
    handoff = _load_json_object(handoff_file, description="manual correction handoff")
    evidence_file = Path(evidence_path).resolve()
    evidence_bytes = evidence_file.read_bytes()
    evidence = validate_movement_boundary_evidence(json.loads(evidence_bytes.decode("utf-8")))

    pages = handoff.get("pages")
    if not isinstance(pages, list) or not pages:
        raise MovementBoundaryReviewError(
            "manual correction handoff pages must be a non-empty list"
        )
    page_indices: set[int] = set()
    for index, page in enumerate(pages):
        if not isinstance(page, Mapping):
            raise MovementBoundaryReviewError(f"handoff pages[{index}] must be an object")
        page_number = page.get("page_number")
        if not isinstance(page_number, int) or isinstance(page_number, bool) or page_number < 1:
            raise MovementBoundaryReviewError(
                f"handoff pages[{index}].page_number must be a positive integer"
            )
        page_indices.add(page_number - 1)

    missing_candidate_pages = sorted(
        {
            candidate["page"]
            for candidate in evidence["candidates"]
            if candidate["page"] not in page_indices
        }
    )
    if missing_candidate_pages:
        raise MovementBoundaryReviewError(
            "movement evidence contains candidate pages absent from the review package: "
            + ", ".join(str(page) for page in missing_candidate_pages)
        )

    destination = package_root / DEFAULT_EVIDENCE_FILENAME
    normalized_evidence_bytes = (
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    if destination.exists() and not overwrite:
        existing_bytes = destination.read_bytes()
        if existing_bytes not in {evidence_bytes, normalized_evidence_bytes}:
            raise FileExistsError(
                f"Refusing to overwrite attached movement evidence: {destination}"
            )
    if overwrite or not destination.exists() or destination.read_bytes() != normalized_evidence_bytes:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(normalized_evidence_bytes)

    if "movement_boundary_evidence" in handoff and not overwrite:
        existing = handoff.get("movement_boundary_evidence")
        if existing != DEFAULT_EVIDENCE_FILENAME:
            raise FileExistsError("manual correction handoff already points to movement evidence")

    handoff["movement_boundary_evidence"] = DEFAULT_EVIDENCE_FILENAME
    handoff["movement_boundary_resolved_output"] = f"corrections/{DEFAULT_RESOLVED_FILENAME}"
    handoff_file.write_text(
        json.dumps(handoff, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return handoff
