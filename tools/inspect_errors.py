import json

import cv2


def load_json(path):
    with open(path) as f:
        return json.load(f)


def get_measure_coords(numbering_data):
    # Map (s_idx, m_idx) -> bbox
    coords = {}
    idx_map = {}  # global_idx -> (s_idx, m_idx)
    g_idx = 0
    if "pages" in numbering_data:
        for s_idx, system in enumerate(numbering_data["pages"][0]["systems"]):
            for m_idx, measure in enumerate(system["measures"]):
                coords[(s_idx, m_idx)] = measure["bbox"]
                idx_map[g_idx] = (s_idx, m_idx)
                g_idx += 1
    return coords, idx_map


def draw_errors(work, page, gt_path, pred_path, numbering_path, img_path, out_path):
    print(f"Processing {work} {page}")
    gt = load_json(gt_path).get("overrides", [])
    pred = load_json(pred_path).get("measure_overrides", [])
    numb = load_json(numbering_path)

    img = cv2.imread(str(img_path))
    if img is None:
        print("Image not found")
        return

    coords, idx_map = get_measure_coords(numb)

    # Draw GT (Green)
    for item in gt:
        g_idx = item["measure_index"]
        count = item["rest_count"]
        if count < 2:
            continue

        if g_idx in idx_map:
            s_idx, m_idx = idx_map[g_idx]
            if (s_idx, m_idx) in coords:
                x1, y1, x2, y2 = coords[(s_idx, m_idx)]
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 3)
                cv2.putText(
                    img, f"GT:{count}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2
                )

    # Draw Pred (Red)
    for item in pred:
        s_idx = item["system"]
        m_idx = item["measure"]
        skip = item["skip"]
        count = skip + 1

        if (s_idx, m_idx) in coords:
            x1, y1, x2, y2 = coords[(s_idx, m_idx)]
            # offset slightly to avoid overlap
            cv2.rectangle(img, (x1 - 5, y1 - 5), (x2 + 5, y2 + 5), (0, 0, 255), 2)
            cv2.putText(
                img, f"Pred:{count}", (x1, y2 + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2
            )

    cv2.imwrite(str(out_path), img)
    print(f"Saved to {out_path}")


def main():
    # Page 004
    draw_errors(
        "prokofiev5",
        "page_004",
        "data/evaluation2/rest_gt/prokofiev5/page_004/rest_gt.json",
        "logs/experiments/batch_cnnv1/prokofiev5/page_004/overrides.json",
        "logs/experiments/batch_cnnv1/prokofiev5/page_004/numbering_initial.json",
        "data/evaluation2/images/prokofiev5/page_004.png",
        "error_vis_page004.jpg",
    )

    # Page 005
    draw_errors(
        "prokofiev5",
        "page_005",
        "data/evaluation2/rest_gt/prokofiev5/page_005/rest_gt.json",
        "logs/experiments/batch_cnnv1/prokofiev5/page_005/overrides.json",
        "logs/experiments/batch_cnnv1/prokofiev5/page_005/numbering_initial.json",
        "data/evaluation2/images/prokofiev5/page_005.png",
        "error_vis_page005.jpg",
    )


if __name__ == "__main__":
    main()
