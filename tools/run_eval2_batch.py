
import subprocess
from pathlib import Path
import sys

# Define inputs
IMG_DIR = Path("data/evaluation2/images")
CMD_SCRIPT = Path("tools/run_hybrid_pipeline.sh")

def get_images():
    # Recursive search for .png
    # Structure: IMG_DIR / <pdf_stem> / page_001.png
    return sorted(list(IMG_DIR.rglob("*.png")))

def run_pipeline(img_path: Path):
    stem = img_path.stem # page_001
    pdf_stem = img_path.parent.name # Shosrakovich...
    
    # Unique RUN_ID
    run_id = f"eval2_{pdf_stem}_{stem}"
    
    cmd = [
        str(CMD_SCRIPT),
        "--image", str(img_path),
        "--run-id", run_id
        # No GT
    ]
    
    print(f"\n========================================")
    print(f"Processing: {img_path}")
    print(f"Run ID: {run_id}")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running pipeline for {img_path}: {e}")
        # Continue to next
    except Exception as e:
        print(f"Unexpected error: {e}")

def main():
    images = get_images()
    print(f"Found {len(images)} images.")
    
    for img in images:
        run_pipeline(img)

if __name__ == "__main__":
    main()
