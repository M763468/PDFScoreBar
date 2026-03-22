"""Script to run the full eval2 set (all 5 PDFs) in a single process."""

import logging
from pathlib import Path
from src.pipeline.main import run_pipeline

logging.basicConfig(level=logging.INFO)

PDFS = [
    ("data/evaluation2/pdfs/Shostakovich-Festival_Overture_Va.pdf", "Shostakovich-Festival_Overture_Va"),
    ("data/evaluation2/pdfs/Shostakovich-Sym5-Va.pdf", "Shostakovich-Sym5-Va"),
    ("data/evaluation2/pdfs/Sibelius-Violin_Concerto-Viola.pdf", "Sibelius-Violin_Concerto-Viola"),
    ("data/evaluation2/pdfs/Va_Prokofiev_Symphony1.pdf", "Va_Prokofiev_Symphony1"),
    ("data/evaluation2/pdfs/Va__Prokofiev_Symphony5.pdf", "Va__Prokofiev_Symphony5"),
]

import argparse
import yaml

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="configs/evaluation2_sr_x2.yaml")
    parser.add_argument("--run_id", type=str, default="eval2_v9_no_heuristics")
    parser.add_argument("--output_root", type=str, default="logs/full_pipeline_runs/eval2_v9")
    parser.add_argument("--pdf", type=str, help="Specific PDF to process")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    
    for pdf_full_path, score_name in PDFS:
        if args.pdf and score_name != args.pdf:
            continue
            
        print(f"=== Processing {score_name} ===")
        with open(args.config, "r") as f:
            cfg = yaml.safe_load(f)
        
        cfg["inputs"]["pdf_path"] = pdf_full_path
        cfg["inputs"]["pdf_to_images"]["pages"] = None # All pages
        
        temp_config = Path(f"temp_v10/config_{score_name}.yaml")
        temp_config.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_config, "w") as f:
            yaml.dump(cfg, f)
        
        run_pipeline(
            temp_config,
            run_id=f"{args.run_id}/{score_name}",
            output_root=output_root,
            skip_existing=not args.overwrite
        )

if __name__ == "__main__":
    main()
