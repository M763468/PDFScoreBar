"""Export only hashes, counts and explicitly selected gates from private #441 runs.

Run after browser and post-restart verification. Never copy private PDFs, images,
annotation text, raw corrections, paths from result records, or whole browser JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import fitz


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_root.resolve()
    repo = Path(__file__).resolve().parents[2]
    code = json.loads((run / "tested-code.json").read_text())
    for name, expected in code["files"].items():
        target = (repo / name).resolve()
        require(target.is_relative_to(repo) and sha(target) == expected, "Tested code changed")
    verification = json.loads((run / "actual-verification-final.json").read_text())
    browser = json.loads((run / "browser-03/browser-report.json").read_text())
    require(browser["passed"] is True and browser["errors"] == [], "Browser did not pass")
    gates = (
        "baseline_matches_retained",
        "edit_changes_numbers",
        "undo_restores_all_numbers",
        "server_restart_restores_exact_result",
    )
    require(all(verification[k] is True for k in gates), "Artifact/restart gate did not pass")
    outputs = {}
    for stage in ("baseline", "edited", "undone"):
        result = browser[stage]
        # Known Docker mount relocation only. No traversal from evidence paths.
        relative = Path(result["final_pdf"]).relative_to("/workspace")
        pdf = (args.workspace_root / relative).resolve()
        require(pdf.is_relative_to(run), "Result escaped the private run root")
        sidecar = pdf.with_suffix(".layer.json")
        require(sha(pdf) == result["final_pdf_sha256"], "PDF changed")
        require(sha(sidecar) == result["number_layer_sidecar_sha256"], "Sidecar changed")
        layer = json.loads(sidecar.read_text())
        require(layer["output_sha256"] == sha(pdf), "Layer and PDF disagree")
        require(
            layer["all_original_dark_pixels_and_annotations_unchanged"] is True,
            "Preservation gate failed",
        )
        labels = [label for page in layer["pages"] for label in page["labels"]]
        require(
            len(labels) == 160 and all(x["font_size"] == 9 for x in labels),
            "Uniform 9pt gate failed",
        )
        with fitz.open(pdf) as doc:
            pages = len(doc)
            notes = sum(len(list(page.annots() or [])) for page in doc)
            require(pages == 15 and notes == 729, "Page/annotation count changed")
            contained = all(
                doc[i].rect.contains(fitz.Rect(label["rect"]))
                for i, page in enumerate(layer["pages"])
                for label in page["labels"]
            )
        require(contained, "Label outside visible CropBox")
        outputs[stage] = {
            "pdf_sha256": sha(pdf),
            "sidecar_sha256": sha(sidecar),
            "pages": pages,
            "annotations": notes,
            "labels": len(labels),
            "font_points": 9,
            "all_labels_inside_cropbox": contained,
            "original_dark_pixels_and_annotations_preserved": True,
        }
    providers = json.loads((run / "actual-providers.json").read_text())
    require(
        len(providers) == 3 and all("CUDAExecutionProvider" in x["text_rec"] for x in providers),
        "Expected three real CUDA OCR applications",
    )
    snapshot = {
        "schema_version": 1,
        "tested_code": code,
        "exporter_sha256": sha(Path(__file__)),
        "verification_tool_sha256": sha(Path(__file__).with_name("verify_product_integration.py")),
        "input_pdf_sha256": "c52167c534ebde75150c7c52c11f7051e864390cfa2103640f631b0644bb89c2",
        "pipeline_image": "sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a",
        "browser_image": "sha256:8771dc4666e7c11440bfc6a0c6b00480e9a15b8891b45f29a52d7d995f8d1492",
        "chromium": browser["chromium"],
        "checks": {**{key: verification[key] for key in gates}, "browser_workflow_passed": True},
        "outputs": outputs,
        "mmr_providers": [{"text_rec": item["text_rec"]} for item in providers],
        "not_run": [
            "MobileSheets numbered-PDF re-export roundtrip",
            "All four correction types in annotated-PDF browser E2E",
            "Full68 / upstream recognition",
            "Physical printing / manual-placement UI",
        ],
        "adopted_private_logs": [
            "regression-final.log",
            "fast-final.log",
            "browser-03.log",
            "verify-public-harness.log",
        ],
    }
    args.output_root.mkdir(parents=True, exist_ok=True)
    for filename, expected in [("regression-final.log", 188), ("fast-final.log", 122)]:
        data = (run / filename).read_text()
        require(
            f"{expected} passed" in data and "FAILED" not in data and "ERROR" not in data,
            "Test log did not pass",
        )
        require(
            all(
                line.startswith((".", " ", str(expected))) or not line for line in data.splitlines()
            ),
            "Unexpected test log content; do not publish",
        )
        target = "product-regression-tests.txt" if expected == 188 else "product-fast-tests.txt"
        (args.output_root / target).write_text(data)
    (args.output_root / "product_integration_snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    )
    print("Verified and exported bounded public evidence; no private score contents copied")


if __name__ == "__main__":
    main()
