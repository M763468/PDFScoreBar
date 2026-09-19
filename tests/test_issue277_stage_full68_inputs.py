import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.issue277 import stage_full68_inputs as staging


class StageFull68InputsTest(unittest.TestCase):
    def _write_fixture(self, root: Path, old: Path, page_count: int = 2) -> tuple[Path, Path]:
        (old / "logs/matrix").mkdir(parents=True)
        (old / "logs/support").mkdir(parents=True)
        (old / "logs/masks").mkdir(parents=True)
        (old / "data/evaluation2/images/ScoreA").mkdir(parents=True)
        (root / "logs").symlink_to(old / "logs", target_is_directory=True)
        (root / "data").symlink_to(old / "data", target_is_directory=True)

        pages = []
        for index in range(1, page_count + 1):
            name = f"page_{index:03d}"
            (old / f"data/evaluation2/images/ScoreA/{name}.png").write_bytes(
                f"image-{index}".encode()
            )
            for suffix in ("staff", "symbols", "brace", "homr"):
                (old / f"logs/masks/{name}_{suffix}.png").write_bytes(
                    f"{suffix}-{index}".encode()
                )
            support = old / f"logs/support/{name}.json"
            support.write_text(
                json.dumps(
                    {
                        "connector_symbols": f"/workspace/logs/masks/{name}_symbols.png",
                        "connector_brace_dot": f"/workspace/logs/masks/{name}_brace.png",
                        "current_homr_staff_mask": f"/workspace/logs/masks/{name}_homr.png",
                        "semantic_marker": index,
                    }
                ),
                encoding="utf-8",
            )
            pages.append(
                {
                    "image": f"/workspace/data/evaluation2/images/ScoreA/{name}.png",
                    "fixed_inputs": {
                        "support_result": f"/workspace/logs/support/{name}.json"
                    },
                    "modes": {
                        "candidate_native_geometry": {
                            "variants": {
                                "B_b377": {
                                    "staff_mask": f"/workspace/logs/masks/{name}_staff.png",
                                    "final_barlines": [],
                                }
                            }
                        }
                    },
                }
            )

        matrix = old / "logs/matrix/chunk.json"
        matrix.write_text(
            json.dumps({"pages": pages, "semantic_marker": "unchanged"}),
            encoding="utf-8",
        )
        manifest = root / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "completed_chunks": [
                        {"matrix_report": "/workspace/logs/matrix/chunk.json", "chunk": 1}
                    ],
                    "semantic_marker": "unchanged",
                }
            ),
            encoding="utf-8",
        )
        accepted = root / "accepted.json"
        accepted.write_text(
            json.dumps({"status": "passed", "canonical": True}),
            encoding="utf-8",
        )
        return manifest, accepted

    def test_full68_contract_constant(self):
        self.assertEqual(staging.EXPECTED_PAGE_COUNT, 68)

    def test_stage_materializes_symlinks_and_rewrites_paths_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old = tmp_path / "old_worktree"
            root = tmp_path / "issue294"
            output = tmp_path / "staged"
            root.mkdir()
            manifest, accepted = self._write_fixture(root, old)

            with patch.object(staging, "EXPECTED_PAGE_COUNT", 2):
                provenance_path = staging.stage(root, manifest, accepted, output)

            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            self.assertEqual(provenance["page_count"], 2)
            self.assertTrue(provenance["validation"]["all_exact_copies_sha_match"])
            self.assertTrue(
                provenance["validation"]["all_derived_json_non_path_semantics_equal"]
            )
            self.assertTrue(provenance["validation"]["read_only_mount_ready"])
            self.assertFalse(any(path.is_symlink() for path in output.rglob("*")))
            symlink_parent_rows = [
                row for row in provenance["files"]
                if "/issue294/logs/" in row["source_lookup_path"]
            ]
            self.assertTrue(symlink_parent_rows)
            self.assertTrue(
                all("/old_worktree/logs/" in row["resolved_source"] for row in symlink_parent_rows)
            )

            runtime_manifest = json.loads(
                (output / "runtime/manifest.json").read_text(encoding="utf-8")
            )
            matrix_path = output / runtime_manifest["completed_chunks"][0]["matrix_report"]
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            self.assertEqual(matrix["semantic_marker"], "unchanged")
            self.assertEqual(len(matrix["pages"]), 2)
            for page in matrix["pages"]:
                image = output / page["image"]
                support_path = output / page["fixed_inputs"]["support_result"]
                staff_mask = output / page["modes"]["candidate_native_geometry"]["variants"][
                    "B_b377"
                ]["staff_mask"]
                self.assertTrue(image.is_file())
                self.assertTrue(staff_mask.is_file())
                support = json.loads(support_path.read_text(encoding="utf-8"))
                for key in (
                    "connector_symbols",
                    "connector_brace_dot",
                    "current_homr_staff_mask",
                ):
                    self.assertTrue((output / support[key]).is_file())


if __name__ == "__main__":
    unittest.main()
