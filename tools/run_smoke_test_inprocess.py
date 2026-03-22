import logging
from pathlib import Path
from src.pipeline.main import run_pipeline

logging.basicConfig(level=logging.INFO)

PDFS = [
    ("data/evaluation2/pdfs/Va_Prokofiev_Symphony1.pdf", "Va_Prokofiev_Symphony1"),
    ("data/evaluation2/pdfs/Va__Prokofiev_Symphony5.pdf", "Va__Prokofiev_Symphony5"),
]

BASE_CONFIG = Path("configs/evaluation2_sr_x2.yaml")
RUN_ID = "smoke_test_inprocess"
OUTPUT_ROOT = Path("logs/test_runs/smoke_test")

def main():
    for pdf_path, score_name in PDFS:
        print(f"=== Processing {score_name} ===")
        import yaml
        with open(BASE_CONFIG, "r") as f:
            cfg = yaml.safe_load(f)
        
        cfg["inputs"]["pdf_path"] = str(pdf_path)
        cfg["inputs"]["pdf_to_images"]["pages"] = "1" # Only 1 page
        
        temp_config = Path(f"temp/config_{score_name}.yaml")
        temp_config.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_config, "w") as f:
            yaml.dump(cfg, f)
        
        run_pipeline(
            temp_config,
            run_id=f"{RUN_ID}/{score_name}",
            output_root=OUTPUT_ROOT,
            skip_existing=False
        )

if __name__ == "__main__":
    main()
