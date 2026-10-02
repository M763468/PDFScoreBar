"""Small deterministic checks for Issue #397 preparation helpers."""

import json
import tempfile
import unittest
from pathlib import Path

from tools.review_correction import acceptance as runner


class AcceptanceRunnerTests(unittest.TestCase):
    def test_only_existing_manifest_paths_are_rebased_and_rewrite_is_recorded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            source = repo / "logs" / "run"
            artifact = repo / "logs" / "asset.bin"
            artifact.parent.mkdir(parents=True)
            source.mkdir(parents=True)
            artifact.write_bytes(b"retained")
            original = {"staff_mask": "logs/asset.bin", "optional": "logs/missing.bin"}
            adapted, rewrites = runner._adapt_manifest_paths(
                original, repo_root=repo, source_run=source, artifact_repo_root=repo
            )
            self.assertEqual(adapted["staff_mask"], str(artifact.resolve()))
            self.assertEqual(adapted["optional"], "logs/missing.bin")
            self.assertEqual(len(rewrites), 1)
            self.assertEqual(rewrites[0]["field"], "staff_mask")

    def test_source_context_copies_numbering_base_without_touching_retained_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "repo" / "logs" / "run"
            source.mkdir(parents=True)
            page = source / "intermediate" / "page_001" / "numbering_base.json"
            page.parent.mkdir(parents=True)
            page.write_text('{"pages": []}\n')
            original_manifest = {"pages": [{"page_id": "page_001", "staff_mask": "logs/mask.png"}]}
            (source / "manifest.json").write_text(json.dumps(original_manifest))
            before = runner.sha256(source / "manifest.json")
            context = runner._prepare_source_context(
                source_run=source,
                context_root=root / "evidence" / "source_context",
                repo_root=root / "repo",
                artifact_repo_root=root / "repo",
            )
            self.assertEqual(runner.sha256(source / "manifest.json"), before)
            self.assertTrue(
                (
                    Path(context["context_root"]) / "intermediate/page_001/numbering_base.json"
                ).is_file()
            )
            self.assertTrue((Path(context["context_root"]) / "manifest.json").is_file())

    def test_numbering_helpers_count_measures_and_preserve_visible_values(self):
        payload = {
            "systems": [{"measures": [{"number": 1}, {"number": 3}]}, {"measures": [{"number": 4}]}]
        }
        self.assertEqual(runner.visible_numbers(payload, 0), [1, 3])
        self.assertEqual(runner.total_measures(payload), 3)

    def test_state_snapshot_retains_current_and_last_successful_result_fields(self):
        last = {"identity": "old-result", "corrected_run": "/retained/run"}
        values = runner.state_values(
            {
                "package": {
                    "status": "stale",
                    "counts": {"stale": 1},
                    "current_result": None,
                    "last_successful_result": last,
                    "current_identity": {"identity": "new-inputs"},
                },
                "states": [{"application_status": "stale", "recording_status": "recorded"}],
            }
        )
        self.assertIsNone(values["current_result"])
        self.assertEqual(values["last_successful_result"], last)
        self.assertEqual(values["current_identity"]["identity"], "new-inputs")
        self.assertEqual(values["application_statuses"], ["stale"])


if __name__ == "__main__":
    unittest.main()
