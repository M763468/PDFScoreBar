#!/usr/bin/env python3
"""Issue #333 temporary read-only audit for parent-worktree retained logs.

This tool is intentionally investigation-only and is expected to be removed
before the final #333 PR is merged.

It reads retained artifacts from a source worktree (normally the main
PDFScoreBar worktree), writes all audit output under the current #333
worktree's logs/ directory, and never modifies the source worktree.

Failures are collected into errors.json and SUMMARY.txt. A recoverable error
does not abort the whole audit, so useful partial evidence remains available.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import tarfile
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Iterable

CURRENT_DEVELOP_SHA = "4e844d1b69cfe7744fce3dffb5a69491814b2db6"
ISSUE268_MERGE_SHA = "9dfb99f5e69d57c746d8ebd98623297e61dc8e6b"
CURRENT_SCHEMA_MARKERS = (
    "issue268.final_numbering.v1",
    "issue268.movement_boundaries.v1",
)
TEXT_SUFFIXES = {".json", ".log", ".txt", ".md", ".yaml", ".yml"}
LINEAGE_PATTERNS = (
    "issue268",
    "Issue #268",
    "PR #341",
    "pr341",
    "issue268.movement_boundaries.v1",
    "issue268.final_numbering.v1",
    "movement_boundar",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="Main worktree whose retained logs should be read.",
    )
    parser.add_argument(
        "--worktree",
        type=Path,
        default=Path.cwd(),
        help="Issue #333 worktree where audit output is written (default: cwd).",
    )
    parser.add_argument(
        "--develop-sha",
        default=CURRENT_DEVELOP_SHA,
        help="Develop SHA treated as current for provenance matching.",
    )
    parser.add_argument(
        "--issue268-merge-sha",
        default=ISSUE268_MERGE_SHA,
        help="#268 merge SHA used for lineage matching.",
    )
    parser.add_argument(
        "--max-text-bytes",
        type=int,
        default=2_000_000,
        help="Maximum bytes read from one contextual text file.",
    )
    return parser.parse_args()


class Audit:
    def __init__(
        self,
        *,
        source_root: Path,
        worktree: Path,
        develop_sha: str,
        issue268_merge_sha: str,
        max_text_bytes: int,
    ) -> None:
        self.source_root = source_root.resolve()
        self.worktree = worktree.resolve()
        self.logs_root = self.source_root / "logs"
        self.develop_sha = develop_sha
        self.issue268_merge_sha = issue268_merge_sha
        self.max_text_bytes = max_text_bytes
        self.errors: list[dict[str, str]] = []
        self.stats = Counter()

        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        self.out = self.worktree / "logs" / f"issue333_parent_log_audit_{stamp}"
        self.out.mkdir(parents=True, exist_ok=True)

    def record_error(self, stage: str, exc: BaseException, path: Path | None = None) -> None:
        item = {
            "stage": stage,
            "error": repr(exc),
            "traceback": traceback.format_exc(),
        }
        if path is not None:
            item["path"] = str(path)
        self.errors.append(item)

    def safe_text(self, path: Path) -> str:
        try:
            if not path.is_file():
                return ""
            with path.open("r", encoding="utf-8", errors="ignore") as fh:
                return fh.read(self.max_text_bytes)
        except Exception as exc:
            self.record_error("read_text", exc, path)
            return ""

    def write_json(self, name: str, payload: Any) -> None:
        path = self.out / name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def run_git(self, *args: str) -> str:
        try:
            proc = subprocess.run(
                ["git", "-C", str(self.worktree), *args],
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                self.errors.append(
                    {
                        "stage": "git",
                        "error": f"git {' '.join(args)} returned {proc.returncode}",
                        "stderr": proc.stderr,
                    }
                )
            return proc.stdout.strip()
        except Exception as exc:
            self.record_error("git", exc)
            return ""

    def context_snapshot(self) -> None:
        payload = {
            "source_root": str(self.source_root),
            "logs_root": str(self.logs_root),
            "worktree": str(self.worktree),
            "develop_sha_expected": self.develop_sha,
            "issue268_merge_sha": self.issue268_merge_sha,
            "worktree_head": self.run_git("rev-parse", "HEAD"),
            "worktree_branch": self.run_git("branch", "--show-current"),
            "worktree_status": self.run_git("status", "--short", "--branch"),
            "created_at": datetime.now().isoformat(),
        }
        self.write_json("00_context.json", payload)

    def related_path_inventory(self) -> None:
        markers = ("issue268", "issue333", "341", "movement", "numbering")
        related: list[str] = []
        numbering: list[dict[str, Any]] = []

        if not self.logs_root.is_dir():
            self.errors.append(
                {
                    "stage": "inventory",
                    "error": f"logs root does not exist: {self.logs_root}",
                }
            )
            return

        for path in self.logs_root.rglob("*"):
            try:
                low = path.name.lower()
                if any(marker in low for marker in markers):
                    related.append(str(path))

                if path.is_file() and path.name in {"numbering_base.json", "numbering_final.json"}:
                    st = path.stat()
                    numbering.append(
                        {
                            "path": str(path),
                            "relative_path": str(path.relative_to(self.source_root)),
                            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
                            "size": st.st_size,
                        }
                    )
            except Exception as exc:
                self.record_error("inventory_path", exc, path)

        numbering.sort(key=lambda item: item["mtime"], reverse=True)
        text_path = self.out / "10_parent_log_inventory.txt"
        with text_path.open("w", encoding="utf-8") as fh:
            fh.write("=== paths mentioning directly related Issues / movement numbering ===\n")
            for item in sorted(set(related)):
                fh.write(item + "\n")
            fh.write("\n=== numbering artifacts anywhere under parent logs ===\n")
            for item in numbering:
                fh.write(
                    f"{item['mtime']}\t{item['size']}\t{item['relative_path']}\n"
                )

        self.stats["related_paths"] = len(set(related))
        self.stats["numbering_artifacts"] = len(numbering)

    @staticmethod
    def flatten_strings(obj: Any) -> Iterable[str]:
        if isinstance(obj, str):
            yield obj
        elif isinstance(obj, dict):
            for key, value in obj.items():
                yield str(key)
                yield from Audit.flatten_strings(value)
        elif isinstance(obj, list):
            for item in obj:
                yield from Audit.flatten_strings(item)

    def nearest_context_files(self, artifact: Path) -> list[Path]:
        found: list[Path] = []
        current = artifact.parent

        for _ in range(7):
            try:
                current.relative_to(self.logs_root)
            except ValueError:
                break

            for name in (
                "pipeline.log",
                "manifest.json",
                "run_manifest.json",
                "config.yaml",
                "config.yml",
                "provenance.json",
                "metadata.json",
            ):
                candidate = current / name
                if candidate.is_file():
                    found.append(candidate)

            try:
                for candidate in sorted(current.glob("*.json")):
                    low = candidate.name.lower()
                    if any(token in low for token in ("manifest", "provenance", "metadata", "summary")):
                        found.append(candidate)
            except Exception as exc:
                self.record_error("context_glob", exc, current)

            if current == self.logs_root:
                break
            current = current.parent

        result: list[Path] = []
        seen: set[str] = set()
        for path in found:
            key = str(path)
            if key not in seen:
                seen.add(key)
                result.append(path)
        return result[:24]

    def classify_numbering_artifacts(self) -> list[dict[str, Any]]:
        artifacts = sorted(
            {
                *self.logs_root.rglob("numbering_base.json"),
                *self.logs_root.rglob("numbering_final.json"),
            }
        )
        records: list[dict[str, Any]] = []

        for path in artifacts:
            try:
                st = path.stat()
                record: dict[str, Any] = {
                    "path": str(path),
                    "relative_path": str(path.relative_to(self.source_root)),
                    "kind": path.name,
                    "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
                    "size": st.st_size,
                    "json_ok": False,
                    "current_contract_marker": False,
                    "movement_boundary_key": False,
                    "nearby_context_files": [],
                    "nearby_current_markers": [],
                    "path_markers": [],
                    "classification": None,
                    "classification_reasons": [],
                }

                low_path = str(path).lower()
                for marker in ("issue268", "issue333", "341", "movement", "dense_full_pipeline"):
                    if marker in low_path:
                        record["path_markers"].append(marker)

                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    record["json_ok"] = True
                    artifact_text = "\n".join(self.flatten_strings(payload)).lower()
                    record["current_contract_marker"] = any(
                        marker.lower() in artifact_text for marker in CURRENT_SCHEMA_MARKERS
                    )
                    record["movement_boundary_key"] = "movement_boundar" in artifact_text
                except Exception as exc:
                    record["json_error"] = repr(exc)
                    self.record_error("parse_numbering_json", exc, path)

                for context_path in self.nearest_context_files(path):
                    record["nearby_context_files"].append(str(context_path))
                    low = self.safe_text(context_path).lower()
                    for pattern in (
                        *LINEAGE_PATTERNS,
                        self.develop_sha,
                        self.issue268_merge_sha,
                    ):
                        if pattern.lower() in low:
                            record["nearby_current_markers"].append(
                                {"file": str(context_path), "marker": pattern}
                            )

                seen_markers: set[tuple[str, str]] = set()
                unique_markers: list[dict[str, str]] = []
                for item in record["nearby_current_markers"]:
                    key = (item["file"], item["marker"])
                    if key not in seen_markers:
                        seen_markers.add(key)
                        unique_markers.append(item)
                record["nearby_current_markers"] = unique_markers

                marker_set = {item["marker"].lower() for item in unique_markers}
                strong = False
                related = False

                if record["current_contract_marker"]:
                    strong = True
                    record["classification_reasons"].append(
                        "artifact contains current #268 schema marker"
                    )
                if record["movement_boundary_key"]:
                    strong = True
                    record["classification_reasons"].append(
                        "artifact contains movement-boundary state/key"
                    )
                if self.develop_sha.lower() in marker_set:
                    strong = True
                    record["classification_reasons"].append(
                        "nearby provenance references expected develop SHA"
                    )
                if self.issue268_merge_sha.lower() in marker_set:
                    strong = True
                    record["classification_reasons"].append(
                        "nearby provenance references #268 merge SHA"
                    )

                lineage_lower = {item.lower() for item in LINEAGE_PATTERNS}
                if marker_set & lineage_lower:
                    related = True
                    record["classification_reasons"].append(
                        "nearby context references #268/#341/movement-boundary lineage"
                    )
                if any(
                    marker in record["path_markers"]
                    for marker in ("issue268", "issue333", "movement")
                ):
                    related = True
                    record["classification_reasons"].append(
                        "artifact path contains directly related issue/movement marker"
                    )

                if st.st_mtime >= datetime(2026, 9, 18).timestamp():
                    record["classification_reasons"].append(
                        "mtime is on/after 2026-09-18 (weak supporting signal only)"
                    )

                if strong:
                    record["classification"] = "CURRENT_STRONG"
                elif related:
                    record["classification"] = "RELATED_NEEDS_REVIEW"
                else:
                    record["classification"] = "UNCLASSIFIED_OR_LEGACY"

                records.append(record)
            except Exception as exc:
                self.record_error("classify_artifact", exc, path)

        self.write_json("20_numbering_artifact_classification.json", records)

        with (self.out / "21_numbering_artifact_classification.txt").open(
            "w", encoding="utf-8"
        ) as fh:
            for classification in (
                "CURRENT_STRONG",
                "RELATED_NEEDS_REVIEW",
                "UNCLASSIFIED_OR_LEGACY",
            ):
                subset = [r for r in records if r["classification"] == classification]
                fh.write(f"\n===== {classification}: {len(subset)} =====\n")
                for record in subset:
                    fh.write(f"\n{record['relative_path']}\n")
                    fh.write(f"  kind: {record['kind']}\n")
                    fh.write(f"  mtime: {record['mtime']}\n")
                    fh.write(f"  size: {record['size']}\n")
                    fh.write(
                        f"  current_contract_marker: {record['current_contract_marker']}\n"
                    )
                    fh.write(
                        f"  movement_boundary_key: {record['movement_boundary_key']}\n"
                    )
                    fh.write(f"  path_markers: {record['path_markers']}\n")
                    fh.write("  reasons:\n")
                    for reason in record["classification_reasons"]:
                        fh.write(f"    - {reason}\n")
                    if record["nearby_current_markers"]:
                        fh.write("  nearby markers:\n")
                        for item in record["nearby_current_markers"]:
                            fh.write(f"    - {item['marker']}: {item['file']}\n")

        for classification in (
            "CURRENT_STRONG",
            "RELATED_NEEDS_REVIEW",
            "UNCLASSIFIED_OR_LEGACY",
        ):
            self.stats[classification] = sum(
                record["classification"] == classification for record in records
            )
        return records

    def lineage_matches(self) -> None:
        matches: list[dict[str, Any]] = []
        exact_patterns = (self.develop_sha, self.issue268_merge_sha)

        for path in self.logs_root.rglob("*"):
            try:
                if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                text = self.safe_text(path)
                if not text:
                    continue
                low = text.lower()
                found = [
                    pattern
                    for pattern in (*LINEAGE_PATTERNS, *exact_patterns)
                    if pattern.lower() in low
                ]
                if found:
                    matches.append(
                        {
                            "path": str(path),
                            "relative_path": str(path.relative_to(self.source_root)),
                            "markers": found,
                        }
                    )
            except Exception as exc:
                self.record_error("lineage_search", exc, path)

        self.write_json("30_current_lineage_matches.json", matches)
        with (self.out / "31_current_lineage_matches.txt").open(
            "w", encoding="utf-8"
        ) as fh:
            for item in matches:
                fh.write(f"{item['relative_path']}\n")
                fh.write(f"  markers: {item['markers']}\n")
        self.stats["lineage_match_files"] = len(matches)

    @staticmethod
    def bbox_union(boxes: list[list[float]]) -> list[float] | None:
        if not boxes:
            return None
        return [
            min(box[0] for box in boxes),
            min(box[1] for box in boxes),
            max(box[2] for box in boxes),
            max(box[3] for box in boxes),
        ]

    def geometry(self, records: list[dict[str, Any]]) -> None:
        current_paths = [
            Path(record["path"])
            for record in records
            if record["classification"] == "CURRENT_STRONG"
        ]
        pages_out: list[dict[str, Any]] = []

        for path in current_paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                pages = payload.get("pages", [])
                if not isinstance(pages, list):
                    continue

                for page_position, page in enumerate(pages):
                    if not isinstance(page, dict):
                        continue
                    systems = page.get("systems", [])
                    if not isinstance(systems, list):
                        continue

                    system_rows: list[dict[str, Any]] = []
                    for system_index, system in enumerate(systems):
                        if not isinstance(system, dict):
                            continue
                        boxes: list[list[float]] = []
                        heights: list[float] = []

                        for staff in system.get("staves", []):
                            if not isinstance(staff, dict):
                                continue
                            bbox = staff.get("bbox")
                            if isinstance(bbox, list) and len(bbox) == 4:
                                try:
                                    converted = [float(value) for value in bbox]
                                except (TypeError, ValueError):
                                    continue
                                boxes.append(converted)
                                heights.append(max(1.0, converted[3] - converted[1]))

                        for measure in system.get("measures", []):
                            if not isinstance(measure, dict):
                                continue
                            bbox = measure.get("bbox")
                            if isinstance(bbox, list) and len(bbox) == 4:
                                try:
                                    boxes.append([float(value) for value in bbox])
                                except (TypeError, ValueError):
                                    pass

                        union = self.bbox_union(boxes)
                        if union is None:
                            continue
                        system_rows.append(
                            {
                                "system": system_index,
                                "bbox": union,
                                "staff_height_scale": median(heights) if heights else None,
                            }
                        )

                    inter_system: list[dict[str, Any]] = []
                    for previous, current in zip(system_rows, system_rows[1:]):
                        gap = current["bbox"][1] - previous["bbox"][3]
                        scales = [
                            value
                            for value in (
                                previous["staff_height_scale"],
                                current["staff_height_scale"],
                            )
                            if isinstance(value, (int, float)) and value > 0
                        ]
                        scale = median(scales) if scales else None
                        inter_system.append(
                            {
                                "before_system": previous["system"],
                                "after_system": current["system"],
                                "vertical_gap": gap,
                                "staff_height_scale": scale,
                                "gap_ratio": gap / scale if scale else None,
                                "left_indent_delta": (
                                    current["bbox"][0] - previous["bbox"][0]
                                ),
                                "previous_bbox": previous["bbox"],
                                "next_bbox": current["bbox"],
                            }
                        )

                    pages_out.append(
                        {
                            "path": str(path),
                            "page_position_in_payload": page_position,
                            "page_number": page.get("page_number"),
                            "system_count": len(system_rows),
                            "systems": system_rows,
                            "inter_system": inter_system,
                        }
                    )
            except Exception as exc:
                self.record_error("geometry", exc, path)

        self.write_json("40_current_geometry.json", pages_out)

        flat: list[dict[str, Any]] = []
        for page in pages_out:
            for item in page["inter_system"]:
                flat.append(
                    {
                        "path": page["path"],
                        "page_number": page["page_number"],
                        **item,
                    }
                )

        def gap_sort_key(item: dict[str, Any]) -> float:
            value = item["gap_ratio"]
            return -math.inf if value is None else float(value)

        with (self.out / "41_current_geometry_summary.txt").open(
            "w", encoding="utf-8"
        ) as fh:
            fh.write("=== largest normalized gaps ===\n")
            for item in sorted(flat, key=gap_sort_key, reverse=True)[:100]:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")

            fh.write("\n=== largest absolute left-indent changes ===\n")
            for item in sorted(
                flat,
                key=lambda row: abs(float(row["left_indent_delta"])),
                reverse=True,
            )[:100]:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")

        self.stats["current_geometry_pages"] = len(pages_out)
        self.stats["current_inter_system_observations"] = len(flat)

    def finalize(self) -> Path | None:
        try:
            self.write_json("errors.json", self.errors)
        except Exception:
            pass

        summary_lines = [
            "Issue #333 parent-log audit",
            "",
            f"source_root: {self.source_root}",
            f"logs_root: {self.logs_root}",
            f"worktree: {self.worktree}",
            f"expected_develop_sha: {self.develop_sha}",
            "",
            "counts:",
        ]
        for key in sorted(self.stats):
            summary_lines.append(f"  {key}: {self.stats[key]}")
        summary_lines.extend(
            [
                f"  recoverable_errors: {len(self.errors)}",
                "",
                "Notes:",
                "  - Source logs are read-only.",
                "  - CURRENT_STRONG requires contract/provenance evidence; mtime alone is insufficient.",
                "  - Geometry output is descriptive only; no movement-detection threshold is selected.",
                "  - This investigation tool is temporary and should be removed before the final PR.",
            ]
        )
        (self.out / "SUMMARY.txt").write_text(
            "\n".join(summary_lines) + "\n", encoding="utf-8"
        )

        archive = self.out.with_suffix(".tar.gz")
        try:
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(self.out, arcname=self.out.name)
            return archive
        except Exception as exc:
            self.record_error("archive", exc)
            try:
                self.write_json("errors.json", self.errors)
            except Exception:
                pass
            return None

    def run(self) -> Path | None:
        stages = (
            ("context_snapshot", self.context_snapshot),
            ("related_path_inventory", self.related_path_inventory),
        )
        for stage_name, stage in stages:
            try:
                stage()
            except Exception as exc:
                self.record_error(stage_name, exc)

        records: list[dict[str, Any]] = []
        try:
            records = self.classify_numbering_artifacts()
        except Exception as exc:
            self.record_error("classify_numbering_artifacts", exc)

        try:
            self.lineage_matches()
        except Exception as exc:
            self.record_error("lineage_matches", exc)

        try:
            self.geometry(records)
        except Exception as exc:
            self.record_error("geometry_all", exc)

        return self.finalize()


def main() -> int:
    args = parse_args()

    audit: Audit | None = None
    archive: Path | None = None
    fatal: BaseException | None = None

    try:
        audit = Audit(
            source_root=args.source_root,
            worktree=args.worktree,
            develop_sha=args.develop_sha,
            issue268_merge_sha=args.issue268_merge_sha,
            max_text_bytes=args.max_text_bytes,
        )
        archive = audit.run()
    except BaseException as exc:
        fatal = exc
        if audit is not None:
            audit.record_error("fatal", exc)
            try:
                archive = audit.finalize()
            except Exception:
                pass

    print()
    print("=" * 72)
    if audit is not None:
        print(f"AUDIT OUTPUT: {audit.out}")
        print(f"RECOVERABLE ERRORS: {len(audit.errors)}")
    if archive is not None:
        print(f"SHARE: {archive}")
    if fatal is not None:
        print(f"FATAL ERROR CAPTURED: {fatal!r}")
    print("The audit process completed without intentionally terminating the parent shell.")
    print("=" * 72)

    # Investigation audit deliberately returns success after recording failures,
    # so a caller's 'set -e' cannot discard the report.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
