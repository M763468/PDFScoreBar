"""Rescore #441 legacy/four-type/repeated-resume evidence; publish counts only."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
from pathlib import Path
from urllib.parse import urlparse

import fitz

from src.pipeline.review.number_layer import (
    MARKER,
    _number_font_signature,
    _validate_saved_output,
    note_signature,
)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numbers(run):
    files = sorted((run / "outputs").glob("page_*/numbering_final.json"))
    require(len(files) == 15, "Expected all 15 pages")
    return [
        [
            [m.get("number") for m in s["measures"]]
            for s in json.loads(p.read_text())["pages"][0]["systems"]
        ]
        for p in files
    ]


def verify(args):
    report = json.loads((args.root / "browser-01/continuation-report.json").read_text())
    require(report["passed"] is True and not report["errors"], "Browser failed")
    require(
        report["legacyCount"] == 12 and report["rejectedReturnPreservesSuccess"],
        "Legacy listing/rejection gate failed",
    )
    stages = report["stages"]
    sequences = {name: numbers(Path(result["corrected_run"])) for name, result in stages.items()}
    for attempt in ["attempt_0001", "attempt_0012"]:
        expected = numbers(args.job / "review/application_runs" / attempt / "corrected")
        require(sequences[attempt] == expected, "Legacy numbering changed")
        consumed = json.loads(
            (args.job / "review/application_runs" / attempt / "consumed_inputs.json").read_text()
        )
        require(
            report[attempt]["initial"] is None,
            "Legacy PDF existence was treated as applied success",
        )
        require(
            report[attempt]["restoredIdentity"]["corrections_identity"]
            == consumed["corrections_identity"],
            "Legacy corrections changed",
        )
    baseline = sequences["attempt_0012"]
    for kind in ["mmr", "measure", "barline", "movement"]:
        require(sequences[kind + "_undo"] == baseline, f"{kind} undo did not recover all numbering")
    require(
        baseline[0][1][0] == 8 and sequences["mmr"][0][1][0] == 9, "MMR test change must be 8->9"
    )
    require(
        sequences["barline"][0][1][0] == 7
        and len(sequences["barline"][0][0]) == len(baseline[0][0]) - 1,
        "Internal barline effect failed",
    )
    require(sequences["movement"][0][1][0] == 1, "Movement reset failed")
    require(
        sequences["measure"] == baseline, "Existing-interval force_measure should be idempotent"
    )
    forced = json.loads(
        (
            Path(stages["measure"]["corrected_run"]) / "review/applied_measure_overrides.json"
        ).read_text()
    )["measure_overrides"]
    require(
        any(
            x.get("force_measure")
            and x.get("page") == 0
            and x.get("system") == 0
            and x.get("measure") == 0
            for x in forced
        ),
        "Force flag was not consumed",
    )
    require(sequences["second_resume"] == baseline, "Repeated resume changed numbering")
    require(
        report["secondIdentity"]["corrections_identity"]
        == report["attempt_0012"]["restoredIdentity"]["corrections_identity"],
        "Older checkpoint not selected",
    )
    outputs = {}
    for name, result in stages.items():
        pdf, sidecar = Path(result["final_pdf"]), Path(result["number_layer_sidecar"])
        require(
            sha(pdf) == result["final_pdf_sha256"]
            and sha(sidecar) == result["number_layer_sidecar_sha256"],
            "Result identity changed",
        )
        handoff = Path(result["source_handoff"])
        resume = json.loads(handoff.read_text())["resume"]
        original = handoff.parent / (resume.get("background_pdf") or resume["input_pdf"])
        layer = json.loads(sidecar.read_text())
        # This executes the final post-save bounds gate on all retained outputs.
        _validate_saved_output(pdf, original, layer)
        with fitz.open(pdf) as doc, fitz.open(handoff.parent / resume["input_pdf"]) as incoming:
            count = sum(len(list(page.annots() or [])) for page in doc)
            expected_count = 730 if name == "second_resume" else 729
            require(count == expected_count, "Annotations were lost")
            require(
                all(
                    note_signature(doc, page) == note_signature(incoming, incoming[i])
                    for i, page in enumerate(doc)
                ),
                "Annotation attributes/appearance changed",
            )
            labels = [x for page in layer["pages"] for x in page["labels"]]
            require(
                len(labels) == 160 and all(x["font_size"] == 9 for x in labels),
                "Uniform label gate failed",
            )
            markers = sum(
                doc.xref_get_key(x, "PDFScoreBarNumbers")[1] == MARKER
                for page in doc
                for x in page.get_contents()
            )
            require(markers == 160, "Repeated numbering left duplicate active streams")
        outputs[name] = {
            "pdf_sha256": sha(pdf),
            "labels": 160,
            "annotations": count,
            "font_points": 9,
            "all_labels_inside_cropbox": True,
            "notes_and_nonowned_dark_pixels_preserved": True,
        }
    second = Path(stages["second_resume"]["source_handoff"])
    resume = json.loads(second.read_text())["resume"]
    require(
        resume["roundtrip"]["removed_number_count"] == 160, "Second-round ownership not verified"
    )
    parent_results = [
        r["final_pdf_sha256"]
        for name, r in stages.items()
        if name not in ["attempt_0001", "second_resume"]
    ]
    require(
        resume["roundtrip"]["trusted_pdf_sha256"] in parent_results,
        "Parent session result was not used",
    )
    result = {
        "schema_version": 1,
        "legacy_attempts_1_and_12_verified": True,
        "listed_legacy_attempts": 12,
        "four_gui_types_saved_applied_undone": True,
        "mmr_row2": [8, 9, 8],
        "barline_row2": [8, 7, 8],
        "movement_row2": [8, 1, 8],
        "force_measure_consumed_idempotently": True,
        "all_undo_number_sequences_restored": True,
        "second_resume_older_checkpoint": True,
        "synthetic_second_round": True,
        "notes_accumulated": [729, 730],
        "rejected_return_preserves_success": True,
        "outputs": outputs,
    }
    check_restart(args, report, result)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print("All legacy, four-type, repeated-resume and retained-output gates passed")


def check_restart(args, report, result):
    stages = report["stages"]
    if args.url:
        url = urlparse(args.url)
        require(url.scheme == "http" and url.hostname == "127.0.0.1", "Use local review server")
        conn = http.client.HTTPConnection(url.hostname, url.port, timeout=30)
        session = urlparse(report["secondUrl"]).query
        try:
            conn.request("GET", "/api/state?" + session)
            response = conn.getresponse()
            state = json.loads(response.read())
            require(
                response.status == 200
                and state["package"]["current_result"]["final_pdf_sha256"]
                == stages["second_resume"]["final_pdf_sha256"],
                "Restart state changed",
            )
            conn.request("GET", "/api/result?" + session)
            response = conn.getresponse()
            data = response.read()
            require(
                response.status == 200
                and hashlib.sha256(data).hexdigest() == stages["second_resume"]["final_pdf_sha256"],
                "Restart result changed",
            )
        finally:
            conn.close()
        result["restart_restores_exact_second_result"] = True


def restart_only(args):
    require(args.url, "Restart-only check needs a local URL")
    report = json.loads((args.root / "browser-01/continuation-report.json").read_text())
    result = json.loads(args.output.read_text())
    require(
        result.get("four_gui_types_saved_applied_undone") is True
        and len(result.get("outputs", {})) == 11,
        "Run full artifact verification first",
    )
    for name, stage in report["stages"].items():
        require(
            sha(Path(stage["final_pdf"])) == result["outputs"][name]["pdf_sha256"],
            "Verified output changed",
        )
        with fitz.open(stage["final_pdf"]) as doc:
            for page in doc:
                _number_font_signature(doc, page)
    result["final_font_metrics_verified"] = True
    check_restart(args, report, result)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print("Restart restored the exact second-round session/PDF; verified artifacts unchanged")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url")
    parser.add_argument("--restart-only", action="store_true")
    args = parser.parse_args()
    (restart_only if args.restart_only else verify)(args)


if __name__ == "__main__":
    main()
