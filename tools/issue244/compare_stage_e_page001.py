"""Compare historical Stage E page-001 numbering with the Issue #236 smoke result.

Temporary Issue #244 investigation helper. Delete before the final PR unless promoted to
maintained diagnostic tooling. Generated artifacts stay under ignored logs/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

SMOKE_RUN = Path("logs/issue236_pipeline_connected_review_smoke/corrected_20260709_125046")
STAGE_E_RUN = Path("logs/issue120_e2e_recovery/stage_e_full_pipeline")
WORK_ROOT = Path("logs/issue244_local_probe/stage_e_page001_compare")
TARGET_SCORE_TOKEN = "Va_Prokofiev_Symphony1_page_001"
SMOKE_PAGE_ID = "page_001"
EXPECTED_ROW_STARTS = [1, 6, 11, 16, 23, 30, 38, 43, 58, 76, 84, 89]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_pages(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    pages = payload.get("pages")
    if isinstance(pages, list):
        return [item for item in pages if isinstance(item, dict)]
    if isinstance(pages, dict):
        return [item for item in pages.values() if isinstance(item, dict)]
    return []


def locate_stage_page_id(manifest_path: Path) -> str:
    payload = load_json(manifest_path)
    for item in manifest_pages(payload):
        haystack = " ".join(
            str(item.get(key, "")) for key in ("page_id", "image", "barlines_json", "source_image")
        )
        if TARGET_SCORE_TOKEN in haystack:
            page_id = item.get("page_id")
            if isinstance(page_id, str) and page_id:
                return page_id
    raise RuntimeError(f"Could not map {TARGET_SCORE_TOKEN!r} in Stage E manifest: {manifest_path}")


def resolve_page_artifact(
    run_dir: Path,
    page_id: str,
    relative_candidates: list[Path],
) -> Path:
    for relative in relative_candidates:
        path = run_dir / relative
        if path.exists():
            return path

    names = {candidate.name for candidate in relative_candidates}
    matches = [
        path for path in run_dir.rglob("*.json") if path.name in names and page_id in path.parts
    ]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise RuntimeError(
            f"Ambiguous artifact for page {page_id}: " + ", ".join(str(path) for path in matches)
        )
    raise FileNotFoundError(
        f"No artifact found for page {page_id}; tried: "
        + ", ".join(str(run_dir / relative) for relative in relative_candidates)
    )


def systems_from_numbering(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    pages = payload.get("pages") if isinstance(payload, dict) else None
    if not isinstance(pages, list) or not pages or not isinstance(pages[0], dict):
        raise ValueError(f"No usable pages[0] in {path}")
    systems = pages[0].get("systems")
    if not isinstance(systems, list):
        raise ValueError(f"No usable systems in {path}")
    return [system for system in systems if isinstance(system, dict)]


def row_starts(systems: list[dict[str, Any]]) -> list[int | None]:
    result: list[int | None] = []
    for system in systems:
        measures = system.get("measures")
        if not isinstance(measures, list) or not measures:
            result.append(None)
            continue
        first = measures[0]
        result.append(first.get("number") if isinstance(first, dict) else None)
    return result


def measure_counts(systems: list[dict[str, Any]]) -> list[int]:
    result = []
    for system in systems:
        measures = system.get("measures")
        result.append(len(measures) if isinstance(measures, list) else 0)
    return result


def numbering_summary(run_dir: Path, page_id: str) -> dict[str, Any]:
    base = resolve_page_artifact(
        run_dir,
        page_id,
        [
            Path("intermediate") / page_id / "numbering_base.json",
            Path("outputs") / page_id / "numbering_base.json",
        ],
    )
    final = resolve_page_artifact(
        run_dir,
        page_id,
        [
            Path("outputs") / page_id / "numbering_final.json",
            Path("intermediate") / page_id / "numbering_final.json",
        ],
    )
    mmr_candidates = [
        run_dir / "intermediate" / page_id / "overrides_mmr.json",
        run_dir / "outputs" / page_id / "overrides_mmr.json",
    ]
    mmr = next((path for path in mmr_candidates if path.exists()), None)

    base_systems = systems_from_numbering(base)
    final_systems = systems_from_numbering(final)
    mmr_payload = load_json(mmr) if mmr else {}

    return {
        "run_dir": str(run_dir),
        "page_id": page_id,
        "base_path": str(base),
        "base_sha256": sha256_file(base),
        "final_path": str(final),
        "final_sha256": sha256_file(final),
        "mmr_path": str(mmr) if mmr else None,
        "base_measure_counts": measure_counts(base_systems),
        "base_row_starts": row_starts(base_systems),
        "final_row_starts": row_starts(final_systems),
        "mmr_overrides": (
            mmr_payload.get("measure_overrides", []) if isinstance(mmr_payload, dict) else []
        ),
    }


def subtract(
    left: list[int | None],
    right: list[int | None],
) -> list[int | None]:
    result: list[int | None] = []
    for left_value, right_value in zip(left, right, strict=False):
        if left_value is None or right_value is None:
            result.append(None)
        else:
            result.append(left_value - right_value)
    return result


def artifact_from_manifest(run_dir: Path, manifest_path: Path, page_id: str) -> Path | None:
    payload = load_json(manifest_path)
    for item in manifest_pages(payload):
        if item.get("page_id") != page_id:
            continue
        raw = item.get("barlines_json")
        if not isinstance(raw, str) or not raw:
            return None
        candidate = Path(raw)
        if candidate.exists():
            return candidate
        rooted = run_dir.parent.parent / candidate
        if rooted.exists():
            return rooted
        return candidate
    return None


def write_markdown(report: dict[str, Any], path: Path) -> None:
    smoke = report["smoke"]
    stage = report["stage_e"]
    lines = [
        "# Issue #244 Stage E page-001 comparison",
        "",
        f"- Stage E page id: `{report['stage_e_page_id']}`",
        f"- expected row starts: `{report['expected_row_starts']}`",
        f"- smoke final row starts: `{smoke['final_row_starts']}`",
        f"- Stage E final row starts: `{stage['final_row_starts']}`",
        f"- smoke base measure counts: `{smoke['base_measure_counts']}`",
        f"- Stage E base measure counts: `{stage['base_measure_counts']}`",
        f"- Stage E matches expected: `{report['comparison']['stage_e_matches_expected']}`",
        "",
        "## Deltas",
        "",
        f"- Stage E minus smoke base counts: `{report['comparison']['stage_e_minus_smoke_base_counts']}`",
        f"- expected minus smoke final: `{report['comparison']['expected_minus_smoke_final']}`",
        f"- expected minus Stage E final: `{report['comparison']['expected_minus_stage_e_final']}`",
        "",
        "## Detector result artifacts",
        "",
        f"- smoke barline artifact: `{report['barline_artifacts']['smoke']}`",
        f"- Stage E barline artifact: `{report['barline_artifacts']['stage_e']}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    work_root = repo_root / WORK_ROOT
    if work_root.exists() and args.force:
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True, exist_ok=True)

    smoke_run = repo_root / SMOKE_RUN
    stage_run = repo_root / STAGE_E_RUN
    smoke_manifest = smoke_run / "manifest.json"
    stage_manifest = stage_run / "manifest.json"

    for required in (smoke_manifest, stage_manifest):
        if not required.exists():
            raise FileNotFoundError(required)

    stage_page_id = locate_stage_page_id(stage_manifest)
    smoke = numbering_summary(smoke_run, SMOKE_PAGE_ID)
    stage = numbering_summary(stage_run, stage_page_id)

    smoke_barline = artifact_from_manifest(smoke_run, smoke_manifest, SMOKE_PAGE_ID)
    stage_barline = artifact_from_manifest(stage_run, stage_manifest, stage_page_id)

    def artifact_record(path: Path | None) -> dict[str, Any] | None:
        if path is None:
            return None
        return {
            "path": str(path),
            "exists": path.exists(),
            "sha256": sha256_file(path) if path.exists() else None,
            "size_bytes": path.stat().st_size if path.exists() else None,
        }

    report = {
        "schema": "issue244.stage_e_page001_compare.v1",
        "temporary_script": str(Path(__file__).relative_to(repo_root)),
        "stage_e_page_id": stage_page_id,
        "expected_row_starts": EXPECTED_ROW_STARTS,
        "smoke": smoke,
        "stage_e": stage,
        "barline_artifacts": {
            "smoke": artifact_record(smoke_barline),
            "stage_e": artifact_record(stage_barline),
        },
        "comparison": {
            "stage_e_minus_smoke_base_counts": subtract(
                stage["base_measure_counts"],
                smoke["base_measure_counts"],
            ),
            "stage_e_minus_smoke_final_starts": subtract(
                stage["final_row_starts"],
                smoke["final_row_starts"],
            ),
            "expected_minus_smoke_final": subtract(
                EXPECTED_ROW_STARTS,
                smoke["final_row_starts"],
            ),
            "expected_minus_stage_e_final": subtract(
                EXPECTED_ROW_STARTS,
                stage["final_row_starts"],
            ),
            "stage_e_matches_expected": stage["final_row_starts"] == EXPECTED_ROW_STARTS,
        },
    }

    json_path = work_root / "stage_e_page001_compare.json"
    md_path = work_root / "stage_e_page001_compare.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_markdown(report, md_path)

    zip_path = work_root.with_name(f"{work_root.name}_review.zip")
    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in (
            json_path,
            md_path,
            Path(smoke["base_path"]),
            Path(smoke["final_path"]),
            Path(stage["base_path"]),
            Path(stage["final_path"]),
        ):
            if path.exists():
                archive.write(path, path.relative_to(repo_root))

    print("Stage E page id:", stage_page_id)
    print("Expected:     ", EXPECTED_ROW_STARTS)
    print("Smoke final:  ", smoke["final_row_starts"])
    print("Stage E final:", stage["final_row_starts"])
    print("Smoke base counts:  ", smoke["base_measure_counts"])
    print("Stage E base counts:", stage["base_measure_counts"])
    print(
        "Stage E minus smoke base counts:",
        report["comparison"]["stage_e_minus_smoke_base_counts"],
    )
    print("Stage E matches expected:", report["comparison"]["stage_e_matches_expected"])
    print("Report:", json_path.relative_to(repo_root))
    print("Review zip:", zip_path.relative_to(repo_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
