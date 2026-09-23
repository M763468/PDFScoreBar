#!/usr/bin/env python3
"""Run fresh production full68 validation for Issue #372 inside canonical Docker.

The runner uses configs/dense_full_pipeline.yaml without changing detector/MMR/
numbering behavior. It only derives per-score input/output paths so the five
canonical scores can be run independently without duplicate page stems.

Validation gates:
- canonical 68 pages complete;
- detector current-unit summary matches the retained combined counterfactual;
- fresh final numbering/MMR blocking fields match the retained combined
  downstream replay on all 68 pages.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import yaml

ROOT_DEFAULT = Path("/workspace")
PIPELINE_PYTHON = Path("/opt/venv_pipeline/bin/python")
CONFIG_REL = Path("configs/dense_full_pipeline.yaml")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _logical_signature(payload: Mapping[str, Any]) -> dict[str, Any]:
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], Mapping):
        raise ValueError("Expected one-page numbering payload")
    page = pages[0]
    systems = []
    for system in page.get("systems", []):
        if not isinstance(system, Mapping):
            continue
        measures = [m for m in system.get("measures", []) if isinstance(m, Mapping)]
        systems.append(
            {
                "measure_count": len(measures),
                "numbers": [
                    m.get("number", m.get("measure_number"))
                    for m in measures
                ],
            }
        )
    return {
        "system_count": len(systems),
        "systems": systems,
    }


def _override_signature(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("measure_overrides", [])
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        result.append(
            {
                "page": row.get("page"),
                "system": row.get("system"),
                "measure": row.get("measure"),
                "skip": row.get("skip"),
            }
        )
    return result


def _reference_rows(report: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    variant = report["variants"]["combined_late_raw_frozen_bands"]
    rows = variant["per_page"]
    result = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        result[(str(row["score"]), str(row["page"]))] = row
    return result


def _derive_config(
    *,
    root: Path,
    score_root: Path,
    staged: Path,
    run_id: str,
) -> Path:
    source = root / CONFIG_REL
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    detection = config.get("detection") or {}
    if int(detection.get("sr_scale", 0)) != 4:
        raise ValueError("Production dense config must use sr_scale=4")
    if detection.get("detector_route") != "dense_full_pipeline":
        raise ValueError("Production config must use detector_route=dense_full_pipeline")
    if detection.get("homr_profile") != "maintained_original":
        raise ValueError("Production config must use homr_profile=maintained_original")
    if detection.get("cnn_model_manifest") != "models/barline_cnn/manifest.json":
        raise ValueError("Production config must use the verified CNN manifest")
    if detection.get("cnn_apply_nms") is not False:
        raise ValueError("Production config must keep cnn_apply_nms=false")

    config["inputs"]["pdf_to_images"]["output_dir"] = str(staged)
    config["inputs"]["pdf_to_images"]["image_glob"] = "page_*.png"
    config["run"]["run_id"] = run_id
    config["detection"]["hybrid_output_root"] = str(score_root / "hybrid_output")

    path = score_root / "config_derived.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _stage_score(root: Path, score_root: Path, score: str, pages: list[str]) -> Path:
    staged = score_root / "input_staging" / score
    staged.mkdir(parents=True, exist_ok=False)
    for page in pages:
        source = root / "data" / "evaluation2" / "images" / score / f"{page}.png"
        if not source.is_file():
            raise FileNotFoundError(source)
        (staged / source.name).symlink_to(source)
    return staged


def _run_score(
    *,
    root: Path,
    output: Path,
    score: str,
    pages: list[str],
) -> dict[str, Any]:
    score_root = output / "runs" / score
    score_root.mkdir(parents=True, exist_ok=False)
    staged = _stage_score(root, score_root, score, pages)
    run_id = f"issue372_production_{score}"
    config = _derive_config(
        root=root,
        score_root=score_root,
        staged=staged,
        run_id=run_id,
    )
    pipeline_output = score_root / "pipeline_output"
    pipeline_run = pipeline_output / run_id
    hybrid_run = score_root / "hybrid_output" / run_id
    log_path = score_root / "pipeline.stdout.log"

    command = [
        str(PIPELINE_PYTHON),
        "-m",
        "src.pipeline.main",
        "--config",
        str(config),
        "--run-id",
        run_id,
        "--output-root",
        str(pipeline_output),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)

    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as stream:
        process = subprocess.run(
            command,
            cwd=root,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
        )
    wall = time.perf_counter() - started

    result: dict[str, Any] = {
        "score": score,
        "pages": pages,
        "page_count": len(pages),
        "returncode": process.returncode,
        "wall_sec": wall,
        "config": str(config),
        "pipeline_run": str(pipeline_run),
        "hybrid_run": str(hybrid_run),
        "log": str(log_path),
    }
    if process.returncode != 0:
        result["status"] = "failed"
        result["log_tail"] = log_path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()[-120:]
        return result

    probe_root = (
        pipeline_run
        / "intermediate"
        / "dense_full_pipeline_route"
        / "dense_candidate_reconstruction"
        / "probe_rescue_candidates"
    )
    if not probe_root.is_dir():
        raise FileNotFoundError(probe_root)

    page_rows: dict[str, Any] = {}
    eval_root = output / "detector_eval_inputs" / score
    for page in pages:
        run_dir = probe_root / f"eval2_{score}_{page}"
        final_detector = run_dir / "pipeline2_no_peak_filtered_cnn.json"
        candidates = run_dir / "pipeline2_no_peak_candidates.json"
        final_numbering = pipeline_run / "outputs" / page / "numbering_final.json"
        mmr_path = pipeline_run / "intermediate" / page / "overrides_mmr.json"
        for required in (final_detector, candidates, final_numbering):
            if not required.is_file():
                raise FileNotFoundError(required)

        eval_page = eval_root / page
        eval_page.mkdir(parents=True, exist_ok=True)
        (eval_page / final_detector.name).symlink_to(final_detector)
        (eval_page / candidates.name).symlink_to(candidates)

        final_payload = _load(final_numbering)
        metadata = final_payload.get("numbering_metadata")
        if not isinstance(metadata, Mapping):
            raise ValueError(f"{score}/{page}: final numbering lacks metadata")
        mmr_payload = _load(mmr_path) if mmr_path.is_file() else {"measure_overrides": []}
        page_rows[page] = {
            "continued_logical": _logical_signature(final_payload),
            "continued_start_number": int(metadata["start_number"]),
            "continued_next_number": int(metadata["next_number"]),
            "mmr_overrides": _override_signature(mmr_payload),
            "final_numbering": str(final_numbering),
            "final_detector": str(final_detector),
            "candidates": str(candidates),
        }

    result.update(
        {
            "status": "completed",
            "probe_root": str(probe_root),
            "page_results": page_rows,
        }
    )
    _write(score_root / "score_summary.json", result)
    return result


def _evaluate_detector(
    *,
    root: Path,
    output: Path,
) -> dict[str, Any]:
    from tools.issue120 import eval_full68_from_intermediates as full68

    args = argparse.Namespace(
        results_dir=str(output / "detector_eval_inputs"),
        gt_root=str(root / "data/evaluation2/annotations"),
        output_dir=str(output / "detector_eval"),
        scored_file="pipeline2_no_peak_filtered_cnn.json",
        candidates_file="pipeline2_no_peak_candidates.json",
        score_threshold=0.4965248107910156,
        rule_name="center_anchor",
        vov_threshold=0.5,
        staff_units_json=str(root / "data/evaluation2/staff_units.json"),
        image_root=str(root / "data/evaluation2/images"),
        xdist_unit_ratio=0.5,
        legacy_fixed_12px=False,
        allow_partial=False,
        measure_summary_json=None,
    )
    contract = full68.evaluate(args)
    return asdict(contract.detector_summary)


def _compare_detector(
    actual: Mapping[str, Any],
    counterfactual: Mapping[str, Any],
) -> dict[str, Any]:
    expected = counterfactual["evaluation"]["current_unit"]
    fields = (
        "gt",
        "pred",
        "candidate_count",
        "tp",
        "fp",
        "fn",
        "fn_det",
        "fn_cnn",
    )
    differences = {
        field: {"expected": expected.get(field), "actual": actual.get(field)}
        for field in fields
        if expected.get(field) != actual.get(field)
    }
    return {
        "match": not differences,
        "expected": {field: expected.get(field) for field in fields},
        "actual": {field: actual.get(field) for field in fields},
        "differences": differences,
    }


def _compare_numbering(
    fresh: Mapping[tuple[str, str], Mapping[str, Any]],
    reference: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    changed = []
    for key in sorted(set(fresh) | set(reference)):
        if key not in fresh or key not in reference:
            changed.append(
                {"score": key[0], "page": key[1], "reason": "missing_page"}
            )
            continue
        left = reference[key]
        right = fresh[key]
        fields = {
            "continued_logical": (
                left["continued_logical"],
                right["continued_logical"],
            ),
            "continued_start_number": (
                left["continued_start_number"],
                right["continued_start_number"],
            ),
            "continued_next_number": (
                left["continued_next_number"],
                right["continued_next_number"],
            ),
            "mmr_overrides": (
                left["mmr_overrides"],
                right["mmr_overrides"],
            ),
        }
        differences = {
            name: {"reference": pair[0], "fresh": pair[1]}
            for name, pair in fields.items()
            if pair[0] != pair[1]
        }
        if differences:
            changed.append(
                {
                    "score": key[0],
                    "page": key[1],
                    "differences": differences,
                }
            )
    return {
        "match": not changed,
        "changed_page_count": len(changed),
        "changed_pages": changed,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.project_root.resolve()
    output = args.output.resolve()
    counterfactual_path = args.counterfactual_report.resolve()
    reference_path = args.reference_replay.resolve()

    if not Path("/.dockerenv").exists():
        raise RuntimeError("Production full68 validation must run inside Docker")
    if root != ROOT_DEFAULT:
        raise RuntimeError(f"Expected project root /workspace, got {root}")
    if not PIPELINE_PYTHON.is_file():
        raise FileNotFoundError(PIPELINE_PYTHON)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output must be new/empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    counterfactual = _load(counterfactual_path)
    reference_report = _load(reference_path)
    reference_rows = _reference_rows(reference_report)

    from tools.issue120.eval_full68_from_intermediates import SCORES

    scores = {score: list(pages) for score, pages in SCORES.items()}
    if sum(len(pages) for pages in scores.values()) != 68:
        raise RuntimeError("Canonical page selection is not 68 pages")

    score_summaries = []
    fresh_rows: dict[tuple[str, str], Mapping[str, Any]] = {}
    for score, pages in scores.items():
        print(f"=== {score}: {len(pages)} pages ===", flush=True)
        summary = _run_score(
            root=root,
            output=output,
            score=score,
            pages=pages,
        )
        score_summaries.append(summary)
        _write(output / "progress.json", {"scores": score_summaries})
        if summary.get("status") != "completed":
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            raise RuntimeError(f"Production full68 failed for {score}")
        for page, row in summary["page_results"].items():
            fresh_rows[(score, page)] = row
        print(
            json.dumps(
                {
                    "score": score,
                    "status": "completed",
                    "wall_sec": summary["wall_sec"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    detector = _evaluate_detector(root=root, output=output)
    detector_comparison = _compare_detector(detector, counterfactual)
    numbering_comparison = _compare_numbering(fresh_rows, reference_rows)

    target_key = ("Shostakovich-Sym5-Va", "page_021")
    target = fresh_rows[target_key]
    target_measures = [
        system["measure_count"]
        for system in target["continued_logical"]["systems"]
    ]
    page021_gate = {
        "measure_counts": target_measures,
        "start_number": target["continued_start_number"],
        "next_number": target["continued_next_number"],
        "expected_measure_counts": [4, 4, 3, 5, 6, 6, 6, 5, 6, 6],
        "expected_start_number": 640,
        "expected_next_number": 691,
    }
    page021_gate["pass"] = (
        page021_gate["measure_counts"] == page021_gate["expected_measure_counts"]
        and page021_gate["start_number"] == page021_gate["expected_start_number"]
        and page021_gate["next_number"] == page021_gate["expected_next_number"]
    )

    result = {
        "schema_version": "issue372.production_full68_validation.v1",
        "source_commit": args.source_commit,
        "canonical_config": str(root / CONFIG_REL),
        "page_count": len(fresh_rows),
        "detector": detector,
        "detector_vs_combined_counterfactual": detector_comparison,
        "numbering_vs_combined_replay": numbering_comparison,
        "page021_gate": page021_gate,
        "score_summaries": score_summaries,
        "pass": (
            len(fresh_rows) == 68
            and detector_comparison["match"]
            and numbering_comparison["match"]
            and page021_gate["pass"]
        ),
    }
    report = output / "production_full68_validation.json"
    _write(report, result)

    print("=== Issue #372 production full68 validation ===")
    print("detector=", json.dumps(detector, ensure_ascii=False))
    print(
        "detector_matches_counterfactual=",
        detector_comparison["match"],
        "differences=",
        detector_comparison["differences"],
    )
    print(
        "numbering_matches_combined_replay=",
        numbering_comparison["match"],
        "changed_pages=",
        numbering_comparison["changed_page_count"],
    )
    for row in numbering_comparison["changed_pages"]:
        print(f"  changed: {row['score']}/{row['page']}")
    print("page_021=", json.dumps(page021_gate, ensure_ascii=False))
    print(f"PASS={result['pass']}")
    print(f"OUTPUT={report}")

    if not result["pass"]:
        raise SystemExit(1)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--counterfactual-report", type=Path, required=True)
    parser.add_argument("--reference-replay", type=Path, required=True)
    run(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
