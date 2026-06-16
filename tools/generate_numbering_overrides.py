import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

import torch

from src.measure_numbering.mmr import MMRProcessor

logger = logging.getLogger(__name__)


def _resolve_model_path(explicit_model_path: Path | None) -> Path:
    if explicit_model_path is not None:
        if explicit_model_path.exists():
            return explicit_model_path
        logger.error(f"Error: Model not found: {explicit_model_path}")
        sys.exit(1)

    search_paths = [
        Path("tools/mmr_training/models/mmr_classifier_best.pth"),
        Path("mmr_classifier_best.pth"),
        Path(__file__).parent / "mmr_training/models/mmr_classifier_best.pth",
        Path(
            "/home/masaki_muramatsu/ws_PDFScoreBar_model_exp/tools/mmr_training/models/mmr_classifier_best.pth"
        ),
    ]
    for model_path in search_paths:
        if model_path.exists():
            return model_path

    logger.error(f"Error: Model not found. Searched: {search_paths}")
    sys.exit(1)


def _copy_debug_image(debug_root: Path, output_debug_image: Path, data: dict) -> None:
    page_number = data.get("pages", [{}])[0].get("page_number", 1)
    generated_debug = debug_root / f"page_{page_number:03d}_mmr_debug.png"
    if generated_debug.exists():
        output_debug_image.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(generated_debug, output_debug_image)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--numbering-json", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-overrides", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, default=None)

    # Legacy arguments accepted for compatibility with older pipeline wrappers.
    parser.add_argument("--notehead-mask", type=Path, help="Legacy ignored")
    parser.add_argument("--staff-mask", type=Path, help="Legacy ignored")
    parser.add_argument("--vertical-margin-check", type=int, default=10, help="Legacy ignored")
    parser.add_argument("--vertical-margin-ocr", type=int, default=80, help="Legacy ignored")
    parser.add_argument("--erode-iter", type=int, default=1, help="Legacy ignored")
    parser.add_argument("--debug-image", type=Path, default=None)

    parser.add_argument("--threshold", type=float, default=0.5, help="High Confidence Threshold")
    parser.add_argument(
        "--rescue-threshold", type=float, default=0.1, help="Low Confidence Rescue Threshold"
    )
    parser.add_argument(
        "--enable-rotation-tta",
        action="store_true",
        help="Enable OCR retry with +/-2 deg rotations",
    )

    args = parser.parse_args()

    threshold = args.threshold
    if threshold > 1.0:
        logger.warning(f"Legacy threshold {threshold} detected. Using default 0.5 for CNN.")
        threshold = 0.5

    model_path = _resolve_model_path(args.model_path)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Using device: {device}")

    with open(args.numbering_json, "r") as f:
        data = json.load(f)

    debug_root = None
    if args.debug_image:
        debug_root = args.debug_image.parent / f"{args.debug_image.stem}_debug_root"
        debug_root.mkdir(parents=True, exist_ok=True)

    processor = MMRProcessor(
        model_path=model_path,
        device=device,
        enable_rotation_tta=args.enable_rotation_tta,
        threshold=threshold,
        rescue_threshold=args.rescue_threshold,
    )
    page_results = processor.process_pages([data], [args.image], debug_root=debug_root)
    output = page_results[0] if page_results else {"measure_overrides": []}

    args.output_overrides.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_overrides, "w") as f:
        json.dump(output, f, indent=2)

    if debug_root is not None and args.debug_image is not None:
        _copy_debug_image(debug_root, args.debug_image, data)


if __name__ == "__main__":
    main()
