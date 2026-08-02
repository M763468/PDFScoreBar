#!/usr/bin/env python3
"""Create a compact upload bundle for the Issue #255 public-baseline A/B."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
from pathlib import Path
from typing import Any, Mapping


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_repo_path(value: str, repo_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute() and path.parts[:2] == ("/", "workspace"):
        return repo_root / path.relative_to("/workspace")
    if path.is_absolute():
        return path
    return repo_root / path


def copy_record(
    source: Path,
    destination: Path,
    *,
    bundle_root: Path,
    manifest: list[dict[str, Any]],
) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    manifest.append(
        {
            "path": str(destination.relative_to(bundle_root)),
            "source": str(source),
            "size_bytes": destination.stat().st_size,
            "sha256": sha256(destination),
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-batch", type=Path, required=True)
    parser.add_argument("--public-batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output = args.output.resolve()
    bundle_root = output.with_suffix("").with_suffix("")
    if output.exists() or bundle_root.exists():
        raise FileExistsError(output if output.exists() else bundle_root)
    bundle_root.mkdir(parents=True)
    manifest: list[dict[str, Any]] = []

    try:
        target_manifest = repo_root / "tools/issue255/gate05_targets.json"
        target_payload = load_json(target_manifest)
        copy_record(
            target_manifest,
            bundle_root / "evidence/gate05_targets.json",
            bundle_root=bundle_root,
            manifest=manifest,
        )
        pages = target_payload.get("pages", {})
        if not isinstance(pages, Mapping):
            raise ValueError("Invalid gate05 target manifest")
        for label, page in pages.items():
            if not isinstance(page, Mapping):
                continue
            accepted = resolve_repo_path(str(page["accepted_barlines"]), repo_root)
            copy_record(
                accepted,
                bundle_root / f"evidence/{label}_accepted_barlines.json",
                bundle_root=bundle_root,
                manifest=manifest,
            )

        for batch_path in (args.control_batch.resolve(), args.public_batch.resolve()):
            batch = load_json(batch_path)
            variant = str(batch.get("variant"))
            if batch.get("status") != "completed" or not isinstance(batch.get("runs"), list):
                raise ValueError(f"Incomplete A/B batch: {batch_path}")
            copy_record(
                batch_path,
                bundle_root / variant / batch_path.name,
                bundle_root=bundle_root,
                manifest=manifest,
            )
            for run in batch["runs"]:
                if not isinstance(run, Mapping):
                    continue
                label = str(run["label"])
                contract = run.get("contract")
                if not isinstance(contract, Mapping):
                    raise ValueError(f"Missing contract: {variant}/{label}")
                contract_path = Path(str(run["contract_path"])).resolve()
                copy_record(
                    contract_path,
                    bundle_root / variant / label / contract_path.name,
                    bundle_root=bundle_root,
                    manifest=manifest,
                )
                run_dir = resolve_repo_path(str(contract["run_dir"]), repo_root)
                effective = run_dir / "issue255_public_baseline_ab_effective_config.json"
                copy_record(
                    effective,
                    bundle_root / variant / label / effective.name,
                    bundle_root=bundle_root,
                    manifest=manifest,
                )
                artifacts = contract.get("artifacts")
                if not isinstance(artifacts, Mapping):
                    raise ValueError(f"Missing artifacts: {variant}/{label}")
                for name in (
                    "input_contract",
                    "fresh_baseline",
                    "current_sr",
                    "current_omr",
                    "hybrid",
                    "cnn_candidates",
                    "cnn_scored",
                    "cnn_accepted",
                    "final_barlines",
                ):
                    record = artifacts.get(name)
                    if not isinstance(record, Mapping) or record.get("exists") is not True:
                        continue
                    source = resolve_repo_path(str(record["path"]), repo_root)
                    copy_record(
                        source,
                        bundle_root / variant / label / f"{name}{source.suffix}",
                        bundle_root=bundle_root,
                        manifest=manifest,
                    )
                handoff = contract.get("baseline_profile_handoff")
                if isinstance(handoff, Mapping):
                    for key in ("provenance_path",):
                        value = handoff.get(key)
                        if not value:
                            continue
                        source = resolve_repo_path(str(value), repo_root)
                        copy_record(
                            source,
                            bundle_root / variant / label / source.name,
                            bundle_root=bundle_root,
                            manifest=manifest,
                        )

        manifest_path = bundle_root / "bundle_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "issue255.public_baseline_ab_bundle.v1",
                    "files": manifest,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        with tarfile.open(output, "w:gz") as archive:
            archive.add(bundle_root, arcname=bundle_root.name)
    finally:
        shutil.rmtree(bundle_root, ignore_errors=True)

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
