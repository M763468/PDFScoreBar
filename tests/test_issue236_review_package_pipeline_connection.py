import json
import sys
import types
from pathlib import Path

sys.modules.setdefault("fitz", types.SimpleNamespace())

from src.pipeline.core.config import load_yaml
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.review.manual_correction_handoff import validate_manual_correction_handoff


def _write_json(path: Path, payload: object | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload or {}, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str = "placeholder") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fake_pipeline_config(
    run_dir: Path,
    *,
    review_enabled: bool | None,
    review_root: Path | str | None = None,
    source_pipeline_command: str | None = None,
    page_ids: tuple[str, ...] = ("page_001",),
    user_exclude: list[int] | None = None,
) -> dict:
    image_dir = run_dir / "inputs" / "images"
    detector_dir = run_dir / "detector"
    for page_id in page_ids:
        _write_text(image_dir / f"{page_id}.png")
        _write_json(
            detector_dir / f"{page_id}_barlines.json",
            {"boxes": [{"bbox": [1, 2, 3, 4]}]},
        )
        _write_text(detector_dir / f"{page_id}_staff.png")

    review_cfg: dict[str, object] = {}
    if review_enabled is not None:
        review_cfg["manual_correction_package"] = review_enabled
    if review_root is not None:
        review_cfg["root"] = str(review_root)
    if source_pipeline_command is not None:
        review_cfg["source_pipeline_command"] = source_pipeline_command

    filters: dict[str, object] = {
        "blank_page": False,
        "staff_detect": False,
    }
    if user_exclude is not None:
        filters["user_exclude"] = user_exclude

    return {
        "inputs": {
            "pdf_to_images": {
                "output_dir": str(image_dir),
                "image_glob": "page_*.png",
            },
            "barlines_root": str(detector_dir),
            "barlines_pattern": "{page_id}_barlines.json",
            "staff_mask_pattern": "{page_id}_staff.png",
        },
        "steps": {
            "pdf_to_images": False,
            "detection": False,
            "numbering_base": False,
            "mmr_overrides": False,
            "apply_measure_overrides": False,
            "overlay": False,
        },
        "filters": filters,
        "outputs": {
            "review": review_cfg,
        },
    }


def _patch_lightweight_pipeline_phases(monkeypatch) -> None:
    def fake_base(self, page_ids, images, resolved, excluded_page_ids):
        return {
            "page_ctx": {page_id: {"index": index} for index, page_id in enumerate(page_ids, 1)},
            "numbering_base_paths": [],
            "barline_override_stats": {
                page_id: {
                    "removed": 0,
                    "added": 0,
                    "remove_requests": 0,
                    "unmatched_remove": 0,
                }
                for page_id in page_ids
            },
        }

    def fake_mmr(self, page_ids, excluded_page_ids, page_ctx):
        for page_id in page_ids:
            if page_id in excluded_page_ids:
                continue
            _write_json(self.run_dir / "intermediate" / page_id / "overrides_mmr.json")

    def fake_final(self, page_ids, excluded_page_ids, page_ctx, user_overrides_payload):
        paths = []
        for page_id in page_ids:
            if page_id in excluded_page_ids:
                continue
            final_path = self.run_dir / "outputs" / page_id / "numbering_final.json"
            _write_json(final_path)
            _write_text(self.run_dir / "outputs" / page_id / "numbering_overlay.png")
            paths.append(final_path)
        return paths

    monkeypatch.setattr(
        PipelineOrchestrator,
        "run_base_numbering_and_barline_correction",
        fake_base,
    )
    monkeypatch.setattr(PipelineOrchestrator, "run_mmr_batch_detection", fake_mmr)
    monkeypatch.setattr(PipelineOrchestrator, "run_final_numbering_and_overlays", fake_final)


def test_pipeline_connection_materializes_enabled_review_package(monkeypatch, tmp_path):
    run_dir = tmp_path / "source_run"
    config = _fake_pipeline_config(run_dir, review_enabled=True)
    _patch_lightweight_pipeline_phases(monkeypatch)

    import src.pipeline.orchestrator as orchestrator_module

    real_materializer = orchestrator_module.materialize_manual_correction_review_package
    call_args = {}

    def spy_materializer(**kwargs):
        call_args.update(kwargs)
        return real_materializer(**kwargs)

    monkeypatch.setattr(
        orchestrator_module,
        "materialize_manual_correction_review_package",
        spy_materializer,
    )

    orchestrator = PipelineOrchestrator(config=config, run_id="source_run", run_dir=run_dir)
    result = orchestrator.run()

    assert result == run_dir
    review_root = run_dir / "review"
    assert call_args["run_root"] == run_dir
    assert call_args["review_root"] == review_root
    assert call_args["pages"] == ["page_001"]
    assert call_args["source_pipeline_command"] is None

    handoff_path = review_root / "manual_correction_input.json"
    handoff = json.loads(handoff_path.read_text())
    page = handoff["pages"][0]
    assert page["barlines_review_source"] == "detector/page_001_barlines.json"
    assert page["barlines_review_source_kind"] == "manifest_resolved_detector_output"
    assert page["barlines_review_source_manifest_field"] == "barlines_json"
    assert (review_root / "pages" / "page_001" / "source.png").exists()
    assert (review_root / "pages" / "page_001" / "numbering_final.json").exists()
    assert (review_root / "pages" / "page_001" / "review_overlay.png").exists()
    assert (review_root / "pages" / "page_001" / "mmr_overrides.json").exists()
    assert (review_root / "pages" / "page_001" / "barlines_review.json").exists()
    assert (review_root / "corrections").is_dir()

    validated = validate_manual_correction_handoff(
        handoff,
        handoff_path=handoff_path,
        mode="issue229_smoke_strict",
        require_existing_artifacts=True,
    )
    assert validated["pages"][0]["page_id"] == "page_001"


def test_pipeline_connection_resolves_relative_review_root_from_run_dir(monkeypatch, tmp_path):
    run_dir = tmp_path / "source_run"
    config = _fake_pipeline_config(
        run_dir,
        review_enabled=True,
        review_root=Path("manual_review"),
        source_pipeline_command="make run-pipeline CONFIG=smoke.yaml",
    )
    _patch_lightweight_pipeline_phases(monkeypatch)

    orchestrator = PipelineOrchestrator(config=config, run_id="source_run", run_dir=run_dir)
    orchestrator.run()

    handoff_path = run_dir / "manual_review" / "manual_correction_input.json"
    assert handoff_path.exists()
    handoff = json.loads(handoff_path.read_text())
    assert handoff["source_pipeline_command"] == "make run-pipeline CONFIG=smoke.yaml"
    assert not (run_dir / "review" / "manual_correction_input.json").exists()


def test_pipeline_connection_uses_absolute_review_root(monkeypatch, tmp_path):
    run_dir = tmp_path / "source_run"
    public_review_root = tmp_path / "public_output" / "review"
    config = _fake_pipeline_config(
        run_dir,
        review_enabled=True,
        review_root=public_review_root,
    )
    _patch_lightweight_pipeline_phases(monkeypatch)

    orchestrator = PipelineOrchestrator(config=config, run_id="source_run", run_dir=run_dir)
    orchestrator.run()

    assert (public_review_root / "manual_correction_input.json").exists()
    assert not (run_dir / "review" / "manual_correction_input.json").exists()


def test_pipeline_connection_does_not_materialize_when_disabled(monkeypatch, tmp_path):
    run_dir = tmp_path / "source_run"
    config = _fake_pipeline_config(run_dir, review_enabled=False)
    _patch_lightweight_pipeline_phases(monkeypatch)

    orchestrator = PipelineOrchestrator(config=config, run_id="source_run", run_dir=run_dir)
    orchestrator.run()

    assert (run_dir / "manifest.json").exists()
    assert not (run_dir / "review").exists()


def test_pipeline_connection_does_not_materialize_when_review_flag_missing(monkeypatch, tmp_path):
    run_dir = tmp_path / "source_run"
    config = _fake_pipeline_config(run_dir, review_enabled=None)
    _patch_lightweight_pipeline_phases(monkeypatch)

    orchestrator = PipelineOrchestrator(config=config, run_id="source_run", run_dir=run_dir)
    orchestrator.run()

    assert (run_dir / "manifest.json").exists()
    assert not (run_dir / "review").exists()


def test_pipeline_connection_treats_null_overwrite_as_default_true(monkeypatch, tmp_path):
    run_dir = tmp_path / "source_run"
    config = _fake_pipeline_config(run_dir, review_enabled=True)
    config["outputs"]["review"]["overwrite"] = None
    _patch_lightweight_pipeline_phases(monkeypatch)

    import src.pipeline.orchestrator as orchestrator_module

    real_materializer = orchestrator_module.materialize_manual_correction_review_package
    call_args = {}

    def spy_materializer(**kwargs):
        call_args.update(kwargs)
        return real_materializer(**kwargs)

    monkeypatch.setattr(
        orchestrator_module,
        "materialize_manual_correction_review_package",
        spy_materializer,
    )

    orchestrator = PipelineOrchestrator(config=config, run_id="source_run", run_dir=run_dir)
    orchestrator.run()

    assert call_args["overwrite"] is True


def test_pipeline_connection_skips_user_excluded_pages_in_review_package(monkeypatch, tmp_path):
    run_dir = tmp_path / "source_run"
    config = _fake_pipeline_config(
        run_dir,
        review_enabled=True,
        page_ids=("page_001", "page_002"),
        user_exclude=[2],
    )
    _patch_lightweight_pipeline_phases(monkeypatch)

    import src.pipeline.orchestrator as orchestrator_module

    real_materializer = orchestrator_module.materialize_manual_correction_review_package
    call_args = {}

    def spy_materializer(**kwargs):
        call_args.update(kwargs)
        return real_materializer(**kwargs)

    monkeypatch.setattr(
        orchestrator_module,
        "materialize_manual_correction_review_package",
        spy_materializer,
    )

    orchestrator = PipelineOrchestrator(config=config, run_id="source_run", run_dir=run_dir)
    orchestrator.run()

    review_root = run_dir / "review"
    assert call_args["pages"] == ["page_001"]
    handoff = json.loads((review_root / "manual_correction_input.json").read_text())
    assert [page["page_id"] for page in handoff["pages"]] == ["page_001"]
    assert (review_root / "pages" / "page_001").is_dir()
    assert not (review_root / "pages" / "page_002").exists()


def test_review_package_example_config_is_parseable():
    config = load_yaml(Path("configs/review_manual_correction_package_example.yaml"))

    assert config["outputs"]["review"]["manual_correction_package"] is True
    assert config["outputs"]["review"]["root"] == "review"
