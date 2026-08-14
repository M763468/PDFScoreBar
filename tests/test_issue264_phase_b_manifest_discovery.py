from __future__ import annotations

import json
from pathlib import Path

from tools.issue264.run_phase_b_page001_acceptance import CANONICAL_RUN, _matching_manifest


def test_matching_manifest_skips_non_mapping_json(tmp_path: Path) -> None:
    list_manifest = tmp_path / "list_manifest.json"
    list_manifest.write_text(json.dumps([{"run_id": CANONICAL_RUN}]) + "\n", encoding="utf-8")

    canonical_manifest = tmp_path / "canonical_manifest.json"
    canonical_manifest.write_text(json.dumps({"run_id": CANONICAL_RUN}) + "\n", encoding="utf-8")

    assert _matching_manifest([list_manifest, canonical_manifest]) == canonical_manifest
