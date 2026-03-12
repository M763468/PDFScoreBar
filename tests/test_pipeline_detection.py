import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.pipeline.detection import run_detection_step
from src.pipeline.detection_hybrid import HybridDetector


class TestPipelineDetection(unittest.TestCase):
    def _base_config(self):
        return {
            "inputs": {"pdf_to_images": {"output_dir": "data/evaluation/images"}},
            "detection": {
                "cnn_model_path": "experiments/cnn_classifier/checkpoints/best_model.pth",
                "ink_threshold": 230,
                "min_ratio": 0.7,
                "min_height_ratio": 0.012,
                "cnn_threshold": 0.1,
            },
        }

    def test_run_detection_step_uses_orchestrator(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hybrid_output_dir = Path(tmpdir) / "hybrid"
            hybrid_output_dir.mkdir(parents=True, exist_ok=True)

            config = self._base_config()
            images = [Path("data/evaluation/images/page_001.png")]
            page_ids = ["page_001"]

            with (
                patch.object(
                    HybridDetector,
                    "run",
                    return_value={"commands": [["hybrid"]], "hybrid_output_dir": hybrid_output_dir},
                ),
                patch("src.pipeline.detection.ensure_dir"),
                patch("src.pipeline.detection.run_probe_scan_batch") as mock_probe,
                patch("src.pipeline.detection.run_cnn_scoring_batch") as mock_cnn,
            ):
                result = run_detection_step(
                    config=config,
                    images=images,
                    page_ids=page_ids,
                    run_id="run123",
                    run_dir=Path(tmpdir),
                    dry_run=False,
                )

            self.assertIn("commands", result)
            self.assertEqual(result["hybrid_output_dir"], hybrid_output_dir)
            self.assertTrue(str(result["probe_output_dir"]).endswith("intermediate/probe_scan"))

            mock_probe.assert_called_once()
            mock_cnn.assert_called_once()

            commands = result["commands"]
            self.assertEqual(commands[0], ["hybrid"])
            self.assertIn("inprocess:probe_scan", commands[1][0])
            self.assertIn("inprocess:cnn_scoring", commands[2][0])

    def test_run_detection_step_skips_probe_and_cnn_on_dry_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hybrid_output_dir = Path(tmpdir) / "hybrid"
            hybrid_output_dir.mkdir(parents=True, exist_ok=True)

            config = self._base_config()
            images = [Path("data/evaluation/images/page_001.png")]
            page_ids = ["page_001"]

            with (
                patch.object(
                    HybridDetector,
                    "run",
                    return_value={"commands": [["hybrid"]], "hybrid_output_dir": hybrid_output_dir},
                ),
                patch("src.pipeline.detection.ensure_dir"),
                patch("src.pipeline.detection.run_probe_scan_batch") as mock_probe,
                patch("src.pipeline.detection.run_cnn_scoring_batch") as mock_cnn,
            ):
                result = run_detection_step(
                    config=config,
                    images=images,
                    page_ids=page_ids,
                    run_id="run123",
                    run_dir=Path(tmpdir),
                    dry_run=True,
                )

            mock_probe.assert_not_called()
            mock_cnn.assert_not_called()
            self.assertEqual(result["commands"][0], ["hybrid"])
            self.assertIn("inprocess:probe_scan", result["commands"][1][0])
            self.assertIn("inprocess:cnn_scoring", result["commands"][2][0])

    def test_probe_score_name_is_forwarded_to_probe_and_cnn(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hybrid_output_dir = Path(tmpdir) / "hybrid"
            hybrid_output_dir.mkdir(parents=True, exist_ok=True)

            config = self._base_config()
            config["detection"]["probe_score_name"] = "FixedScore"
            images = [Path("data/evaluation/images/page_001.png")]
            page_ids = ["page_001"]

            with (
                patch.object(
                    HybridDetector,
                    "run",
                    return_value={"commands": [["hybrid"]], "hybrid_output_dir": hybrid_output_dir},
                ),
                patch("src.pipeline.detection.ensure_dir"),
                patch("src.pipeline.detection.run_probe_scan_batch") as mock_probe,
                patch("src.pipeline.detection.run_cnn_scoring_batch") as mock_cnn,
            ):
                run_detection_step(
                    config=config,
                    images=images,
                    page_ids=page_ids,
                    run_id="run123",
                    run_dir=Path(tmpdir),
                    dry_run=False,
                )

            self.assertEqual(mock_probe.call_args.kwargs["score_name"], "FixedScore")
            self.assertEqual(mock_cnn.call_args.kwargs["score_name"], "FixedScore")


if __name__ == "__main__":
    unittest.main()
