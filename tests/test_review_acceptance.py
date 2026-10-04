"""Small deterministic checks for Issue #397 preparation helpers."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.review_correction import acceptance as runner


class AcceptanceRunnerTests(unittest.TestCase):
    def test_candidate_commit_uses_checkout_when_git_lookup_succeeds(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                runner,
                "run_git",
                return_value={"exit_code": 0, "stdout": "abc123", "stderr": ""},
            ),
        ):
            provenance = runner.candidate_commit_provenance(Path("/repo"))
        self.assertEqual(provenance["candidate_commit"], "abc123")
        self.assertEqual(provenance["candidate_commit_source"], "checkout")

    def test_candidate_commit_requires_operator_identity_without_git(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                runner,
                "run_git",
                return_value={"exit_code": 128, "stdout": "", "stderr": "not a git repository"},
            ),
        ):
            with self.assertRaisesRegex(ValueError, "PDFSCOREBAR_SOURCE_COMMIT"):
                runner.candidate_commit_provenance(Path("/container/source"))

    def test_candidate_commit_accepts_explicit_identity_without_git(self):
        with (
            patch.dict(os.environ, {"PDFSCOREBAR_SOURCE_COMMIT": " frozen-sha "}),
            patch.object(
                runner,
                "run_git",
                return_value={"exit_code": 128, "stdout": "", "stderr": "not a git repository"},
            ),
        ):
            provenance = runner.candidate_commit_provenance(Path("/container/source"))
        self.assertEqual(provenance["candidate_commit"], "frozen-sha")
        self.assertEqual(provenance["operator_candidate_commit"], "frozen-sha")
        self.assertEqual(provenance["candidate_commit_source"], "operator")

    def test_prepare_rejects_missing_candidate_commit_before_creating_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence_root = root / "evidence"
            args = type(
                "Args",
                (),
                {
                    "source_run": root / "source",
                    "evidence_root": evidence_root,
                    "repo_root": root / "gitless-source",
                    "artifact_repo_root": root,
                    "movement_review": None,
                    "runtime_identity": None,
                },
            )()
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(
                    runner,
                    "run_git",
                    return_value={"exit_code": 128, "stdout": "", "stderr": "not a git repository"},
                ),
            ):
                with self.assertRaisesRegex(ValueError, "candidate source commit"):
                    runner.prepare(args)
            self.assertFalse(evidence_root.exists())

    def test_movement_evidence_fields_survive_focused_package_subset(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_review = root / "retained" / "review"
            page_dir = source_review / "pages" / "page_008"
            page_dir.mkdir(parents=True)
            handoff = {
                "source_artifact_root": str((root / "artifacts").resolve()),
                "pages": [
                    {
                        "page_id": "page_008",
                        "page_number": 7,
                        "source_image": "pages/page_008/source.png",
                        "numbering_final": "pages/page_008/numbering.json",
                    }
                ],
            }
            (source_review / "manual_correction_input.json").write_text(
                json.dumps(handoff), encoding="utf-8"
            )
            (page_dir / "unused.json").write_text("{}", encoding="utf-8")
            evidence = {
                "schema_version": "issue333.movement_boundary_evidence.v1",
                "source_document": {"sha256": "a" * 64, "page_order": "ordered_pipeline_input"},
                "input_artifacts": {
                    "numbering_base": {
                        "path": "intermediate/numbering_base.json",
                        "sha256": "b" * 64,
                    }
                },
                "producer": {
                    "name": "fixture",
                    "version": "1",
                    "source_commit": "abc",
                    "parameters": {},
                },
                "candidates": [
                    {
                        "id": "page:6:system:5",
                        "page": 6,
                        "system": 5,
                        "state": "ambiguous_review_required",
                    }
                ],
            }
            evidence_path = source_review / "movement_boundary_evidence.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            destination = root / "prepared" / "movement"
            runner._copy_package(
                source_review,
                destination,
                root / "artifacts",
                movement_evidence=evidence_path,
                repo_root=Path(__file__).resolve().parents[1],
                movement_page_subset=6,
            )
            prepared_handoff = json.loads(
                (destination / "manual_correction_input.json").read_text(encoding="utf-8")
            )
            evidence_attached = (destination / "movement_boundary_evidence.json").is_file()
        self.assertEqual(
            prepared_handoff["movement_boundary_evidence"], "movement_boundary_evidence.json"
        )
        self.assertEqual(
            prepared_handoff["movement_boundary_resolved_output"],
            "corrections/movement_boundaries.json",
        )
        self.assertTrue(evidence_attached)

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
