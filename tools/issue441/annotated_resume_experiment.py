"""Resume retained corrections onto the supplied annotated PDF in isolated copies.

No detector inference, original mutation, or product GUI integration. Run inside
the validated runtime with original source read-only and only issue logs writable.
"""

from __future__ import annotations

import argparse
import json
import shutil
from copy import deepcopy
from pathlib import Path

import fitz

from src.measure_numbering import rapidocr_provider
from tools.issue441.crop_label_layer import records_from_run, write_number_layer
from tools.issue441.mobile_export_probe import match_source
from tools.issue441.phase0_probe import sha
from tools.review_correction.application import CorrectionApplication
from tools.review_correction.server import ReviewPackage


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def relocate(value, job):
    old_root = f"/results/{job.name}"
    if isinstance(value, str) and (value == old_root or value.startswith(old_root + "/")):
        result = job / value.removeprefix(old_root + "/")
        if not result.resolve().is_relative_to(job.resolve()):
            raise ValueError("Retained path escaped known job root")
        return str(result)
    if isinstance(value, list):
        return [relocate(x, job) for x in value]
    if isinstance(value, dict):
        return {k: relocate(v, job) for k, v in value.items()}
    return value


def clone_checkpoint(job, attempt_name, destination):
    attempt = job / "review/application_runs" / attempt_name
    old = ReviewPackage(attempt / "input_review/manual_correction_input.json")
    consumed = json.loads((attempt / "consumed_inputs.json").read_text())
    assert old.state.capture_identity()["corrections_identity"] == consumed["corrections_identity"]
    review = destination / "review"
    review.mkdir(parents=True, exist_ok=False)
    for relative in old.reads:
        target = review / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(old.readable(relative), target)
    for relative in old.writes:
        path = old.writable(relative)
        if path.is_file():
            target = review / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    original_manifest = job / ".engine-retained/runs" / job.name / "local_manifest.json"
    manifest = destination / "retained/local_manifest.json"
    write_json(manifest, relocate(json.loads(original_manifest.read_text()), job))
    # Preserve the actual retained pre-correction geometry, rather than falling
    # back to already-numbered/modified final geometry in the source package.
    payload = json.loads(old.handoff_path.read_text())
    for page in payload["pages"]:
        base = original_manifest.parent / "intermediate" / page["page_id"] / "numbering_base.json"
        target = manifest.parent / "intermediate" / page["page_id"] / "numbering_base.json"
        target.parent.mkdir(parents=True)
        shutil.copyfile(base, target)
    payload["source_manifest"] = str(manifest.resolve())
    payload["output_name"] = f"resumed_{attempt_name}"
    with fitz.open(job / ".engine-retained/input/source.pdf") as source:
        for index, page in enumerate(payload["pages"]):
            page["page_size_points"] = [source[index].mediabox.width, source[index].mediabox.height]
    handoff = review / "manual_correction_input.json"
    write_json(handoff, payload)
    package = ReviewPackage(handoff)
    assert (
        package.state.capture_identity()["corrections_identity"] == consumed["corrections_identity"]
    )
    assert package.state.snapshot()["package"]["current_result"] is None
    provenance = {
        "checkpoint_attempt": attempt_name,
        "original_identity": consumed,
        "original_manifest_sha256": sha(original_manifest),
        "restored_identity": package.state.capture_identity(),
        "input_pdf_role": "annotated_source_with_known_original_background",
    }
    write_json(destination / "resume_provenance.json", provenance)
    return package, provenance


def apply(package):
    app = CorrectionApplication(package, package.handoff_path)
    app.start()
    app.thread.join()
    snapshot = package.state.snapshot()
    if snapshot["package"]["status"] == "error" or not snapshot["package"]["current_result"]:
        raise RuntimeError(f"Downstream apply failed: {snapshot}")
    result = snapshot["package"]["current_result"]
    run = Path(result["corrected_run"])
    summary = json.loads((run / "review/correction_summary.json").read_text())
    assert summary["upstream_inference_rerun"] is False
    return run, result


def numbers(run):
    result = []
    for path in sorted((Path(run) / "outputs").glob("page_*/numbering_final.json")):
        page = json.loads(path.read_text())["pages"][0]
        result.append([[m.get("number") for m in s.get("measures", [])] for s in page["systems"]])
    return result


def summarize_layer(layer):
    return {
        k: layer[k]
        for k in (
            "output_sha256",
            "label_count",
            "all_original_dark_pixels_and_annotations_unchanged",
            "previous_layer_removed_to_exact_original",
        )
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    original_hash = sha(args.pdf)
    match_source(args.pdf, args.job / ".engine-retained/input/source.pdf")
    report = {
        "annotated_pdf_sha256": original_hash,
        "probe_sha256": sha(Path(__file__)),
        "label_code_sha256": sha(Path(__file__).with_name("crop_label_layer.py")),
        "checkpoints": {},
        "mmr_runtime_providers": [],
    }
    original_factory = rapidocr_provider.create_mmr_rapidocr

    def checked_factory(mode):
        engine = original_factory(mode)
        actual = rapidocr_provider.collect_rapidocr_providers(engine)
        if not actual or any("CUDAExecutionProvider" not in p for p in actual.values()):
            raise RuntimeError(f"MMR OCR runtime did not use CUDA: {actual}")
        report["mmr_runtime_providers"].append(actual)
        print(f"Confirmed MMR runtime providers: {actual}", flush=True)
        return engine

    # Inspection only: return the real production engine, reject runtime fallback.
    rapidocr_provider.create_mmr_rapidocr = checked_factory
    for name in ("attempt_0001", "attempt_0012"):
        print(f"Restoring {name}", flush=True)
        destination = args.output / name
        package, provenance = clone_checkpoint(args.job, name, destination)
        baseline, baseline_result = apply(package)
        expected = args.job / "review/application_runs" / name / "corrected"
        assert numbers(baseline) == numbers(expected), "Restored checkpoint changed its numbering"
        sidecar, layer = write_number_layer(
            args.pdf,
            args.pdf,
            records_from_run(package.handoff_path, baseline),
            destination / "annotated_numbered.pdf",
        )
        current = {
            "restored_correction_identity": provenance["restored_identity"]["corrections_identity"],
            "baseline_matches_retained_numbers": True,
            "baseline_result": baseline_result,
            "layer": summarize_layer(layer),
        }
        report["checkpoints"][name] = current
        if name == "attempt_0012":
            correction = package.root / "corrections/mmr_measure_spans.json"
            items = json.loads(correction.read_text())["items"]
            chosen = deepcopy(next(x for x in items if x.get("op") == "set_measure_span"))
            page = chosen["page"]
            original_items = [x for x in items if x["page"] == page]
            changed_items = deepcopy(original_items)
            target = next(x for x in changed_items if x == chosen)
            target["measure_span"] += 1
            package.record_correction(page, "mmr_measure_span", changed_items)
            assert package.state.snapshot()["package"]["status"] in ("mixed", "stale")
            assert package.state.snapshot()["package"]["current_result"] is None
            assert all(
                s["application_status"] == "stale" for s in package.state.snapshot()["states"]
            )
            assert package.state.snapshot()["package"]["last_successful_result"] == baseline_result
            print("Applying one additional MMR measure (+1)", flush=True)
            edited, edited_result = apply(package)
            old_numbers, new_numbers = numbers(baseline), numbers(edited)
            assert old_numbers[0] == new_numbers[0]
            assert new_numbers[page + 1][0][0] == old_numbers[page + 1][0][0] + 1
            assert old_numbers != new_numbers
            new_sidecar, changed_layer = write_number_layer(
                destination / "annotated_numbered.pdf",
                args.pdf,
                records_from_run(package.handoff_path, edited),
                destination / "annotated_numbered_edited.pdf",
                previous_sidecar=sidecar,
            )
            package.record_correction(page, "mmr_measure_span", original_items)
            print("Undoing the MMR edit and applying again", flush=True)
            undone, _ = apply(package)
            assert numbers(undone) == old_numbers
            _, undo_layer = write_number_layer(
                destination / "annotated_numbered_edited.pdf",
                args.pdf,
                records_from_run(package.handoff_path, undone),
                destination / "annotated_numbered_undone.pdf",
                previous_sidecar=new_sidecar,
            )
            current.update(
                {
                    "edit": {
                        k: v
                        for k, v in chosen.items()
                        if k in ("page", "system", "measure", "measure_span")
                    },
                    "new_measure_span": chosen["measure_span"] + 1,
                    "following_page_first_number": [
                        old_numbers[page + 1][0][0],
                        new_numbers[page + 1][0][0],
                    ],
                    "edited_result": edited_result,
                    "edited_layer": summarize_layer(changed_layer),
                    "undo_numbers_exactly_restored": True,
                    "undo_layer": summarize_layer(undo_layer),
                }
            )
        write_json(args.output / "progress.json", report)
    assert (
        report["checkpoints"]["attempt_0001"]["restored_correction_identity"]
        != report["checkpoints"]["attempt_0012"]["restored_correction_identity"]
    )
    assert sha(args.pdf) == original_hash
    report["original_annotated_pdf_unchanged"] = True
    write_json(args.output / "summary.json", report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
