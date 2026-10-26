"""Re-layout retained numbering without rerunning OCR; keep private previews local."""

from __future__ import annotations

import argparse
import html
import json
import statistics
from collections import Counter
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

from tools.issue441.crop_label_layer import (
    FONT_POINTS,
    digit_ink_bounds,
    distance_to_staff_start,
    records_from_run,
    write_number_layer,
)
from tools.issue441.phase0_probe import sha


def read(path):
    return json.loads(path.read_text())


def stats(values):
    return {
        "min": min(values),
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "max": max(values),
    }


def compare_placement(previous, updated):
    font = fitz.Font("hebo")
    before, after = [], []
    pages = []
    for index, (old_page, new_page) in enumerate(
        zip(previous["pages"], updated["pages"], strict=True)
    ):
        for old, new in zip(old_page["labels"], new_page["labels"], strict=True):
            if old["number"] != new["number"] or old["row_id"] != new["row_id"]:
                raise ValueError("Numbering changed during typography-only update")
            baseline = old["rect"][1] + font.ascender * old["font_size"]
            origin = old["rect"][0]
            old_ink = digit_ink_bounds(str(old["number"]), old["font_size"]) + (
                origin,
                baseline,
                origin,
                baseline,
            )
            anchor = fitz.Rect(
                *new["staff_start"], new["staff_start"][0] + 1, new["staff_start"][1] + 1
            )
            before.append(distance_to_staff_start(old_ink, anchor))
            after.append(new["distance_to_staff_start_points"])
        sizes = [x["font_size"] for x in new_page["labels"]]
        if set(sizes) != {FONT_POINTS}:
            raise ValueError("Labels do not share one document-wide font size")
        pages.append({"page": index + 1, "labels": len(sizes), "font_points": FONT_POINTS})
    if len(before) != 160:
        raise ValueError("Expected all 160 row labels, without exclusions")
    return {
        "labels": len(before),
        "pages": pages,
        "font_points_before": stats(
            [x["font_size"] for p in previous["pages"] for x in p["labels"]]
        ),
        "font_points_after": FONT_POINTS,
        "distance_before_points": stats(before),
        "distance_after_points": stats(after),
        "closer": sum(b < a - 1e-6 for a, b in zip(before, after, strict=True)),
        "farther": sum(b > a + 1e-6 for a, b in zip(before, after, strict=True)),
        "same_distance": sum(abs(b - a) <= 1e-6 for a, b in zip(before, after, strict=True)),
    }


def previews(root, pdfs):
    assets = root / "preview"
    assets.mkdir()
    count = None
    for name, path in pdfs.items():
        with fitz.open(path) as doc:
            count = len(doc)
            for index, page in enumerate(doc):
                page.get_pixmap().save(assets / f"{name}_{index + 1:02d}.png")
    labels = {
        "original": "書き込み済み原本",
        "previous": "旧配置 8〜10pt",
        "revised": "統一9pt・近接配置",
        "edited": "MMR追加修正",
        "undone": "修正取消後",
    }
    body = [
        "<!doctype html><meta charset='utf-8'><title>Issue441 非公開の配置比較</title>",
        "<style>body{font:16px sans-serif;margin:20px;background:#eee}nav{position:sticky;top:0;background:white;padding:10px}.row{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}.row img{width:100%;background:white}figure{margin:0}h2{scroll-margin-top:55px}figcaption{text-align:center;padding:8px}</style>",
        "<h1>Issue #441 番号配置の比較（非公開）</h1><p>原本・旧配置・統一9pt・追加修正・取消後を比較します。画像を開くと拡大できます。</p>",
        "<nav>" + " | ".join(f"<a href='#p{i}'>p{i}</a>" for i in range(1, count + 1)) + "</nav>",
    ]
    for index in range(1, count + 1):
        body.append(f"<h2 id='p{index}'>Page {index}</h2><div class='row'>")
        for name in pdfs:
            filename = f"{name}_{index:02d}.png"
            body.append(
                f"<figure><figcaption>{html.escape(labels[name])}</figcaption><a href='{filename}'><img loading='lazy' src='{filename}'></a></figure>"
            )
        body.append("</div>")
    (assets / "index.html").write_text("\n".join(body))
    contact = Image.new("RGB", (600, 5 * 295), "#ddd")
    draw = ImageDraw.Draw(contact)
    for index in range(count):
        x, y = (index % 3) * 200, (index // 3) * 295
        with Image.open(assets / f"revised_{index + 1:02d}.png") as image:
            image.thumbnail((194, 265))
            contact.paste(image, (x + 3, y + 24))
        draw.text((x + 6, y + 6), f"Page {index + 1}: 9pt", fill="black")
    contact.save(assets / "all_15_pages.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retained-run", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_report = read(args.retained_run / "summary.json")
    if sha(args.pdf) != source_report["annotated_pdf_sha256"]:
        raise ValueError("Annotated source identity mismatch")
    args.output.mkdir(parents=True, exist_ok=False)
    originals = {str(args.pdf): sha(args.pdf)}
    stages = []
    files = {}
    for checkpoint, variants in {
        "attempt_0001": [("baseline", "annotated_numbered", 1)],
        "attempt_0012": [
            ("baseline", "annotated_numbered", 1),
            ("edited", "annotated_numbered_edited", 2),
            ("undone", "annotated_numbered_undone", 3),
        ],
    }.items():
        retained = args.retained_run / checkpoint
        destination = args.output / checkpoint
        destination.mkdir()
        prior_pdf, prior_sidecar = None, None
        for stage, filename, attempt in variants:
            old_pdf, old_sidecar = retained / f"{filename}.pdf", retained / f"{filename}.layer.json"
            originals.update({str(p): sha(p) for p in (old_pdf, old_sidecar)})
            numbering = records_from_run(
                retained / "review/manual_correction_input.json",
                retained / f"review/application_runs/attempt_{attempt:04d}/corrected",
            )
            output = destination / f"{filename}_uniform9.pdf"
            sidecar, report = write_number_layer(
                prior_pdf or old_pdf,
                args.pdf,
                numbering,
                output,
                previous_sidecar=prior_sidecar or old_sidecar,
            )
            comparison = compare_placement(read(old_sidecar), report)
            comparison.update(
                {
                    "checkpoint": checkpoint,
                    "stage": stage,
                    "output_sha256": report["output_sha256"],
                    "annotation_dark_pixels_and_background_preserved": report[
                        "all_original_dark_pixels_and_annotations_unchanged"
                    ],
                    "publication": report["publication"],
                }
            )
            stages.append(comparison)
            files[(checkpoint, stage)] = output
            prior_pdf, prior_sidecar = output, sidecar
            print(json.dumps(comparison), flush=True)
    previews(
        args.output,
        {
            "original": args.pdf,
            "previous": args.retained_run / "attempt_0012/annotated_numbered.pdf",
            "revised": files[("attempt_0012", "baseline")],
            "edited": files[("attempt_0012", "edited")],
            "undone": files[("attempt_0012", "undone")],
        },
    )
    if originals != {p: sha(Path(p)) for p in originals}:
        raise ValueError("An original input or previous result changed")
    with fitz.open(args.pdf) as doc:
        counts = Counter(a.type[1] for page in doc for a in page.annots() or [])
    result = {
        "schema": "issue441.typography_revision.v1",
        "retained_numbering_reused_no_OCR_rerun": True,
        "font_points": FONT_POINTS,
        "original_inputs_unchanged": True,
        "input_pdf_sha256": sha(args.pdf),
        "annotation_counts": dict(counts),
        "stages": stages,
        "tested_code_sha256": {
            name: sha(Path(__file__).with_name(name))
            for name in ("crop_label_layer.py", "refine_annotated_layout.py")
        },
    }
    (args.output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Completed 4 layouts and private 15-page comparison preview", flush=True)


if __name__ == "__main__":
    main()
