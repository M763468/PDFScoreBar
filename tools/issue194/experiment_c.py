import json
import os
from pathlib import Path
import numpy as np
import cv2

PAGES_INFO = {
    "page_021": {
        "image": "logs/issue120_e2e_recovery/stage_e_full_pipeline/images/Shostakovich-Sym5-Va_page_013.png",
        "numbering": "logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/page_021/numbering_base.json"
    },
    "page_022": {
        "image": "logs/issue120_e2e_recovery/stage_e_full_pipeline/images/Shostakovich-Sym5-Va_page_014.png",
        "numbering": "logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/page_022/numbering_base.json"
    },
    "page_045": {
        "image": "logs/issue120_e2e_recovery/stage_e_full_pipeline/images/Va_Prokofiev_Symphony1_page_004.png",
        "numbering": "logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/page_045/numbering_base.json"
    }
}

def check_aligned_connection_sim(s1_bbox, s2_bbox, aligned_xs, bin_img):
    """
    Simulate the vertical connectivity check at aligned positions.
    """
    if not aligned_xs:
        return False, 0
        
    y1_bot = int(s1_bbox[3])
    y2_top = int(s2_bbox[1])
    gap_h = y2_top - y1_bot
    if gap_h <= 0:
        return True, 0
        
    h_img, w_img = bin_img.shape[:2]
    valid_connections = 0
    
    for cx in aligned_xs:
        # Inspection window X-range
        x1 = max(0, int(cx) - 4)
        x2 = min(w_img, int(cx) + 4)
        
        roi = bin_img[y1_bot:y2_top, x1:x2]
        if gap_h < 5:
            valid_connections += 1
            continue
            
        v_kernel_size = max(1, int(gap_h * 0.8))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_size))
        opened = cv2.morphologyEx(roi, cv2.MORPH_OPEN, kernel)
        
        if cv2.countNonZero(opened) > 0:
            valid_connections += 1
            
    return valid_connections >= 1, valid_connections

def analyze_page(page_id, info):
    print(f"\n================ Analyzing {page_id} ================")
    with open(info["numbering"], "r") as f:
        numbering = json.load(f)
    img = cv2.imread(info["image"], cv2.IMREAD_GRAYSCALE)
    if img is not None:
        _, bin_img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        bin_img = None
        
    page = numbering["pages"][0]
    
    # 全ての staves を平坦化して y1 順にソート（元々の system 境界を一旦無視してペアごとに解析）
    all_staves = []
    # numbering_base.json に登録されている staves を抽出
    for sys in page["systems"]:
        for staff in sys["staves"]:
            # bbox と、その staff の barlines を取得
            # numbering_base.json には measures があるが、barlines 自体は measures の境界から抽出
            # measures の左右境界 x 座標を barlines とする
            staff_bbox = staff["bbox"]
            barline_xs = []
            for m in sys.get("measures", []):
                # この staff の y 範囲と measure.bbox.y 範囲が重なっているかチェック
                my1, my2 = m["bbox"][1], m["bbox"][3]
                sy1, sy2 = staff_bbox[1], staff_bbox[3]
                if max(sy1, my1) < min(sy2, my2):
                    barline_xs.append(m["bbox"][0])
                    barline_xs.append(m["bbox"][2])
            barline_xs = sorted(list(set(barline_xs)))
            all_staves.append({
                "bbox": staff_bbox,
                "barline_xs": barline_xs
            })
            
    all_staves.sort(key=lambda s: s["bbox"][1])
    
    # 隣接するペアを走査
    for i in range(len(all_staves) - 1):
        s1 = all_staves[i]
        s2 = all_staves[i+1]
        
        s1_bbox = s1["bbox"]
        s2_bbox = s2["bbox"]
        
        gap = s2_bbox[1] - s1_bbox[3]
        h1 = s1_bbox[3] - s1_bbox[1]
        h2 = s2_bbox[3] - s2_bbox[1]
        avg_h = (h1 + h2) / 2
        ratio = gap / avg_h
        
        # アラインした小節線数をカウント
        aligned_xs = []
        ALIGN_TOL = 15
        for x1 in s1["barline_xs"]:
            for x2 in s2["barline_xs"]:
                if abs(x1 - x2) <= ALIGN_TOL:
                    aligned_xs.append((x1 + x2) / 2)
                    break
        aligned_xs = sorted(list(set(aligned_xs)))
        
        # 接続チェック
        connected = False
        valid_conn_count = 0
        if bin_img is not None:
            connected, valid_conn_count = check_aligned_connection_sim(s1_bbox, s2_bbox, aligned_xs, bin_img)
            
        print(f"Pair {i} -> {i+1}:")
        print(f"  Staff 1 bbox: {s1_bbox}")
        print(f"  Staff 2 bbox: {s2_bbox}")
        print(f"  Vertical Gap: {gap} px (Ratio to Avg Staff Height: {ratio:.2f})")
        print(f"  Aligned Barlines Count: {len(aligned_xs)} (positions: {[int(x) for x in aligned_xs]})")
        print(f"  Ink Connection Check: {'CONNECTED' if connected else 'DISCONNECTED'} ({valid_conn_count} valid connections)")
        print(f"  Left Edge Diff: {abs(s1_bbox[0] - s2_bbox[0])} px, Width Diff: {abs((s1_bbox[2]-s1_bbox[0]) - (s2_bbox[2]-s2_bbox[0]))} px")

def main():
    for page_id, info in PAGES_INFO.items():
        analyze_page(page_id, info)

if __name__ == "__main__":
    main()
