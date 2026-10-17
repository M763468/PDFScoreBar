import json

from tools.review_correction import application


def test_numbering_preview_uses_retained_artifact_consumer_without_mutating_package(
    tmp_path, monkeypatch
):
    package = tmp_path / "review"
    package.mkdir()
    handoff = package / "manual_correction_input.json"
    handoff.write_text("{}", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"config": {}}), encoding="utf-8")
    normalized = {
        "pages": [
            {
                "page_id": "page_001",
                "page_number": 1,
                "manual_outputs": {},
            }
        ]
    }
    calls = {}

    monkeypatch.setattr(application, "load_manual_correction_handoff", lambda _path: {})
    monkeypatch.setattr(
        application,
        "validate_manual_correction_handoff",
        lambda *_args, **_kwargs: normalized,
    )
    monkeypatch.setattr(
        application,
        "_resolve_source_manifest_path",
        lambda *_args: manifest,
    )
    monkeypatch.setattr(
        application,
        "_read_existing_override_inputs",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        application,
        "_load_movement_boundary_input",
        lambda **_kwargs: ({"boundaries": []}, None, None),
    )

    def run_retained_consumer(**kwargs):
        calls.update(kwargs)
        output = kwargs["new_run_dir"] / "outputs/page_001/numbering_final.json"
        output.parent.mkdir(parents=True)
        output.write_text(
            json.dumps(
                {
                    "pages": [
                        {
                            "systems": [
                                {"index": 0, "measures": [{"number": 3}, {"number": 4}]},
                                {"index": 1, "measures": [{"number": 7}]},
                            ]
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(application, "_run_retained_artifact_correction", run_retained_consumer)

    result = application.preview_numbering(handoff)

    assert result == {
        "status": "provisional",
        "basis": "saved_review_corrections",
        "pages": [
            {
                "page": 0,
                "page_number": 1,
                "page_id": "page_001",
                "systems": [
                    {"system": 0, "first_measure_number": 3, "measure_count": 2},
                    {"system": 1, "first_measure_number": 7, "measure_count": 1},
                ],
            }
        ],
    }
    assert calls["package_root"] == package
    assert calls["source_manifest"]["config"] == {}
    assert handoff.read_text(encoding="utf-8") == "{}"
