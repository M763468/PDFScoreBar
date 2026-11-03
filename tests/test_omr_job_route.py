"""Route selection and production wiring of the per-job OMR route (Issue #459)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from src.pipeline.detection import current_support_worker, omr_job
from src.pipeline.detection import profile_sources_batch_sr as batch_sr
from src.pipeline.detection.maintained_profile_hybrid import BatchSRVerifiedProfileHybridDetector

AUTO = {"mode": "auto", "min_pages": 2, "allowed_uids": [0], "timeout_sec": 900}


@pytest.mark.parametrize(
    ("policy", "pages", "uid", "mode", "dry_run", "route", "reason"),
    [
        (AUTO, 3, 0, "production", False, "job_reuse", "measured envelope"),
        (AUTO, 2, 0, "production", False, "job_reuse", "measured envelope"),
        (AUTO, 1, 0, "production", False, "per_page", "fewer pages than min_pages"),
        (AUTO, 3, 1000, "production", False, "per_page", "process uid outside allowed_uids"),
        (AUTO, 3, 0, "exploration", False, "per_page", "non-production model selection"),
        (AUTO, 3, 0, "production", True, "per_page", "dry run"),
        ({**AUTO, "mode": "off"}, 3, 0, "production", False, "per_page", "disabled"),
        (None, 3, 0, "production", False, "per_page", "disabled"),
    ],
)
def test_route_is_selected_from_explicit_envelope(policy, pages, uid, mode, dry_run, route, reason):
    decision = omr_job.select_route(
        policy, page_count=pages, uid=uid, model_validation=mode, dry_run=dry_run
    )
    assert (decision["route"], decision["reason"]) == (route, reason)


@pytest.mark.parametrize(
    "policy",
    [
        {"mode": "on"},
        {"min_pages": 1},
        {"allowed_uids": []},
        {"allowed_uids": ["0"]},
        {"timeout_sec": 0},
        {"fallback": "per_page"},
    ],
)
def test_invalid_policy_is_rejected(policy):
    with pytest.raises(ValueError):
        omr_job.select_route(
            {**AUTO, **policy}, page_count=3, uid=0, model_validation="production", dry_run=False
        )


def _pages(tmp_path, count):
    score = tmp_path / "Score"
    score.mkdir()
    images = []
    for index in range(count):
        image = score / f"page_{index + 1:03d}.png"
        image.write_bytes(f"source{index}".encode())
        images.append(image)
    return images


def _sr(images, support_output):
    """Write this job's SR request plus fresh outputs inside the support directory."""
    items, by_image = [], {}
    for image in images:
        output = support_output / image.parent.name / image.stem / "artifacts/sr/batch" / image.name
        output.parent.mkdir(parents=True)
        output.write_bytes(b"sr-" + image.read_bytes())
        items.append({"image": str(image.resolve()), "output": str(output.resolve())})
        by_image[image.resolve()] = {
            "image": str(image.resolve()),
            "sr_image": str(output.resolve()),
            "sr_sha256": omr_job.digest(output),
            "historical_detector_artifact_runtime_input": False,
        }
    batch = support_output / "_sr_batch"
    batch.mkdir(parents=True)
    (batch / "request.json").write_text(json.dumps({"items": items}))
    return by_image


def test_bind_sr_rejects_changed_source_and_foreign_sr(tmp_path):
    images = _pages(tmp_path, 2)
    support = tmp_path / "support"
    binding = omr_job.bind_sources(images)
    by_image = _sr(images, support)
    expected = {
        Path(i["image"]): Path(i["output"])
        for i in json.loads((support / "_sr_batch/request.json").read_text())["items"]
    }
    rows = omr_job.bind_sr(binding, by_image, support_output=support, expected_outputs=expected)
    assert [r["job_run_id"] for r in rows] == [binding["run_id"]] * 2

    foreign = tmp_path / "foreign.png"
    foreign.write_bytes(b"other job")
    moved = {
        **by_image,
        images[1].resolve(): {**by_image[images[1].resolve()], "sr_image": str(foreign)},
    }
    with pytest.raises(ValueError, match="fresh output"):
        omr_job.bind_sr(binding, moved, support_output=support, expected_outputs=expected)

    images[0].write_bytes(b"changed during SR")
    with pytest.raises(ValueError, match="source changed"):
        omr_job.bind_sr(binding, by_image, support_output=support, expected_outputs=expected)


def _detector(tmp_path, images, *, policy=AUTO):
    det_cfg = {
        "enable_sr": True,
        "sr_scale": 4,
        "homr_profile": "maintained_original",
        "detector_route": "dense_full_pipeline",
        "source_concurrency": {"workers": 1, "timeout_sec": 900, "on_unavailable": "error"},
    }
    if policy is not None:
        det_cfg["omr_job_reuse"] = policy
    return BatchSRVerifiedProfileHybridDetector(
        det_cfg=det_cfg,
        images=images,
        run_id="test",
        project_root=tmp_path,
        dry_run=False,
        skip_existing=False,
        profile_name="maintained_original",
    )


def _drive(tmp_path, monkeypatch, count, *, uid=0, policy=AUTO, build_error=None):
    images = _pages(tmp_path, count)
    detector = _detector(tmp_path, images, policy=policy)
    support_output = tmp_path / "hybrid/support"
    baseline_output = tmp_path / "hybrid/baseline"
    events = []

    def fake_sr(self, *, support_output):
        events.append("sr")
        by_image = _sr(images, support_output)
        return by_image, ["sr"], {"status": "completed", "outputs": list(by_image.values())}

    def fake_phase(self, binding, by_image, *, support_output):
        events.append("omr_job")
        if build_error is not None:
            raise build_error
        handoff = omr_job.Handoff(
            tmp_path / "completed.json", "a" * 64, binding["run_id"], tmp_path / "m.pt", "b" * 64
        )
        return handoff, ["omr-job"]

    seen = []

    def fake_source(self, *, image, precomputed_omr=None, **kwargs):
        events.append("source")
        seen.append(precomputed_omr)
        artifacts = kwargs["support_output"] / image.parent.name / image.stem / "artifacts"
        detection = artifacts / "current_homr" / f"{image.stem}_detections.json"
        omr = artifacts / "omr_sr" / image.stem / "predictions.json"
        detection.parent.mkdir(parents=True, exist_ok=True)
        omr.parent.mkdir(parents=True, exist_ok=True)
        detection.write_text("[]")
        omr.write_text("[]")
        return (
            {
                "image": str(image.resolve()),
                "current_sr_detection": str(detection),
                "current_omr": str(omr),
                "commands": [],
            },
            ["source", image.stem],
        )

    monkeypatch.setattr(batch_sr.os, "getuid", lambda: uid)
    monkeypatch.setattr(batch_sr, "available_resources", lambda: (32.0, 8.0, "test"))
    monkeypatch.setattr(BatchSRVerifiedProfileHybridDetector, "_batch_sr_worker", fake_sr)
    monkeypatch.setattr(BatchSRVerifiedProfileHybridDetector, "_omr_job_phase", fake_phase)
    monkeypatch.setattr(BatchSRVerifiedProfileHybridDetector, "_source_page_worker", fake_source)
    monkeypatch.setattr(
        BatchSRVerifiedProfileHybridDetector,
        "_current_detection_path",
        lambda self, p: Path(p["current_sr_detection"]),
    )
    result = detector._generate_page_sources(
        baseline_output=baseline_output, support_output=support_output
    )
    return detector, events, seen, result


def test_root_multi_page_job_runs_one_omr_phase_before_sources(tmp_path, monkeypatch):
    detector, events, seen, (_, _, commands) = _drive(tmp_path, monkeypatch, 3)
    assert events == ["sr", "omr_job", "source", "source", "source"]
    assert detector._omr_route["route"] == "job_reuse"
    assert all(h is not None and h["run_id"] == seen[0]["run_id"] for h in seen)
    assert commands[:2] == [["sr"], ["omr-job"]]


@pytest.mark.parametrize(
    ("count", "uid", "policy", "reason"),
    [
        (1, 0, AUTO, "fewer pages than min_pages"),
        (3, 1000, AUTO, "process uid outside allowed_uids"),
        (3, 0, None, "disabled"),
    ],
)
def test_excluded_jobs_keep_the_per_page_route(tmp_path, monkeypatch, count, uid, policy, reason):
    detector, events, seen, _ = _drive(tmp_path, monkeypatch, count, uid=uid, policy=policy)
    assert "omr_job" not in events
    assert seen == [None] * count
    assert (detector._omr_route["route"], detector._omr_route["reason"]) == ("per_page", reason)


def test_job_failure_never_falls_back_to_per_page_sources(tmp_path, monkeypatch):
    with pytest.raises(subprocess.CalledProcessError):
        _drive(
            tmp_path,
            monkeypatch,
            3,
            build_error=subprocess.CalledProcessError(137, ["omr_job_worker"]),
        )


def _support_request(tmp_path, monkeypatch, handoff):
    image = tmp_path / "Score/page_001.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"source")
    output_root = tmp_path / "support/artifacts"
    sr = output_root / "sr/batch/page_001/page_001.png"
    sr.parent.mkdir(parents=True)
    sr.write_bytes(b"sr")
    request = {
        "detection": {"sr_scale": 4},
        "image": str(image),
        "output_root": str(output_root),
        "precomputed_sr": {"image": str(image), "sr_image": str(sr), "sr_sha256": "x"},
        "precomputed_omr": handoff,
    }
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))
    monkeypatch.setattr(
        current_support_worker,
        "_require_precomputed_sr",
        lambda request, image: request["precomputed_sr"],
    )
    monkeypatch.setattr(
        current_support_worker, "_run_child_worker", lambda **kwargs: ({}, ["homr"])
    )
    homr = {
        k: output_root / f"{k}.json"
        for k in ("current_sr_detection", "staff_mask", "connector_symbols", "connector_brace_dot")
    }
    monkeypatch.setattr(
        current_support_worker, "_require_current_homr_bundle", lambda payload: homr
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("per-page OMR must not run on the job route")

    monkeypatch.setattr(current_support_worker, "run_with_logging", forbidden)
    return image, sr, output_root, path


def test_support_worker_consumes_job_prediction_without_running_omr(tmp_path, monkeypatch):
    consumed = []

    def consume(handoff, image, sr_image, output):
        consumed.append((handoff.run_id, Path(image), Path(sr_image)))
        output.parent.mkdir(parents=True)
        output.write_bytes(b"[[1,2,3,4]]")

    monkeypatch.setattr(omr_job, "consume", consume)
    handoff = {
        "manifest": str(tmp_path / "completed.json"),
        "manifest_sha256": "a" * 64,
        "run_id": "run",
        "model": str(tmp_path / "m.pt"),
        "model_sha256": "b" * 64,
    }
    image, sr, output_root, request = _support_request(tmp_path, monkeypatch, handoff)
    result = tmp_path / "result.json"
    current_support_worker.run(request, result)
    payload = json.loads(result.read_text())
    assert consumed == [("run", image.resolve(), sr.resolve())]
    assert payload["omr_execution_scope"] == "omr_job_process"
    assert payload["commands"][-1][0] == "omr-job-handoff"
    assert payload["memory_phase_boundaries"][1] == "omr_job_process_exited"
    assert Path(payload["current_omr"]).read_bytes() == b"[[1,2,3,4]]"


def test_support_worker_rejects_incomplete_job_without_publishing(tmp_path, monkeypatch):
    missing = {
        "manifest": str(tmp_path / "phase/completed.json"),
        "manifest_sha256": "a" * 64,
        "run_id": "run",
        "model": str(tmp_path / "m.pt"),
        "model_sha256": "b" * 64,
    }
    _, _, output_root, request = _support_request(tmp_path, monkeypatch, missing)
    with pytest.raises(FileNotFoundError):
        current_support_worker.run(request, tmp_path / "result.json")
    assert not (output_root / "omr_sr").exists()
    assert not (tmp_path / "result.json").exists()


def test_coordinator_rejects_result_from_the_other_route(tmp_path, monkeypatch):
    images = _pages(tmp_path, 1)
    detector = _detector(tmp_path, images)
    payload = {
        "status": "completed",
        "memory_boundary": "top_level_python_per_page",
        "sr_execution_scope": "dedicated_sr_batch_process",
        "historical_detector_artifact_runtime_input": False,
        "homr_neural_inference_count": 2,
        "x4_homr_neural_inference_count": 1,
        "omr_execution_scope": "page_subprocess",
    }

    class Jobs:
        def run(self, command, **kwargs):
            Path(command[command.index("--result") + 1]).write_text(json.dumps(payload))
            return subprocess.CompletedProcess(command, 0)

    detector._source_jobs = Jobs()
    with pytest.raises(ValueError, match="selected OMR route"):
        detector._source_page_worker(
            image=images[0],
            worker_output=tmp_path / "workers",
            baseline_output=tmp_path / "baseline",
            support_output=tmp_path / "support",
            precomputed_sr={"image": str(images[0])},
            precomputed_omr={"run_id": "run"},
        )
