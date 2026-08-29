"""Run one canonical full-68 Issue #284 variant with an explicit SR compile mode.

This is a thin specialization of ``run_full68_variant.py`` for the final
``torch.compile`` A/B. It keeps the committed dense config as the provenance
anchor, overrides only ``detection.sr_compile_mode`` in each derived score config,
and shares one Inductor/Triton cache across all five score processes when compile
is enabled.

The compiler cache is isolated only through PyTorch/Triton-specific environment
variables. HOME and XDG_CACHE_HOME are deliberately preserved so the compiled and
eager variants use the same downstream runtime/cache environment.

The output layout and ``variant_summary.json`` remain compatible with
``compare_full68_variants.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

from tools.issue284 import run_full68_variant as base

COMPILE_MODES = (
    "off",
    "default",
    "reduce-overhead",
    "max-autotune-no-cudagraphs",
    "max-autotune",
)


def _cache_snapshot(root: Path | None) -> dict[str, Any] | None:
    if root is None or not root.exists():
        return None
    files = [path for path in root.rglob("*") if path.is_file()]
    return {
        "root": str(root),
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
    }


def _derive_config(
    root: Path,
    score_root: Path,
    staged: Path,
    *,
    compile_mode: str,
) -> Path:
    source = root / base.CANONICAL_CONFIG_REL
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    detection = config.get("detection", {})
    if int(detection.get("sr_scale", 0)) != 4:
        raise ValueError("Canonical dense config must use sr_scale=4")
    if detection.get("detector_route") != "dense_full_pipeline":
        raise ValueError("Canonical dense config must use detector_route=dense_full_pipeline")
    if detection.get("homr_profile") != "stage_e_verified":
        raise ValueError("Canonical dense config must use homr_profile=stage_e_verified")

    config["inputs"]["pdf_to_images"]["output_dir"] = str(staged)
    config["detection"]["hybrid_output_root"] = str(score_root / "hybrid_output")
    if compile_mode == "off":
        config["detection"].pop("sr_compile_mode", None)
    else:
        config["detection"]["sr_compile_mode"] = compile_mode

    path = score_root / "config_derived.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _worker_env(root: Path, cache_root: Path | None) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    env.pop("PDFSCORE_PERF_TRACE_DIR", None)

    # Do not inherit an unrelated compiler cache from the launch environment.
    # Keep HOME/XDG unchanged: those affect downstream libraries and would make
    # this A/B broader than the SR compile-mode change under test.
    env.pop("TORCHINDUCTOR_CACHE_DIR", None)
    env.pop("TRITON_CACHE_DIR", None)
    if cache_root is None:
        return env

    inductor = cache_root / "inductor"
    triton = cache_root / "triton"
    inductor.mkdir(parents=True, exist_ok=True)
    triton.mkdir(parents=True, exist_ok=True)
    env["TORCHINDUCTOR_CACHE_DIR"] = str(inductor)
    env["TRITON_CACHE_DIR"] = str(triton)
    return env


def _run_score(
    *,
    root: Path,
    output: Path,
    label: str,
    score: str,
    pages: list[str],
    compile_mode: str,
    cache_root: Path | None,
) -> dict[str, Any]:
    score_root = output / score
    score_root.mkdir(parents=True, exist_ok=False)
    staged = base.stage_score(root, score_root, score, pages)
    config = _derive_config(root, score_root, staged, compile_mode=compile_mode)
    run_id = f"issue284_{label}_{score}"
    pipeline_output = score_root / "pipeline_output"
    hybrid_root = score_root / "hybrid_output"
    pipeline_run = pipeline_output / run_id
    hybrid_run = hybrid_root / run_id
    log = score_root / "pipeline.stdout.log"

    command = [
        str(base.PIPELINE_PYTHON),
        "-m",
        "src.pipeline.main",
        "--config",
        str(config),
        "--run-id",
        run_id,
        "--output-root",
        str(pipeline_output),
    ]
    env = _worker_env(root, cache_root)
    cache_before = _cache_snapshot(cache_root)

    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(
            command,
            cwd=root,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
        )
        sampler = base.ResourceSampler(
            process.pid,
            score_root / "resource_samples.jsonl",
        )
        sampler.start()
        returncode = process.wait()
        resources = sampler.finish()
    wall = time.perf_counter() - started
    cache_after = _cache_snapshot(cache_root)

    summary: dict[str, Any] = {
        "schema_version": "issue284.compile_full68_variant_score.v1",
        "score": score,
        "pages": pages,
        "page_count": len(pages),
        "returncode": returncode,
        "e2e_wall_sec": wall,
        "compile_mode_override": compile_mode,
        "compile_cache_before": cache_before,
        "compile_cache_after": cache_after,
        "config": str(config),
        "command": command,
        "pipeline_run": str(pipeline_run),
        "hybrid_run": str(hybrid_run),
        "log": str(log),
        "resources": resources,
    }

    if returncode != 0:
        summary["status"] = "failed"
        summary["log_tail"] = log.read_text(encoding="utf-8", errors="replace").splitlines()[-100:]
        (score_root / "score_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return summary

    page_results = {
        page: base.page_artifacts(
            score=score,
            page=page,
            pipeline_run=pipeline_run,
            hybrid_run=hybrid_run,
        )
        for page in pages
    }
    sr_batch_path = hybrid_run / "current_support" / "_sr_batch" / "result.json"
    if not sr_batch_path.is_file():
        raise FileNotFoundError(sr_batch_path)
    sr_batch = base.load_json(sr_batch_path)
    runtime = sr_batch.get("runtime") if isinstance(sr_batch, dict) else None
    actual_mode = runtime.get("compile_mode") if isinstance(runtime, dict) else None
    expected_mode = None if compile_mode == "off" else compile_mode
    if actual_mode != expected_mode:
        raise RuntimeError(
            f"SR compile mode mismatch for {score}: expected={expected_mode!r} actual={actual_mode!r}"
        )

    summary.update(
        {
            "status": "completed",
            "effective_sr_compile_mode": actual_mode,
            "page_artifacts": page_results,
            "sr_batch_result": str(sr_batch_path),
            "sr_batch": sr_batch,
        }
    )
    (score_root / "score_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def _write_variant_summary(
    *,
    output: Path,
    label: str,
    root: Path,
    config_sha: str,
    source_commit: str,
    source_clean_verified: bool,
    compile_mode: str,
    cache_root: Path | None,
    score_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    completed = [item for item in score_summaries if item.get("status") == "completed"]
    payload = {
        "schema_version": "issue284.full68_variant.v1",
        "status": "completed" if len(completed) == 5 else "incomplete",
        "label": label,
        "project_root": str(root),
        "git_commit": source_commit,
        "git_dirty": not source_clean_verified,
        "source_provenance": {
            "verification": "host",
            "git_commit": source_commit,
            "git_clean_verified": source_clean_verified,
        },
        "config": str(root / base.CANONICAL_CONFIG_REL),
        "config_sha256": config_sha,
        "compile_ab": {
            "compile_mode_override": compile_mode,
            "effective_sr_compile_mode": None if compile_mode == "off" else compile_mode,
            "shared_compile_cache": cache_root is not None,
            "compile_cache_root": str(cache_root) if cache_root is not None else None,
            "compile_cache_final": _cache_snapshot(cache_root),
            "home_xdg_preserved": True,
        },
        "canonical_page_count": sum(int(item.get("page_count", 0)) for item in completed),
        "total_score_e2e_wall_sec": sum(float(item.get("e2e_wall_sec", 0.0)) for item in completed),
        "total_sr_batch_wall_sec": sum(
            float((item.get("sr_batch") or {}).get("batch_wall_sec", 0.0)) for item in completed
        ),
        "scores": score_summaries,
    }
    (output / "variant_summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("/workspace"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--source-commit", type=base.parse_source_commit, required=True)
    parser.add_argument("--sr-compile-mode", choices=COMPILE_MODES, required=True)
    parser.add_argument(
        "--host-clean-verified",
        action="store_true",
        help="Assert that the host verified the project checkout is clean before launch",
    )
    args = parser.parse_args()

    root = args.project_root.resolve()
    base.require_canonical_runtime(root)
    base.require_host_provenance(
        source_commit=args.source_commit,
        clean_verified=args.host_clean_verified,
    )

    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output must be fresh and empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    scores = base.load_scores(root)
    if sum(len(pages) for pages in scores.values()) != 68:
        raise RuntimeError("Canonical page selection is not 68 pages")

    compile_mode = str(args.sr_compile_mode)
    cache_root = output / "_compile_cache" if compile_mode != "off" else None
    if cache_root is not None:
        cache_root.mkdir(parents=True, exist_ok=False)

    config_sha = base.sha256(root / base.CANONICAL_CONFIG_REL)
    score_summaries: list[dict[str, Any]] = []
    for score, pages in scores.items():
        print(f"=== {score}: {len(pages)} pages; compile={compile_mode} ===", flush=True)
        summary = _run_score(
            root=root,
            output=output,
            label=args.label,
            score=score,
            pages=pages,
            compile_mode=compile_mode,
            cache_root=cache_root,
        )
        score_summaries.append(summary)
        _write_variant_summary(
            output=output,
            label=args.label,
            root=root,
            config_sha=config_sha,
            source_commit=args.source_commit,
            source_clean_verified=args.host_clean_verified,
            compile_mode=compile_mode,
            cache_root=cache_root,
            score_summaries=score_summaries,
        )
        if summary.get("status") != "completed":
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return 1

        sr_batch = summary.get("sr_batch") or {}
        outputs = sr_batch.get("outputs") or []
        page_times = [
            float(item["page_wall_sec"])
            for item in outputs
            if isinstance(item, dict) and item.get("page_wall_sec") is not None
        ]
        print(
            json.dumps(
                {
                    "score": score,
                    "status": summary["status"],
                    "e2e_wall_sec": summary["e2e_wall_sec"],
                    "sr_batch_wall_sec": sr_batch.get("batch_wall_sec"),
                    "effective_sr_compile_mode": summary.get("effective_sr_compile_mode"),
                    "first_sr_page_wall_sec": page_times[0] if page_times else None,
                    "compile_cache_before": summary.get("compile_cache_before"),
                    "compile_cache_after": summary.get("compile_cache_after"),
                    "peak_process_tree_rss_bytes": summary["resources"].get(
                        "peak_process_tree_rss_bytes"
                    ),
                    "peak_gpu_memory_mb_by_uuid": summary["resources"].get(
                        "peak_gpu_memory_mb_by_uuid"
                    ),
                },
                indent=2,
                ensure_ascii=False,
            ),
            flush=True,
        )

    payload = _write_variant_summary(
        output=output,
        label=args.label,
        root=root,
        config_sha=config_sha,
        source_commit=args.source_commit,
        source_clean_verified=args.host_clean_verified,
        compile_mode=compile_mode,
        cache_root=cache_root,
        score_summaries=score_summaries,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
