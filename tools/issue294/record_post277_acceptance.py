#!/usr/bin/env python3
"""Record the latest completed Issue #294 post-#277 acceptance run.

This temporary experiment helper locates the newest completed local runner log,
validates the focused/full68 artifacts and provenance, writes a compact machine-
readable acceptance record under that run directory, and posts an idempotent summary
to GitHub Issue #294. It does not rerun inference or modify production code/config.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_ROOT = PROJECT_ROOT / "logs/issue294"
REPOSITORY = "M763468/PDFScoreBar"
ISSUE_NUMBER = 294
MAINTAINED_HOMR_COMMIT = "b377620a3a55bd7ff657481cec5b688dfbc9cee9"
REQUIRED_VARIANTS = (
    "A_production",
    "B_b377_mapping_guarded",
    "C_latest_mapping_guarded",
)
REFERENCE_KEYS = (
    "expected",
    "detected",
    "matched_tp",
    "missed_fn",
    "skip_mismatch",
    "unexpected_fp",
)


def _capture(command: list[str], *, input_text: str | None = None) -> str:
    return subprocess.check_output(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        input=input_text,
        stderr=subprocess.PIPE,
    ).strip()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_recorded_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_completed_log(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    marker_indexes = [index for index, line in enumerate(lines) if line.strip() == "=== completed ==="]
    if not marker_indexes:
        raise ValueError(f"Runner log has no completed marker: {path}")
    fields: dict[str, str] = {}
    for line in lines[marker_indexes[-1] + 1 :]:
        if not line.strip():
            if fields:
                break
            continue
        if "=" not in line:
            if fields:
                break
            continue
        key, value = line.split("=", 1)
        fields[key.strip()] = value.strip()
    required = {"head", "run_tag", "focused", "manifest", "mmr", "log"}
    missing = sorted(required - fields.keys())
    if missing:
        raise ValueError(f"Runner completion block missing fields {missing}: {path}")
    return fields


def _latest_completed_run() -> tuple[Path, dict[str, str]]:
    candidates = sorted(
        LOG_ROOT.glob("issue294_post277_full68_*_resume_local.log"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    failures: list[str] = []
    for path in candidates:
        try:
            return path, _parse_completed_log(path)
        except ValueError as error:
            failures.append(str(error))
    detail = "; ".join(failures[:3]) if failures else "no runner logs found"
    raise FileNotFoundError(f"No completed Issue #294 post-#277 runner log under {LOG_ROOT}: {detail}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _git_is_ancestor(ancestor: str, descendant: str) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _manifest_head(manifest: Mapping[str, Any]) -> str | None:
    checkout = manifest.get("checkout")
    if isinstance(checkout, Mapping) and isinstance(checkout.get("head"), str):
        return str(checkout["head"])
    return None


def _variant_summary(mmr: Mapping[str, Any]) -> dict[str, Any]:
    variants = mmr.get("variants")
    _require(isinstance(variants, Mapping), "MMR report lacks variants")
    summary: dict[str, Any] = {}
    for name in REQUIRED_VARIANTS:
        variant = variants.get(name)
        _require(isinstance(variant, Mapping), f"MMR report lacks variant {name}")
        totals = variant.get("totals")
        gates = variant.get("gates")
        _require(isinstance(totals, Mapping), f"MMR variant {name} lacks totals")
        _require(isinstance(gates, Mapping), f"MMR variant {name} lacks gates")
        summary[name] = {
            "totals": {key: totals.get(key) for key in totals},
            "gates": {key: bool(value) for key, value in gates.items()},
            "elapsed_sec": variant.get("elapsed_sec"),
            "support_stats": variant.get("support_stats"),
        }
    return summary


def _validate_and_build_record(
    *,
    runner_log: Path,
    completion: Mapping[str, str],
    focused_path: Path,
    manifest_path: Path,
    mmr_path: Path,
    wrapper_path: Path,
) -> dict[str, Any]:
    focused = _load_json(focused_path)
    manifest = _load_json(manifest_path)
    mmr = _load_json(mmr_path)
    wrapper = _load_json(wrapper_path)

    experiment_head = str(completion["head"])
    current_head = _capture(["git", "rev-parse", "HEAD"])
    current_branch = _capture(["git", "branch", "--show-current"]) or "<detached>"
    _require(
        _git_is_ancestor(experiment_head, current_head),
        f"Experiment HEAD {experiment_head} is not an ancestor of current HEAD {current_head}",
    )

    run_tag = str(completion["run_tag"])
    _require(manifest.get("status") == "completed", "Full68 manifest status is not completed")
    _require(int(manifest.get("completed_page_count", 0)) == 68, "Full68 manifest is not 68/68")
    _require(_manifest_head(manifest) == experiment_head, "Full68 manifest HEAD mismatch")

    _require(wrapper.get("status") == "completed", "Post-#277 full68 wrapper is not completed")
    _require(str(wrapper.get("run_tag")) == run_tag, "Full68 wrapper run_tag mismatch")
    _require(int(wrapper.get("completed_page_count", 0)) == 68, "Full68 wrapper is not 68/68")
    wrapper_checkout = wrapper.get("checkout")
    _require(isinstance(wrapper_checkout, Mapping), "Full68 wrapper lacks checkout provenance")
    _require(wrapper_checkout.get("head") == experiment_head, "Full68 wrapper HEAD mismatch")

    _require(focused.get("status") == "completed", "Focused MMR status is not completed")
    _require(focused.get("mode") == "focused", "Focused MMR report has wrong mode")
    _require(bool(focused.get("all_gates_pass")), "Focused MMR acceptance gates did not all pass")
    focused_git = focused.get("git")
    _require(isinstance(focused_git, Mapping), "Focused MMR report lacks git provenance")
    _require(focused_git.get("head") == experiment_head, "Focused MMR HEAD mismatch")

    _require(mmr.get("status") == "completed", "Full68 MMR status is not completed")
    _require(mmr.get("mode") == "full68", "Full68 MMR report has wrong mode")
    _require(bool(mmr.get("all_gates_pass")), "Full68 MMR acceptance gates did not all pass")
    selected_pages = mmr.get("selected_pages")
    _require(isinstance(selected_pages, list) and len(selected_pages) == 68, "MMR report is not full68")
    mmr_git = mmr.get("git")
    _require(isinstance(mmr_git, Mapping), "Full68 MMR report lacks git provenance")
    _require(mmr_git.get("head") == experiment_head, "Full68 MMR HEAD mismatch")
    mmr_manifest = mmr.get("manifest")
    _require(isinstance(mmr_manifest, Mapping), "Full68 MMR report lacks manifest provenance")
    _require(mmr_manifest.get("checkout_head") == experiment_head, "Full68 MMR manifest HEAD mismatch")
    _require(bool(mmr_manifest.get("require_manifest_head")), "Full68 MMR did not require manifest HEAD")

    overall_gates = mmr.get("gates")
    _require(isinstance(overall_gates, Mapping), "Full68 MMR report lacks gates")
    failed_overall = sorted(key for key, value in overall_gates.items() if not bool(value))
    _require(not failed_overall, f"Full68 MMR failed gates: {failed_overall}")

    variants = _variant_summary(mmr)
    reference = mmr.get("production_reference_expected")
    _require(isinstance(reference, Mapping), "Full68 MMR lacks production reference")
    a_totals = variants["A_production"]["totals"]
    reference_mismatch = {
        key: {"expected": reference.get(key), "actual": a_totals.get(key)}
        for key in REFERENCE_KEYS
        if int(a_totals.get(key, -1)) != int(reference.get(key, -2))
    }
    _require(not reference_mismatch, f"Production reference mismatch: {reference_mismatch}")

    source_files = {
        "runner_log": runner_log,
        "focused_mmr": focused_path,
        "full68_manifest": manifest_path,
        "full68_wrapper": wrapper_path,
        "full68_mmr": mmr_path,
    }
    artifacts = {
        name: {
            "path": str(path.resolve()),
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for name, path in source_files.items()
    }

    return {
        "schema_version": "issue294.post277_acceptance_record.v1",
        "status": "passed",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": REPOSITORY,
        "issue": ISSUE_NUMBER,
        "run_tag": run_tag,
        "experiment_execution_head": experiment_head,
        "collector": {
            "head": current_head,
            "branch": current_branch,
            "experiment_head_is_ancestor": True,
        },
        "artifacts": artifacts,
        "full68": {
            "completed_page_count": 68,
            "manifest_status": manifest.get("status"),
            "wrapper_status": wrapper.get("status"),
            "maintained_homr_commit": MAINTAINED_HOMR_COMMIT,
            "latest_homr_commit": wrapper.get("latest_homr_commit"),
            "manifest_gates_diagnostic_only": manifest.get("gates"),
            "mapping_guarded_grouping": wrapper.get("mapping_guarded_grouping"),
            "production_source_modified": wrapper.get("production_source_modified"),
            "production_dispatch_modified": wrapper.get("production_dispatch_modified"),
            "historical_A_comparison_gates_diagnostic_only": wrapper.get(
                "historical_A_comparison_gates_diagnostic_only"
            ),
        },
        "focused_mmr": {
            "all_gates_pass": True,
            "selected_page_count": len(focused.get("selected_pages", [])),
            "gates": focused.get("gates"),
        },
        "full68_mmr": {
            "all_gates_pass": True,
            "selected_page_count": len(selected_pages),
            "production_reference_expected": dict(reference),
            "variants": variants,
            "gates": {key: bool(value) for key, value in overall_gates.items()},
            "runtime": mmr.get("runtime"),
            "accepted_issue264_rebase": mmr.get("accepted_issue264_rebase"),
            "execution_contract": mmr.get("execution_contract"),
        },
    }


def _metric_cell(totals: Mapping[str, Any]) -> str:
    return "/".join(str(totals.get(key, "?")) for key in REFERENCE_KEYS)


def _issue_markdown(record: Mapping[str, Any]) -> str:
    full68_mmr = record["full68_mmr"]
    variants = full68_mmr["variants"]
    run_tag = record["run_tag"]
    experiment_head = record["experiment_execution_head"]
    marker = f"<!-- issue294-post277-acceptance:{run_tag}:{experiment_head} -->"
    lines = [
        marker,
        "## Post-#277 canonical full68 acceptance record",
        "",
        f"- status: **{record['status']}**",
        f"- run tag: `{run_tag}`",
        f"- experiment HEAD: `{experiment_head}`",
        f"- collector HEAD: `{record['collector']['head']}`",
        f"- maintained HOMR candidate (B): `{record['full68']['maintained_homr_commit']}`",
        f"- latest HOMR comparison candidate (C): `{record['full68']['latest_homr_commit']}`",
        "- full68: 68/68 completed",
        f"- focused MMR gates: `{record['focused_mmr']['all_gates_pass']}`",
        f"- full68 MMR gates: `{full68_mmr['all_gates_pass']}`",
        "- production source/dispatch modified by experiment: "
        f"`{record['full68']['production_source_modified']}` / "
        f"`{record['full68']['production_dispatch_modified']}`",
        "",
        "MMR metrics are `expected/detected/TP/FN/mismatch/FP`:",
        "",
        "| variant | metrics |",
        "| --- | --- |",
    ]
    for name in REQUIRED_VARIANTS:
        lines.append(f"| `{name}` | `{_metric_cell(variants[name]['totals'])}` |")
    lines.extend(
        [
            "",
            "Production reference:",
            f"`{_metric_cell(full68_mmr['production_reference_expected'])}`",
            "",
            "All full68 semantic gates, per-page candidate-not-worse gates, zero-fixture controls, "
            "row-start controls, page033 one-bar veto, page042 controls, and B/C exactness gates passed.",
            "",
            "Artifact provenance (SHA-256):",
        ]
    )
    for name, artifact in record["artifacts"].items():
        lines.append(f"- `{name}`: `{artifact['sha256']}` — `{artifact['path']}`")
    return "\n".join(lines) + "\n"


def _existing_comment(marker: str) -> dict[str, Any] | None:
    page = 1
    while True:
        raw = _capture(
            [
                "gh",
                "api",
                f"repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/comments?per_page=100&page={page}",
            ]
        )
        comments = json.loads(raw)
        if not isinstance(comments, list):
            raise RuntimeError("Unexpected GitHub comments response")
        for comment in comments:
            if isinstance(comment, Mapping) and marker in str(comment.get("body", "")):
                return dict(comment)
        if len(comments) < 100:
            return None
        page += 1


def _post_issue_comment(body: str, marker: str) -> dict[str, Any]:
    existing = _existing_comment(marker)
    if existing is not None:
        return {
            "status": "existing",
            "id": existing.get("id"),
            "html_url": existing.get("html_url"),
        }
    payload = json.dumps({"body": body}, ensure_ascii=False)
    raw = _capture(
        [
            "gh",
            "api",
            "--method",
            "POST",
            "-H",
            "Content-Type: application/json",
            "--input",
            "-",
            f"repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/comments",
        ],
        input_text=payload,
    )
    response = json.loads(raw)
    if not isinstance(response, Mapping):
        raise RuntimeError("Unexpected GitHub comment creation response")
    return {
        "status": "posted",
        "id": response.get("id"),
        "html_url": response.get("html_url"),
    }


def main() -> int:
    try:
        if shutil.which("gh") is None:
            raise RuntimeError("GitHub CLI `gh` is required to persist the acceptance record on Issue #294")
        _capture(["gh", "auth", "status"])

        runner_log, completion = _latest_completed_run()
        focused_path = _resolve_recorded_path(completion["focused"])
        manifest_path = _resolve_recorded_path(completion["manifest"])
        mmr_path = _resolve_recorded_path(completion["mmr"])
        run_dir = manifest_path.parent
        wrapper_path = run_dir / "post277_mapping_guarded_full68_host.json"

        for label, path in (
            ("focused", focused_path),
            ("manifest", manifest_path),
            ("mmr", mmr_path),
            ("wrapper", wrapper_path),
        ):
            if not path.is_file():
                raise FileNotFoundError(f"{label} artifact missing: {path}")

        record = _validate_and_build_record(
            runner_log=runner_log,
            completion=completion,
            focused_path=focused_path,
            manifest_path=manifest_path,
            mmr_path=mmr_path,
            wrapper_path=wrapper_path,
        )
        output_path = run_dir / "post277_acceptance_record.json"
        markdown_path = run_dir / "post277_acceptance_record.md"
        markdown = _issue_markdown(record)
        marker = markdown.splitlines()[0]

        markdown_path.write_text(markdown, encoding="utf-8")
        issue_comment = _post_issue_comment(markdown, marker)
        record["issue_comment"] = issue_comment
        output_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        print(
            json.dumps(
                {
                    "status": record["status"],
                    "run_tag": record["run_tag"],
                    "experiment_execution_head": record["experiment_execution_head"],
                    "collector_head": record["collector"]["head"],
                    "focused_all_gates_pass": record["focused_mmr"]["all_gates_pass"],
                    "full68_all_gates_pass": record["full68_mmr"]["all_gates_pass"],
                    "record": str(output_path),
                    "issue_comment": issue_comment,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
