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
    layers.register_layer("staffs", staff_objects)
    layers.register_layer("zones", zones)

    # --- Step 6: Barline detection logic ---
    print("Detecting barlines...")
    mix = symbols_pred - stems_rests_pred_dilated - notehead_pred_dilated - clefs_keys_pred_dilated
    mix[mix < 0] = 0

    # staff_line_heightを取得
    staff_line_height = 0
    # print(f"Type of staff_objects: {type(staff_objects)}")
    # print(f"Content of staff_objects: {staff_objects}")
    if staff_objects.size > 0:
        # staff_objectsはStaffオブジェクトのリストのリストなので、flattenしてStaffオブジェクトのリストにする
        staff_line_height = np.mean([st.lower_bound - st.upper_bound for st in staff_objects.flatten()])
    if staff_line_height == 0: # 検出できなかった場合、デフォルト値
        # 画像の高さから適当なデフォルト値を設定。これは調整が必要かもしれない。
        staff_line_height = unet_map.shape[0] / 20 # 例: 画像高さの1/20

    