#!/usr/bin/env python3
"""Record the latest Issue #294 post-#277 runner attempt.

This temporary experiment helper discovers the newest local runner attempt from its
log/run tag even when the runner exited before its final ``=== completed ===`` block.
It records existing focused/full68 artifacts, validates their provenance and gates,
writes a compact JSON/Markdown record under the run directory (or logs/issue294 for
an incomplete run), and posts the same idempotent summary to Issue #294.

The recorder does not rerun inference and does not modify production code/config.
A failed acceptance gate is evidence: it is recorded as ``failed`` rather than being
discarded as "no completed run".
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
RUN_PREFIX = "issue294_post277_full68_"
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


def _log_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    completed = False
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if line == "=== completed ===":
            completed = True
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key in {
            "run_tag",
            "execution_head",
            "head",
            "focused",
            "manifest",
            "mmr",
            "log",
        }:
            fields[key] = value
    if completed:
        fields["runner_completed_marker"] = "true"
    return fields


def _path_from_field(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _suffix_for_run_tag(run_tag: str) -> str | None:
    if run_tag.startswith(RUN_PREFIX):
        return run_tag.removeprefix(RUN_PREFIX)
    return None


def _attempt_from_log(path: Path) -> dict[str, Any]:
    fields = _log_fields(path)
    run_tag = fields.get("run_tag")
    if not run_tag:
        name = path.name
        suffix = "_resume_local.log"
        if name.startswith(RUN_PREFIX) and name.endswith(suffix):
            run_tag = name[: -len(suffix)]
    if not run_tag:
        raise ValueError(f"Cannot determine run_tag from {path}")

    run_dir = LOG_ROOT / run_tag
    suffix = _suffix_for_run_tag(run_tag)
    focused = _path_from_field(fields.get("focused"))
    if focused is None and suffix:
        focused = LOG_ROOT / f"issue294_post277_focused_{suffix}.json"

    return {
        "run_tag": run_tag,
        "runner_log": path,
        "runner_completed_marker": fields.get("runner_completed_marker") == "true",
        "experiment_head_from_log": fields.get("head") or fields.get("execution_head"),
        "focused": focused,
        "manifest": _path_from_field(fields.get("manifest")) or run_dir / "full68_host.json",
        "mmr": _path_from_field(fields.get("mmr")) or run_dir / "post277_mapping_guarded_mmr.json",
        "wrapper": run_dir / "post277_mapping_guarded_full68_host.json",
        "run_dir": run_dir,
    }


def _latest_attempt() -> dict[str, Any]:
    logs = sorted(
        LOG_ROOT.glob(f"{RUN_PREFIX}*_resume_local.log"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    errors: list[str] = []
    for path in logs:
        try:
            return _attempt_from_log(path)
        except ValueError as error:
            errors.append(str(error))

    dirs = sorted(
        (path for path in LOG_ROOT.glob(f"{RUN_PREFIX}*") if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if dirs:
        run_dir = dirs[0]
        run_tag = run_dir.name
        suffix = _suffix_for_run_tag(run_tag)
        return {
            "run_tag": run_tag,
            "runner_log": None,
            "runner_completed_marker": False,
            "experiment_head_from_log": None,
            "focused": LOG_ROOT / f"issue294_post277_focused_{suffix}.json" if suffix else None,
            "manifest": run_dir / "full68_host.json",
            "mmr": run_dir / "post277_mapping_guarded_mmr.json",
            "wrapper": run_dir / "post277_mapping_guarded_full68_host.json",
            "run_dir": run_dir,
        }

    detail = "; ".join(errors[:3]) if errors else "no runner logs or run directories found"
    raise FileNotFoundError(f"No Issue #294 post-#277 attempt under {LOG_ROOT}: {detail}")


def _manifest_head(payload: Mapping[str, Any] | None) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    checkout = payload.get("checkout")
    if isinstance(checkout, Mapping) and isinstance(checkout.get("head"), str):
        return str(checkout["head"])
    return None


def _nested_head(payload: Mapping[str, Any] | None, key: str) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    nested = payload.get(key)
    if isinstance(nested, Mapping) and isinstance(nested.get("head"), str):
        return str(nested["head"])
    return None


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


def _failed_gates(payload: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(payload, Mapping):
        return []
    gates = payload.get("gates")
    if not isinstance(gates, Mapping):
        return []
    return sorted(str(key) for key, value in gates.items() if not bool(value))


def _variant_summary(mmr: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(mmr, Mapping):
        return {}
    variants = mmr.get("variants")
    if not isinstance(variants, Mapping):
        return {}
    result: dict[str, Any] = {}
    for name in REQUIRED_VARIANTS:
        variant = variants.get(name)
        if not isinstance(variant, Mapping):
            continue
        totals = variant.get("totals")
        gates = variant.get("gates")
        result[name] = {
            "totals": dict(totals) if isinstance(totals, Mapping) else None,
            "gates": (
                {str(key): bool(value) for key, value in gates.items()}
                if isinstance(gates, Mapping)
                else None
            ),
            "elapsed_sec": variant.get("elapsed_sec"),
            "support_stats": variant.get("support_stats"),
        }
    return result


def _artifact_entry(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
        "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
    }


def _log_tail(path: Path | None, *, lines: int = 40) -> list[str]:
    if path is None or not path.is_file():
        return []
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return content[-lines:]


def _build_record(attempt: Mapping[str, Any]) -> dict[str, Any]:
    paths = {
        "runner_log": attempt.get("runner_log"),
        "focused_mmr": attempt.get("focused"),
        "full68_manifest": attempt.get("manifest"),
        "full68_wrapper": attempt.get("wrapper"),
        "full68_mmr": attempt.get("mmr"),
    }
    payloads: dict[str, dict[str, Any] | None] = {}
    parse_errors: list[str] = []
    for name in ("focused_mmr", "full68_manifest", "full68_wrapper", "full68_mmr"):
        path = paths[name]
        if isinstance(path, Path) and path.is_file():
            try:
                payloads[name] = _load_json(path)
            except Exception as error:  # noqa: BLE001
                payloads[name] = None
                parse_errors.append(f"{name}: {type(error).__name__}: {error}")
        else:
            payloads[name] = None

    focused = payloads["focused_mmr"]
    manifest = payloads["full68_manifest"]
    wrapper = payloads["full68_wrapper"]
    mmr = payloads["full68_mmr"]

    experiment_head = attempt.get("experiment_head_from_log")
    candidate_heads = [
        experiment_head,
        _nested_head(focused, "git"),
        _manifest_head(manifest),
        _nested_head(wrapper, "checkout"),
        _nested_head(mmr, "git"),
    ]
    heads = [str(value) for value in candidate_heads if value]
    if experiment_head is None and heads:
        experiment_head = heads[0]

    current_head = _capture(["git", "rev-parse", "HEAD"])
    current_branch = _capture(["git", "branch", "--show-current"]) or "<detached>"

    checks: dict[str, bool] = {}
    failures: list[str] = list(parse_errors)
    missing = [
        name
        for name in ("focused_mmr", "full68_manifest", "full68_wrapper", "full68_mmr")
        if payloads[name] is None
    ]

    if heads:
        checks["artifact_heads_consistent"] = len(set(heads)) == 1
        if not checks["artifact_heads_consistent"]:
            failures.append(f"artifact HEAD mismatch: {sorted(set(heads))}")
    else:
        checks["artifact_heads_consistent"] = False
        failures.append("no experiment HEAD found in log/artifacts")

    checks["experiment_head_is_ancestor_of_collector"] = bool(
        experiment_head and _git_is_ancestor(str(experiment_head), current_head)
    )
    if not checks["experiment_head_is_ancestor_of_collector"]:
        failures.append(
            f"experiment HEAD {experiment_head!r} is not an ancestor of collector HEAD {current_head}"
        )

    if isinstance(focused, Mapping):
        checks["focused_status_completed"] = focused.get("status") == "completed"
        checks["focused_mode"] = focused.get("mode") == "focused"
        checks["focused_all_gates_pass"] = bool(focused.get("all_gates_pass"))
        for key in ("focused_status_completed", "focused_mode", "focused_all_gates_pass"):
            if not checks[key]:
                failures.append(key)

    if isinstance(manifest, Mapping):
        checks["full68_manifest_status_completed"] = manifest.get("status") == "completed"
        checks["full68_manifest_68_pages"] = int(manifest.get("completed_page_count", 0)) == 68
        if experiment_head:
            checks["full68_manifest_head_matches"] = _manifest_head(manifest) == experiment_head
        for key in (
            "full68_manifest_status_completed",
            "full68_manifest_68_pages",
            "full68_manifest_head_matches",
        ):
            if key in checks and not checks[key]:
                failures.append(key)

    if isinstance(wrapper, Mapping):
        checks["full68_wrapper_status_completed"] = wrapper.get("status") == "completed"
        checks["full68_wrapper_68_pages"] = int(wrapper.get("completed_page_count", 0)) == 68
        checks["full68_wrapper_run_tag_matches"] = str(wrapper.get("run_tag")) == str(
            attempt["run_tag"]
        )
        if experiment_head:
            checks["full68_wrapper_head_matches"] = (
                _nested_head(wrapper, "checkout") == experiment_head
            )
        for key in (
            "full68_wrapper_status_completed",
            "full68_wrapper_68_pages",
            "full68_wrapper_run_tag_matches",
            "full68_wrapper_head_matches",
        ):
            if key in checks and not checks[key]:
                failures.append(key)

    variants = _variant_summary(mmr)
    reference = None
    reference_mismatch: dict[str, Any] = {}
    if isinstance(mmr, Mapping):
        checks["full68_mmr_status_completed"] = mmr.get("status") == "completed"
        checks["full68_mmr_mode"] = mmr.get("mode") == "full68"
        selected_pages = mmr.get("selected_pages")
        checks["full68_mmr_68_pages"] = (
            isinstance(selected_pages, list) and len(selected_pages) == 68
        )
        checks["full68_mmr_all_gates_pass"] = bool(mmr.get("all_gates_pass"))
        mmr_manifest = mmr.get("manifest")
        if experiment_head:
            checks["full68_mmr_head_matches"] = _nested_head(mmr, "git") == experiment_head
            checks["full68_mmr_manifest_head_matches"] = bool(
                isinstance(mmr_manifest, Mapping)
                and mmr_manifest.get("checkout_head") == experiment_head
            )
        checks["full68_mmr_require_manifest_head"] = bool(
            isinstance(mmr_manifest, Mapping) and mmr_manifest.get("require_manifest_head")
        )
        reference_raw = mmr.get("production_reference_expected")
        if isinstance(reference_raw, Mapping):
            reference = dict(reference_raw)
        a_variant = variants.get("A_production")
        a_totals = a_variant.get("totals") if isinstance(a_variant, Mapping) else None
        if isinstance(reference, Mapping) and isinstance(a_totals, Mapping):
            reference_mismatch = {
                key: {"expected": reference.get(key), "actual": a_totals.get(key)}
                for key in REFERENCE_KEYS
                if int(a_totals.get(key, -1)) != int(reference.get(key, -2))
            }
            checks["production_reference_exact"] = not reference_mismatch
        else:
            checks["production_reference_exact"] = False
        for key in (
            "full68_mmr_status_completed",
            "full68_mmr_mode",
            "full68_mmr_68_pages",
            "full68_mmr_all_gates_pass",
            "full68_mmr_head_matches",
            "full68_mmr_manifest_head_matches",
            "full68_mmr_require_manifest_head",
            "production_reference_exact",
        ):
            if key in checks and not checks[key]:
                failures.append(key)

    if missing:
        status = "incomplete"
    elif failures:
        status = "failed"
    else:
        status = "passed"

    artifacts = {
        name: entry
        for name, path in paths.items()
        if (entry := _artifact_entry(path if isinstance(path, Path) else None)) is not None
    }

    return {
        "schema_version": "issue294.post277_attempt_record.v2",
        "status": status,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": REPOSITORY,
        "issue": ISSUE_NUMBER,
        "run_tag": attempt["run_tag"],
        "runner_completed_marker": bool(attempt.get("runner_completed_marker")),
        "experiment_execution_head": experiment_head,
        "collector": {
            "head": current_head,
            "branch": current_branch,
        },
        "artifacts": artifacts,
        "missing_artifacts": missing,
        "checks": checks,
        "failures": failures,
        "focused_mmr": {
            "status": focused.get("status") if isinstance(focused, Mapping) else None,
            "all_gates_pass": (
                bool(focused.get("all_gates_pass")) if isinstance(focused, Mapping) else None
            ),
            "failed_gates": _failed_gates(focused),
            "selected_page_count": (
                len(focused.get("selected_pages", [])) if isinstance(focused, Mapping) else None
            ),
        },
        "full68": {
            "manifest_status": manifest.get("status") if isinstance(manifest, Mapping) else None,
            "completed_page_count": (
                manifest.get("completed_page_count") if isinstance(manifest, Mapping) else None
            ),
            "manifest_gates_diagnostic_only": (
                manifest.get("gates") if isinstance(manifest, Mapping) else None
            ),
            "wrapper_status": wrapper.get("status") if isinstance(wrapper, Mapping) else None,
            "maintained_homr_commit": MAINTAINED_HOMR_COMMIT,
            "latest_homr_commit": (
                wrapper.get("latest_homr_commit") if isinstance(wrapper, Mapping) else None
            ),
            "mapping_guarded_grouping": (
                wrapper.get("mapping_guarded_grouping") if isinstance(wrapper, Mapping) else None
            ),
            "production_source_modified": (
                wrapper.get("production_source_modified") if isinstance(wrapper, Mapping) else None
            ),
            "production_dispatch_modified": (
                wrapper.get("production_dispatch_modified")
                if isinstance(wrapper, Mapping)
                else None
            ),
        },
        "full68_mmr": {
            "status": mmr.get("status") if isinstance(mmr, Mapping) else None,
            "all_gates_pass": bool(mmr.get("all_gates_pass")) if isinstance(mmr, Mapping) else None,
            "failed_gates": _failed_gates(mmr),
            "production_reference_expected": reference,
            "production_reference_mismatch": reference_mismatch,
            "variants": variants,
            "runtime": mmr.get("runtime") if isinstance(mmr, Mapping) else None,
            "accepted_issue264_rebase": (
                mmr.get("accepted_issue264_rebase") if isinstance(mmr, Mapping) else None
            ),
            "execution_contract": (
                mmr.get("execution_contract") if isinstance(mmr, Mapping) else None
            ),
        },
        "runner_log_tail": _log_tail(
            paths["runner_log"] if isinstance(paths["runner_log"], Path) else None
        ),
    }


def _metric_cell(totals: Mapping[str, Any] | None) -> str:
    if not isinstance(totals, Mapping):
        return "n/a"
    return "/".join(str(totals.get(key, "?")) for key in REFERENCE_KEYS)


def _issue_markdown(record: Mapping[str, Any]) -> str:
    run_tag = str(record["run_tag"])
    experiment_head = str(record.get("experiment_execution_head") or "unknown")
    marker = f"<!-- issue294-post277-run-record:{run_tag}:{experiment_head} -->"
    full68 = record["full68"]
    focused = record["focused_mmr"]
    mmr = record["full68_mmr"]
    lines = [
        marker,
        "## Post-#277 canonical full68 run record",
        "",
        f"- status: **{record['status']}**",
        f"- run tag: `{run_tag}`",
        f"- experiment HEAD: `{experiment_head}`",
        f"- collector HEAD: `{record['collector']['head']}`",
        f"- runner completed marker: `{record['runner_completed_marker']}`",
        f"- full68 manifest: `{full68['manifest_status']}` / pages `{full68['completed_page_count']}`",
        f"- focused MMR all gates pass: `{focused['all_gates_pass']}`",
        f"- full68 MMR all gates pass: `{mmr['all_gates_pass']}`",
        "",
    ]

    if mmr["variants"]:
        lines.extend(
            [
                "MMR metrics are `expected/detected/TP/FN/mismatch/FP`:",
                "",
                "| variant | metrics |",
                "| --- | --- |",
            ]
        )
        for name in REQUIRED_VARIANTS:
            variant = mmr["variants"].get(name)
            totals = variant.get("totals") if isinstance(variant, Mapping) else None
            lines.append(f"| `{name}` | `{_metric_cell(totals)}` |")
        lines.extend(
            [
                "",
                f"Production reference: `{_metric_cell(mmr['production_reference_expected'])}`",
                "",
            ]
        )

    if focused["failed_gates"]:
        lines.append(
            "Focused failed gates: " + ", ".join(f"`{item}`" for item in focused["failed_gates"])
        )
    if mmr["failed_gates"]:
        lines.append(
            "Full68 MMR failed gates: " + ", ".join(f"`{item}`" for item in mmr["failed_gates"])
        )
    if record["missing_artifacts"]:
        lines.append(
            "Missing artifacts: " + ", ".join(f"`{item}`" for item in record["missing_artifacts"])
        )
    if record["failures"]:
        lines.append("Validation failures:")
        for failure in record["failures"]:
            lines.append(f"- `{failure}`")

    lines.extend(["", "Artifact provenance (SHA-256):"])
    for name, artifact in record["artifacts"].items():
        lines.append(f"- `{name}`: `{artifact['sha256']}` — `{artifact['path']}`")

    tail = record.get("runner_log_tail") or []
    if record["status"] != "passed" and tail:
        tail_text = "\n".join(str(line) for line in tail)
        if len(tail_text) > 6000:
            tail_text = tail_text[-6000:]
        lines.extend(
            [
                "",
                "Runner log tail:",
                "",
                "```text",
                tail_text,
                "```",
            ]
        )
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
        input_text=json.dumps({"body": body}, ensure_ascii=False),
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
            raise RuntimeError(
                "GitHub CLI `gh` is required to persist the run record on Issue #294"
            )
        _capture(["gh", "auth", "status"])

        attempt = _latest_attempt()
        record = _build_record(attempt)

        run_dir = attempt["run_dir"]
        output_dir = run_dir if run_dir.is_dir() else LOG_ROOT
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "post277_attempt_record.json"
        markdown_path = output_dir / "post277_attempt_record.md"

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
                    "recorded": True,
                    "status": record["status"],
                    "run_tag": record["run_tag"],
                    "experiment_execution_head": record["experiment_execution_head"],
                    "collector_head": record["collector"]["head"],
                    "runner_completed_marker": record["runner_completed_marker"],
                    "focused_all_gates_pass": record["focused_mmr"]["all_gates_pass"],
                    "full68_all_gates_pass": record["full68_mmr"]["all_gates_pass"],
                    "failed_gates": {
                        "focused": record["focused_mmr"]["failed_gates"],
                        "full68": record["full68_mmr"]["failed_gates"],
                    },
                    "missing_artifacts": record["missing_artifacts"],
                    "record": str(output_path),
                    "issue_comment": issue_comment,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        # Recording a failed/incomplete experiment is successful recorder execution.
        return 0
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "recorded": False,
                    "status": "recorder_failed",
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
