#!/usr/bin/env python3
"""Package authoritative fresh and accepted focused evidence for Issue #255 analysis."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ACCEPTED_ROOT = ROOT / "logs/issue197_system_grouping/full_visual_check"
TOP_LEVEL_ACCEPTED_EVIDENCE = (
    "current_grouping_summary.json",
    "input_file_inventory.json",
    "input_resolution_candidates.json",
    "proxy_connector_pair_evidence.json",
    "system_grouping_decision_trace.json",
)
REFERENCE_SUFFIXES = {".json", ".yaml", ".yml", ".png", ".jpg", ".jpeg", ".txt", ".log"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_record_path(value: str | Path, *, root: Path = ROOT) -> Path:
    """Map container `/workspace` records back to the host repository checkout."""
    path = Path(value)
    if path.is_absolute() and path.parts[:2] == ("/", "workspace"):
        return root / path.relative_to("/workspace")
    if path.is_absolute():
        return path
    return root / path


def iter_path_strings(value: Any) -> Iterable[str]:
    """Yield path-like strings from nested JSON-compatible values."""
    if isinstance(value, str):
        if Path(value).suffix.lower() in REFERENCE_SUFFIXES:
            yield value
        return
    if isinstance(value, Mapping):
        for child in value.values():
            yield from iter_path_strings(child)
        return
    if isinstance(value, list):
        for child in value:
            yield from iter_path_strings(child)


def _copy_file(source: Path, destination: Path, manifest: list[dict[str, Any]]) -> None:
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    manifest.append(
        {
            "source": str(source),
            "bundle_path": str(destination),
            "size_bytes": source.stat().st_size,
            "sha256": _sha256(source),
        }
    )


def _copy_tree(source: Path, destination: Path, manifest: list[dict[str, Any]]) -> None:
    for path in sorted(source.rglob("*")):
        if path.is_file():
            _copy_file(path, destination / path.relative_to(source), manifest)


def _accepted_directory(accepted_root: Path, *, score: str, page: str) -> Path:
    matches = sorted(path for path in accepted_root.glob(f"*_{score}_{page}") if path.is_dir())
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one accepted directory for {score}/{page}, found {matches}"
        )
    return matches[0]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_bundle(
    *, batch_summary: Path, accepted_root: Path, output: Path, root: Path = ROOT
) -> dict[str, Any]:
    batch_summary = batch_summary.resolve()
    accepted_root = accepted_root.resolve()
    output = output.resolve()
    payload = _load_json(batch_summary)
    if not isinstance(payload, Mapping) or payload.get("status") != "completed":
        raise ValueError("Focused fresh batch summary must be completed")
    runs = payload.get("runs")
    if not isinstance(runs, list) or len(runs) != 2:
        raise ValueError("Focused fresh batch must contain exactly two runs")

    staging = output.parent / f"{output.name}.staging"
    if output.exists() or staging.exists():
        raise FileExistsError(f"Bundle output already exists: {output} or {staging}")
    staging.mkdir(parents=True)
    manifest: list[dict[str, Any]] = []
    referenced_json_sources: list[Path] = []

    try:
        _copy_file(batch_summary, staging / "fresh" / batch_summary.name, manifest)
        for run in runs:
            if not isinstance(run, Mapping):
                raise ValueError("Invalid focused run record")
            contract = run.get("contract")
            if not isinstance(contract, Mapping) or contract.get("status") != "completed":
                raise ValueError(f"Incomplete focused run contract: {run.get('label')}")
            label = str(run["label"])
            score = str(run["score"])
            page = str(run["page"])
            run_root = staging / "fresh" / label

            contract_path = resolve_record_path(str(run["contract_path"]), root=root)
            _copy_file(contract_path, run_root / "run_contract.json", manifest)
            referenced_json_sources.append(contract_path)

            detail = resolve_record_path(str(run["detail"]), root=root)
            if detail.is_file():
                _copy_file(detail, run_root / "console.log", manifest)

            artifacts = contract.get("artifacts")
            if not isinstance(artifacts, Mapping):
                raise ValueError(f"Missing artifact inventory: {label}")
            for name, record in artifacts.items():
                if not isinstance(record, Mapping) or record.get("exists") is not True:
                    continue
                source = resolve_record_path(str(record["path"]), root=root)
                suffix = "".join(source.suffixes) or ".bin"
                destination = run_root / "artifacts" / f"{name}{suffix}"
                _copy_file(source, destination, manifest)
                if source.suffix.lower() == ".json":
                    referenced_json_sources.append(source)

            accepted_dir = _accepted_directory(accepted_root, score=score, page=page)
            accepted_destination = staging / "accepted" / label / accepted_dir.name
            _copy_tree(accepted_dir, accepted_destination, manifest)
            referenced_json_sources.extend(sorted(accepted_dir.rglob("*.json")))

        accepted_base = accepted_root.parent
        for name in TOP_LEVEL_ACCEPTED_EVIDENCE:
            source = accepted_base / name
            if source.is_file():
                destination = staging / "accepted" / "shared" / name
                _copy_file(source, destination, manifest)
                referenced_json_sources.append(source)

        copied_references: set[Path] = set()
        for json_source in referenced_json_sources:
            try:
                json_payload = _load_json(json_source)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            for raw in iter_path_strings(json_payload):
                reference = resolve_record_path(raw, root=root).resolve()
                if not reference.is_file() or reference.suffix.lower() not in REFERENCE_SUFFIXES:
                    continue
                try:
                    relative = reference.relative_to(root.resolve())
                except ValueError:
                    continue
                if reference in copied_references:
                    continue
                copied_references.add(reference)
                _copy_file(
                    reference,
                    staging / "accepted_references" / relative,
                    manifest,
                )

        bundle_manifest = {
            "schema_version": "issue255.focused_first_loss_bundle.v1",
            "status": "completed",
            "batch_summary": str(batch_summary),
            "expected_commit": payload.get("expected_commit"),
            "expected_branch": payload.get("expected_branch"),
            "file_count": len(manifest),
            "files": manifest,
        }
        (staging / "bundle_manifest.json").write_text(
            json.dumps(bundle_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(output, "w:gz") as archive:
            archive.add(staging, arcname=output.stem)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return {**bundle_manifest, "output": str(output), "size_bytes": output.stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-summary", type=Path, required=True)
    parser.add_argument("--accepted-root", type=Path, default=DEFAULT_ACCEPTED_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_bundle(
            batch_summary=args.batch_summary,
            accepted_root=args.accepted_root,
            output=args.output,
        )
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"status": "failed", "error_type": type(error).__name__, "error": str(error)}))
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
