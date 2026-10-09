#!/usr/bin/env python3
"""Replay all retained #409 Full68 Phase-C inputs without upstream inference.

Run from the checkout root with PYTHONPATH=.; requires the pipeline environment.
The retained base JSON/MMR predictions are copied unchanged; only final numbering
and final PDF materialization execute. All physical-measure deltas are retained.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import fitz
from PIL import Image

from src.common.connector_artifacts import connector_mask_paths_for_numbering
from src.pipeline.core import load_json, write_json
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.review.final_output import (
    _render_final_page_image,
    materialize_corrected_final_outputs,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_path(raw: str, root: Path) -> Path:
    path = Path(raw)
    if path.is_relative_to("/workspace"):
        return root / path.relative_to("/workspace")
    return path


def geometry(page: dict) -> dict:
    result = deepcopy(page)
    for system in result["systems"]:
        for measure in system["measures"]:
            measure.pop("number")
    return result


def verify_pdf_images(summary: dict) -> list[dict]:
    """Check actual PDF image pixels, including labels, without a tolerance.

    PIL's PDF writer uses JPEG. Encode the same expected page with its default
    JPEG encoder before comparing decoded pixels to the actual embedded image.
    """
    results = []
    with fitz.open(summary["final_pdf"]) as pdf:
        assert len(pdf) == len(summary["pages"])
        for index, page in enumerate(summary["pages"]):
            expected, _ = _render_final_page_image(
                source_image_path=Path(page["source_image"]),
                numbering_path=Path(page["corrected_numbering_final"]),
                page_id=page["page_id"],
                page_number=page["page_number"],
            )
            buffer = io.BytesIO()
            expected.save(buffer, format="JPEG")
            expected.close()
            images = pdf[index].get_images()
            assert len(images) == 1, (page["page_id"], "PDF image count")
            embedded = pdf.extract_image(images[0][0])
            with (
                Image.open(io.BytesIO(buffer.getvalue())) as reference,
                Image.open(io.BytesIO(embedded["image"])) as actual,
            ):
                assert actual.size == reference.size
                actual_hash = hashlib.sha256(actual.convert("RGB").tobytes()).hexdigest()
                expected_hash = hashlib.sha256(reference.convert("RGB").tobytes()).hexdigest()
                assert actual_hash == expected_hash, (page["page_id"], "PDF pixel mismatch")
            results.append({"page_id": page["page_id"], "decoded_rgb_sha256": actual_hash})
    return results


def audit_score(
    score_name: str, baseline: list[dict], candidate: list[dict], predictions: list[dict]
):
    assert len(baseline) == len(candidate) == len(predictions), "page scope changed"
    old_measures, new_measures = [], []
    expected = {}
    for p, (old, new, prediction) in enumerate(zip(baseline, candidate, predictions)):
        assert geometry(old["pages"][0]) == geometry(new["pages"][0]), (score_name, p, "geometry")
        for ov in prediction["measure_overrides"]:
            if ov["page"] == p:
                expected[(p, ov["system"], ov["measure"])] = ov.get("skip", 0)
        for s, system in enumerate(old["pages"][0]["systems"]):
            old_measures.extend(
                ((p, s, m), measure) for m, measure in enumerate(system["measures"])
            )
        for s, system in enumerate(new["pages"][0]["systems"]):
            new_measures.extend(
                ((p, s, m), measure) for m, measure in enumerate(system["measures"])
            )
    assert [key for key, _ in old_measures] == [key for key, _ in new_measures]
    assert set(expected) <= {key for key, _ in new_measures}, (
        score_name,
        "missing override target",
    )
    records = []
    for i, ((key, old), (_, new)) in enumerate(zip(old_measures, new_measures)):
        old_next = (
            old_measures[i + 1][1]["number"]
            if i + 1 < len(old_measures)
            else baseline[-1]["numbering_metadata"]["next_number"]
        )
        new_next = (
            new_measures[i + 1][1]["number"]
            if i + 1 < len(new_measures)
            else candidate[-1]["numbering_metadata"]["next_number"]
        )
        recognized = expected.get(key, 0)
        records.append(
            {
                "score": score_name,
                "page": baseline[key[0]]["page_id"],
                "page_index": key[0],
                "system": key[1],
                "measure": key[2],
                "bbox": new["bbox"],
                "old_number": old["number"],
                "new_number": new["number"],
                "recognized_skip": recognized,
                "old_applied_skip": old_next - old["number"] - 1,
                "new_applied_skip": new_next - new["number"] - 1,
            }
        )
    return records


def replay(retained: Path, output: Path) -> dict:
    root = Path.cwd().resolve()
    if output.exists():
        raise FileExistsError(f"Use a fresh output directory: {output}")
    output.mkdir(parents=True)
    source = load_json(retained / "candidate/variant_summary.json")
    assert source["canonical_page_count"] == 68
    contract = {
        "scope": "all five retained scores / 68 pages; compact physical system and measure indices",
        "primary_gate": "recognized skip equals applied increment at every physical measure",
        "required_gates": [
            "104 baseline mismatches reproduced and resolved",
            "unchanged geometry",
            "unchanged source/OCR/config artifacts",
            "page continuity",
            "per-page/combined/PDF row-label agreement",
        ],
        "retained_source_commit": source["git_commit"],
        "candidate_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "candidate_diff_sha256": hashlib.sha256(
            subprocess.check_output(["git", "diff", "HEAD"])
        ).hexdigest(),
        "command": "python tools/issue413/replay_phase_c.py --retained-root "
        f"{retained} --output {output}",
        "upstream_inference_reexecuted": False,
        "execution_config_changes": "detection/pdf render/filter/Phase A disabled; retained Phase B "
        "files reused via skip_existing; standard input resolution only",
    }
    write_json(output / "contract.json", contract)
    hashes = {}
    all_records = []
    score_reports = []
    page_total = 0
    for entry in source["scores"]:
        score_name = entry["score"]
        score_root = retained / "candidate" / score_name
        old_run = local_path(entry["pipeline_run"], root)
        manifest_path = old_run / "manifest.json"
        manifest = load_json(manifest_path)
        assert not manifest["config"]["inputs"].get("measure_overrides")
        assert not manifest["config"]["inputs"].get("movement_boundaries")
        assert not manifest["config"]["steps"].get("apply_barline_overrides")
        pages = manifest["pages"]
        assert [page["page_id"] for page in pages] == entry["pages"]
        new_run = output / score_name
        images = new_run / "inputs/images"
        images.mkdir(parents=True)
        config = deepcopy(manifest["config"])
        config["steps"].update(
            pdf_to_images=False,
            detection=False,
            filter_pages=False,
            numbering_base=False,
            mmr_overrides=True,
            apply_measure_overrides=True,
            overlay=False,
        )
        # All model steps are skipped. This selector only bypasses preparation
        # of fresh MMR support; the original predictions remain authoritative.
        config["detection"]["detector_route"] = "standard"
        first = pages[0]
        config["inputs"].update(
            pdf_to_images={"output_dir": str(images), "image_glob": "page_*.png"},
            barlines_root=str(root),
            barlines_pattern=str(local_path(first["barlines_json"], root)).replace(
                first["page_id"], "{page_id}"
            ),
            staff_mask_pattern=str(local_path(first["staff_mask"], root)).replace(
                first["page_id"], "{page_id}"
            ),
        )
        baseline = []
        predictions = []
        handoff_pages = []
        for page in pages:
            page_id = page["page_id"]
            intermediate = new_run / "intermediate" / page_id
            intermediate.mkdir(parents=True)
            source_image = local_path(page["image_path"], root)
            shutil.copyfile(source_image, images / f"{page_id}.png")
            for name in ("numbering_base.json", "overrides_mmr.json"):
                original = old_run / "intermediate" / page_id / name
                hashes[str(original)] = sha256(original)
                shutil.copyfile(original, intermediate / name)
            old = load_json(old_run / "outputs" / page_id / "numbering_final.json")
            old["page_id"] = page_id
            baseline.append(old)
            predictions.append(load_json(intermediate / "overrides_mmr.json"))
            mask = local_path(page["staff_mask"], root)
            connector_paths = connector_mask_paths_for_numbering(mask)
            assert connector_paths, (score_name, page_id, "missing retained connector semantics")
            for path in [
                source_image,
                local_path(page["barlines_json"], root),
                mask,
                *connector_paths.values(),
            ]:
                hashes[str(path)] = sha256(path)
            handoff_pages.append(
                {
                    "page_id": page_id,
                    "page_number": old["pages"][0]["page_number"],
                    "source_image": f"inputs/images/{page_id}.png",
                }
            )
        for path in (manifest_path, score_root / "config_derived.yaml"):
            hashes[str(path)] = sha256(path)
        write_json(new_run / "replay_config.json", config)
        orchestrator = PipelineOrchestrator(
            config, f"issue413_{score_name}", new_run, skip_existing=True
        )
        orchestrator.run()
        candidate = [
            load_json(new_run / "outputs" / page["page_id"] / "numbering_final.json")
            for page in pages
        ]
        combined = load_json(new_run / "outputs/numbering_final.json")
        assert combined["pages"] == [page["pages"][0] for page in candidate]
        assert (
            combined["numbering_metadata"]["next_number"]
            == candidate[-1]["numbering_metadata"]["next_number"]
        )
        previous_next = 1
        for page in candidate:
            assert page["numbering_metadata"]["start_number"] == previous_next
            previous_next = page["numbering_metadata"]["next_number"]
        records = audit_score(score_name, baseline, candidate, predictions)
        all_records.extend(records)
        handoff = new_run / "handoff.json"
        write_json(handoff, {"pages": handoff_pages})
        final = materialize_corrected_final_outputs(
            handoff_path=handoff, corrected_run_dir=new_run, output_name=score_name
        )
        row_labels = 0
        for page, summary in zip(candidate, final["pages"]):
            expected_rows = [
                system["measures"][0]["number"] for system in page["pages"][0]["systems"]
            ]
            assert [
                row["row_start_measure_number"] for row in summary["row_labels"]
            ] == expected_rows
            row_labels += len(expected_rows)
        write_json(new_run / "review/pdf-pixel-verification.json", verify_pdf_images(final))
        page_total += len(pages)
        score_reports.append(
            {
                "score": score_name,
                "pages": len(pages),
                "physical_measures": len(records),
                "pdf": final["final_pdf"],
                "pdf_pages": len(pages),
                "row_labels": row_labels,
                "next_number": previous_next,
            }
        )
        print(
            f"{score_name}: {len(pages)} pages, {len(records)} measures, {row_labels} PDF row labels",
            flush=True,
        )
    assert page_total == 68
    for path, digest in hashes.items():
        assert sha256(Path(path)) == digest, (path, "retained input changed")
    write_json(output / "input_sha256.json", hashes)
    baseline_errors = [r for r in all_records if r["old_applied_skip"] != r["recognized_skip"]]
    remaining_errors = [r for r in all_records if r["new_applied_skip"] != r["recognized_skip"]]
    prior_errors = load_json(retained / "recognized-vs-applied-increments.json")["errors"]

    def identity(r):
        return r["score"], r["page"], r["system"], r["measure"]

    assert {identity(r) for r in baseline_errors} == {identity(r) for r in prior_errors}
    write_json(output / "all-physical-measures.json", all_records)
    write_json(output / "resolved-104.json", baseline_errors)
    write_json(
        output / "number-deltas.json",
        [r for r in all_records if r["old_number"] != r["new_number"]],
    )
    report = {
        "contract": contract,
        "pages": page_total,
        "scores": score_reports,
        "physical_measures": len(all_records),
        "baseline_errors": len(baseline_errors),
        "remaining_errors": remaining_errors,
        "number_deltas": sum(r["old_number"] != r["new_number"] for r in all_records),
        "status": "PASS" if len(baseline_errors) == 104 and not remaining_errors else "FAIL",
    }
    write_json(output / "report.json", report)
    assert report["status"] == "PASS", report
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retained-root", type=Path, default=Path("logs/issue409/full68-numbering-20261009")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = replay(args.retained_root.resolve(), args.output.resolve())
    print(
        json.dumps(
            {key: value for key, value in report.items() if key not in ("contract", "scores")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
