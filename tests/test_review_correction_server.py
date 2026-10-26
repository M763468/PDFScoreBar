import http.client
import json
import subprocess
import sys
from pathlib import Path
from threading import Thread

import pytest

import tools.review_correction.server as review_server_module
from tools.gt_relabel_gui.server import Handler as DeveloperHandler
from tools.review_correction.server import ReviewPackage, create_server


def _handoff(tmp_path):
    root = tmp_path / "source_run" / "review"
    page = root / "pages" / "page_001"
    page.mkdir(parents=True)
    (page / "source.png").write_bytes(b"image")
    for name in ("numbering_final.json", "mmr_overrides.json", "barlines_review.json"):
        (page / name).write_text("{}", encoding="utf-8")
    (page / "numbering_final.json").write_text(json.dumps({"systems": [{"index": 0}]}))
    handoff = root / "manual_correction_input.json"
    handoff.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "manual_correction_input",
                "pages": [
                    {
                        "page_id": "page_001",
                        "page_number": 1,
                        "source_image": "pages/page_001/source.png",
                        "numbering_final": "pages/page_001/numbering_final.json",
                        "mmr_overrides": "pages/page_001/mmr_overrides.json",
                        "barlines_review": "pages/page_001/barlines_review.json",
                        "correction_output": "corrections",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return handoff


@pytest.fixture
def review_server(tmp_path):
    handoff = _handoff(tmp_path)
    server = create_server(handoff, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, handoff
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _request(server, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
    data = None if body is None else json.dumps(body)
    request_headers = {"Content-Type": "application/json"} if body is not None else {}
    request_headers.update(headers or {})
    conn.request(
        method,
        path,
        body=data,
        headers=request_headers,
    )
    response = conn.getresponse()
    result = response.status, response.read()
    conn.close()
    return result


def test_review_entry_requires_handoff_and_has_no_developer_modes(tmp_path):
    script = Path(__file__).resolve().parents[1] / "tools" / "review_correction" / "server.py"
    for args in (
        [],
        ["--mode", "gt"],
        ["--root", str(tmp_path)],
        ["--config", "other.json"],
        ["--host", "0.0.0.0"],
    ):
        result = subprocess.run(
            [sys.executable, str(script), *args], capture_output=True, text=True
        )
        assert result.returncode != 0
    with pytest.raises(ValueError, match="manual_correction_input.json"):
        ReviewPackage(tmp_path / "other.json")
    handoff = _handoff(tmp_path)
    package = ReviewPackage(handoff)
    assert package.root == handoff.parent
    assert package.pages[0]["image"] == "pages/page_001/source.png"


def test_review_routes_only_serve_declared_artifacts(review_server):
    server, handoff = review_server
    assert server.server_address[0] == "127.0.0.1"
    assert _request(server, "GET", "/")[0] == 200
    assert _request(server, "GET", "/app_manual.js")[0] == 200
    assert _request(server, "GET", "/app.js")[0] == 200
    assert _request(server, "GET", "/strings.js")[0] == 200
    assert _request(server, "GET", "/correction_state.js")[0] == 200
    html = _request(server, "GET", "/")[1].decode("utf-8")
    assert 'src="correction_state.js"' in html
    assert _request(server, "GET", "/api/pages")[0] == 200
    status, pages = _request(server, "GET", "/api/pages?mode=gt")
    assert status == 200
    assert "output_raw" not in pages.decode("utf-8")
    assert _request(server, "GET", "/file?path=pages/page_001/source.png")[0] == 200
    assert (
        _request(server, "GET", "/api/template?path=pages/page_001/numbering_final.json")[0] == 200
    )
    assert _request(server, "GET", "/api/boxes?path=pages/page_001/barlines_review.json")[0] == 200

    hidden = handoff.parent / "pages" / "page_001" / "private.json"
    hidden.write_text('{"secret": true}', encoding="utf-8")
    for path in (
        "/app_gt.js",
        "/app_rest.js",
        "/api/items",
        "/api/probe_log",
        "/api/template?path=pages/page_001/private.json",
        "/api/template?path=pages/page_001/barlines_review.json",
        "/file?path=manual_correction_input.json",
        "/file?path=../canonical_gt.json",
    ):
        assert _request(server, "GET", path)[0] in (403, 404)
    assert _request(server, "POST", "/api/probe_log", {"page": "page_001"})[0] == 404


def test_numbering_preview_endpoint_uses_the_active_package_without_options(
    review_server, monkeypatch
):
    server, handoff = review_server
    monkeypatch.setattr(
        review_server_module,
        "preview_numbering",
        lambda path: {"status": "provisional", "handoff": str(path)},
    )
    status, content = _request(server, "POST", "/api/preview_numbering", {})
    assert status == 200
    assert json.loads(content) == {
        "status": "provisional",
        "handoff": str(handoff.resolve()),
    }
    assert _request(server, "POST", "/api/preview_numbering", {"path": "/outside"})[0] == 400


def test_review_save_cannot_select_gt_or_canonical_paths(review_server):
    server, handoff = review_server
    root = handoff.parent
    canonical = root / "pages" / "page_001" / "barlines_review.json"
    before = canonical.read_bytes()
    body = {
        "page": 0,
        "correction_type": "barline_construction",
        "items": [{"page": 0, "op": "test"}],
    }
    assert _request(server, "POST", "/api/save", body)[0] == 200
    output = root / "corrections" / "barline_construction_overrides.json"
    assert json.loads(output.read_text())["items"] == body["items"]
    assert (
        _request(server, "GET", "/api/manual_corrections?type=barline_construction&page=0")[0]
        == 200
    )
    for change in (
        {"correction_type": "gt"},
        {"correction_type": "rest"},
        {"correction_type": "relabel"},
        {"page": "missing"},
    ):
        assert _request(server, "POST", "/api/save", {**body, **change})[0] == 400
    assert canonical.read_bytes() == before


def test_failed_atomic_save_preserves_last_recorded_correction(review_server, monkeypatch):
    server, handoff = review_server
    output = handoff.parent / "corrections" / "barline_construction_overrides.json"
    output.parent.mkdir(parents=True)
    original = (
        b'{"schema_version":1,"correction_type":"barline_construction","items":[{"page":0}]}\n'
    )
    output.write_bytes(original)

    def fail_replace(_src, _dst):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(review_server_module.os, "replace", fail_replace)
    status, _ = _request(
        server,
        "POST",
        "/api/save",
        {"page": 0, "correction_type": "barline_construction", "items": [{"page": 0}]},
    )
    assert status == 400
    assert output.read_bytes() == original
    state = json.loads(_request(server, "GET", "/api/state")[1])
    barline = next(s for s in state["states"] if s["correction_type"] == "barline_construction")
    assert barline["recording_status"] == "recorded"
    assert "error" in barline


def test_server_state_pending_api(review_server):
    server, _ = review_server
    pending = {"page": 0, "correction_type": "barline_construction", "items": [{"page": 0}]}
    assert _request(server, "POST", "/api/state/pending", pending)[0] == 200
    state = json.loads(_request(server, "GET", "/api/state")[1])
    barline = next(s for s in state["states"] if s["correction_type"] == "barline_construction")
    assert barline["edit_status"] == "pending"
    assert (
        _request(
            server,
            "POST",
            "/api/state/pending/clear",
            {"page": 0, "correction_type": "barline_construction"},
        )[0]
        == 200
    )


def test_review_rejects_cross_origin_writes(review_server):
    server, handoff = review_server
    body = {"page": 0, "correction_type": "barline_construction", "items": []}
    output = handoff.parent / "corrections" / "barline_construction_overrides.json"
    for headers, expected in (
        ({"Origin": "https://example.test"}, 403),
        ({"Origin": "null"}, 403),
        ({"Content-Type": "text/plain"}, 415),
        ({"Host": "example.test"}, 403),
    ):
        assert _request(server, "POST", "/api/save", body, headers)[0] == expected
        assert not output.exists()
    assert _request(server, "GET", "/api/pages", headers={"Host": "example.test"})[0] == 403
    assert (
        _request(
            server,
            "POST",
            "/api/export_movement_boundaries",
            {},
            {"Origin": "https://example.test"},
        )[0]
        == 403
    )
    local_origin = f"http://127.0.0.1:{server.server_port}"
    assert _request(server, "POST", "/api/save", body, {"Origin": local_origin})[0] == 200


def test_review_rechecks_symlinks_at_request_time(review_server, tmp_path):
    server, handoff = review_server
    root = handoff.parent
    source = root / "pages" / "page_001" / "source.png"
    source.unlink()
    source.symlink_to(root / "pages" / "page_001" / "numbering_final.json")
    assert _request(server, "GET", "/file?path=pages/page_001/source.png")[0] == 403

    external = tmp_path / "canonical_gt.json"
    external.write_text("unchanged", encoding="utf-8")
    corrections = root / "corrections"
    corrections.mkdir()
    output = corrections / "barline_construction_overrides.json"
    output.symlink_to(external)
    body = {"page": 0, "correction_type": "barline_construction", "items": []}
    assert _request(server, "POST", "/api/save", body)[0] == 400
    assert external.read_text() == "unchanged"


def test_review_movement_export_uses_declared_package_paths(tmp_path):
    handoff = _handoff(tmp_path)
    root = handoff.parent
    payload = json.loads(handoff.read_text())
    payload["movement_boundary_evidence"] = "movement_boundary_evidence.json"
    payload["movement_boundary_resolved_output"] = "corrections/movement_boundaries.json"
    handoff.write_text(json.dumps(payload), encoding="utf-8")
    (root / "movement_boundary_evidence.json").write_text(
        json.dumps({"schema_version": "issue333.movement_boundary_evidence.v1", "candidates": []}),
        encoding="utf-8",
    )
    server = create_server(handoff, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert _request(server, "POST", "/api/export_movement_boundaries", {})[0] == 400
        assert (
            _request(
                server,
                "POST",
                "/api/save",
                {"page": 0, "correction_type": "movement_boundary", "items": []},
            )[0]
            == 200
        )
        assert _request(server, "POST", "/api/export_movement_boundaries", {})[0] == 200
        assert (
            json.loads((root / "corrections" / "movement_boundaries.json").read_text())[
                "boundaries"
            ]
            == []
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _load_saved_movement(package):
    from src.pipeline.review.apply_corrections import _load_movement_boundary_input

    return _load_movement_boundary_input(
        normalized_handoff={
            "pages": package.pages,
            "movement_boundary_resolved_output": "corrections/movement_boundaries.json",
        },
        package_root=package.root,
        source_config={},
    )[0]


def test_manual_movement_save_is_ready_for_numbering_without_detector_evidence(review_server):
    server, _ = review_server
    item = {"page": 0, "system": 0, "op": "boundary", "reason": "new movement"}
    assert (
        _request(
            server,
            "POST",
            "/api/save",
            {"page": 0, "correction_type": "movement_boundary", "items": [item]},
        )[0]
        == 200
    )
    payload = _load_saved_movement(server.package)
    assert [(b["page"], b["system"], b["reset_number"]) for b in payload["boundaries"]] == [
        (0, 0, 1)
    ]
    boundary = payload["boundaries"][0]
    assert boundary["source"] == "manual"
    assert boundary["provenance"]["review"]["sha256"]
    assert "evidence" not in boundary["provenance"]
    server.package.record_correction(0, "movement_boundary", [])
    assert _load_saved_movement(server.package)["boundaries"] == []


@pytest.mark.parametrize(
    "item",
    [
        {"page": 0, "system": 99, "op": "boundary"},
        {"page": 1, "system": 0, "op": "boundary"},
        {"page": 0, "system": 0, "op": "no_boundary"},
    ],
)
def test_manual_movement_rejects_unsupported_targets_before_writing(review_server, item):
    server, _ = review_server
    status, _ = _request(
        server,
        "POST",
        "/api/save",
        {
            "page": 0,
            "correction_type": "movement_boundary",
            "items": [item],
        },
    )
    assert status == 400
    assert not server.package.output(0, "movement_boundary").exists()


def test_manual_movement_partial_save_cannot_apply_stale_reset(review_server, monkeypatch):
    server, _ = review_server
    package = server.package
    item = {"page": 0, "system": 0, "op": "boundary"}
    package.record_correction(0, "movement_boundary", [item])
    original_write = review_server_module._atomic_write

    def fail_resolved(path, value):
        if path.name == "movement_boundaries.json":
            raise OSError("resolved write failed")
        original_write(path, value)

    changed = [{**item, "reason": "changed decision"}]
    with monkeypatch.context() as patch:
        patch.setattr(review_server_module, "_atomic_write", fail_resolved)
        with pytest.raises(OSError, match="resolved write failed"):
            package.record_correction(0, "movement_boundary", changed)
    # A failed save rolls back both raw and resolved decisions atomically.
    assert len(_load_saved_movement(package)["boundaries"]) == 1
    assert package.state.snapshot()["package"]["status"] == "error"
    package.record_correction(0, "movement_boundary", changed)
    assert len(_load_saved_movement(package)["boundaries"]) == 1


@pytest.mark.parametrize("custom_outputs", [False, True])
def test_manual_movement_save_preserves_other_pages_and_rechecks_saved_bytes(
    tmp_path, custom_outputs
):
    handoff = _handoff(tmp_path)
    data = json.loads(handoff.read_text())
    data["pages"].append({**data["pages"][0], "page_id": "page_002", "page_number": 2})
    if custom_outputs:
        for index, page in enumerate(data["pages"]):
            page["correction_outputs"] = {
                "mmr_measure_span": f"corrections/page{index}-mmr.json",
                "measure_construction": f"corrections/page{index}-measures.json",
                "barline_construction": f"corrections/page{index}-barlines.json",
                "movement_boundary": "corrections/shared-movements.json",
            }
    handoff.write_text(json.dumps(data))
    package = ReviewPackage(handoff)
    for page in (0, 1):
        package.record_correction(
            page, "movement_boundary", [{"page": page, "system": 0, "op": "boundary"}]
        )
    assert len(_load_saved_movement(package)["boundaries"]) == 2
    package.record_correction(0, "movement_boundary", [])
    assert [b["page"] for b in _load_saved_movement(package)["boundaries"]] == [1]
    path = package.output(1, "movement_boundary")
    path.write_text(
        json.dumps({"schema_version": 1, "correction_type": "movement_boundary", "items": []})
    )
    with pytest.raises(ValueError, match="stale"):
        _load_saved_movement(package)


def test_distinct_movement_paths_are_rejected_before_any_save_or_apply(tmp_path):
    handoff = _handoff(tmp_path)
    data = json.loads(handoff.read_text())
    data["pages"].append({**data["pages"][0], "page_id": "page_002", "page_number": 2})
    handoff.write_text(json.dumps(data))
    package = ReviewPackage(handoff)
    package.pages[1]["manual_outputs"]["movement_boundary"] = "corrections/other-movements.json"
    with pytest.raises(ValueError, match="one shared package-local path"):
        _load_saved_movement(package)

    data["pages"][1]["correction_outputs"] = {
        **package.pages[1]["manual_outputs"],
    }
    handoff.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="one shared package-local path"):
        ReviewPackage(handoff)
    assert not (handoff.parent / "corrections").exists()


def test_review_rejects_handoff_output_targeting_artifact_or_external_symlink(tmp_path):
    handoff = _handoff(tmp_path)
    payload = json.loads(handoff.read_text())
    payload["pages"][0]["correction_output"] = "pages/page_001"
    handoff.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="review/corrections"):
        ReviewPackage(handoff)

    payload["pages"][0]["correction_output"] = "corrections"
    handoff.write_text(json.dumps(payload), encoding="utf-8")
    (handoff.parent / "corrections").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="stay inside the review package|symlink"):
        ReviewPackage(handoff)


def test_developer_entrypoint_retains_gt_modes():
    script = Path(__file__).resolve().parents[1] / "tools" / "gt_relabel_gui" / "server.py"
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "relabel" in result.stdout and "gt" in result.stdout and "rest" in result.stdout


def test_developer_gt_save_route_still_operates(tmp_path):
    from http.server import HTTPServer

    server = HTTPServer(("127.0.0.1", 0), DeveloperHandler)
    server.mode = "gt"
    server.root = tmp_path
    server.gt_config = [
        {"name": "page_001", "output_raw": "raw.json", "output_sorted": "sorted.json"}
    ]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _ = _request(
            server, "POST", "/api/save", {"page": "page_001", "boxes": [[1, 2, 3, 4]]}
        )
        assert status == 200
        assert json.loads((tmp_path / "raw.json").read_text())[0]["barline_location"] == [
            1,
            2,
            3,
            4,
        ]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize(
    "kind",
    ["mmr_measure_span", "measure_construction", "barline_construction", "movement_boundary"],
)
def test_all_corrections_share_record_transition_and_failure_preservation(
    review_server, monkeypatch, kind
):
    server, _ = review_server
    package = server.package
    first = [
        {
            "page": 0,
            "system": 0,
            "op": "boundary" if kind == "movement_boundary" else "set_measure_span",
        }
    ]
    changed = [{**first[0], "reason": "new draft"}]
    package.state.set_pending(0, kind, first)
    package.record_correction(0, kind, first)
    state = next(s for s in package.state.snapshot()["states"] if s["correction_type"] == kind)
    assert state["edit_status"] == "none"
    assert state["recording_status"] == "recorded"
    before = package.output(0, kind).read_bytes()
    package.state.set_pending(0, kind, changed)

    def fail_replace(*args):
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(review_server_module.os, "replace", fail_replace)
        with pytest.raises(OSError, match="disk full"):
            package.record_correction(0, kind, changed)
    assert package.output(0, kind).read_bytes() == before
    state = next(s for s in package.state.snapshot()["states"] if s["correction_type"] == kind)
    assert state["edit_status"] == "pending"
    assert state["recording_status"] == "recorded"
    assert state["error"] == "disk full"
    package.record_correction(0, kind, changed)
    state = next(s for s in package.state.snapshot()["states"] if s["correction_type"] == kind)
    assert state["edit_status"] == "none"
    assert "error" not in state
