"""Run one fresh canonical full-68 production variant for Issue #284.

The runner is intentionally production-neutral. It stages the committed canonical
68-page selection score-by-score, derives only input/output paths from
``configs/dense_full_pipeline.yaml``, and invokes ``src.pipeline.main`` without
changing detector, SR, grouping, MMR, or numbering settings.

It can be copied outside the worktree and run against another checkout by passing
``--project-root /workspace``. This allows the post-#285 develop control and the
#284 candidate to use the exact same validation helper.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import yaml

PIPELINE_PYTHON = Path("/opt/venv_pipeline/bin/python")
CANONICAL_CONFIG_REL = Path("configs/dense_full_pipeline.yaml")
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_source_commit(value: str) -> str:
    commit = value.strip().lower()
    if not COMMIT_SHA_RE.fullmatch(commit):
        raise argparse.ArgumentTypeError(
            "--source-commit must be a full 40-character hexadecimal commit SHA"
        )
    return commit


def require_host_provenance(*, source_commit: str, clean_verified: bool) -> None:
    if not COMMIT_SHA_RE.fullmatch(source_commit):
        raise RuntimeError("Invalid host-verified source commit")
    if not clean_verified:
        raise RuntimeError("Full68 variant requires a host-verified clean checkout")


def require_canonical_runtime(root: Path) -> None:
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Issue #284 full68 runner must execute inside Docker")
    if root.resolve() != Path("/workspace").resolve():
        raise RuntimeError(f"Expected project root /workspace, got {root}")
    if not PIPELINE_PYTHON.is_file():
        raise FileNotFoundError(PIPELINE_PYTHON)
    if not Path(sys.executable).as_posix().startswith("/opt/venv_pipeline/"):
        raise RuntimeError(f"Runner must use /opt/venv_pipeline/bin/python, got {sys.executable}")


class ResourceSampler:
    """Best-effort process-tree RSS plus nvidia-smi GPU sampling."""

    def __init__(self, pid: int, output: Path, interval: float = 1.0) -> None:
        self.pid = pid
        self.output = output
        self.interval = interval
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.sample_count = 0
        self.peak_process_tree_rss_bytes = 0
        self.peak_children_rss_bytes = 0
        self.peak_gpu_memory_mb_by_uuid: dict[str, int] = {}
        self.peak_gpu_utilization_pct_by_uuid: dict[str, int] = {}

    @staticmethod
    def _gpu() -> list[dict[str, Any]]:
        try:
            output = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=uuid,index,name,memory.used,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return []

        rows: list[dict[str, Any]] = []
        for line in output.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != 5:
                continue
            uuid, index, name, memory_used, utilization = parts
            try:
                rows.append(
                    {
                        "uuid": uuid,
                        "index": int(index),
                        "name": name,
                        "memory_used_mb": int(memory_used),
                        "utilization_gpu_pct": int(utilization),
                    }
                )
            except ValueError:
                continue
        return rows

    def _process(self) -> dict[str, Any]:
        try:
            import psutil  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001
            return {"psutil_available": False}

        try:
            root = psutil.Process(self.pid)
            children = root.children(recursive=True)
        except psutil.Error:
            return {"psutil_available": True, "root_alive": False}

        total_rss = 0
        children_rss = 0
        pids: list[int] = []
        for index, process in enumerate([root, *children]):
            try:
                value = int(process.memory_info().rss)
            except psutil.Error:
                continue
            total_rss += value
            if index:
                children_rss += value
            pids.append(int(process.pid))

        self.peak_process_tree_rss_bytes = max(
            self.peak_process_tree_rss_bytes,
            total_rss,
        )
        self.peak_children_rss_bytes = max(
            self.peak_children_rss_bytes,
            children_rss,
        )
        return {
            "psutil_available": True,
            "root_alive": True,
            "process_tree_rss_bytes": total_rss,
            "children_rss_bytes": children_rss,
            "process_count": len(pids),
            "process_ids": pids,
        }

    def _run(self) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        with self.output.open("w", encoding="utf-8") as stream:
            while not self.stop.is_set():
                gpu = self._gpu()
                for row in gpu:
                    uuid = str(row["uuid"])
                    self.peak_gpu_memory_mb_by_uuid[uuid] = max(
                        self.peak_gpu_memory_mb_by_uuid.get(uuid, 0),
                        int(row["memory_used_mb"]),
                    )
                    self.peak_gpu_utilization_pct_by_uuid[uuid] = max(
                        self.peak_gpu_utilization_pct_by_uuid.get(uuid, 0),
                        int(row["utilization_gpu_pct"]),
                    )
                stream.write(
                    json.dumps(
                        {
                            "timestamp_monotonic_sec": time.perf_counter(),
                            "process": self._process(),
                            "gpu": gpu,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                stream.flush()
                self.sample_count += 1
                self.stop.wait(self.interval)

    def start(self) -> None:
        self.thread.start()

    def finish(self) -> dict[str, Any]:
        self.stop.set()
        self.thread.join(timeout=max(2.0, self.interval * 2))
        return {
            "sample_count": self.sample_count,
            "sample_interval_sec": self.interval,
            "samples_path": str(self.output),
            "peak_process_tree_rss_bytes": self.peak_process_tree_rss_bytes,
            "peak_children_rss_bytes": self.peak_children_rss_bytes,
            "peak_gpu_memory_mb_by_uuid": self.peak_gpu_memory_mb_by_uuid,
            "peak_gpu_utilization_pct_by_uuid": (self.peak_gpu_utilization_pct_by_uuid),
        }


def load_scores(root: Path) -> dict[str, list[str]]:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from tools.issue120.eval_full68_from_intermediates import SCORES

    return {score: list(pages) for score, pages in SCORES.items()}


def stage_score(root: Path, score_root: Path, score: str, pages: list[str]) -> Path:
    staged = score_root / "input_staging" / score
    staged.mkdir(parents=True, exist_ok=False)
    for page in pages:
        source = root / "data/evaluation2/images" / score / f"{page}.png"
        if not source.is_file():
            raise FileNotFoundError(source)
        (staged / source.name).symlink_to(source)
    return staged


def derive_config(root: Path, score_root: Path, staged: Path) -> Path:
    source = root / CANONICAL_CONFIG_REL
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
    path = score_root / "config_derived.yaml"
    path.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )
    return path


def page_artifacts(
    *,
    score: str,
    page: str,
    pipeline_run: Path,
    hybrid_run: Path,
) -> dict[str, Any]:
    paths = {
        "hybrid": hybrid_run / "hybrid_results" / f"{page}_hybrid.json",
        "numbering_base": pipeline_run / "intermediate" / page / "numbering_base.json",
        "overrides_mmr": pipeline_run / "intermediate" / page / "overrides_mmr.json",
        "numbering_final": pipeline_run / "outputs" / page / "numbering_final.json",
        "current_support": hybrid_run / "current_support" / score / page / "result.json",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing full68 page artifacts: " + ", ".join(missing))

    support = load_json(paths["current_support"])
    return {key: str(value) for key, value in paths.items()} | {
        "sr_sha256": support.get("sr_sha256"),
        "sr_execution_scope": support.get("sr_execution_scope"),
        "connector_complete": support.get("connector_complete"),
        "historical_detector_artifact_runtime_input": support.get(
            "historical_detector_artifact_runtime_input"
        ),
    }


def run_score(
    *,
    root: Path,
    output: Path,
    label: str,
    score: str,
    pages: list[str],
) -> dict[str, Any]:
    score_root = output / score
    score_root.mkdir(parents=True, exist_ok=False)
    staged = stage_score(root, score_root, score, pages)
    config = derive_config(root, score_root, staged)
    run_id = f"issue284_{label}_{score}"
    pipeline_output = score_root / "pipeline_output"
    hybrid_root = score_root / "hybrid_output"
    pipeline_run = pipeline_output / run_id
    hybrid_run = hybrid_root / run_id
    log = score_root / "pipeline.stdout.log"

    command = [
        str(PIPELINE_PYTHON),
        "-m",
        "src.pipeline.main",
        "--config",
        str(config),
        "--run-id",
        run_id,
        "--output-root",
        str(pipeline_output),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    env.pop("PDFSCORE_PERF_TRACE_DIR", None)

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
        sampler = ResourceSampler(
            process.pid,
            score_root / "resource_samples.jsonl",
        )
        sampler.start()
        returncode = process.wait()
        resources = sampler.finish()
    wall = time.perf_counter() - started

    summary: dict[str, Any] = {
        "schema_version": "issue284.full68_variant_score.v1",
        "score": score,
        "pages": pages,
        "page_count": len(pages),
        "returncode": returncode,
        "e2e_wall_sec": wall,
        "config": str(config),
        "command": command,
        "pipeline_run": str(pipeline_run),
        "hybrid_run": str(hybrid_run),
        "log": str(log),
        "resources": resources,
    }

    if returncode != 0:
        summary["status"] = "failed"
        summary["log_tail"] = log.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()[-100:]
        (score_root / "score_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return summary

    page_results = {
        page: page_artifacts(
            score=score,
            page=page,
            pipeline_run=pipeline_run,
            hybrid_run=hybrid_run,
        )
        for page in pages
    }

    sr_batch_path = hybrid_run / "current_support" / "_sr_batch" / "result.json"
    sr_batch = load_json(sr_batch_path) if sr_batch_path.is_file() else None
    summary.update(
        {
            "status": "completed",
            "page_artifacts": page_results,
            "sr_batch_result": str(sr_batch_path) if sr_batch is not None else None,
            "sr_batch": sr_batch,
        }
    )
    (score_root / "score_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def write_variant_summary(
    *,
    output: Path,
    label: str,
    root: Path,
    config_sha: str,
    source_commit: str,
    source_clean_verified: bool,
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
        "config": str(root / CANONICAL_CONFIG_REL),
        "config_sha256": config_sha,
        "canonical_page_count": sum(int(item.get("page_count", 0)) for item in completed),
        "total_score_e2e_wall_sec": sum(float(item.get("e2e_wall_sec", 0.0)) for item in completed),
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
    parser.add_argument("--source-commit", type=parse_source_commit, required=True)
    parser.add_argument(
        "--host-clean-verified",
        action="store_true",
        help="Assert that the host verified the project checkout is clean before launch",
    )
    args = parser.parse_args()

    root = args.project_root.resolve()
    require_canonical_runtime(root)
    require_host_provenance(
        source_commit=args.source_commit,
        clean_verified=args.host_clean_verified,
    )

    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output must be fresh and empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    scores = load_scores(root)
    if sum(len(pages) for pages in scores.values()) != 68:
        raise RuntimeError("Canonical page selection is not 68 pages")

    config_sha = sha256(root / CANONICAL_CONFIG_REL)
    score_summaries: list[dict[str, Any]] = []
    for score, pages in scores.items():
        print(f"=== {score}: {len(pages)} pages ===", flush=True)
        summary = run_score(
            root=root,
            output=output,
            label=args.label,
            score=score,
            pages=pages,
        )
        score_summaries.append(summary)
        write_variant_summary(
            output=output,
            label=args.label,
            root=root,
            config_sha=config_sha,
            source_commit=args.source_commit,
            source_clean_verified=args.host_clean_verified,
            score_summaries=score_summaries,
        )
        if summary.get("status") != "completed":
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return 1
        print(
            json.dumps(
                {
                    "score": score,
                    "status": summary["status"],
                    "e2e_wall_sec": summary["e2e_wall_sec"],
                    "peak_process_tree_rss_bytes": summary["resources"].get(
                        "peak_process_tree_rss_bytes"
                    ),
                    "peak_gpu_memory_mb_by_uuid": summary["resources"].get(
                        "peak_gpu_memory_mb_by_uuid"
                    ),
                    "sr_batch_wall_sec": (summary.get("sr_batch") or {}).get("batch_wall_sec"),
                },
                indent=2,
                ensure_ascii=False,
            ),
            flush=True,
        )

    payload = write_variant_summary(
        output=output,
        label=args.label,
        root=root,
        config_sha=config_sha,
        source_commit=args.source_commit,
        source_clean_verified=args.host_clean_verified,
        score_summaries=score_summaries,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
