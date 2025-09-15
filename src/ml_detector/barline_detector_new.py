import os
import cv2
import numpy as np
from PIL import Image
import pickle

from oemer.inference import inference, resize_image
from oemer.barline_extraction import get_barline_box, get_barline_map
from oemer.bbox import find_lines, draw_bounding_boxes, get_center, get_bbox
from oemer import layers
from oemer.staffline_extraction import extract as staff_extract
from oemer.utils import get_unit_size
from oemer.general_filtering_rules import filter_out_of_range_bbox

def get_degree(line):
    return np.rad2deg(np.arctan2(line[3] - line[1], line[2] - line[0]))

def check_overlap(box1, box2):
    # box = (x1, y1, x2, y2)
    return not (box1[2] < box2[0] or box1[0] > box2[2] or box1[3] < box2[1] or box1[1] > box2[3])

def filter_lines_extended(lines, notehead_bboxes, min_degree=75, extension_ratio=0.5, max_width_ratio=0.4, min_height_ratio=3.5):
    staffs = layers.get_layer('staffs')

    lines = filter_out_of_range_bbox(lines)
    min_y = min([st.y_upper for st in staffs.reshape(-1, 1).squeeze()])
    max_y = max([st.y_lower for st in staffs.reshape(-1, 1).squeeze()])

    cands = []
    for line in lines:
        degree = get_degree(line)
        if degree < min_degree:
            continue

        if line[1] < min_y or line[3] > max_y:
            continue

        center_x, center_y = get_center(line)
        unit_size = get_unit_size(center_x, center_y)

        # Width check
        width = line[2] - line[0]
        if width > unit_size * max_width_ratio:
            continue

        # Height check
        height = line[3] - line[1]
        if height < unit_size * min_height_ratio:
            continue

        # Extend the line vertically
        extension = int(unit_size * extension_ratio)
        extended_line = (line[0], line[1] - extension, line[2], line[3] + extension)

        # Check for overlap with noteheads
        is_stem = False
        for notehead_box in notehead_bboxes:
            if check_overlap(extended_line, notehead_box):
                is_stem = True
                break
        if is_stem:
            continue

        cands.append(line)
    return cands



def detect_barlines_ml(img_path: str, unet_model_path: str, segnet_model_path: str, output_dir: str):
    group_map = None # Initialize group_map
    """
    Detects barlines in a sheet music image using a two-model approach inspired by oemer.
    1. unet_big: Separates stafflines and a broad 'symbols' category.
    2. seg_net: Separates symbols into finer categories (stems/rests, noteheads, clefs/keys).
    """
    # --- Step 1: Inference with unet_big to get stafflines and coarse symbols ---
    print("Running inference with unet_big model...")
    unet_map, _ = inference(unet_model_path, img_path)
    staff_pred = np.where(unet_map == 1, 1, 0).astype(np.uint8)
    symbols_coarse = np.where(unet_map == 2, 1, 0).astype(np.uint8)

    # --- Step 2: Inference with seg_net to get detailed symbol categories ---
    print("Running inference with seg_net model...")
    seg_map, _ = inference(segnet_model_path, img_path)
    stems_rests_pred = np.where(seg_map == 1, 1, 0).astype(np.uint8)
    notehead_pred = np.where(seg_map == 2, 1, 0).astype(np.uint8)
    clefs_keys_pred = np.where(seg_map == 3, 1, 0).astype(np.uint8)

    # Get notehead bounding boxes
    notehead_bboxes = get_bbox(notehead_pred)

    # --- Step 3: Dilate symbol masks to remove more noise ---
    kernel = np.ones((5,5), np.uint8)
    stems_rests_pred_dilated = cv2.dilate(stems_rests_pred, kernel, iterations = 1)
    notehead_pred_dilated = cv2.dilate(notehead_pred, kernel, iterations = 1)
    clefs_keys_pred_dilated = cv2.dilate(clefs_keys_pred, kernel, iterations = 1)

    # --- Step 4: Combine predictions and register layers ---
    symbols_pred = symbols_coarse + clefs_keys_pred + stems_rests_pred
    symbols_pred[symbols_pred > 1] = 1

    layers.register_layer("staff_pred", staff_pred)
    layers.register_layer("symbols_pred", symbols_pred)
    layers.register_layer("stems_rests_pred", stems_rests_pred_dilated)
    layers.register_layer("notehead_pred", notehead_pred_dilated)
    layers.register_layer("clefs_keys_pred", clefs_keys_pred_dilated)

    # --- Step 5: Run staffline extraction ---
    print("Extracting staff objects...")
    staff_objects, zones = staff_extract(line_threshold=0.8)
    print(f"DEBUG: Type of staff_objects: {type(staff_objects)}")
    if isinstance(staff_objects, np.ndarray):
        print(f"DEBUG: Shape of staff_objects: {staff_objects.shape}")
    layers.register_layer("staffs", staff_objects)
    layers.register_layer("zones", zones)

    # --- Step 6: Barline detection logic ---
    print("Detecting barlines...")
    mix = symbols_pred - stems_rests_pred_dilated - notehead_pred_dilated - clefs_keys_pred_dilated
    mix[mix < 0] = 0

    # staff_line_heightを取得
    staff_line_height = 0
    if staff_objects.size > 0:
        staff_line_height = np.mean([st.y_lower - st.y_upper for st in staff_objects.flatten()])
    if staff_line_height == 0:
        staff_line_height = unet_map.shape[0] / 20

    # Find vertical lines in the 'mix' image
    lines = find_lines(mix)
    filtered_lines = filter_lines_extended(lines, notehead_bboxes)

    # バーラインマップを生成し、バーラインを抽出
    barline_map = get_barline_map(symbols_pred, filtered_lines)
    print(f"DEBUG: Type of barline_map after get_barline_map: {type(barline_map)}")
    if isinstance(barline_map, np.ndarray):
        print(f"DEBUG: Shape of barline_map after get_barline_map: {barline_map.shape}")
    print(f"DEBUG: Type of stems_rests_pred_dilated: {type(stems_rests_pred_dilated)}")
    if isinstance(stems_rests_pred_dilated, np.ndarray):
        print(f"DEBUG: Shape of stems_rests_pred_dilated: {stems_rests_pred_dilated.shape}")

    # oemerの例に従い、stems_rests_pred_dilated をバーラインマップに追加
    barline_map = barline_map + stems_rests_pred_dilated
    barline_map[barline_map > 1] = 1

    barline_coords = get_barline_box(barline_map)

    # --- Step 7: Visualization and Output ---
    original_img = Image.open(img_path).convert("RGB")
    original_img_cv = np.array(original_img)
    # Convert RGB to BGR for OpenCV
    original_img_cv = original_img_cv[:, :, ::-1].copy()
    
    draw_bounding_boxes(original_img_cv, barline_coords, color=(0, 0, 255)) # Red for barlines in BGR

    # Save the debug image
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    output_filename = os.path.splitext(os.path.basename(img_path))[0]
    output_path = os.path.join(output_dir, f"{output_filename}_detected_ml_barlines.png")
    Image.fromarray(cv2.cvtColor(original_img_cv, cv2.COLOR_BGR2RGB)).save(output_path)
    print(f"Detected barlines saved to {output_path}")

    # Save debug images of intermediate steps
    Image.fromarray((mix * 255).astype(np.uint8)).save(os.path.join(output_dir, "debug_mix.png"))
    Image.fromarray((staff_pred * 255).astype(np.uint8)).save(os.path.join(output_dir, "debug_staff_pred.png"))
    Image.fromarray((symbols_coarse * 255).astype(np.uint8)).save(os.path.join(output_dir, "debug_symbols_coarse.png"))
    Image.fromarray((stems_rests_pred * 255).astype(np.uint8)).save(os.path.join(output_dir, "debug_stems_rests.png"))
    Image.fromarray((notehead_pred * 255).astype(np.uint8)).save(os.path.join(output_dir, "debug_notehead.png"))
    Image.fromarray((clefs_keys_pred * 255).astype(np.uint8)).save(os.path.join(output_dir, "debug_clefs_keys.png"))
    
    symbols_final = symbols_pred.copy()
    draw_bounding_boxes(symbols_final, notehead_bboxes, color=(1,1,1))
    Image.fromarray((symbols_final * 255).astype(np.uint8)).save(os.path.join(output_dir, "debug_symbols_final.png"))

    return barline_coords

if __name__ == "__main__":
    """
    このスクリプトが直接実行された場合に、テスト実行するためのメイン関数
    """
    # --- 設定項目 ---
    # 入力画像のパス
    img_path = "data/input_images/page_3.png"
    # oemerの事前学習済みモデルのパス
    unet_model_path = "src/archive/oemer/oemer_src/oemer/checkpoints/unet_big"
    segnet_model_path = "src/archive/oemer/oemer_src/oemer/checkpoints/seg_net"
    # 結果を出力するディレクトリ
    output_dir = "output/ml_detector/"

    print("--- Barline Detection Test ---")
    print(f"Input Image: {img_path}")
    print(f"U-Net Model: {unet_model_path}")
    print(f"SegNet Model: {segnet_model_path}")
    print(f"Output Directory: {output_dir}")
    print("------------------------------")

    # 縦線検出を実行
    try:
        barline_coords = detect_barlines_ml(img_path, unet_model_path, segnet_model_path, output_dir)
        print(f"\nSuccessfully detected {len(barline_coords)} barlines.")
        print(f"Output image saved in '{output_dir}' directory.")
    except Exception as e:
        print(f"\nAn error occurred during barline detection: {e}")
