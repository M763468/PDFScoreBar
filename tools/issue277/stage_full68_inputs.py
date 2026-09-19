#!/usr/bin/env python3
"""Materialize retained #294/#264 full68 inputs into a symlink-free runtime tree.

This is experiment/validation infrastructure only. Source JSON files are retained byte-for-byte
under ``raw/``. Runtime JSON copies rewrite only file-reference fields so a read-only Docker mount
can consume a self-contained staging directory without following old-worktree symlinks.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "issue277.full68_input_staging.v1"
EXPECTED_PAGE_COUNT = 68


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _safe_component(value: str) -> str:
    result = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value)
    return result or "unnamed"


def _resolve_retained_path(value: str | Path, issue294_root: Path) -> Path:
    raw = Path(value)
    candidates: list[Path] = [raw]
    if not raw.is_absolute():
        candidates.append(issue294_root / raw)

    text = str(raw)
    if "/workspace/" in text:
        candidates.append(issue294_root / text.split("/workspace/", 1)[1])

    parts = raw.parts
    for marker in ("ws_PDFScoreBar_issue294", "ws_PDFScoreBar"):
        if marker in parts:
            index = parts.index(marker)
            candidates.append(issue294_root.joinpath(*parts[index + 1 :]))
    if "logs" in parts:
        index = parts.index("logs")
        candidates.append(issue294_root.joinpath(*parts[index:]))
    if "data" in parts:
        index = parts.index("data")
        candidates.append(issue294_root.joinpath(*parts[index:]))

    seen: set[str] = set()
    failures: list[str] = []
    for candidate in candidates:
        key = os.fspath(candidate)
        if key in seen:
            continue
        seen.add(key)
        try:
            if candidate.is_file():
                return candidate
        except OSError as error:
            failures.append(f"{candidate}: {error}")
    detail = f"; failures={failures}" if failures else ""
    raise FileNotFoundError(f"Unable to resolve retained path: {raw}{detail}")


class Stager:
    def __init__(self, source_root: Path, output_root: Path) -> None:
        self.source_root = source_root
        self.output_root = output_root
        self.files: list[dict[str, Any]] = []
        self.derived_json: list[dict[str, Any]] = []

    def _record_source_link(self, source: Path) -> dict[str, Any]:
        info: dict[str, Any] = {"source_is_symlink": source.is_symlink()}
        if source.is_symlink():
            try:
                info["source_symlink_target"] = os.readlink(source)
            except OSError as error:
                info["source_symlink_target_error"] = str(error)
        return info

    def copy_exact(self, reference: str | Path, relative_dest: str | Path, *, role: str) -> Path:
        source = _resolve_retained_path(reference, self.source_root)
        destination = self.output_root / Path(relative_dest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)
        source_sha = _sha256(source)
        with source.open("rb") as src, destination.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        staged_sha = _sha256(destination)
        if source_sha != staged_sha:
            raise RuntimeError(f"SHA mismatch while staging {source} -> {destination}")
        if destination.is_symlink():
            raise RuntimeError(f"Staged file unexpectedly became symlink: {destination}")
        lookup_path = source.absolute()
        try:
            resolved_source = source.resolve(strict=True)
            resolved_source_error = None
        except OSError as error:
            resolved_source = None
            resolved_source_error = str(error)
        self.files.append(
            {
                "role": role,
                "source_reference": str(reference),
                "source_lookup_path": str(lookup_path),
                "resolved_source": None if resolved_source is None else str(resolved_source),
                "resolved_source_error": resolved_source_error,
                "source_sha256": source_sha,
                "size": source.stat().st_size,
                "staged_path": str(destination.relative_to(self.output_root)),
                "staged_sha256": staged_sha,
                "byte_preserved": True,
                **self._record_source_link(source),
            }
        )
        return destination

    def write_derived_json(
        self,
        *,
        role: str,
        source_path: Path,
        raw_payload: Any,
        runtime_payload: Any,
        relative_dest: str | Path,
        rewrites: list[dict[str, str]],
    ) -> Path:
        reconstructed = copy.deepcopy(runtime_payload)
        for rewrite in rewrites:
            _set_pointer(reconstructed, rewrite["pointer"], rewrite["source_value"])
        if reconstructed != raw_payload:
            raise RuntimeError(f"Runtime JSON changed non-path semantics for {source_path}")
        destination = self.output_root / Path(relative_dest)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)
        _write_json(destination, runtime_payload)
        self.derived_json.append(
            {
                "role": role,
                "source_path": str(source_path.absolute()),
                "source_sha256": _sha256(source_path),
                "staged_path": str(destination.relative_to(self.output_root)),
                "staged_sha256": _sha256(destination),
                "allowed_rewrites": rewrites,
                "non_path_semantics_equal": True,
            }
        )
        return destination


def _set_pointer(payload: Any, pointer: str, value: Any) -> None:
    if not pointer.startswith("/"):
        raise ValueError(pointer)
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]
    current = payload
    for part in parts[:-1]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    leaf = parts[-1]
    if isinstance(current, list):
        current[int(leaf)] = value
    else:
        current[leaf] = value


def _pointer(*parts: str | int) -> str:
    encoded = []
    for part in parts:
        text = str(part).replace("~", "~0").replace("/", "~1")
        encoded.append(text)
    return "/" + "/".join(encoded)


def _stage_support(
    stager: Stager,
    source_reference: str,
    *,
    page_token: str,
) -> str:
    source = _resolve_retained_path(source_reference, stager.source_root)
    stager.copy_exact(
        source_reference,
        Path("raw/support") / f"{page_token}.json",
        role="support_result_raw",
    )
    raw_payload = _load_json(source)
    if not isinstance(raw_payload, Mapping):
        raise ValueError(f"Support result is not an object: {source}")
    runtime = copy.deepcopy(raw_payload)
    rewrites: list[dict[str, str]] = []
    for key in ("connector_symbols", "connector_brace_dot", "current_homr_staff_mask"):
        if key not in raw_payload:
            raise ValueError(f"Support result lacks {key}: {source}")
        src_ref = str(raw_payload[key])
        suffix = Path(src_ref).suffix or ".bin"
        staged = stager.copy_exact(
            src_ref,
            Path("runtime/assets") / page_token / f"{key}{suffix}",
            role=key,
        )
        staged_rel = str(staged.relative_to(stager.output_root))
        runtime[key] = staged_rel
        rewrites.append(
            {"pointer": _pointer(key), "source_value": src_ref, "staged_value": staged_rel}
        )
    runtime_path = stager.write_derived_json(
        role="support_result_runtime",
        source_path=source,
        raw_payload=raw_payload,
        runtime_payload=runtime,
        relative_dest=Path("runtime/support") / f"{page_token}.json",
        rewrites=rewrites,
    )
    return str(runtime_path.relative_to(stager.output_root))


def _stage_matrix_report(
    stager: Stager,
    source_reference: str,
    *,
    chunk_index: int,
) -> tuple[str, int]:
    source = _resolve_retained_path(source_reference, stager.source_root)
    stager.copy_exact(
        source_reference,
        Path("raw/matrix_reports") / f"chunk_{chunk_index:03d}.json",
        role="matrix_report_raw",
    )
    raw_payload = _load_json(source)
    if not isinstance(raw_payload, Mapping) or not isinstance(raw_payload.get("pages"), list):
        raise ValueError(f"Matrix report lacks pages: {source}")
    runtime = copy.deepcopy(raw_payload)
    rewrites: list[dict[str, str]] = []
    seen_page_tokens: set[str] = set()

    for page_index, page in enumerate(raw_payload["pages"]):
        if not isinstance(page, Mapping):
            raise ValueError(f"Malformed matrix page {page_index}: {source}")
        image_ref = str(page["image"])
        image_path = Path(image_ref)
        score = _safe_component(image_path.parent.name)
        page_name = _safe_component(image_path.stem)
        page_token = f"{score}__{page_name}"
        if page_token in seen_page_tokens:
            raise RuntimeError(f"Duplicate page token in matrix report: {page_token}")
        seen_page_tokens.add(page_token)

        image_suffix = image_path.suffix or ".png"
        staged_image = stager.copy_exact(
            image_ref,
            Path("runtime/data/evaluation2/images") / score / f"{page_name}{image_suffix}",
            role="page_image",
        )
        image_rel = str(staged_image.relative_to(stager.output_root))
        runtime["pages"][page_index]["image"] = image_rel
        rewrites.append(
            {
                "pointer": _pointer("pages", page_index, "image"),
                "source_value": image_ref,
                "staged_value": image_rel,
            }
        )

        support_ref = str(page["fixed_inputs"]["support_result"])
        support_rel = _stage_support(stager, support_ref, page_token=page_token)
        runtime["pages"][page_index]["fixed_inputs"]["support_result"] = support_rel
        rewrites.append(
            {
                "pointer": _pointer("pages", page_index, "fixed_inputs", "support_result"),
                "source_value": support_ref,
                "staged_value": support_rel,
            }
        )

        variant = page["modes"]["candidate_native_geometry"]["variants"]["B_b377"]
        staff_ref = str(variant["staff_mask"])
        staff_suffix = Path(staff_ref).suffix or ".png"
        staged_staff = stager.copy_exact(
            staff_ref,
            Path("runtime/assets") / page_token / f"candidate_staff_mask{staff_suffix}",
            role="candidate_staff_mask",
        )
        staff_rel = str(staged_staff.relative_to(stager.output_root))
        runtime["pages"][page_index]["modes"]["candidate_native_geometry"]["variants"]["B_b377"][
            "staff_mask"
        ] = staff_rel
        rewrites.append(
            {
                "pointer": _pointer(
                    "pages",
                    page_index,
                    "modes",
                    "candidate_native_geometry",
                    "variants",
                    "B_b377",
                    "staff_mask",
                ),
                "source_value": staff_ref,
                "staged_value": staff_rel,
            }
        )

    runtime_path = stager.write_derived_json(
        role="matrix_report_runtime",
        source_path=source,
        raw_payload=raw_payload,
        runtime_payload=runtime,
        relative_dest=Path("runtime/matrix_reports") / f"chunk_{chunk_index:03d}.json",
        rewrites=rewrites,
    )
    return str(runtime_path.relative_to(stager.output_root)), len(raw_payload["pages"])


def stage(issue294_root: Path, manifest_path: Path, accepted_rebase_report: Path, output_root: Path) -> Path:
    issue294_root = issue294_root.absolute()
    manifest_path = _resolve_retained_path(manifest_path, issue294_root)
    accepted_rebase_report = _resolve_retained_path(accepted_rebase_report, issue294_root)
    output_root = output_root.absolute()
    if output_root.exists():
        raise FileExistsError(f"Staging output already exists: {output_root}")
    output_root.mkdir(parents=True)

    stager = Stager(issue294_root, output_root)
    try:
        stager.copy_exact(manifest_path, "raw/manifest.json", role="manifest_raw")
        raw_manifest = _load_json(manifest_path)
        if not isinstance(raw_manifest, Mapping):
            raise ValueError("Manifest is not a JSON object")
        chunks = raw_manifest.get("completed_chunks")
        if not isinstance(chunks, list):
            raise ValueError("Manifest lacks completed_chunks")
        runtime_manifest = copy.deepcopy(raw_manifest)
        manifest_rewrites: list[dict[str, str]] = []
        page_count = 0
        for index, chunk in enumerate(chunks):
            if not isinstance(chunk, Mapping) or "matrix_report" not in chunk:
                raise ValueError(f"Malformed completed chunk {index}")
            source_ref = str(chunk["matrix_report"])
            staged_ref, chunk_pages = _stage_matrix_report(stager, source_ref, chunk_index=index)
            runtime_manifest["completed_chunks"][index]["matrix_report"] = staged_ref
            manifest_rewrites.append(
                {
                    "pointer": _pointer("completed_chunks", index, "matrix_report"),
                    "source_value": source_ref,
                    "staged_value": staged_ref,
                }
            )
            page_count += chunk_pages
        if page_count != EXPECTED_PAGE_COUNT:
            raise RuntimeError(f"Expected {EXPECTED_PAGE_COUNT} staged pages, got {page_count}")

        runtime_manifest_path = stager.write_derived_json(
            role="manifest_runtime",
            source_path=manifest_path,
            raw_payload=raw_manifest,
            runtime_payload=runtime_manifest,
            relative_dest="runtime/manifest.json",
            rewrites=manifest_rewrites,
        )

        stager.copy_exact(
            accepted_rebase_report,
            "raw/accepted_rebase_report.json",
            role="accepted_rebase_raw",
        )
        runtime_accepted = stager.copy_exact(
            accepted_rebase_report,
            "runtime/accepted_rebase_report.json",
            role="accepted_rebase_runtime",
        )

        symlinks = [
            str(path.relative_to(output_root))
            for path in output_root.rglob("*")
            if path.is_symlink()
        ]
        if symlinks:
            raise RuntimeError(f"Staging tree contains symlinks: {symlinks}")

        provenance = {
            "schema_version": SCHEMA,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_issue294_root": str(issue294_root),
            "source_manifest": str(manifest_path.absolute()),
            "source_manifest_sha256": _sha256(manifest_path),
            "accepted_rebase_report": str(accepted_rebase_report.absolute()),
            "accepted_rebase_sha256": _sha256(accepted_rebase_report),
            "page_count": page_count,
            "runtime": {
                "issue294_root": str(output_root),
                "manifest": str(runtime_manifest_path),
                "accepted_rebase_report": str(runtime_accepted),
            },
            "files": stager.files,
            "derived_json": stager.derived_json,
            "validation": {
                "expected_page_count": EXPECTED_PAGE_COUNT,
                "page_count_matches": page_count == EXPECTED_PAGE_COUNT,
                "staging_tree_symlink_count": 0,
                "all_exact_copies_sha_match": all(
                    item["source_sha256"] == item["staged_sha256"] for item in stager.files
                ),
                "all_derived_json_non_path_semantics_equal": all(
                    item["non_path_semantics_equal"] for item in stager.derived_json
                ),
                "read_only_mount_ready": True,
            },
        }
        provenance_path = output_root / "provenance.json"
        _write_json(provenance_path, provenance)
        return provenance_path
    except Exception:
        shutil.rmtree(output_root, ignore_errors=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue294-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--accepted-rebase-report", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        provenance = stage(
            args.issue294_root,
            args.manifest,
            args.accepted_rebase_report,
            args.output_root,
        )
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"status": "failed", "error_type": type(error).__name__, "error": str(error)}))
        return 1
    payload = _load_json(provenance)
    print(
        json.dumps(
            {
                "status": "completed",
                "schema_version": payload["schema_version"],
                "page_count": payload["page_count"],
                "provenance": str(provenance),
                "runtime": payload["runtime"],
                "validation": payload["validation"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
