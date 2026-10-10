"""The retained replay must audit silent misapplication, including last rests."""

from copy import deepcopy

import pytest
from PIL import Image

from src.pipeline.core import write_json
from src.pipeline.review.final_output import materialize_corrected_final_outputs
from tools.issue413 import replay_phase_c
from tools.issue413.replay_phase_c import audit_score, verify_pdf_images


def page(page_id, numbers, next_number):
    return {
        "page_id": page_id,
        "pages": [
            {
                "systems": [
                    {
                        "staves": [{"bbox": [0, 0, 100, 40]}],
                        "measures": [
                            {"number": number, "bbox": [index * 20, 0, index * 20 + 19, 40]}
                            for index, number in enumerate(numbers)
                        ],
                    }
                ]
            }
        ],
        "numbering_metadata": {"next_number": next_number},
    }


def test_audit_includes_unrecognized_targets_page_boundary_and_terminal_skip():
    baseline = [page("page_001", [1, 5], 6), page("page_002", [6, 7], 8)]
    candidate = [page("page_001", [1, 2], 6), page("page_002", [6, 7], 10)]
    predictions = [
        {"measure_overrides": [{"page": 0, "system": 0, "measure": 1, "skip": 3}]},
        {"measure_overrides": [{"page": 1, "system": 0, "measure": 1, "skip": 2}]},
    ]
    records = audit_score("fixture", baseline, candidate, predictions)
    assert [r["recognized_skip"] for r in records] == [0, 3, 0, 2]
    assert [r["old_applied_skip"] for r in records] == [3, 0, 0, 0]
    assert [r["new_applied_skip"] for r in records] == [0, 3, 0, 2]


def test_audit_rejects_changed_geometry_and_missing_override_target():
    baseline = [page("page_001", [1, 2], 3)]
    candidate = deepcopy(baseline)
    candidate[0]["pages"][0]["systems"][0]["measures"][0]["bbox"][0] += 1
    with pytest.raises(AssertionError, match="geometry"):
        audit_score("fixture", baseline, candidate, [{"measure_overrides": []}])
    with pytest.raises(AssertionError, match="missing override target"):
        audit_score(
            "fixture",
            baseline,
            baseline,
            [{"measure_overrides": [{"page": 0, "system": 1, "measure": 0, "skip": 2}]}],
        )


def test_pdf_verification_reads_embedded_pixels_and_detects_stale_labels(tmp_path):
    source = tmp_path / "source.png"
    Image.new("RGB", (300, 200), "white").save(source)
    numbering = page("page_001", [1, 2], 3)
    numbering_path = tmp_path / "outputs/page_001/numbering_final.json"
    write_json(numbering_path, numbering)
    handoff = tmp_path / "handoff.json"
    write_json(handoff, {"pages": [{"page_id": "page_001", "source_image": "source.png"}]})
    summary = materialize_corrected_final_outputs(handoff_path=handoff, corrected_run_dir=tmp_path)
    assert len(verify_pdf_images(summary)) == 1
    numbering["pages"][0]["systems"][0]["measures"][0]["number"] = 42
    write_json(numbering_path, numbering)
    with pytest.raises(AssertionError, match="PDF pixel mismatch"):
        verify_pdf_images(summary)


@pytest.fixture
def canonical_fixture(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    retained = repo / "retained"
    image = repo / "source.png"
    config = repo / "dense.yaml"
    predictions = retained / "overrides_mmr.json"
    derived = retained / "config_derived.yaml"
    baseline = retained / "numbering_final.json"
    retained.mkdir(parents=True)
    Image.new("RGB", (8, 8), "white").save(image)
    config.write_text("threshold: 0.5\n")
    derived.write_text("threshold: 0.5\n")
    write_json(predictions, {"measure_overrides": [{"skip": 8}]})
    write_json(baseline, page("page_001", [1, 2], 3))
    manifest = tmp_path / "canonical_inputs.json"
    write_json(
        manifest,
        {
            "schema_version": "issue413.canonical_inputs.v1",
            "repo_files": {p.name: replay_phase_c.sha256(p) for p in (image, config)},
            "retained_files": {
                p.name: replay_phase_c.sha256(p) for p in (predictions, derived, baseline)
            },
        },
    )
    monkeypatch.setattr(replay_phase_c, "CANONICAL_INPUTS_PATH", manifest)
    monkeypatch.chdir(repo)
    return repo, retained, (image, config, predictions, derived, baseline)


def test_preflight_uses_fixed_baseline_and_retains_expected_hashes(canonical_fixture):
    repo, retained, files = canonical_fixture
    expected = replay_phase_c.canonical_input_hashes(repo, retained)
    assert len(expected) == 5
    assert expected[str(files[2])] == replay_phase_c.sha256(files[2])
    files[2].write_text('{"measure_overrides": [{"skip": 9}]}')
    # The post-run guard also uses the original baseline, not a refreshed digest.
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        replay_phase_c.verify_input_hashes(expected)


@pytest.mark.parametrize(
    "file_index",
    range(5),
    ids=["source-image", "canonical-config", "mmr-predictions", "derived-config", "baseline-final"],
)
def test_replay_rejects_preexisting_corruption_before_orchestration(
    canonical_fixture, monkeypatch, file_index
):
    _repo, retained, files = canonical_fixture
    path = files[file_index]
    if path.suffix == ".png":
        Image.new("RGB", (8, 8), "black").save(path)
    elif path.name == "overrides_mmr.json":
        write_json(path, {"measure_overrides": [{"skip": 9}]})
    elif path.name == "numbering_final.json":
        write_json(path, page("page_001", [1, 5], 6))
    else:
        path.write_text("threshold: 0.6\n")

    def unexpected_orchestration(*_args, **_kwargs):
        pytest.fail("corrupt canonical input must be rejected before orchestration")

    monkeypatch.setattr(replay_phase_c, "PipelineOrchestrator", unexpected_orchestration)
    output = retained.parent / "output"
    with pytest.raises(ValueError, match="SHA-256 mismatch") as error:
        replay_phase_c.replay(retained, output)
    assert path.name in str(error.value)
    assert not output.exists()


def test_preflight_rejects_missing_inputs_and_unlisted_consumers(canonical_fixture):
    repo, retained, files = canonical_fixture
    hashes = replay_phase_c.canonical_input_hashes(repo, retained)
    with pytest.raises(ValueError, match="not in canonical manifest"):
        replay_phase_c.require_canonical_input(repo / "alternate_source.png", hashes)
    files[2].unlink()
    with pytest.raises(ValueError, match="Cannot verify canonical input"):
        replay_phase_c.canonical_input_hashes(repo, retained)
