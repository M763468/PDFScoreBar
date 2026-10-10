#!/usr/bin/env python3
"""Rescore retained numbering against reviewed physical MMR events; no inference."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def read(path: Path):
    return json.loads(path.read_text())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def integer(value, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def index_overrides(items: list[dict], targets: set[tuple[int, int]]) -> dict:
    result = {}
    for item in items:
        key = (integer(item["system"], "system"), integer(item["measure"], "measure"))
        if key not in targets or key in result:
            raise ValueError(f"Missing or duplicate override target: {key}")
        result[key] = integer(item["skip"], "skip")
    return result


def audit_pages(entries: list[dict]) -> dict:
    """Entries supply base, final, recognized, GT, and explicit incoming resets.

    Numbers are audited locally using the page's own terminal next_number. An
    incoming reset hides the preceding measure's skip from number differences;
    report that limitation rather than claiming its skip was observed.
    """
    records, application, gt_errors, continuity, reset_masked = [], [], [], [], []
    counts = dict(
        expected=0, detected=0, matched_tp=0, missed_fn=0, skip_mismatch=0, unexpected_fp=0
    )
    expected_start = 1
    for entry in entries:
        page = entry["page"]
        if len(entry["final"]["pages"]) != 1 or len(entry["base"]["pages"]) != 1:
            raise ValueError(f"Expected one physical page payload: {page}")
        systems = entry["final"]["pages"][0]["systems"]
        original = entry["base"]["pages"][0]["systems"]

        def geometry(rows):
            return [[m["bbox"] for m in s["measures"]] for s in rows]

        if geometry(systems) != geometry(original):
            raise ValueError(f"Changed physical geometry: {page}")
        items = [
            ((s, m), v) for s, row in enumerate(systems) for m, v in enumerate(row["measures"])
        ]
        targets = {key for key, _ in items}
        recognized = index_overrides(entry["recognized"], targets)
        gt = index_overrides(entry["gt"], targets)
        resets = {}
        for reset in entry.get("resets", []):
            key = (
                integer(reset["system"], "reset system"),
                integer(reset.get("measure", 0), "reset measure"),
            )
            if key not in targets or key in resets:
                raise ValueError(f"Missing or duplicate reset target: {key}")
            resets[key] = integer(reset["number"], "reset number", 1)
        terminal = integer(entry["final"]["numbering_metadata"]["next_number"], "next_number", 1)
        metadata_start = entry["final"]["numbering_metadata"].get("start_number", expected_start)
        if metadata_start != expected_start:
            continuity.append(
                dict(
                    page=page, kind="metadata_start", expected=expected_start, actual=metadata_start
                )
            )
        if items:
            first_key, first = items[0]
            start = resets.get(first_key, expected_start)
            if first["number"] != start:
                continuity.append(dict(page=page, expected=start, actual=first["number"]))
        elif terminal != expected_start:
            continuity.append(dict(page=page, expected=expected_start, actual=terminal))
        for i, (key, measure) in enumerate(items):
            current = integer(measure["number"], "measure number", 1)
            if key in resets and current != resets[key]:
                continuity.append(
                    dict(
                        page=page,
                        system=key[0],
                        measure=key[1],
                        expected=resets[key],
                        actual=current,
                    )
                )
            next_key, successor = items[i + 1] if i + 1 < len(items) else (None, None)
            # A reset on the next PAGE does not hide this page's stored terminal.
            applied = (
                None
                if next_key in resets
                else (successor["number"] if successor else terminal) - current - 1
            )
            rec = dict(
                page=page,
                system=key[0],
                measure=key[1],
                bbox=measure["bbox"],
                number=current,
                recognized_skip=recognized.get(key, 0),
                gt_skip=gt.get(key, 0),
                applied_skip=applied,
            )
            records.append(rec)
            if applied is None:
                reset_masked.append(rec)
            else:
                if applied != rec["recognized_skip"]:
                    application.append(rec)
                if applied != rec["gt_skip"]:
                    gt_errors.append(rec)
            if key in gt:
                counts["expected"] += 1
                if key not in recognized:
                    counts["missed_fn"] += 1
                elif gt[key] == recognized[key]:
                    counts["matched_tp"] += 1
                else:
                    counts["skip_mismatch"] += 1
            if key in recognized:
                counts["detected"] += 1
                if key not in gt:
                    counts["unexpected_fp"] += 1
        expected_start = terminal
    return dict(
        physical_measures=len(records),
        pages=len(entries),
        recognition=counts,
        application_errors=application,
        gt_increment_errors=gt_errors,
        continuity_errors=continuity,
        reset_masked=reset_masked,
        records=records,
        absolute_numbering_certified=False,
    )


def resolve(base: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Expected relative path: {relative}")
    return base / path


def materialized_path(path: Path, repo: Path) -> Path:
    """Translate retained Docker /workspace symlinks for host-side read-only use."""
    target = path.resolve()
    if target.is_relative_to("/workspace"):
        return repo / target.relative_to("/workspace")
    return target


def audit_row_samples(repo: Path, final_root: Path, sample_path: Path) -> dict:
    samples = read(sample_path)
    if samples["schema_version"] != "issue415.row_start_samples.v1":
        raise ValueError("Unsupported row-start samples")
    records = []
    seen = set()
    for sample in samples["samples"]:
        key = (sample["score"], sample["page"], sample["system"])
        if key in seen:
            raise ValueError(f"Duplicate row sample: {key}")
        seen.add(key)
        image = resolve(repo, sample["source_image"])
        if digest(image) != sample["source_sha256"]:
            raise ValueError(f"Row sample source SHA-256 mismatch: {image}")
        final = read(
            final_root / sample["score"] / "outputs" / sample["page"] / "numbering_final.json"
        )
        first = final["pages"][0]["systems"][sample["system"]]["measures"][0]
        if first["bbox"] != sample["first_measure_bbox"]:
            raise ValueError(f"Row sample physical identity changed: {key}")
        expected = integer(sample["expected_row_start"], "expected row start", 1)
        records.append(
            dict(**sample, actual_row_start=first["number"], matches=first["number"] == expected)
        )
    return dict(
        manifest_sha256=digest(sample_path),
        reviewed=len(records),
        mismatches=[r for r in records if not r["matches"]],
        records=records,
        absolute_numbering_certified=False,
    )


def verify_consumers(repo: Path, final_root: Path, scores: list[dict], *, pixels: bool) -> dict:
    """Verify retained per-page/combined/PDF consumers without regenerating them."""

    def translate(value):
        if isinstance(value, dict):
            return {k: translate(v) for k, v in value.items()}
        if isinstance(value, list):
            return [translate(v) for v in value]
        if isinstance(value, str) and value.startswith("/workspace/"):
            return str(repo / Path(value).relative_to("/workspace"))
        return value

    results = []
    for score in scores:
        name = score["score"]
        base = final_root / name
        finals = [read(base / "outputs" / p / "numbering_final.json") for p in score["pages"]]
        combined = read(base / "outputs/numbering_final.json")
        if combined["pages"] != [f["pages"][0] for f in finals]:
            raise ValueError(f"Per-page/combined mismatch: {name}")
        if (
            combined["numbering_metadata"]["next_number"]
            != finals[-1]["numbering_metadata"]["next_number"]
        ):
            raise ValueError(f"Combined next_number mismatch: {name}")
        summary = translate(read(base / "review/corrected_final_summary.json"))
        if [p["page_id"] for p in summary["pages"]] != score["pages"]:
            raise ValueError(f"PDF page identity mismatch: {name}")
        rows = 0
        for f, p in zip(finals, summary["pages"]):
            expected_numbering = base / "outputs" / p["page_id"] / "numbering_final.json"
            if Path(p["corrected_numbering_final"]).absolute() != expected_numbering.absolute():
                raise ValueError(f"PDF consumer points to another numbering artifact: {name}")
            expected = [
                s["measures"][0]["number"] for s in f["pages"][0]["systems"] if s["measures"]
            ]
            if expected != [r["row_start_measure_number"] for r in p["row_labels"]]:
                raise ValueError(f"PDF row label mismatch: {name}/{p['page_id']}")
            rows += len(expected)
        verified = []
        if pixels:
            from tools.issue413.replay_phase_c import verify_pdf_images

            verified = verify_pdf_images(summary)
        results.append(
            dict(
                score=name,
                pages=len(finals),
                row_labels=rows,
                pdf_sha256=digest(Path(summary["final_pdf"])),
                pixel_verification=verified,
            )
        )
    return dict(scores=results, pdf_pixels_verified=pixels)


def audit_retained(repo: Path, retained: Path, final_root: Path, manifest_path: Path) -> dict:
    repo, retained, final_root = repo.absolute(), retained.absolute(), final_root.absolute()
    manifest = read(manifest_path)
    if manifest["schema_version"] != "issue415.reviewed_gt.v1":
        raise ValueError("Unsupported reviewed GT manifest")
    # This fixed inventory predates this audit; never refresh expected hashes.
    canonical = read(repo / "tools/issue413/canonical_inputs.json")
    inputs = {}
    for section, base in [("repo_files", repo), ("retained_files", retained)]:
        for relative, expected in canonical[section].items():
            path = resolve(base, relative)
            if digest(materialized_path(path, repo)) != expected:
                raise ValueError(f"Canonical input SHA-256 mismatch: {path}")
            inputs[str(path)] = expected
    for relative, expected in manifest["reviewed_source_sha256"].items():
        path = resolve(repo, relative)
        if digest(path) != expected:
            raise ValueError(f"Reviewed GT source SHA-256 mismatch: {path}")
        inputs[str(path)] = expected
    summary = read(retained / "candidate/variant_summary.json")
    by_key = {(p["score"], p["page"]): p for p in manifest["pages"]}
    keys = [(s["score"], p) for s in summary["scores"] for p in s["pages"]]
    if len(by_key) != len(manifest["pages"]) or set(keys) != set(by_key) or len(keys) != 68:
        raise ValueError("Full68 page scope changed")
    results = []
    consumed_final = {}
    for score in summary["scores"]:
        entries = []
        baseline_entries = []
        for page_index, page in enumerate(score["pages"]):
            review = by_key[(score["score"], page)]
            mapped = {}
            for mapping in review["historical_mappings"]:
                key = tuple(mapping["current_key"])
                value = (mapping["skip"], mapping["current_bbox"])
                if key in mapped and mapped[key] != value:
                    raise ValueError(f"Conflicting coalesced fixture event: {key}")
                mapped[key] = value
            events = {(e["system"], e["measure"]): (e["skip"], e["bbox"]) for e in review["events"]}
            if events != mapped or len(events) != len(review["events"]):
                raise ValueError(f"Reviewed events disagree with historical mappings: {page}")

            # Fixed #409 paths are /workspace-relative, but root can be relocated.
            def source(raw):
                path = Path(raw)
                if not path.is_relative_to("/workspace"):
                    raise ValueError(f"Unknown retained path convention: {raw}")
                rel = path.relative_to("/workspace/logs/issue409/full68-numbering-20261009")
                local = resolve(retained, str(rel))
                if str(local) not in inputs:
                    raise ValueError(f"Input absent from fixed manifest: {local}")
                return read(materialized_path(local, repo))

            artifacts = score["page_artifacts"][page]
            base = source(artifacts["numbering_base"])
            recognized = source(artifacts["overrides_mmr"])["measure_overrides"]
            if any(item["page"] != page_index for item in recognized):
                raise ValueError(f"Recognition page index mismatch: {score['score']}/{page}")
            final_path = final_root / score["score"] / "outputs" / page / "numbering_final.json"
            final = read(final_path)
            consumed_final[str(final_path)] = digest(final_path)
            for event in review["events"]:
                bbox = base["pages"][0]["systems"][event["system"]]["measures"][event["measure"]][
                    "bbox"
                ]
                if bbox != event["bbox"]:
                    raise ValueError(f"Reviewed GT event moved: {score['score']}/{page}")
            entries.append(
                dict(page=page, base=base, final=final, recognized=recognized, gt=review["events"])
            )
            baseline_entries.append(dict(entries[-1], final=source(artifacts["numbering_final"])))
        result = audit_pages(entries)
        result["score"] = score["score"]
        result["baseline"] = audit_pages(baseline_entries)
        results.append(result)
    # A report cannot turn previously known residuals into a successful GT gate.
    recognition = {
        key: sum(s["recognition"][key] for s in results) for key in results[0]["recognition"]
    }
    aggregate = dict(
        pages=sum(s["pages"] for s in results),
        physical_measures=sum(s["physical_measures"] for s in results),
        recognition=recognition,
        application_errors=sum(len(s["application_errors"]) for s in results),
        gt_increment_errors=sum(len(s["gt_increment_errors"]) for s in results),
        continuity_errors=sum(len(s["continuity_errors"]) for s in results),
        reset_masked=sum(len(s["reset_masked"]) for s in results),
    )
    return dict(
        contract=manifest["contract"],
        manifest_sha256=digest(manifest_path),
        verified_input_sha256=inputs,
        consumed_final_sha256=consumed_final,
        aggregate=aggregate,
        scores=results,
        original_baseline=dict(
            application_errors=sum(len(s["baseline"]["application_errors"]) for s in results),
            gt_increment_errors=sum(len(s["baseline"]["gt_increment_errors"]) for s in results),
        ),
        absolute_numbering_certified=False,
    )


def correctness_failed(report: dict) -> bool:
    aggregate = report["aggregate"]
    return (
        bool(report["row_samples"]["mismatches"])
        or any(
            aggregate[k]
            for k in [
                "application_errors",
                "gt_increment_errors",
                "continuity_errors",
                "reset_masked",
            ]
        )
        or any(aggregate["recognition"][k] for k in ["missed_fn", "skip_mismatch", "unexpected_fp"])
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--retained-root", type=Path, required=True)
    parser.add_argument("--final-root", type=Path, required=True)
    parser.add_argument(
        "--manifest", type=Path, default=Path(__file__).with_name("reviewed_gt.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--row-samples", type=Path, default=Path(__file__).with_name("row_start_samples.json")
    )
    parser.add_argument(
        "--verify-pdf", action="store_true", help="Compare actual embedded PDF pixels; CPU-only"
    )
    args = parser.parse_args()
    report = audit_retained(args.repo_root, args.retained_root, args.final_root, args.manifest)
    report["row_samples"] = audit_row_samples(args.repo_root, args.final_root, args.row_samples)
    scores = read(args.retained_root / "candidate/variant_summary.json")["scores"]
    report["consumers"] = verify_consumers(
        args.repo_root, args.final_root, scores, pixels=args.verify_pdf
    )
    for raw, expected in report["verified_input_sha256"].items():
        if digest(materialized_path(Path(raw), args.repo_root)) != expected:
            raise ValueError(f"Input changed during audit: {raw}")
    for raw, expected in report["consumed_final_sha256"].items():
        if digest(Path(raw)) != expected:
            raise ValueError(f"Final numbering changed during audit: {raw}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["aggregate"], indent=2))
    # Nonzero means an unmet correctness gate, not a failed ability to rescore.
    return int(correctness_failed(report))


if __name__ == "__main__":
    raise SystemExit(main())
