import json
import logging
from pathlib import Path
import torch

from src.measure_numbering.rapidocr_provider import normalize_rapidocr_provider
from src.pipeline.steps.numbering import run_mmr_batch
from tools.issue94.eval_mmr_overrides import _load_json, _write_json, _build_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("eval_all_mmr")


def main():
    model_path = Path("tools/mmr_training/models/mmr_classifier_best.pth")
    page_inputs_path = Path("logs/issue94_mmr_current_state/page_inputs.json")
    output_root = Path("logs/issue94_mmr_current_state/eval")

    with open(page_inputs_path, "r", encoding="utf-8") as f:
        inputs = json.load(f)

    pages = inputs["pages"]
    logger.info(f"Loaded {len(pages)} pages to evaluate.")

    # 実行パラメータ
    device = "cuda" if torch.cuda.is_available() else "cpu"
    rapidocr_provider = "cuda" if device == "cuda" else "cpu"
    threshold = 0.5
    rescue_threshold = 0.1
    enable_rotation_tta = False

    # バッチ処理用リストの作成
    pages_data = []
    image_paths = []
    output_paths = []

    for p in pages:
        page_id = p["page_id"]
        nb_path = Path(p["numbering_base"])
        img_path = Path(p["image"])
        out_dir = output_root / page_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "mmr_overrides.json"

        pages_data.append(_load_json(nb_path))
        image_paths.append(img_path)
        output_paths.append(out_path)

    logger.info(f"Running run_mmr_batch on {device} with rapidocr_provider={rapidocr_provider}...")
    run_mmr_batch(
        pages_data=pages_data,
        image_paths=image_paths,
        output_paths=output_paths,
        model_path=model_path,
        device=torch.device(device),
        enable_rotation_tta=enable_rotation_tta,
        threshold=threshold,
        rescue_threshold=rescue_threshold,
        debug_root=None,  # デバッグ画像出力は不要
        rapidocr_provider=normalize_rapidocr_provider(rapidocr_provider),
    )
    logger.info("run_mmr_batch completed. Generating summaries...")
    
    total_base_measures = 0
    total_detected = 0
    total_expected = 0
    total_matched = 0
    total_missed = 0
    total_skip_mismatch = 0
    total_unexpected = 0
    
    page_summaries = []
    
    # 各ページの要約を生成
    for p, nb_payload, out_path in zip(pages, pages_data, output_paths):
        page_id = p["page_id"]
        detected_payload = _load_json(out_path)
        
        # Load expected overrides if exists
        expected_path = Path("tests/fixtures") / f"expected_overrides_{page_id}.json"
        expected_payload = _load_json(expected_path) if expected_path.exists() else None
        
        summary = _build_summary(
            numbering_json=Path(p["numbering_base"]),
            image=Path(p["image"]),
            model_path=model_path,
            rapidocr_provider=rapidocr_provider,
            threshold=threshold,
            rescue_threshold=rescue_threshold,
            enable_rotation_tta=enable_rotation_tta,
            numbering_payload=nb_payload,
            detected_payload=detected_payload,
            expected_payload=expected_payload,
        )
        
        # Aggregate counts
        cnt = summary["counts"]
        total_base_measures += cnt["base_measures"]
        total_detected += cnt["detected_overrides"]
        total_expected += cnt["expected_overrides"]
        total_matched += cnt["matched"]
        total_missed += cnt["missed"]
        total_skip_mismatch += cnt["skip_mismatch"]
        total_unexpected += cnt["unexpected"]
        
        page_summaries.append({
            "page_id": page_id,
            "image": Path(p["image"]).name,
            "expected": cnt["expected_overrides"],
            "detected": cnt["detected_overrides"],
            "matched": cnt["matched"],
            "missed": cnt["missed"],
            "mismatch": cnt["skip_mismatch"],
            "unexpected": cnt["unexpected"]
        })
        
        summary_path = output_root / page_id / "mmr_eval_summary.json"
        _write_json(summary_path, summary)
        
    # Print quantitative summary metrics
    print("\n" + "="*50)
    print(" MMR EVALUATION METRICS SUMMARY (REST GT)")
    print("="*50)
    print(f"Total Pages:         {len(pages)}")
    print(f"Total Base Measures: {total_base_measures}")
    print(f"Total Expected:      {total_expected} (Positive MMRs in GT)")
    print(f"Total Detected:      {total_detected}")
    print(f"Matched (TP):        {total_matched}")
    print(f"Missed (FN):         {total_missed}")
    print(f"Skip Mismatch:       {total_skip_mismatch}")
    print(f"Unexpected (FP):     {total_unexpected}")
    
    # Calculate Precision / Recall
    # Precision = TP / (TP + FP) = Matched / Detected
    # Recall = TP / Expected = Matched / Expected
    precision = total_matched / total_detected if total_detected > 0 else 0
    recall = total_matched / total_expected if total_expected > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    print("-"*50)
    print(f"Precision:           {precision:.4f}")
    print(f"Recall:              {recall:.4f}")
    print(f"F1-Score:            {f1:.4f}")
    print("="*50)
    
    # Write aggregated summary to logs
    aggregated_report = {
        "summary": {
            "total_pages": len(pages),
            "total_base_measures": total_base_measures,
            "total_expected": total_expected,
            "total_detected": total_detected,
            "matched_tp": total_matched,
            "missed_fn": total_missed,
            "skip_mismatch": total_skip_mismatch,
            "unexpected_fp": total_unexpected,
            "precision": precision,
            "recall": recall,
            "f1_score": f1
        },
        "pages": page_summaries
    }
    _write_json(output_root / "aggregated_eval_summary.json", aggregated_report)
    logger.info("All evaluations completed. Aggregated summary saved.")
    
if __name__ == "__main__":
    main()
