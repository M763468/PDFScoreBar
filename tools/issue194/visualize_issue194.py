import json
from pathlib import Path

import cv2

PAGES_INFO = {
    "page_021": {
        "image": "logs/issue120_e2e_recovery/stage_e_full_pipeline/images/Shostakovich-Sym5-Va_page_013.png",
        "numbering": "logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/page_021/numbering_base.json",
        "candidates": "logs/issue120_e2e_recovery/stage_e_full_pipeline/dense_candidate_reconstruction/probe_candidates_filtered/Shostakovich-Sym5-Va/page_013/pipeline2_no_peak_candidates.json",
    },
    "page_045": {
        "image": "logs/issue120_e2e_recovery/stage_e_full_pipeline/images/Va_Prokofiev_Symphony1_page_004.png",
        "numbering": "logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/page_045/numbering_base.json",
        "candidates": "logs/issue120_e2e_recovery/stage_e_full_pipeline/dense_candidate_reconstruction/probe_candidates_filtered/Va_Prokofiev_Symphony1/page_004/pipeline2_no_peak_candidates.json",
    },
    "page_053": {
        "image": "logs/issue120_e2e_recovery/stage_e_full_pipeline/images/Va__Prokofiev_Symphony5_page_007.png",
        "numbering": "logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/page_053/numbering_base.json",
        "candidates": "logs/issue120_e2e_recovery/stage_e_full_pipeline/dense_candidate_reconstruction/probe_candidates_filtered/Va__Prokofiev_Symphony5/page_007/pipeline2_no_peak_candidates.json",
    },
    "page_060": {
        "image": "logs/issue120_e2e_recovery/stage_e_full_pipeline/images/Va__Prokofiev_Symphony5_page_015.png",
        "numbering": "logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/page_060/numbering_base.json",
        "candidates": "logs/issue120_e2e_recovery/stage_e_full_pipeline/dense_candidate_reconstruction/probe_candidates_filtered/Va__Prokofiev_Symphony5/page_015/pipeline2_no_peak_candidates.json",
    },
    "page_022": {
        "image": "logs/issue120_e2e_recovery/stage_e_full_pipeline/images/Shostakovich-Sym5-Va_page_014.png",
        "numbering": "logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/page_022/numbering_base.json",
        "candidates": "logs/issue120_e2e_recovery/stage_e_full_pipeline/dense_candidate_reconstruction/probe_candidates_filtered/Shostakovich-Sym5-Va/page_014/pipeline2_no_peak_candidates.json",
    },
}

OUTPUT_DIR = Path("logs/issue194_measure_interval_construction")


def draw_boxes(image, boxes, color, thickness=3, label_func=None):
    img_copy = image.copy()
    for i, box in enumerate(boxes):
        x1, y1, x2, y2 = box
        cv2.rectangle(img_copy, (x1, y1), (x2, y2), color, thickness)
        if label_func:
            label = label_func(i, box)
            cv2.putText(img_copy, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2, cv2.LINE_AA)
    return img_copy


def main():
    for page_id, info in PAGES_INFO.items():
        print(f"Processing {page_id}...")
        image_path = Path(info["image"])
        numbering_path = Path(info["numbering"])
        candidates_path = Path(info["candidates"])
        if not image_path.exists():
            print(f"Warning: image file not found: {image_path}")
            continue
        if not numbering_path.exists():
            print(f"Warning: numbering file not found: {numbering_path}")
            continue

        img = cv2.imread(str(image_path))
        if img is None:
            print(f"Warning: could not read image: {image_path}")
            continue

        with open(numbering_path, "r") as f:
            numbering_data = json.load(f)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        page_data = numbering_data["pages"][0]
        systems = page_data["systems"]

        staff_boxes = []
        for system in systems:
            for staff in system["staves"]:
                staff_boxes.append(staff["bbox"])
        img_staff = draw_boxes(img, staff_boxes, (255, 0, 0), thickness=3)
        cv2.imwrite(str(OUTPUT_DIR / f"staff_bbox_{page_id}.png"), img_staff)

        system_boxes = []
        for system in systems:
            x1_min, y1_min = float("inf"), float("inf")
            x2_max, y2_max = float("-inf"), float("-inf")

            for staff in system["staves"]:
                sx1, sy1, sx2, sy2 = staff["bbox"]
                x1_min = min(x1_min, sx1)
                y1_min = min(y1_min, sy1)
                x2_max = max(x2_max, sx2)
                y2_max = max(y2_max, sy2)

            for measure in system.get("measures", []):
                mx1, my1, mx2, my2 = measure["bbox"]
                x1_min = min(x1_min, mx1)
                y1_min = min(y1_min, my1)
                x2_max = max(x2_max, mx2)
                y2_max = max(y2_max, my2)

            if x1_min != float("inf"):
                system_boxes.append([int(x1_min), int(y1_min), int(x2_max), int(y2_max)])

        img_system = draw_boxes(img, system_boxes, (0, 255, 255), thickness=4, label_func=lambda idx, box: f"Sys {idx}")
        cv2.imwrite(str(OUTPUT_DIR / f"system_bbox_{page_id}.png"), img_system)

        measure_boxes = []
        measure_numbers = []
        for system in systems:
            for measure in system.get("measures", []):
                measure_boxes.append(measure["bbox"])
                measure_numbers.append(measure["number"])

        img_measure = draw_boxes(
            img,
            measure_boxes,
            (0, 0, 255),
            thickness=3,
            label_func=lambda idx, box: f"M {measure_numbers[idx]}",
        )
        cv2.imwrite(str(OUTPUT_DIR / f"measure_bbox_{page_id}.png"), img_measure)

        if candidates_path.exists():
            with open(candidates_path, "r") as f:
                candidates = json.load(f)
            img_candidates = draw_boxes(img, candidates, (0, 255, 0), thickness=2)
            cv2.imwrite(str(OUTPUT_DIR / f"barline_candidates_{page_id}.png"), img_candidates)
        else:
            print(f"Warning: candidates file not found: {candidates_path}")


if __name__ == "__main__":
    main()
