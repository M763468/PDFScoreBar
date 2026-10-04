#!/usr/bin/env python3
"""Prepare and execute the Issue #397 real-artifact acceptance smoke.

This runner copies retained review packages into an issue-scoped evidence root, freezes
inputs before apply, then drives only the package-scoped review HTTP API. It never edits
source runs. Place this file at tools/review_correction/issue397_acceptance.py when
integrating; --repo-root makes scratch execution explicit meanwhile.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_SOURCE_RUN = Path("logs/issue354/manual_gui_smoke/production_page001_20260921T144416Z")
DEFAULT_MOVEMENT_REVIEW = Path("logs/issue346/ux_shostakovich5")
BARLINE_TARGET = [777, 3723, 784, 3824]
MMR_ITEM = {
    "op": "set_measure_span",
    "page": 0,
    "system": 0,
    "measure": 0,
    "measure_span": 2,
    "reason": "Issue 397 acceptance: visible measure 1 spans two measures",
}
BARLINE_ITEM = {
    "op": "remove_barline",
    "page": 0,
    "bbox": BARLINE_TARGET,
    "reason": "Issue 397 acceptance: remove internal barline between measures 76 and 77",
}
MOVEMENT_PAGE = 6
MOVEMENT_SYSTEM = 5
MOVEMENT_CANDIDATE_ID = "page:6:system:5"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_identity(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "exists": path.is_file(),
        "sha256": sha256(path) if path.is_file() else None,
    }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def run_git(repo_root: Path, *args: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args], capture_output=True, text=True, timeout=10
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"exit_code": None, "stdout": "", "stderr": str(exc)}


def candidate_commit_provenance(repo_root: Path) -> dict[str, Any]:
    """Require an identifiable candidate commit even in containers without Git metadata."""

    checkout = run_git(repo_root, "rev-parse", "HEAD")
    checkout_commit = (
        checkout["stdout"]
        if checkout.get("exit_code") == 0 and isinstance(checkout.get("stdout"), str)
        else ""
    ).strip()
    operator_commit = os.environ.get("PDFSCOREBAR_SOURCE_COMMIT", "").strip()
    candidate_commit = operator_commit or checkout_commit
    if not candidate_commit:
        detail = checkout.get("stderr") or "git rev-parse HEAD returned no commit"
        raise ValueError(
            "Cannot freeze acceptance evidence without a candidate source commit: "
            "the checkout commit lookup failed and PDFSCOREBAR_SOURCE_COMMIT is unset. "
            f"Provide PDFSCOREBAR_SOURCE_COMMIT in Git-less containers. Git detail: {detail}"
        )
    return {
        "current_checkout_commit": checkout,
        "operator_candidate_commit": operator_commit or None,
        "candidate_commit": candidate_commit,
        "candidate_commit_source": "operator" if operator_commit else "checkout",
    }


def configured_model_identity(repo_root: Path, source_run: Path) -> dict[str, Any]:
    manifest = load_json(source_run / "manifest.json")
    model_ref = manifest.get("config", {}).get("mmr", {}).get("model_path")
    configured = (repo_root / model_ref).resolve() if model_ref else None
    canonical = (repo_root / "models/mmr/mmr_classifier_best.pth").resolve()
    return {
        "configured_path": str(configured) if configured else None,
        "configured_exists": bool(configured and configured.is_file()),
        "configured_sha256": sha256(configured) if configured and configured.is_file() else None,
        "known_canonical_path": str(canonical),
        "known_canonical_exists": canonical.is_file(),
        "known_canonical_sha256": sha256(canonical) if canonical.is_file() else None,
        "substitution_performed": False,
    }


def _torch_identity() -> dict[str, Any]:
    import torch

    available = torch.cuda.is_available()
    return {
        "version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "cuda_available": available,
        "device": torch.cuda.get_device_name(0) if available else None,
    }


def capture_runtime_identity(
    repo_root: Path, model: dict[str, Any], explicit: str | None
) -> dict[str, Any]:
    docker_info: dict[str, Any] = {"status": "not_checked"}
    docker = shutil.which("docker")
    if docker:
        try:
            result = subprocess.run(
                [
                    docker,
                    "image",
                    "inspect",
                    "pdfscore_pipeline_gpu",
                    "--format",
                    "{{.Id}} {{json .Config.Labels}}",
                ],
                capture_output=True,
                text=True,
                timeout=8,
            )
            docker_info = {
                "status": "available" if result.returncode == 0 else "blocked_or_missing",
                "exit_code": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except (OSError, subprocess.TimeoutExpired) as exc:
            docker_info = {"status": "blocked_or_missing", "stderr": str(exc)}
    return {
        "declared_runtime": explicit or os.environ.get("PDFSCOREBAR_RUNTIME_IDENTITY"),
        "python": sys.version,
        "torch": _torch_identity(),
        "platform": platform.platform(),
        "docker_image": docker_info,
        "mmr_model": model,
        "apply_execution": "not_started; acceptance inputs frozen before smoke",
    }


def _inventory_tree(root: Path) -> list[dict[str, Any]]:
    result = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Retained review package contains a symlink: {path}")
        if path.is_file():
            result.append(
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    return result


_PATHISH_KEY = re.compile(r"(path|root|dir|manifest|image|mask|output|override|artifact)$", re.I)


def _resolve_source_path(
    raw: str, *, repo_root: Path, source_run: Path, artifact_repo_root: Path | None = None
) -> str:
    candidate = Path(raw)
    if candidate.is_absolute():
        return str(candidate.resolve()) if candidate.exists() else raw
    for base in (artifact_repo_root, repo_root, source_run, source_run.parent):
        if base is None:
            continue
        resolved = (base / candidate).resolve()
        if resolved.exists():
            return str(resolved)
    return raw


def infer_artifact_repo_root(source_run: Path) -> Path | None:
    """Infer the original checkout prefix before logs/ for retained relative paths."""
    resolved = source_run.resolve()
    parts = resolved.parts
    if "logs" not in parts:
        return None
    index = parts.index("logs")
    if index == 0:
        return None
    return Path(*parts[:index])


def _adapt_manifest_paths(
    value: Any,
    *,
    repo_root: Path,
    source_run: Path,
    artifact_repo_root: Path | None = None,
    path: str = "",
) -> tuple[Any, list[dict[str, str]]]:
    """Resolve only existing path-valued manifest strings and record each rewrite."""
    rewrites: list[dict[str, str]] = []
    if isinstance(value, dict):
        adapted: dict[str, Any] = {}
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if isinstance(child, str) and _PATHISH_KEY.search(key):
                resolved = _resolve_source_path(
                    child,
                    repo_root=repo_root,
                    source_run=source_run,
                    artifact_repo_root=artifact_repo_root,
                )
                adapted[key] = resolved
                if resolved != child:
                    rewrites.append({"field": child_path, "original": child, "adapted": resolved})
            else:
                adapted[key], nested = _adapt_manifest_paths(
                    child,
                    repo_root=repo_root,
                    source_run=source_run,
                    artifact_repo_root=artifact_repo_root,
                    path=child_path,
                )
                rewrites.extend(nested)
        return adapted, rewrites
    if isinstance(value, list):
        adapted_list = []
        for index, child in enumerate(value):
            adapted_child, nested = _adapt_manifest_paths(
                child,
                repo_root=repo_root,
                source_run=source_run,
                artifact_repo_root=artifact_repo_root,
                path=f"{path}[{index}]",
            )
            adapted_list.append(adapted_child)
            rewrites.extend(nested)
        return adapted_list, rewrites
    return value, rewrites


def _prepare_source_context(
    *,
    source_run: Path,
    context_root: Path,
    repo_root: Path,
    artifact_repo_root: Path | None = None,
    page_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Copy a source manifest context; rewrite existing paths, copy numbering bases."""
    original = load_json(source_run / "manifest.json")
    adapted, rewrites = _adapt_manifest_paths(
        copy.deepcopy(original),
        repo_root=repo_root,
        source_run=source_run,
        artifact_repo_root=artifact_repo_root,
    )
    context_root.mkdir(parents=True, exist_ok=False)
    manifest_path = context_root / "manifest.json"
    write_json(manifest_path, adapted)
    copied_bases = []
    for page in original.get("pages", []):
        page_id = page.get("page_id")
        if not isinstance(page_id, str) or (page_ids is not None and page_id not in page_ids):
            continue
        source = source_run / "intermediate" / page_id / "numbering_base.json"
        if source.is_file():
            target = context_root / "intermediate" / page_id / "numbering_base.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied_bases.append(file_identity(source) | {"context_path": str(target.resolve())})
    return {
        "source_manifest_before": file_identity(source_run / "manifest.json"),
        "source_manifest_context": file_identity(manifest_path),
        "manifest_path_rewrites": rewrites,
        "numbering_bases_copied": copied_bases,
        "context_root": str(context_root.resolve()),
        "artifact_repo_root": str(artifact_repo_root.resolve()) if artifact_repo_root else None,
    }


def _copy_package(
    source_review: Path,
    destination: Path,
    source_root: Path,
    *,
    movement_evidence: Path | None = None,
    repo_root: Path,
    movement_page_subset: int | None = None,
) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(f"Refusing to replace prepared package: {destination}")
    handoff_source = source_review / "manual_correction_input.json"
    if not handoff_source.is_file():
        raise FileNotFoundError(f"Missing review handoff: {handoff_source}")
    shutil.copytree(source_review, destination, symlinks=True)
    handoff = load_json(destination / "manual_correction_input.json")
    previous_root = handoff.get("source_artifact_root")
    handoff["source_artifact_root"] = str(source_root.resolve())
    write_json(destination / "manual_correction_input.json", handoff)
    adaptation = {
        "field": "source_artifact_root",
        "previous": previous_root,
        "value": str(source_root.resolve()),
        "reason": "record the exact existing retained source directory available to this host; source_manifest remains manifest.json",
    }

    evidence_adaptation = None
    if movement_evidence is not None:
        # Existing package and evidence form a real retained workflow, not synthetic evidence.
        sys.path.insert(0, str(repo_root))
        from src.pipeline.review.movement_boundary_review import attach_movement_boundary_evidence

        handoff = attach_movement_boundary_evidence(
            handoff_path=destination / "manual_correction_input.json",
            evidence_path=movement_evidence,
            overwrite=True,
        )
        evidence_adaptation = {
            "source_evidence": file_identity(movement_evidence),
            "attached_package_path": "movement_boundary_evidence.json",
            "action": "copied and attached with maintained attach_movement_boundary_evidence helper",
        }

    subset_adaptation = None
    if movement_page_subset is not None:
        selected_page = next(
            (
                page
                for page in handoff.get("pages", [])
                if int(page.get("page_number", -1)) - 1 == movement_page_subset
            ),
            None,
        )
        if selected_page is None:
            raise ValueError(
                f"Movement package has no frozen package page index {movement_page_subset}"
            )
        original_count = len(handoff["pages"])
        handoff["pages"] = [selected_page]
        write_json(destination / "manual_correction_input.json", handoff)
        selected_files = {
            selected_page.get(key)
            for key in (
                "source_image",
                "numbering_final",
                "review_overlay",
                "mmr_overrides",
                "barlines_review",
            )
        }
        for page_dir in (destination / "pages").glob("page_*"):
            for file in page_dir.iterdir():
                relative = file.relative_to(destination).as_posix()
                if relative not in selected_files:
                    file.unlink()
            try:
                page_dir.rmdir()
            except OSError:
                pass
        subset_adaptation = {
            "original_handoff_page_count": original_count,
            "retained_package_page": selected_page.get("page_id"),
            "zero_based_package_page": movement_page_subset,
            "reason": "predeclared focused movement acceptance target; retain page_008 containing unresolved candidate page:6/system:5",
            "evidence_candidates_retained": [
                item.get("id")
                for item in load_json(destination / "movement_boundary_evidence.json").get(
                    "candidates", []
                )
            ],
        }

    original_corrections = []
    correction_root = destination / "corrections"
    if correction_root.exists():
        for path in sorted(correction_root.glob("*.json")):
            original_corrections.append(
                {"path": path.relative_to(destination).as_posix(), "sha256": sha256(path)}
            )
        # Start smoke scenarios with no previously saved correction decisions/results.
        for path in correction_root.glob("*.json"):
            path.unlink()
    return {
        "handoff": str((destination / "manual_correction_input.json").resolve()),
        "source_root_adaptation": adaptation,
        "movement_evidence_adaptation": evidence_adaptation,
        "page_subset_adaptation": subset_adaptation,
        "preexisting_corrections_copied_then_cleared_for_smoke": original_corrections,
        "package_files_after_prepare": _inventory_tree(destination),
    }


def numbering_page(path: Path, page_index: int = 0) -> dict[str, Any]:
    payload = load_json(path)
    pages = payload.get("pages")
    if not isinstance(pages, list) or page_index >= len(pages):
        raise ValueError(f"Numbering artifact has no page index {page_index}: {path}")
    return pages[page_index]


def visible_numbers(numbering_page_data: dict[str, Any], system_index: int) -> list[int]:
    systems = numbering_page_data.get("systems") or []
    if system_index >= len(systems):
        raise ValueError(f"Numbering artifact has no system index {system_index}")
    return [int(measure["number"]) for measure in systems[system_index].get("measures", [])]


def total_measures(numbering_page_data: dict[str, Any]) -> int:
    return sum(len(system.get("measures", [])) for system in numbering_page_data.get("systems", []))


def freeze_plan(
    *,
    source_run: Path,
    evidence_root: Path,
    repo_root: Path,
    movement_review: Path | None,
    runtime_identity: str | None,
    source_context: dict[str, Any] | None = None,
    movement_context: dict[str, Any] | None = None,
    candidate_provenance: dict[str, Any],
) -> dict[str, Any]:
    source_run = source_run.resolve()
    source_review = source_run / "review"
    manifest_path = source_run / "manifest.json"
    handoff_path = source_review / "manual_correction_input.json"
    for required in (manifest_path, handoff_path):
        if not required.is_file():
            raise FileNotFoundError(f"Required retained artifact is absent: {required}")
    manifest = load_json(manifest_path)
    baseline_path = source_run / "outputs/page_001/numbering_final.json"
    baseline = numbering_page(baseline_path)
    baseline_numbers_sys0 = visible_numbers(baseline, 0)
    visible_numbers(baseline, 9)
    barline_payload = load_json(source_review / "pages/page_001/barlines_review.json")
    if BARLINE_TARGET not in barline_payload:
        raise ValueError(
            f"Frozen barline bbox is no longer present in retained artifact: {BARLINE_TARGET}"
        )
    movement_record: dict[str, Any]
    if movement_review:
        movement_review = movement_review.resolve()
        movement_handoff = movement_review / "review/manual_correction_input.json"
        movement_evidence = movement_review / "review/movement_boundary_evidence.json"
        movement_source_root = Path(load_json(movement_handoff).get("source_artifact_root", ""))
        if (
            not movement_handoff.is_file()
            or not movement_evidence.is_file()
            or not (movement_source_root / "manifest.json").is_file()
        ):
            raise FileNotFoundError(f"Movement review package is incomplete: {movement_review}")
        evidence = load_json(movement_evidence)
        candidate = next(
            (
                item
                for item in evidence.get("candidates", [])
                if item.get("id") == MOVEMENT_CANDIDATE_ID
            ),
            None,
        )
        if not candidate or candidate.get("state") != "ambiguous_review_required":
            raise ValueError(
                f"Expected retained unresolved movement candidate is absent: {MOVEMENT_CANDIDATE_ID}"
            )
        movement_page_file = movement_review / "review/pages/page_008/numbering_final.json"
        movement_page = numbering_page(movement_page_file)
        movement_record = {
            "status": "prepared",
            "review_root": str(movement_review),
            "source_root": str(movement_source_root.resolve()),
            "source_manifest": file_identity(movement_source_root / "manifest.json"),
            "handoff": file_identity(movement_handoff),
            "evidence": file_identity(movement_evidence),
            "source_context_adaptation": movement_context,
            "focused_package_scope": {
                "selected_page_id": "page_008",
                "source_page_number": 7,
                "persisted_page_index": MOVEMENT_PAGE,
                "source_handoff_pages": 22,
                "selection_frozen_before_execution": True,
            },
            "evidence_candidate": candidate,
            "target": {
                "page": MOVEMENT_PAGE,
                "system": MOVEMENT_SYSTEM,
                "candidate_id": MOVEMENT_CANDIDATE_ID,
            },
            "expected_boundary_effect": {
                "baseline_first_measure_number": visible_numbers(movement_page, MOVEMENT_SYSTEM)[0],
                "after_reviewed_boundary_first_measure_number": 1,
            },
            "expected_unresolved_effect": {
                "unreviewed_candidate_is_not_applied": True,
                "first_measure_number_remains": visible_numbers(movement_page, MOVEMENT_SYSTEM)[0],
            },
        }
    else:
        movement_record = {
            "status": "blocked",
            "reason": "No --movement-review retained package provided; movement boundary and unresolved-candidate gates cannot be claimed.",
        }
    model = configured_model_identity(repo_root, source_run)
    plan = {
        "schema_version": 1,
        "issue": 397,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "run_root": str(source_run),
            "run_id": manifest.get("run_id"),
            "manifest": file_identity(manifest_path),
            "handoff": file_identity(handoff_path),
            "source_commit": manifest.get("source_commit") or manifest.get("commit"),
            "source_commit_status": "recorded_from_manifest"
            if manifest.get("source_commit") or manifest.get("commit")
            else "not_recorded_in_source_manifest",
            "current_checkout_commit": candidate_provenance["current_checkout_commit"],
            "operator_candidate_commit": candidate_provenance["operator_candidate_commit"],
            "candidate_commit": candidate_provenance["candidate_commit"],
            "candidate_commit_source": candidate_provenance["candidate_commit_source"],
            "source_package_inventory": _inventory_tree(source_review),
        },
        "runtime": capture_runtime_identity(repo_root, model, runtime_identity),
        "source_context_adaptation": source_context,
        "acceptance_inputs": {
            "mmr": {
                "package_page": 0,
                "correction_type": "mmr_measure_span",
                "items": [MMR_ITEM],
                "expected": {
                    "visible_system_1_measure_2_number": 3,
                    "baseline": baseline_numbers_sys0[1],
                    "pdf_row_index": 1,
                    "pdf_row_start": 7,
                },
            },
            "barline": {
                "package_page": 0,
                "correction_type": "barline_construction",
                "items": [BARLINE_ITEM],
                "expected": {
                    "total_measures": total_measures(baseline) - 1,
                    "baseline_total_measures": total_measures(baseline),
                    "affected_visible_system": 10,
                    "target_bbox": BARLINE_TARGET,
                    "pdf_row_index": 10,
                    "pdf_row_start": 83,
                },
            },
            "movement": movement_record,
        },
        "source_artifact_reuse": {
            "pdf_render": "retained; no image rendering",
            "detector_homr_cnn": "retained; no inference intended",
            "numbering_base": file_identity(
                source_run / "intermediate/page_001/numbering_base.json"
            ),
        },
        "scope_guards": {
            "source_run_read_only": True,
            "only_source_artifact_root_is_rebased_to_exact_host_absolute_path_in_package_copy": True,
            "correction_packages_are_copied_under_evidence_root": True,
            "production_detector_homr_mmr_grouping_not_retuned": True,
        },
        "procedure": [
            "Copy review package(s) under evidence root and freeze source/runtime/correction inputs.",
            "Open copied handoff with tools.review_correction.server.create_server.",
            "Use HTTP GET /api/state and POST /api/save; verify recorded/not-applied before POST /api/apply with {}.",
            "GET /api/result and compare corrected numbering JSON to the frozen expected effect.",
            "Exercise stale and failed-apply preservation on a copied scenario only.",
        ],
    }
    return plan


def prepare(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    source_run = args.source_run.resolve()
    evidence_root = args.evidence_root.resolve()
    repo_root = args.repo_root.resolve()
    artifact_repo_root = (
        args.artifact_repo_root.resolve()
        if args.artifact_repo_root
        else infer_artifact_repo_root(source_run)
    )
    # Validate provenance before creating the evidence root or copying any artifacts.
    candidate_provenance = candidate_commit_provenance(repo_root)
    if evidence_root.exists() and any(evidence_root.iterdir()):
        raise FileExistsError(
            f"Evidence root must be absent or empty before freeze: {evidence_root}"
        )
    evidence_root.mkdir(parents=True, exist_ok=True)
    source_context = _prepare_source_context(
        source_run=source_run,
        context_root=evidence_root / "source_context" / "source",
        repo_root=repo_root,
        artifact_repo_root=artifact_repo_root,
    )
    movement_context = None
    if args.movement_review:
        movement_root = Path(
            load_json(args.movement_review.resolve() / "review/manual_correction_input.json")[
                "source_artifact_root"
            ]
        ).resolve()
        movement_context = _prepare_source_context(
            source_run=movement_root,
            context_root=evidence_root / "source_context" / "movement",
            repo_root=repo_root,
            artifact_repo_root=infer_artifact_repo_root(movement_root),
            page_ids={"page_008"},
        )
    plan = freeze_plan(
        source_run=source_run,
        evidence_root=evidence_root,
        repo_root=repo_root,
        movement_review=args.movement_review,
        runtime_identity=args.runtime_identity,
        source_context=source_context,
        movement_context=movement_context,
        candidate_provenance=candidate_provenance,
    )
    # Freeze first. No server creation, correction write, or apply happens before this file exists.
    write_json(evidence_root / "acceptance_plan.json", plan)
    source_copy = evidence_root / "packages" / "source"
    source_copy_info = _copy_package(
        source_run / "review",
        source_copy,
        Path(source_context["context_root"]),
        repo_root=repo_root,
    )
    movement_copy_info = None
    if args.movement_review:
        movement_source_review = args.movement_review.resolve() / "review"
        Path(plan["acceptance_inputs"]["movement"]["source_root"])
        movement_evidence = (
            args.movement_review.resolve() / "review/movement_boundary_evidence.json"
        )
        movement_copy_info = _copy_package(
            movement_source_review,
            evidence_root / "packages" / "movement",
            Path(movement_context["context_root"]),
            movement_evidence=movement_evidence,
            repo_root=repo_root,
            movement_page_subset=MOVEMENT_PAGE,
        )
    metadata = {"source_package": source_copy_info, "movement_package": movement_copy_info}
    write_json(evidence_root / "package_preparation.json", metadata)
    return evidence_root, plan


def _request(
    base_url: str, path: str, *, payload: dict[str, Any] | None = None, timeout: int = 900
) -> tuple[int, dict[str, Any] | bytes, str]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(
        base_url + path, data=body, headers=headers, method="POST" if body is not None else "GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read()
            content_type = response.headers.get("Content-Type", "")
            if "json" in content_type:
                return response.status, json.loads(data), content_type
            return response.status, data, content_type
    except urllib.error.HTTPError as exc:
        return (
            exc.code,
            exc.read().decode("utf-8", errors="replace"),
            exc.headers.get("Content-Type", ""),
        )
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        return 0, str(exc), ""


@dataclass
class AppSession:
    server: Any
    base_url: str
    thread: threading.Thread

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def start_app_session(repo_root: Path, handoff: Path) -> AppSession:
    sys.path.insert(0, str(repo_root))
    from tools.review_correction.server import create_server

    server = create_server(handoff, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return AppSession(server, f"http://127.0.0.1:{server.server_port}", thread)


def state_values(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"raw": payload}
    package = payload.get("package", {})
    statuses = [
        entry.get("application_status")
        for entry in payload.get("states", [])
        if isinstance(entry, dict)
    ]
    record = [
        entry.get("recording_status")
        for entry in payload.get("states", [])
        if isinstance(entry, dict)
    ]
    return {
        "package_status": package.get("status"),
        "counts": package.get("counts"),
        "application_statuses": statuses,
        "recording_statuses": record,
        "current_result": package.get("current_result"),
        "last_successful_result": package.get("last_successful_result"),
        "current_identity": package.get("current_identity"),
        "states": payload.get("states", []),
        "labels": payload.get("labels", {}),
    }


def expect_http(
    status: int, expected: set[int], gate: dict[str, Any], label: str, body: Any
) -> bool:
    okay = status in expected
    gate.setdefault("steps", []).append(
        {
            "step": label,
            "http_status": status,
            "expected_http_statuses": sorted(expected),
            "response": body if isinstance(body, (dict, str)) else {"bytes": len(body)},
        }
    )
    return okay


def _state(
    session: AppSession, gate: dict[str, Any], phase: str, timeout: int
) -> dict[str, Any] | None:
    status, payload, _ = _request(session.base_url, "/api/state", timeout=timeout)
    if not expect_http(status, {200}, gate, f"state:{phase}", payload):
        gate["status"] = "blocked" if status in (0, 404) else "failed"
        gate["reason"] = f"GET /api/state returned HTTP {status}: {payload}"
        return None
    result = state_values(payload)
    gate.setdefault("states", {})[phase] = result
    return result


def _save(
    session: AppSession, gate: dict[str, Any], kind: str, page: int, items: list[dict], timeout: int
) -> bool:
    status, payload, _ = _request(
        session.base_url,
        "/api/save",
        payload={"page": page, "correction_type": kind, "items": items},
        timeout=timeout,
    )
    return expect_http(status, {200}, gate, f"save:{kind}:page{page}", payload)


def _apply(
    session: AppSession, gate: dict[str, Any], timeout: int, *, expect_failure: bool = False
) -> tuple[bool, Any]:
    status, payload, _ = _request(session.base_url, "/api/apply", payload={}, timeout=timeout)
    if not expect_http(status, {200}, gate, "apply_acknowledged", payload):
        return False, payload
    deadline = time.monotonic() + timeout
    last_state = None
    while time.monotonic() < deadline:
        last_state = _state(session, gate, "apply_poll", min(timeout, 15))
        if last_state is None:
            return False, payload
        if (
            last_state["package_status"] == "applying"
            or "applying" in last_state["application_statuses"]
        ):
            time.sleep(2)
            continue
        current_result = last_state.get("current_result")
        current_identity = last_state.get("current_identity")
        statuses = last_state.get("application_statuses", [])
        succeeded = (
            bool(current_result)
            and bool(current_identity)
            and "applying" not in statuses
            and "error" not in statuses
            and current_result.get("identity") == current_identity.get("identity")
        )
        failed = (
            last_state["package_status"] == "error" or "error" in last_state["application_statuses"]
        )
        if succeeded or failed:
            terminal = "success" if succeeded else "error"
            gate["apply_terminal"] = {
                "status": terminal,
                "last_successful_result": last_state.get("last_successful_result"),
                "current_identity": last_state.get("current_identity"),
            }
            return (not expect_failure) if succeeded else expect_failure, payload
        time.sleep(2)
    gate["apply_terminal"] = {
        "status": "blocked",
        "reason": "Timed out waiting for /api/state to leave applying",
        "last_state": last_state,
    }
    return False, payload


def _result(session: AppSession, gate: dict[str, Any], timeout: int) -> tuple[bool, Any]:
    status, payload, content_type = _request(session.base_url, "/api/result", timeout=timeout)
    okay = expect_http(status, {200}, gate, "result", payload)
    if okay and isinstance(payload, bytes):
        pdf_path = Path(gate["evidence_root"]) / "final_pdf" / f"{gate['name']}.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(payload)
        gate["final_pdf"] = {
            "path": str(pdf_path),
            "sha256": sha256(pdf_path),
            "bytes": pdf_path.stat().st_size,
            "content_type": content_type,
        }
        okay = payload.startswith(b"%PDF-")
        gate["final_pdf"]["signature_valid"] = okay
    else:
        gate["result_response"] = payload
    return okay, payload


def _extract_run_dir(apply_payload: Any, state: dict[str, Any] | None) -> Path | None:
    candidates: list[Any] = []
    if isinstance(apply_payload, dict):
        for key in ("output_dir", "run_dir", "corrected_run_dir", "corrected_run"):
            candidates.append(apply_payload.get(key))
        nested = apply_payload.get("summary")
        if isinstance(nested, dict):
            candidates.extend(
                nested.get(key)
                for key in ("output_dir", "run_dir", "corrected_run_dir", "corrected_run")
            )
    current = (
        (state.get("current_result") or state.get("last_successful_result")) if state else None
    )
    if isinstance(current, dict):
        candidates.extend(
            current.get(key)
            for key in ("output_dir", "run_dir", "corrected_run_dir", "corrected_run")
        )
    for candidate in candidates:
        if isinstance(candidate, str) and Path(candidate).is_dir():
            return Path(candidate).resolve()
    return None


def _load_numbering(
    run_dir: Path | None, page_id: str, fallback_path: Path, page_index: int = 0
) -> dict[str, Any] | None:
    if run_dir:
        for candidate in (
            run_dir / "outputs" / page_id / "numbering_final.json",
            run_dir / "outputs" / "page_001" / "numbering_final.json",
        ):
            if candidate.is_file():
                try:
                    return numbering_page(candidate, page_index)
                except (ValueError, KeyError):
                    pass
    return None


def verify_pdf_content(
    gate: dict[str, Any], run_dir: Path, page_id: str, row_index: int, expected_number: int
) -> bool:
    """Check frozen label semantics and the actual PDF's embedded raster bytes."""
    import hashlib
    import io

    import fitz

    from src.pipeline.review.final_output import _render_final_page_image

    summary = load_json(run_dir / "review/corrected_final_summary.json")
    clean_final = all(path.suffix == ".pdf" for path in (run_dir / "final").iterdir())
    pages = summary["pages"]
    page_index = next(i for i, page in enumerate(pages) if page["page_id"] == page_id)
    page = pages[page_index]
    image, labels = _render_final_page_image(
        source_image_path=Path(page["source_image"]),
        numbering_path=Path(page["corrected_numbering_final"]),
        page_id=page_id,
        page_number=page["page_number"],
    )
    try:
        encoded = io.BytesIO()
        image.save(encoded, format="JPEG")
        expected_hash = hashlib.sha256(encoded.getvalue()).hexdigest()
        with fitz.open(gate["final_pdf"]["path"]) as pdf:
            embedded = pdf[page_index].get_images(full=True)
            actual_hashes = [
                hashlib.sha256(pdf.extract_image(item[0])["image"]).hexdigest() for item in embedded
            ]
            label_number = labels[row_index]["row_start_measure_number"]
            okay = (
                clean_final
                and len(pdf) == len(pages)
                and label_number == expected_number
                and expected_hash in actual_hashes
            )
            evidence = Path(gate["evidence_root"]) / "pdf-render.png"
            pdf[page_index].get_pixmap(matrix=fitz.Matrix(0.5, 0.5)).save(evidence)
            gate["pdf_content"] = {
                "passed": okay,
                "clean_final": clean_final,
                "page_count": len(pdf),
                "row_index": row_index,
                "expected_row_start": expected_number,
                "observed_row_start": label_number,
                "expected_jpeg_sha256": expected_hash,
                "embedded_jpeg_sha256": actual_hashes,
                "render": str(evidence),
            }
            return okay
    finally:
        image.close()


def run_single_correction(
    *,
    repo_root: Path,
    handoff: Path,
    gate_root: Path,
    name: str,
    kind: str,
    page: int,
    items: list[dict],
    timeout: int,
    expected: dict[str, Any],
    baseline_path: Path,
    page_id: str = "page_001",
    page_index: int = 0,
    system_index: int = 0,
    effect: str = "mmr",
) -> dict[str, Any]:
    gate: dict[str, Any] = {
        "name": name,
        "evidence_root": str(gate_root),
        "status": "running",
        "correction": {"correction_type": kind, "page": page, "items": items},
        "expected": expected,
        "steps": [],
        "judgment": "not yet determined",
    }
    session = start_app_session(repo_root, handoff)
    try:
        initial = _state(session, gate, "before_save", timeout)
        if initial is None:
            return gate
        if not _save(session, gate, kind, page, items, timeout):
            gate["status"] = (
                "blocked" if any(step["http_status"] == 404 for step in gate["steps"]) else "failed"
            )
            return gate
        if kind == "movement_boundary":
            status, payload, _ = _request(
                session.base_url, "/api/export_movement_boundaries", payload={}, timeout=timeout
            )
            if not expect_http(status, {200}, gate, "finalize_movement_review", payload):
                gate["status"] = "failed"
                gate["reason"] = (
                    "Movement review could not be finalized through the review application API."
                )
                return gate
        recorded = _state(session, gate, "recorded_before_apply", timeout)
        if recorded is None:
            return gate
        gate["recorded_not_applied_check"] = {
            "application_statuses": recorded["application_statuses"],
            "current_result_identity": recorded["current_result"],
            "expected": "correction is recorded while the current result is absent or still not-current for this new correction set",
        }
        if (
            "recorded" not in recorded["recording_statuses"]
            or recorded["current_result"] is not None
            or "current" in recorded["application_statuses"]
        ):
            gate["status"] = "failed"
            gate["reason"] = "Recorded correction was incorrectly reported as applied."
            return gate
        applied, apply_payload = _apply(session, gate, timeout)
        gate["apply_response"] = apply_payload
        if not applied:
            gate["status"] = (
                "blocked"
                if any(step["http_status"] in (0, 404) for step in gate["steps"][-1:])
                else "failed"
            )
            gate["reason"] = "Authoritative /api/apply {} route did not complete successfully."
            return gate
        current = _state(session, gate, "after_apply", timeout)
        if current is None:
            return gate
        result_ok, result_payload = _result(session, gate, timeout)
        run_dir = _extract_run_dir(apply_payload, current)
        gate["corrected_run_dir"] = str(run_dir) if run_dir else None
        if run_dir:
            corrected_path = run_dir / "outputs" / page_id / "numbering_final.json"
            if corrected_path.is_file():
                corrected = numbering_page(corrected_path, 0)
                baseline = numbering_page(baseline_path, 0)
                if effect == "mmr":
                    actual = visible_numbers(corrected, system_index)
                    gate["observed"] = {
                        "system_numbers": actual,
                        "second_visible_measure_number": actual[1] if len(actual) > 1 else None,
                        "baseline_system_numbers": visible_numbers(baseline, system_index),
                    }
                    gate["effect_pass"] = (
                        len(actual) > 1
                        and actual[1] == expected["visible_system_1_measure_2_number"]
                    )
                elif effect == "barline":
                    actual = total_measures(corrected)
                    gate["observed"] = {
                        "total_measures": actual,
                        "baseline_total_measures": total_measures(baseline),
                    }
                    gate["effect_pass"] = actual == expected["total_measures"]
                else:
                    actual = visible_numbers(corrected, system_index)
                    gate["observed"] = {
                        "system_numbers": actual,
                        "first_measure_number": actual[0] if actual else None,
                    }
                    gate["effect_pass"] = bool(actual) and actual[0] == expected.get(
                        "first_measure_number"
                    )
            else:
                gate["numbering_observation"] = {
                    "status": "blocked",
                    "reason": "Apply response did not identify a corrected run with outputs/<page>/numbering_final.json.",
                }
        else:
            gate["numbering_observation"] = {
                "status": "blocked",
                "reason": "Apply response/state did not expose corrected run directory; no numbering file was guessed or selected by recency.",
            }
        gate["corrected_result_state"] = current
        pdf_content_ok = (
            bool(run_dir)
            and result_ok
            and verify_pdf_content(
                gate, run_dir, page_id, expected["pdf_row_index"], expected["pdf_row_start"]
            )
        )
        gate["result_pass"] = result_ok and pdf_content_ok
        if gate.get("effect_pass") and gate["result_pass"]:
            gate["status"] = "passed"
            gate["judgment"] = "Observable numbering effect and corrected result both verified."
        else:
            gate["status"] = (
                "blocked"
                if not gate.get("effect_pass")
                and gate.get("numbering_observation", {}).get("status") == "blocked"
                else "failed"
            )
            gate["judgment"] = "Acceptance effect not established."
        return gate
    finally:
        session.close()


def _extract_identity(state: dict[str, Any] | None) -> Any:
    if not state:
        return None
    result = state.get("last_successful_result") or state.get("current_result")
    if not isinstance(result, dict):
        return result
    return {
        key: result.get(key)
        for key in (
            "identity",
            "result_identity",
            "run_id",
            "final_pdf_sha256",
            "source_identity",
            "corrections_identity",
            "output_dir",
            "final_pdf",
        )
        if key in result
    }


def run_stale_gate(
    *,
    repo_root: Path,
    handoff: Path,
    gate_root: Path,
    timeout: int,
    successful_handoff_gate: dict[str, Any],
) -> dict[str, Any]:
    gate: dict[str, Any] = {
        "name": "stale_and_failed_apply",
        "evidence_root": str(gate_root),
        "status": "running",
        "steps": [],
    }
    session = start_app_session(repo_root, handoff)
    try:
        before = _state(session, gate, "after_prior_success", timeout)
        if before is None:
            return gate
        prior_identity = _extract_identity(before)
        gate["prior_successful_result_identity"] = prior_identity
        # Removing the recorded MMR correction must stale the prior result without deleting its identity.
        if not _save(session, gate, "mmr_measure_span", 0, [], timeout):
            gate["status"] = "blocked"
            gate["reason"] = "Could not record correction removal"
            return gate
        stale = _state(session, gate, "after_removal", timeout)
        if stale is None:
            return gate
        gate["stale_state"] = stale
        still_same_identity = bool(prior_identity) and _extract_identity(stale) == prior_identity
        gate["stale_identity_preserved"] = (
            still_same_identity
            and stale["current_result"] is None
            and "stale" in stale["application_statuses"]
        )
        # This malformed operation is isolated to the copied package and induces a later apply failure.
        invalid_item = {
            "op": "set_measure_span",
            "page": 0,
            "system": 0,
            "measure": 0,
            "reason": "Issue 397 isolated invalid-apply probe",
        }
        if not _save(session, gate, "mmr_measure_span", 0, [invalid_item], timeout):
            gate["status"] = "blocked"
            gate["reason"] = "Could not record isolated invalid-apply probe"
            return gate
        failure_expected, failure_payload = _apply(session, gate, timeout, expect_failure=True)
        gate["induced_failed_apply"] = failure_payload
        after_failure = _state(session, gate, "after_failed_apply", timeout)
        if after_failure is None:
            return gate
        gate["after_failure"] = after_failure
        gate["failed_apply_preserved_identity"] = (
            bool(prior_identity) and _extract_identity(after_failure) == prior_identity
        )
        pdf_ok, pdf_payload = _result(session, gate, timeout)
        gate["previous_result_remains_discoverable"] = pdf_ok
        if (
            failure_expected
            and gate["stale_identity_preserved"]
            and gate["failed_apply_preserved_identity"]
            and pdf_ok
        ):
            gate["status"] = "passed"
            gate["judgment"] = (
                "Correction removal marked prior output stale; later failed apply retained the prior successful result identity and result artifact."
            )
        else:
            gate["status"] = "failed"
            gate["judgment"] = (
                "Stale/failed-apply identity contract did not satisfy all expected gates."
            )
        return gate
    finally:
        session.close()


def run_acceptance(
    args: argparse.Namespace, evidence_root: Path, plan: dict[str, Any]
) -> dict[str, Any]:
    repo_root = args.repo_root.resolve()
    packages = evidence_root / "packages"
    source_handoff = packages / "source/manual_correction_input.json"
    source_run = args.source_run.resolve()
    base_numbering = source_run / "outputs/page_001/numbering_final.json"
    numbering_page(base_numbering)
    results: dict[str, Any] = {
        "schema_version": 1,
        "issue": 397,
        "plan": str(evidence_root / "acceptance_plan.json"),
        "gates": {},
    }
    baseline_gate = {
        "name": "responsibility_boundary_and_baseline_api",
        "evidence_root": str(evidence_root),
        "status": "running",
        "steps": [],
    }
    session = start_app_session(repo_root, source_handoff)
    try:
        status, payload, _ = _request(session.base_url, "/api/state", timeout=args.timeout)
        baseline_gate["status"] = (
            "passed" if status == 200 else ("blocked" if status in (0, 404) else "failed")
        )
        baseline_gate["steps"].append(
            {"step": "initial_state", "http_status": status, "response": payload}
        )
        status_pages, pages, _ = _request(session.base_url, "/api/pages", timeout=args.timeout)
        baseline_gate["steps"].append(
            {"step": "page_navigation_data", "http_status": status_pages, "response": pages}
        )
        if status_pages == 200 and isinstance(pages, dict):
            baseline_gate["user_pages"] = len(pages.get("pages", []))
        # These denied routes prove developer/GT modes are not reachable from this entry.
        for path in ("/gt", "/api/gt", "/api/rest_relabel", "/api/config?path=/etc/passwd"):
            denied, body, _ = _request(session.base_url, path, timeout=args.timeout)
            baseline_gate["steps"].append(
                {
                    "step": f"boundary_probe:{path}",
                    "http_status": denied,
                    "expected": "404/403",
                    "response": body,
                }
            )
            if denied not in (403, 404):
                baseline_gate["status"] = "failed"
        for route, body in (
            ("/api/apply", {"handoff": "/etc/passwd"}),
            ("/api/apply", {"output_root": "/tmp/another_package"}),
            ("/api/save", {"page": 0, "correction_type": "gt", "items": []}),
            (
                "/api/save",
                {"page": "another_package", "correction_type": "mmr_measure_span", "items": []},
            ),
        ):
            denied, response, _ = _request(
                session.base_url, route, payload=body, timeout=args.timeout
            )
            if not expect_http(denied, {400}, baseline_gate, "reject_substitution", response):
                baseline_gate["status"] = "failed"
        results["gates"][baseline_gate["name"]] = baseline_gate
    finally:
        session.close()

    mmr_root = evidence_root / "packages/source"
    mmr_plan = plan["acceptance_inputs"]["mmr"]
    results["gates"]["mmr"] = run_single_correction(
        repo_root=repo_root,
        handoff=mmr_root / "manual_correction_input.json",
        gate_root=evidence_root / "apply/mmr",
        name="mmr_span",
        kind="mmr_measure_span",
        page=0,
        items=mmr_plan["items"],
        timeout=args.timeout,
        expected=mmr_plan["expected"],
        baseline_path=base_numbering,
        page_id="page_001",
        system_index=0,
        effect="mmr",
    )
    barline_plan = plan["acceptance_inputs"]["barline"]
    # Rebuild a clean copy so the independent barline gate starts from the frozen source set.
    barline_handoff = clone_clean_package(mmr_root, evidence_root / "packages/barline", repo_root)
    results["gates"]["barline"] = run_single_correction(
        repo_root=repo_root,
        handoff=barline_handoff,
        gate_root=evidence_root / "apply/barline",
        name="barline_remove",
        kind="barline_construction",
        page=0,
        items=barline_plan["items"],
        timeout=args.timeout,
        expected=barline_plan["expected"],
        baseline_path=base_numbering,
        page_id="page_001",
        system_index=0,
        effect="barline",
    )
    movement_plan = plan["acceptance_inputs"]["movement"]
    if movement_plan.get("status") == "prepared":
        movement_handoff = evidence_root / "packages/movement/manual_correction_input.json"
        movement_base_run = Path(movement_plan["source_root"])
        movement_base_run / "outputs/page_008/numbering_final.json"
        movement_package_baseline = (
            evidence_root / "packages/movement/pages/page_008/numbering_final.json"
        )
        load_json(movement_package_baseline)
        movement_plan["evidence_candidate"]
        target = {
            "op": "boundary",
            "page": MOVEMENT_PAGE,
            "system": MOVEMENT_SYSTEM,
            "reason": "Issue 397 acceptance: confirm retained boundary candidate",
            "evidence_candidate_id": MOVEMENT_CANDIDATE_ID,
            "review_kind": "accepted_candidate",
        }
        movement_gate = run_single_correction(
            repo_root=repo_root,
            handoff=movement_handoff,
            gate_root=evidence_root / "apply/movement",
            name="movement_boundary",
            kind="movement_boundary",
            page=MOVEMENT_PAGE,
            items=[target],
            timeout=args.timeout,
            expected={
                "first_measure_number": 1,
                "pdf_row_index": MOVEMENT_SYSTEM,
                "pdf_row_start": 1,
            },
            baseline_path=movement_package_baseline,
            page_id="page_008",
            page_index=0,
            system_index=MOVEMENT_SYSTEM,
            effect="movement",
        )
        # An unresolved candidate case uses another pristine copy: no accepted/rejected decisions are recorded.
        unresolved_handoff = clone_clean_package(
            evidence_root / "packages/movement",
            evidence_root / "packages/movement_unresolved",
            repo_root,
        )
        unresolved_gate = run_no_correction_apply(
            repo_root=repo_root,
            handoff=unresolved_handoff,
            gate_root=evidence_root / "apply/movement_unresolved",
            timeout=args.timeout,
            baseline_path=movement_package_baseline,
            page_id="page_008",
            page_index=6,
            system_index=MOVEMENT_SYSTEM,
            expected_first=movement_plan["expected_unresolved_effect"][
                "first_measure_number_remains"
            ],
        )
        movement_gate["unresolved_candidate_gate"] = unresolved_gate
        if movement_gate["status"] == "passed" and unresolved_gate["status"] != "passed":
            movement_gate["status"] = unresolved_gate["status"]
        results["gates"]["movement"] = movement_gate
    else:
        results["gates"]["movement"] = {
            "name": "movement",
            "status": "blocked",
            "reason": movement_plan.get("reason"),
            "judgment": "No movement result is claimed.",
        }

    stale_handoff = clone_clean_package(mmr_root, evidence_root / "packages/stale_probe", repo_root)
    stale_success = run_single_correction(
        repo_root=repo_root,
        handoff=stale_handoff,
        gate_root=evidence_root / "apply/stale_probe_first_success",
        name="stale_probe_seed",
        kind="mmr_measure_span",
        page=0,
        items=mmr_plan["items"],
        timeout=args.timeout,
        expected=mmr_plan["expected"],
        baseline_path=base_numbering,
        page_id="page_001",
        system_index=0,
        effect="mmr",
    )
    if stale_success["status"] == "passed":
        results["gates"]["stale_result"] = run_stale_gate(
            repo_root=repo_root,
            handoff=stale_handoff,
            gate_root=evidence_root / "apply/stale_probe_followup",
            timeout=args.timeout,
            successful_handoff_gate=stale_success,
        )
    else:
        results["gates"]["stale_result"] = {
            "name": "stale_result",
            "status": "blocked",
            "reason": "Requires a successful initial result; see stale_probe_seed gate.",
        }
    return results


def clone_clean_package(source_package: Path, destination: Path, repo_root: Path) -> Path:
    if destination.exists():
        raise FileExistsError(f"Refusing to replace package copy: {destination}")
    shutil.copytree(source_package, destination, symlinks=True)
    correction_root = destination / "corrections"
    correction_root.mkdir(exist_ok=True)
    for path in correction_root.glob("*.json"):
        path.unlink()
    return destination / "manual_correction_input.json"


def run_no_correction_apply(
    *,
    repo_root: Path,
    handoff: Path,
    gate_root: Path,
    timeout: int,
    baseline_path: Path,
    page_id: str,
    page_index: int,
    system_index: int,
    expected_first: int,
) -> dict[str, Any]:
    gate = {
        "name": "unresolved_candidate_no_reset",
        "evidence_root": str(gate_root),
        "status": "running",
        "steps": [],
        "expected_first_measure_number": expected_first,
    }
    handoff_data = load_json(handoff)
    evidence_rel = handoff_data.get("movement_boundary_evidence")
    evidence = load_json(handoff.parent / evidence_rel) if evidence_rel else {}
    candidate = next(
        (
            item
            for item in evidence.get("candidates", [])
            if item.get("id") == MOVEMENT_CANDIDATE_ID
        ),
        None,
    )
    gate["candidate_before_apply"] = candidate
    if not candidate or candidate.get("state") != "ambiguous_review_required":
        gate["status"] = "blocked"
        gate["reason"] = "Frozen unresolved candidate is absent from the copied package."
        return gate
    session = start_app_session(repo_root, handoff)
    try:
        before = _state(session, gate, "before_apply", timeout)
        if before is None:
            return gate
        okay, apply_payload = _apply(session, gate, timeout)
        if not okay:
            gate["status"] = "blocked"
            gate["reason"] = "Could not apply pristine package through user app API"
            return gate
        after = _state(session, gate, "after_apply", timeout)
        result_ok, _ = _result(session, gate, timeout)
        run_dir = _extract_run_dir(apply_payload, after)
        corrected_path = run_dir / "outputs" / page_id / "numbering_final.json" if run_dir else None
        if not corrected_path or not corrected_path.is_file():
            gate["status"] = "blocked"
            gate["reason"] = "Corrected numbering path is not identified by apply result metadata"
            return gate
        actual = visible_numbers(numbering_page(corrected_path, 0), system_index)[0]
        baseline = visible_numbers(numbering_page(baseline_path, 0), system_index)[0]
        gate["observed_first_measure_number"] = actual
        gate["baseline_first_measure_number"] = baseline
        gate["unresolved_candidate_is_present"] = True
        result_ok = result_ok and verify_pdf_content(
            gate, run_dir, page_id, system_index, expected_first
        )
        gate["result_available"] = result_ok
        gate["status"] = "passed" if actual == expected_first and result_ok else "failed"
        gate["judgment"] = (
            "An unresolved candidate did not create a numbering reset."
            if gate["status"] == "passed"
            else "Observed numbering differs from the frozen no-reset expectation."
        )
        return gate
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-run",
        type=Path,
        required=True,
        help="Retained run root containing manifest.json and review/manual_correction_input.json",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        required=True,
        help="Fresh logs/issue397/acceptance/<run> destination",
    )
    parser.add_argument(
        "--movement-review",
        type=Path,
        help="Optional retained review-package root containing review/movement_boundary_evidence.json",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="PDFScoreBar checkout used for app/API and source identity",
    )
    parser.add_argument(
        "--artifact-repo-root",
        type=Path,
        help="Original checkout root used to resolve retained manifest-relative paths; inferred from the source-run path when omitted",
    )
    parser.add_argument(
        "--runtime-identity", help="Explicit runtime/image identity supplied by operator"
    )
    parser.add_argument(
        "--timeout", type=int, default=1800, help="Per HTTP request timeout in seconds"
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Freeze inputs and copy packages without running HTTP acceptance steps",
    )
    args = parser.parse_args()
    try:
        evidence_root, plan = prepare(args)
        if args.prepare_only:
            print(
                json.dumps(
                    {
                        "status": "prepared",
                        "evidence_root": str(evidence_root),
                        "plan": str(evidence_root / "acceptance_plan.json"),
                    },
                    indent=2,
                )
            )
            return 0
        report = run_acceptance(args, evidence_root, plan)
        write_json(evidence_root / "acceptance_report.json", report)
        statuses = [gate.get("status") for gate in report["gates"].values()]
        overall = (
            "passed"
            if statuses and all(status == "passed" for status in statuses)
            else (
                "blocked"
                if any(status == "blocked" for status in statuses)
                and not any(status == "failed" for status in statuses)
                else "failed"
            )
        )
        report["overall_status"] = overall
        write_json(evidence_root / "acceptance_report.json", report)
        print(
            json.dumps(
                {
                    "overall_status": overall,
                    "evidence_root": str(evidence_root),
                    "gates": {name: gate.get("status") for name, gate in report["gates"].items()},
                },
                indent=2,
            )
        )
        return 0 if overall == "passed" else 2
    except Exception as exc:
        if args.evidence_root.is_dir():
            write_json(
                args.evidence_root / "acceptance_error.json",
                {"status": "blocked", "error": str(exc), "exception": type(exc).__name__},
            )
        print(f"acceptance runner blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
