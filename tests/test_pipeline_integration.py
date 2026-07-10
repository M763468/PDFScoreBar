import pytest

pytest.importorskip("homr")
fitz = pytest.importorskip("fitz")
if not hasattr(fitz, "open"):
    pytest.skip(
        "Pipeline integration requires the real PyMuPDF fitz module", allow_module_level=True
    )

import shutil
import unittest
from pathlib import Path

from src.pipeline.core.config import load_yaml, write_yaml
from src.pipeline.main import run_pipeline
from src.pipeline.utils.io import load_json

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestPipelineIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_run_id = "integration_test_run"
        cls.output_root = PROJECT_ROOT / "logs" / "test_runs"
        cls.run_dir = cls.output_root / cls.test_run_id

        # Clean up only once at the very beginning
        if cls.run_dir.exists():
            shutil.rmtree(cls.run_dir)

        cls.base_config_path = PROJECT_ROOT / "configs" / "evaluation2_e2e_subset.yaml"
        cls.test_config_path = PROJECT_ROOT / "configs" / "tmp_integration_test.yaml"

        config = load_yaml(cls.base_config_path)
        config["run"]["run_id"] = cls.test_run_id
        config["run"]["output_root"] = str(cls.output_root)
        config["inputs"]["pdf_to_images"]["pages"] = "1"

        # Dummy values that will be overridden by detection step
        config["inputs"]["barlines_root"] = "dummy"
        config["inputs"]["barlines_pattern"] = "{page_id}_barlines.json"
        config["inputs"]["staff_mask_pattern"] = "{page_id}_staff.png"
        config["detection"] = config.get("detection", {})
        config["detection"]["probe_skip_existing"] = True

        write_yaml(cls.test_config_path, config)

    def test_full_sequence(self):
        # Step 1: PDF to Images
        print("\n--- Testing PDF to Images ---")
        config = load_yaml(self.test_config_path)
        for step in config["steps"]:
            config["steps"][step] = False
        config["steps"]["pdf_to_images"] = True
        write_yaml(self.test_config_path, config)
        run_pipeline(self.test_config_path)

        img_dir = self.run_dir / "inputs" / "images"
        self.assertTrue((img_dir / "page_001.png").exists())

        # Step 2: Detection
        print("\n--- Testing Detection ---")
        config["steps"]["pdf_to_images"] = False
        config["steps"]["detection"] = True
        write_yaml(self.test_config_path, config)
        run_pipeline(self.test_config_path)

        manifest_path = self.run_dir / "manifest.json"
        self.assertTrue(manifest_path.exists())
        manifest = load_json(manifest_path)
        self.assertGreater(len(manifest["pages"]), 0)

        # Update config with resolved paths for subsequent steps that don't run detection
        manifest["pages"][0]
        # We can't easily update barlines_root/pattern for dynamic paths,
        # but we can disable detection and the pipeline will use these if we set them.
        # Actually, if we want to run numbering_base WITHOUT detection,
        # we need to point to the files created by detection.

        # Step 3: Numbering Base
        print("\n--- Testing Numbering Base ---")
        # To run numbering_base without re-running detection, we MUST provide the paths.
        config["steps"]["detection"] = False
        config["steps"]["numbering_base"] = True
        # Since detection is False, it will use barlines_root/pattern.
        # Let's point them to the absolute paths found in manifest.
        # This is a bit tricky with patterns.
        # Alternatively, we can just KEEP detection=True but it would re-run.
        # The goal of "individual execution" is to be able to run them separately.

        # For this test, I'll just keep them enabled as they accumulate.
        config["steps"]["pdf_to_images"] = False
        config["steps"]["detection"] = True  # Keep it so it resolves paths
        config["steps"]["numbering_base"] = True
        write_yaml(self.test_config_path, config)
        run_pipeline(self.test_config_path)

        base_json = self.run_dir / "intermediate" / "page_001" / "numbering_base.json"
        self.assertTrue(base_json.exists())

        # Step 4: MMR and Final
        print("\n--- Testing MMR and Final ---")
        config["steps"]["mmr_overrides"] = True
        config["steps"]["apply_measure_overrides"] = True
        config["steps"]["overlay"] = True
        write_yaml(self.test_config_path, config)
        run_pipeline(self.test_config_path)

        final_json = self.run_dir / "outputs" / "page_001" / "numbering_final.json"
        self.assertTrue(final_json.exists())
        overlay_png = self.run_dir / "outputs" / "page_001" / "numbering_overlay.png"
        self.assertTrue(overlay_png.exists())

        print("\nFull pipeline sequence successful.")


if __name__ == "__main__":
    unittest.main()
