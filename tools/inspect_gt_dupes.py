import sys
from pathlib import Path

# Add project roots
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from homr_eval_scripts.homr_evaluator import load_ground_truth_boxes
from src.common.barline_evaluation import center_distance_x


def main():
    gt_path = (
        PROJECT_ROOT
        / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/boxes_sorted.json"
    )
    gt_boxes = load_ground_truth_boxes(gt_path)

    pairs = [(38, 39), (40, 41)]
    for i, j in pairs:
        dist = center_distance_x(gt_boxes[i], gt_boxes[j])
        print(f"GT {i} vs GT {j}: dist={dist:.2f}")
        print(f"  GT {i}: {gt_boxes[i]}")
        print(f"  GT {j}: {gt_boxes[j]}")


if __name__ == "__main__":
    main()
