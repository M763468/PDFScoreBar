"""Publish an allowlisted metadata snapshot, never private score/correction data.

Reads retained experiment outputs; does not rerun inference or tests. Verifies
the tested code revision and emits only aggregate metrics and hashes for review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

TESTED_COMMIT = "d3b8fa95861a50887217f6a0a9494f744d1f8f58"
IMAGE = "sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a"


def read(path):
    return json.loads(path.read_text())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_code(relative, expected):
    committed = subprocess.run(
        ["git", "show", f"{TESTED_COMMIT}:{relative}"], check=True, capture_output=True
    ).stdout
    assert digest(committed) == expected
    assert digest(Path(relative).read_bytes()) == expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--unit-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = read(args.run / "summary.json")
    inventory = read(args.inventory)["pdf"]
    restart = read(args.run / "restart_check.json")
    assert inventory["sha256"] == summary["annotated_pdf_sha256"]
    code = {
        "tools/issue441/crop_label_layer.py": summary["label_code_sha256"],
        "tools/issue441/annotated_resume_experiment.py": summary["probe_sha256"],
    }
    for path, expected in code.items():
        verify_code(path, expected)
    tests = "tests/test_issue441_annotated_layer.py"
    verify_code(tests, digest(Path(tests).read_bytes()))
    code[tests] = digest(Path(tests).read_bytes())
    stages = []
    for checkpoint, names in {
        "attempt_0001": ["annotated_numbered"],
        "attempt_0012": [
            "annotated_numbered",
            "annotated_numbered_edited",
            "annotated_numbered_undone",
        ],
    }.items():
        for name in names:
            sidecar_path = args.run / checkpoint / f"{name}.layer.json"
            layer = read(sidecar_path)
            assert (
                digest((args.run / checkpoint / f"{name}.pdf").read_bytes())
                == layer["output_sha256"]
            )
            pages = []
            for index, page in enumerate(layer["pages"]):
                x0, y0, x1, y1 = inventory["pages"][index]["crop"]
                inside = all(
                    0 <= r["rect"][0] <= r["rect"][2] <= x1 - x0
                    and 0 <= r["rect"][1] <= r["rect"][3] <= y1 - y0
                    for r in page["labels"]
                )
                fonts = [r["font_size"] for r in page["labels"]]
                assert inside and min(fonts) >= 8
                pages.append(
                    {
                        "page": index + 1,
                        "label_count": len(fonts),
                        "all_inside_crop": inside,
                        "font_points_min": min(fonts),
                        "font_points_max": max(fonts),
                    }
                )
            assert layer["all_original_dark_pixels_and_annotations_unchanged"]
            assert sum(p["label_count"] for p in pages) == 160
            stages.append(
                {
                    "checkpoint": checkpoint,
                    "stage": name,
                    "output_pdf_sha256": layer["output_sha256"],
                    "sidecar_sha256": digest(sidecar_path.read_bytes()),
                    "original_dark_pixels_and_annotations_unchanged": True,
                    "previous_layer_removed_to_exact_original": layer[
                        "previous_layer_removed_to_exact_original"
                    ],
                    "pages": pages,
                }
            )
    unit_output = args.unit_log.read_text()
    assert "Ran 5 tests" in unit_output and unit_output.rstrip().endswith("OK")
    checks = summary["checkpoints"]
    assert all(c["baseline_matches_retained_numbers"] for c in checks.values())
    assert checks["attempt_0012"]["undo_numbers_exactly_restored"]
    assert all(
        r["current_matches_persisted_result"] and r["same_correction_items_after_undo"]
        for r in restart.values()
    )
    assert all(
        "CUDAExecutionProvider" in session["text_rec"]
        for session in summary["mmr_runtime_providers"]
    )
    evidence = {
        "schema": "issue441.public_review_snapshot.v1",
        "evidence_kind": "retained_experiment_snapshot_not_a_new_test_run",
        "tested_commit": TESTED_COMMIT,
        "tested_code_sha256": code,
        "runtime_image": IMAGE,
        "mmr_actual_providers": summary["mmr_runtime_providers"],
        "input_pdf_sha256": summary["annotated_pdf_sha256"],
        "original_pdf_unchanged": summary["original_annotated_pdf_unchanged"],
        "pages": inventory["page_count"],
        "annotation_counts": inventory["annotations"],
        "baseline_number_sequences_match_retained_results": {
            k: v["baseline_matches_retained_numbers"] for k, v in checks.items()
        },
        "additional_mmr_edit": {
            "span_before": checks["attempt_0012"]["edit"]["measure_span"],
            "span_after": checks["attempt_0012"]["new_measure_span"],
            "following_page_first_number": checks["attempt_0012"]["following_page_first_number"],
            "undo_number_sequences_exactly_restored": True,
        },
        "restart_checks": restart,
        "output_stages": stages,
        "focused_tests": {
            "count": 5,
            "status": "passed",
            "output_sha256": digest(unit_output.encode()),
            "command": "python -m unittest discover -s tests -p test_issue441_annotated_layer.py -v",
        },
        "not_run": [
            "product_browser_E2E",
            "MobileSheets_reexport_roundtrip",
            "physical_print",
            "all_correction_type_combinations",
            "Full68",
        ],
        "limitations": [
            "8_to_10_point_labels_need_user_readability_acceptance",
            "owned_layer_update_requires_matching_sidecar_and_unmodified_PDF_identity",
            "no_automatic_acceptance_of_unknown_PDF_rewrites",
            "product_upload_checkpoint_selection_and_annotated_review_UI_not_integrated",
        ],
        "historical_nonpassing_attempts": [
            "fixed_gutter_cropped_134_of_160_label_bboxes",
            "resume_01_stopped_after_unintended_CPU_fallback",
            "restart_01_compared_undo_identity_with_initial_instead_of_final_saved_identity",
        ],
    }
    serialized = json.dumps(evidence, indent=2) + "\n"
    assert all(
        token not in serialized for token in ("/home/", "/workspace/", "Nielsen-", "Mobile User")
    )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "annotated_resume_snapshot.json").write_text(serialized)
    (args.output / "focused-tests.txt").write_text(unit_output)
    print(
        f"Published aggregate snapshot: {len(stages)} stages, 15 pages, 160 labels each; no new inference/tests"
    )


if __name__ == "__main__":
    main()
