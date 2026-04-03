import json
from pathlib import Path


def load_json(p):
    with open(p, "r") as f:
        return json.load(f)


def main():
    det_file = Path(
        "logs/hybrid_generalization/repro_shostakovich_100/20260324_153852/sr/batch/page_001/page_001_detections.json"
    )
    data = load_json(det_file)
    preds = [tuple(p["orig_bbox"]) for p in data["predictions"]]

    fns = [(1211, 1830, 1215, 1943), (2607, 2279, 2611, 2395)]

    for fn in fns:
        print(f"\nLooking for preds near FN: {fn}")
        fx = (fn[0] + fn[2]) / 2.0
        fy = (fn[1] + fn[3]) / 2.0
        for p in preds:
            px = (p[0] + p[2]) / 2.0
            py = (p[1] + p[3]) / 2.0
            if abs(px - fx) < 100 and abs(py - fy) < 200:
                print(f"  Pred: {p}, dist_x={abs(px - fx):.1f}, dist_y={abs(py - fy):.1f}")


if __name__ == "__main__":
    main()
