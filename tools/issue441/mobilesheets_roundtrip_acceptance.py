"""Fixed #441 annotation-only MobileSheets roundtrip experiment, private inputs.

Prepare an isolated checkpoint and copy an already-attested numbered result;
serve the real review application; export only bounded counts/hashes after E2E.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

INPUT_SHA = "77018813d3c7e9d16aa51eef234c92af7069bb797fdeb0e043324a3791f83574"
PIPELINE_IMAGE = "sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a"
BROWSER_IMAGE = "sha256:8771dc4666e7c11440bfc6a0c6b00480e9a15b8891b45f29a52d7d995f8d1492"
CODE_FILES = [
    "src/pipeline/review/number_layer.py",
    "tools/review_correction/resume.py",
    "tools/review_correction/application.py",
    "tools/review_correction/server.py",
    "tools/review_correction/state.py",
    "tools/review_correction/strings.js",
    "tests/test_issue441_mobilesheets_roundtrip.py",
    "tools/issue441/mobilesheets_roundtrip_acceptance.py",
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def prepare(args):
    from tools.issue441.annotated_resume_experiment import clone_checkpoint

    require(sha(args.pdf) == INPUT_SHA, "Fixed roundtrip input changed")
    source_report = json.loads(args.seed_report.read_text())
    result = source_report["baseline"]
    pdf, sidecar = Path(result["final_pdf"]), Path(result["number_layer_sidecar"])
    require(
        sha(pdf) == result["final_pdf_sha256"]
        and sha(sidecar) == result["number_layer_sidecar_sha256"],
        "Original attested artifacts changed",
    )
    review = Path(result["source_handoff"]).parent
    journal = json.loads((review / "history/applications/attempt_0001.json").read_text())
    require(
        journal["status"] == "succeeded" and journal["result"] == result,
        "No original success attestation",
    )
    package, _ = clone_checkpoint(args.job, "attempt_0012", args.root / "actual")
    target = package.root / "application_runs/attempt_0001/corrected/final/baseline.pdf"
    target.parent.mkdir(parents=True)
    shutil.copyfile(pdf, target)
    shutil.copyfile(sidecar, target.with_suffix(".layer.json"))
    imported = dict(
        result, final_pdf=str(target), number_layer_sidecar=str(target.with_suffix(".layer.json"))
    )
    journal.update(result=imported, imported_from_result_identity=result["result_identity"])
    with package.history.transaction():
        package.history.application_record("attempt_0001", journal)
        checkpoint = package.history.capture(label="retained attempt_0012")
    repo = Path(__file__).resolve().parents[2]
    write(
        args.root / "plan.json",
        {
            "input_sha256": INPUT_SHA,
            "pages": 15,
            "labels": 160,
            "annotations": 820,
            "font_points": 9,
            "source_base_commit": os.environ["PDFSCOREBAR_SOURCE_COMMIT"],
            "pipeline_image": PIPELINE_IMAGE,
            "browser_image": BROWSER_IMAGE,
            "code_sha256": {name: sha(repo / name) for name in CODE_FILES},
            "seed_pdf_sha256": sha(pdf),
            "seed_sidecar_sha256": sha(sidecar),
            "checkpoint_id": checkpoint,
        },
    )
    print(
        "Prepared independent checkpoint with an imported, verified success attestation", flush=True
    )


def serve(args):
    from src.measure_numbering import rapidocr_provider
    from tools.review_correction.server import create_server

    factory = rapidocr_provider.create_mmr_rapidocr
    providers = []

    def checked(mode):
        engine = factory(mode)
        actual = rapidocr_provider.collect_rapidocr_providers(engine)
        require(
            actual and all("CUDAExecutionProvider" in p for p in actual.values()),
            "MMR CPU fallback",
        )
        providers.append(actual)
        write(args.root / "providers.json", providers)
        print("Actual MMR providers", actual, flush=True)
        return engine

    rapidocr_provider.create_mmr_rapidocr = checked
    server = create_server(args.root / "actual/review/manual_correction_input.json", port=args.port)
    print("Serving real review application", args.port, flush=True)
    server.serve_forever()


def export(args):
    import fitz

    from src.pipeline.review.number_layer import MARKER, note_signature

    plan = json.loads((args.root / "plan.json").read_text())
    repo = Path(__file__).resolve().parents[2]
    require(
        all(sha(repo / name) == expected for name, expected in plan["code_sha256"].items()),
        "Tested code changed",
    )
    browser = json.loads((args.root / "browser-02/browser-report.json").read_text())
    require(browser["passed"] and not browser["errors"], "Browser failed")
    require(browser["applicationStatuses"] == ["succeeded"] * 3, "Attempt history failed")
    verification = json.loads((args.root / "verification-final.json").read_text())
    expected_gates = {
        "baseline_matches_retained",
        "edit_changes_numbers",
        "undo_restores_all_numbers",
        "server_restart_restores_exact_result",
        "all_three_attempts_retained_after_restart",
    }
    require(
        set(verification) == expected_gates and all(v is True for v in verification.values()),
        "Semantic numbering or restart gate failed",
    )
    handoff = json.loads(Path(browser["baseline"]["source_handoff"]).read_text())
    resume = handoff["resume"]
    require(
        resume["input_sha256"] == INPUT_SHA and resume["roundtrip"]["removed_number_count"] == 160,
        "Roundtrip ownership provenance missing",
    )
    require(
        sha(Path(browser["baseline"]["source_handoff"]).parent / resume["input_pdf"]) == INPUT_SHA,
        "Upload changed",
    )
    outputs = {}
    for name in ("baseline", "edited", "undone"):
        result = browser[name]
        pdf, sidecar = Path(result["final_pdf"]), Path(result["number_layer_sidecar"])
        require(
            sha(pdf) == result["final_pdf_sha256"]
            and sha(sidecar) == result["number_layer_sidecar_sha256"],
            "Artifacts changed",
        )
        layer = json.loads(sidecar.read_text())
        labels = [label for page in layer["pages"] for label in page["labels"]]
        require(
            len(labels) == 160 and all(x["font_size"] == 9 for x in labels),
            "Uniform label gate failed",
        )
        require(layer["all_original_dark_pixels_and_annotations_unchanged"], "Preservation failed")
        incoming = Path(browser["baseline"]["source_handoff"]).parent / resume["input_pdf"]
        with fitz.open(pdf) as doc, fitz.open(incoming) as uploaded:
            require(
                all(
                    note_signature(doc, page) == note_signature(uploaded, uploaded[i])
                    for i, page in enumerate(doc)
                ),
                "Input annotation attributes or appearance changed",
            )
            notes = sum(len(list(page.annots() or [])) for page in doc)
            markers = sum(
                doc.xref_get_key(x, "PDFScoreBarNumbers")[1] == MARKER
                for page in doc
                for x in page.get_contents()
            )
            require(
                len(doc) == 15 and notes == 820 and markers == 160,
                "Double numbering / note count gate failed",
            )
            require(
                all(
                    doc[i].rect.contains(fitz.Rect(label["rect"]))
                    for i, page in enumerate(layer["pages"])
                    for label in page["labels"]
                ),
                "CropBox gate failed",
            )
        outputs[name] = {
            "pdf_sha256": sha(pdf),
            "sidecar_sha256": sha(sidecar),
            "labels": 160,
            "font_points": 9,
            "annotations": 820,
            "active_number_streams": markers,
            "cropbox_preserved": True,
            "all_nonowned_dark_pixels_and_annotations_preserved": True,
        }
    providers = json.loads((args.root / "providers.json").read_text())
    require(
        len(providers) == 3
        and all("CUDAExecutionProvider" in item["text_rec"] for item in providers),
        "Runtime identity failed",
    )
    args.output.mkdir(parents=True, exist_ok=True)
    for source, target, count in [
        ("regression-final-03.log", "roundtrip-regression-tests.txt", 198),
        ("fast-final-02.log", "roundtrip-fast-tests.txt", 122),
    ]:
        data = (args.root / source).read_text()
        require(
            f"{count} passed" in data and "ERROR" not in data and "FAILED" not in data,
            "Tests did not pass",
        )
        require(
            all(not line or line.startswith((".", " ", str(count))) for line in data.splitlines()),
            "Unexpected private log content",
        )
        (args.output / target).write_text(data)
    write(
        args.output / "mobilesheets_roundtrip_snapshot.json",
        {
            "schema_version": 1,
            "plan": plan,
            "checks": verification,
            "ownership_verified": True,
            "removed_old_numbers": 160,
            "input_annotations": 820,
            "previous_annotations": 729,
            "added_annotations": 91,
            "outputs": outputs,
            "mmr_providers": providers,
            "browser_chromium": browser["chromium"],
            "not_run": [
                "Other MobileSheets export settings/versions",
                "Flattened/re-encoded or native-content edits",
                "Full four-correction-type browser combination",
                "Manual placement UI",
                "Physical print",
                "Full68 / upstream inference",
            ],
        },
    )
    print("Roundtrip gates passed; exported hashes/counts only")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "serve", "export"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--job", type=Path)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--seed-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--port", type=int, default=8441)
    args = parser.parse_args()
    args.root = args.root.resolve()
    args.root.mkdir(parents=True, exist_ok=True)
    {"prepare": prepare, "serve": serve, "export": export}[args.mode](args)


if __name__ == "__main__":
    main()
