from pathlib import Path

from tools.issue255.package_focused_first_loss_inputs import (
    iter_path_strings,
    resolve_record_path,
)


def test_resolve_record_path_maps_container_workspace(tmp_path: Path) -> None:
    assert resolve_record_path("/workspace/logs/run/artifact.json", root=tmp_path) == (
        tmp_path / "logs/run/artifact.json"
    )


def test_iter_path_strings_recurses_json_payload() -> None:
    payload = {
        "direct": "logs/a.json",
        "nested": [{"image": "/workspace/data/page.png"}, "not-a-path"],
        "ignored": "notes.md",
    }

    assert list(iter_path_strings(payload)) == [
        "logs/a.json",
        "/workspace/data/page.png",
    ]
