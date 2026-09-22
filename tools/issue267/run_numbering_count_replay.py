#!/usr/bin/env python3
"""Replay Issue #267 base numbering from retained accepted upstream artifacts.

This runner deliberately does not execute detector, SR, HOMR, CNN, MMR, or OCR.
It reuses the accepted Issue #264 Phase-A semantic-support artifacts and canonical
detector barlines, then executes only the current checkout's measure-numbering
path.  Use the same artifact root for the pre-#267 baseline and candidate runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CANONICAL_RUN = "issue255_production_restore_full68_top_level_worker_01"
DEFAULT_SUPPORT_RUN = "issue264_phase_c_current_production_full68_02"
IMAGE_STEM_RE = re.compile(r"^(?P<score>.+)_page_(?P<page>\d{3})$")


@dataclass(frozen=True)
class PageSpec:
    page_id: str
    page_number: int
    score: str
    page_name: str
    image_stem: str
    image: Path
    barlines: Path
    staff_mask: Path


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head(code_root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(code_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _install_code_root(code_root: Path) -> None:
    resolved = code_root.resolve()
    if not (resolved / "src").is_dir():
        raise FileNotFoundError(f"Code root does not contain src/: {resolved}")
    os.chdir(resolved)
    sys.path.insert(0, str(resolved))


def _parse_image_stem(stem: str) -> tuple[str, str]:
    match = IMAGE_STEM_RE.fullmatch(stem)
    if match is None:
        raise ValueError(f"Unexpected evaluation image stem: {stem}")
    return match.group("score"), f"page_{match.group('page')}"


def build_page_specs(
    input_root: Path,
    *,
    support_run: str,
    page_limit: int | None = None,
) -> list[PageSpec]:
    page_index = input_root / "logs/issue94_mmr_current_state/page_inputs.json"
    payload = _load_json(page_index)
    raw_pages = payload.get("pages")
    if not isinstance(raw_pages, list):
        raise ValueError(f"Page index lacks pages list: {page_index}")

    specs: list[PageSpec] = []
    selected = raw_pages[:page_limit] if page_limit is not None else raw_pages
    for position, raw in enumerate(selected, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Malformed page entry at position {position}")
        page_id = str(raw.get("page_id", ""))
        expected_page_id = f"page_{position:03d}"
        if page_id != expected_page_id:
            raise ValueError(
                f"Global page mapping changed at position {position}: "
                f"expected {expected_page_id}, got {page_id}"
            )

        image_stem = Path(str(raw.get("image", ""))).stem
        score, page_name = _parse_image_stem(image_stem)
        image = input_root / "data/evaluation2/images" / score / f"{page_name}.png"
        barlines = (
            input_root
            / "logs/verification/detector_full68"
            / CANONICAL_RUN
            / "production_runs"
            / score
            / "intermediate/dense_full_pipeline_route/dense_candidate_reconstruction"
            / "probe_rescue_candidates"
            / f"eval2_{image_stem}"
            / "pipeline2_no_peak_filtered_cnn.json"
        )
        staff_mask = (
            input_root
            / "logs/issue264_phase_c_mmr_regression"
            / support_run
            / "phase_a_hybrid_replay"
            / score
            / "sr/batch"
            / page_name
            / f"{page_name}_proxy_debug_3_staff.png"
        )
        specs.append(
            PageSpec(
                page_id=page_id,
                page_number=position,
                score=score,
                page_name=page_name,
                image_stem=image_stem,
                image=image,
                barlines=barlines,
                staff_mask=staff_mask,
            )
        )
    return specs


def validate_inputs(specs: list[PageSpec], *, expect_full68: bool) -> None:
    if expect_full68 and len(specs) != 68:
        raise ValueError(f"Expected 68 pages, got {len(specs)}")

    missing: list[str] = []
    for spec in specs:
        for label, path in (
            ("image", spec.image),
            ("barlines", spec.barlines),
            ("staff_mask", spec.staff_mask),
        ):
            if not path.is_file():
                missing.append(f"{spec.page_id} {label}: {path}")
    if missing:
        raise FileNotFoundError("Missing Issue #267 replay inputs:\n" + "\n".join(f"- {x}" for x in missing))


def run(
    *,
    code_root: Path,
    input_root: Path,
    output_root: Path,
    support_run: str,
    page_limit: int | None,
) -> Path:
    _install_code_root(code_root)

    import cv2

    from src.common.connector_artifacts import describe_connector_artifacts
    from src.measure_numbering.pipeline import MeasureNumberingPipeline
    from src.measure_numbering.serialization import score_to_dict
    from src.measure_numbering.types import Score
    from src.pipeline.steps.barlines import normalize_barlines

    specs = build_page_specs(input_root, support_run=support_run, page_limit=page_limit)
    validate_inputs(specs, expect_full68=page_limit is None)

    output_root.mkdir(parents=True, exist_ok=True)
    pipeline = MeasureNumberingPipeline()
    page_reports: list[dict[str, Any]] = []

    for spec in specs:
        connector_description = describe_connector_artifacts(spec.staff_mask)
        if connector_description.get("source") != "proxy_symbol_layers":
            raise RuntimeError(
                f"{spec.page_id}: expected proxy_symbol_layers connector semantics, "
                f"got {connector_description}"
            )

        image = cv2.imread(str(spec.image), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"Could not read image: {spec.image}")
        height, width = image.shape[:2]

        raw_barlines = _load_json(spec.barlines)
        barline_boxes = normalize_barlines(raw_barlines)
        page = pipeline.process_page(
            barline_boxes,
            spec.staff_mask,
            (width, height),
            page_number=spec.page_number,
            image=image,
        )

        score = Score()
        score.pages.append(page)
        pipeline.numberer.number_score(score, start_number=1)
        payload = score_to_dict(score)

        numbering_path = output_root / "intermediate" / spec.page_id / "numbering_base.json"
        _write_json(numbering_path, payload)

        counts = [len(system.get("measures", [])) for system in payload["pages"][0]["systems"]]
        page_reports.append(
            {
                "page_id": spec.page_id,
                "score": spec.score,
                "score_page": spec.page_name,
                "barline_count": len(barline_boxes),
                "system_measure_counts": counts,
                "physical_measure_total": sum(counts),
                "connector_source": connector_description.get("source"),
                "inputs": {
                    "image": str(spec.image),
                    "barlines": str(spec.barlines),
                    "staff_mask": str(spec.staff_mask),
                },
            }
        )
        print(
            f"{spec.page_id}: systems={len(counts)} "
            f"physical={sum(counts)} signature={counts}"
        )

    report = {
        "schema_version": "issue267.numbering_count_replay.v1",
        "code_root": str(code_root.resolve()),
        "git_head": _git_head(code_root),
        "input_root": str(input_root.resolve()),
        "support_run": support_run,
        "detector_reexecuted": False,
        "sr_reexecuted": False,
        "homr_reexecuted": False,
        "mmr_reexecuted": False,
        "pages": len(page_reports),
        "physical_measure_total": sum(item["physical_measure_total"] for item in page_reports),
        "page_reports": page_reports,
        "provenance": {
            "page_index": {
                "path": str(input_root / "logs/issue94_mmr_current_state/page_inputs.json"),
                "sha256": _sha256(input_root / "logs/issue94_mmr_current_state/page_inputs.json"),
            },
            "canonical_detector_run": CANONICAL_RUN,
        },
    }
    report_path = output_root / "issue267_numbering_count_replay_report.json"
    _write_json(report_path, report)
    print(f"report: {report_path}")
    print(f"physical measure total: {report['physical_measure_total']}")
    return report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--code-root",
        type=Path,
        required=True,
        help="Checkout/worktree whose src/ implementation should be executed.",
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        required=True,
        help="Checkout containing retained data/ and logs/ artifacts.",
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--support-run", default=DEFAULT_SUPPORT_RUN)
    parser.add_argument(
        "--page-limit",
        type=int,
        help="Optional smoke-only prefix length. Omit for the required full 68-page replay.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run(
        code_root=args.code_root,
        input_root=args.input_root,
        output_root=args.output_root,
        support_run=args.support_run,
        page_limit=args.page_limit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
