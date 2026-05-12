#!/usr/bin/env python3
"""Inventory tracked Issue #120 artifacts.

The script uses `git ls-files` so it audits what is already tracked, not what is
present in ignored local output directories.  It is intended for #135 cleanup
reviews and can be run from any checkout without Docker/GPU dependencies.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ClassifiedPath:
    path: str
    classification: str
    reason: str


GENERATED_FILENAMES = {
    "global_summary.csv",
    "detector_metrics.json",
    "detector_page_metrics.csv",
    "evaluation_contract.json",
    "intermediate_provenance.json",
    "manifest.json",
    "missing_pages.json",
}

CANONICAL_INTERMEDIATE_FILENAMES = {
    "pipeline2_no_peak_candidates.json",
    "pipeline2_no_peak_filtered_cnn.json",
    "pipeline2_no_peak_scored.json",
}

GENERATED_PATH_KEEPERS = {
    "artifacts/.gitkeep",
    "logs/README.md",
}


def git_ls_files(repo_root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise SystemExit("git is required to run the artifact inventory") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace")
        raise SystemExit(f"git ls-files failed:\n{stderr}") from exc

    raw = result.stdout.decode("utf-8", errors="replace")
    return [item for item in raw.split("\0") if item]


def classify_path(path: str) -> ClassifiedPath:
    p = Path(path)
    name = p.name
    suffix = p.suffix.lower()

    if path in GENERATED_PATH_KEEPERS:
        return ClassifiedPath(
            path,
            "generated_path_keeper",
            "Tracked placeholder/documentation file that keeps or explains an otherwise ignored generated-output path.",
        )

    if path.startswith("data/evaluation2/golden_baseline_eval2_bc23deb/"):
        if name in CANONICAL_INTERMEDIATE_FILENAMES:
            return ClassifiedPath(
                path,
                "retained_issue120_intermediate_fixture",
                "Stage A/B/C canonical detector reconstruction still depends on this saved intermediate fixture.",
            )
        if name == "eval_config.yaml":
            return ClassifiedPath(
                path,
                "retained_issue120_provenance_fixture",
                "Small provenance/config snapshot for the retained golden-baseline intermediate fixture.",
            )
        if name in GENERATED_FILENAMES:
            return ClassifiedPath(
                path,
                "generated_artifact",
                "Generated evaluation summary/output; regenerate under ignored logs/ instead of tracking.",
            )
        return ClassifiedPath(
            path,
            "review_issue120_fixture",
            "Inside the golden-baseline fixture tree but not a known canonical intermediate filename.",
        )

    if path.startswith("data/evaluation2/annotations/"):
        return ClassifiedPath(
            path,
            "source_evaluation_input",
            "Canonical full-68 ground-truth input, not a generated run output.",
        )

    if path.startswith("data/evaluation2/images/"):
        return ClassifiedPath(
            path,
            "source_evaluation_input",
            "Canonical full-68 image input, not a generated run output.",
        )

    if path.startswith(("logs/", "artifacts/", "output/", "debug_outputs/", "temp/")):
        return ClassifiedPath(
            path,
            "generated_artifact",
            "Tracked file is under a generated-output path that should stay ignored.",
        )

    if path.startswith("configs/") and (p.name.startswith("tmp_") or "generated" in p.name):
        return ClassifiedPath(
            path,
            "generated_artifact",
            "Temporary/generated config should not be tracked.",
        )

    if name in GENERATED_FILENAMES:
        return ClassifiedPath(
            path,
            "generated_artifact",
            "Generated evaluation summary/output; regenerate under ignored logs/ instead of tracking.",
        )

    if suffix in {".log"}:
        return ClassifiedPath(path, "generated_artifact", "Log file should not be tracked.")

    if suffix in {".png", ".jpg", ".jpeg"} and not path.startswith("data/evaluation2/images/"):
        return ClassifiedPath(
            path,
            "review_visual_artifact",
            "Image outside canonical evaluation input; likely crop/overlay/contact-sheet evidence.",
        )

    if path.startswith(("docs/", "tools/", "src/", "tests/", ".github/")):
        return ClassifiedPath(path, "source", "Source, tests, tooling, or documentation.")

    if path.startswith("configs/"):
        return ClassifiedPath(path, "source_config", "Tracked config/template.")

    return ClassifiedPath(path, "source_or_unclassified", "No Issue #120 generated-artifact pattern matched.")


def summarize(items: Iterable[ClassifiedPath], *, example_limit: int) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[ClassifiedPath]] = defaultdict(list)
    for item in items:
        grouped[item.classification].append(item)

    summary: dict[str, dict[str, object]] = {}
    for classification in sorted(grouped):
        paths = grouped[classification]
        reasons = Counter(item.reason for item in paths)
        summary[classification] = {
            "count": len(paths),
            "primary_reason": reasons.most_common(1)[0][0],
            "examples": [item.path for item in paths[:example_limit]],
        }
    return summary


def render_markdown(summary: dict[str, dict[str, object]]) -> str:
    lines = [
        "# Issue 120 tracked artifact inventory",
        "",
        "| Classification | Count | Primary reason | Examples |",
        "| --- | ---: | --- | --- |",
    ]
    for classification, payload in summary.items():
        examples = "<br>".join(str(path) for path in payload["examples"])
        reason = str(payload["primary_reason"]).replace("|", "\\|")
        lines.append(f"| `{classification}` | {payload['count']} | {reason} | {examples} |")
    lines.append("")
    lines.append("Generated artifacts should be removed from Git or moved under ignored `logs/` paths.")
    lines.append("Retained Issue #120 fixtures require an explicit rationale in `docs/ISSUE120_ARTIFACT_RETENTION.md`.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root to inspect. Defaults to the current directory.",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--example-limit",
        type=int,
        default=8,
        help="Maximum example paths per classification.",
    )
    parser.add_argument(
        "--fail-on-generated",
        action="store_true",
        help="Exit non-zero if tracked generated artifacts are found.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    repo_root = args.repo_root.resolve()
    classified = [classify_path(path) for path in git_ls_files(repo_root)]
    summary = summarize(classified, example_limit=args.example_limit)

    if args.format == "json":
        payload = {
            "schema_version": "issue120.tracked_artifact_inventory.v1",
            "repo_root": str(repo_root),
            "summary": summary,
            "paths": [asdict(item) for item in classified],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(summary))

    if args.fail_on_generated and "generated_artifact" in summary:
        count = summary["generated_artifact"]["count"]
        print(f"Tracked generated artifacts found: {count}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
