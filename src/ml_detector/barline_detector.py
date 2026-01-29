import os

import cv2
import numpy as np
import scipy.ndimage
from oemer import layers
from oemer.bbox import (
    draw_lines,
    find_lines,
    get_bbox,
    get_center,
    rm_merge_overlap_bbox,
)
from oemer.general_filtering_rules import filter_out_of_range_bbox
from oemer.inference import inference
from oemer.note_group_extraction import extract as group_extract
from oemer.notehead_extraction import extract as note_extract
from oemer.staffline_extraction import extract as staff_extract
from oemer.utils import get_unit_size, slope_to_degree
from PIL import Image


def get_degree(line):
    return np.rad2deg(np.arctan2(line[3] - line[1], line[2] - line[0]))


def check_overlap(box1, box2):
    # box = (x1, y1, x2, y2)
    return not (box1[2] < box2[0] or box1[0] > box2[2] or box1[3] < box2[1] or box1[1] > box2[3])


def filter_lines_extended(
    lines,
    notehead_bboxes,
    min_degree=75,
    extension_ratio=0.5,
    max_width_ratio=0.4,
    min_height_ratio=3.5,
):
    staffs = layers.get_layer("staffs")

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


def register_note_id() -> None:
    symbols = layers.get_layer("symbols_pred")
    layer = layers.get_layer("note_id")
    notes = layers.get_layer("notes")
    for idx, note in enumerate(notes):
        x1, y1, x2, y2 = note.bbox
        yi, xi = np.where(symbols[y1:y2, x1:x2] > 0)
        yi += y1
        xi += x1
        layer[yi, xi] = idx
        notes[idx].id = idx


def draw_barlines_on_image(
    img: np.ndarray, bboxes: list, color=(0, 0, 255), thickness=2
) -> np.ndarray:
    """Draws bounding boxes directly on the image using OpenCV."""
    img_copy = img.copy()
    for bbox in bboxes:
        x1, y1, x2, y2 = bbox
        cv2.rectangle(img_copy, (x1, y1), (x2, y2), color, thickness)
    return img_copy


def filter_barlines(lines: list, min_height_unit_ratio: float = 3.75) -> np.ndarray:
    lines = filter_out_of_range_bbox(lines)
    lines = rm_merge_overlap_bbox(lines, mode="merge", overlap_ratio=0)

    # First round check, with line mode.
    valid_lines = []
    for line in lines:
        x1, y1, x2, y2 = line
        unit_size = get_unit_size(*get_center(line))

        # Check slope. Degree should be within 80~100.
        deg = slope_to_degree(y2 - y1, x2 - x1)
        if abs(deg) < 75:
            continue

        valid_lines.append(line)

    # Second round check, in bbox mode.
    valid_lines = np.array(valid_lines)
    if len(valid_lines) == 0:
        return np.array([])
    max_x = np.max(valid_lines[..., 2])
    max_y = np.max(valid_lines[..., 3])
    data = np.zeros((max_y + 10, max_x + 10, 3))
    data = draw_lines(valid_lines, data, width=1)
    boxes = get_bbox(data[..., 1])
    valid_box = []
    for box in boxes:
        _, y1, _, y2 = box
        unit_size = get_unit_size(*get_center(box))

        # Check height
        if (y2 - y1) < unit_size * min_height_unit_ratio:
            continue

        valid_box.append(box)

    # Check overall height. Filter out height below threshold after norm.
    if not valid_box:
        return np.array([])
    valid_box = sorted(valid_box, key=lambda box: box[3] - box[1])
    heights = [b[3] - b[1] for b in valid_box]
    top_5 = np.mean(heights[-5:])
    if top_5 == 0:
        return np.array([])  # Avoid division by zero
    norm = np.array(heights) / top_5
    idx = np.where(norm > 0.5)[0]
    valid_box = np.array(valid_box)[idx]

    return valid_box


def parse_barlines(
    group_map: np.ndarray,
    stems_rests: np.ndarray,
    symbols: np.ndarray,
    min_height_unit_ratio: float = 3.75,
) -> np.ndarray:
    # Create a binary mask from group_map
    notes_mask = np.where(group_map > -1, 1, 0)

    # Remove note groups from stems/rests prediction to get barline candidates
    barline_cand = stems_rests - notes_mask
    barline_cand[barline_cand < 0] = 0

    # Remove note groups from all symbols to get non-note symbols
    no_note = symbols - notes_mask
    no_note[no_note < 0] = 0

    # Label each region by connected pixels.
    bar_label, bnum = scipy.ndimage.label(barline_cand)
    sym_label, _ = scipy.ndimage.label(no_note)

    # Check for overlapping regions between barline candidates and other symbols
    sym_barline_map = np.zeros_like(no_note)
    for i in range(1, bnum + 1):
        idx = bar_label == i
        region = sym_label[idx]
        labels = set(np.unique(region))
        if 0 in labels:
            labels.remove(0)
        for label in labels:
            sym_idx = sym_label == label
            sym_barline_map[sym_idx] += no_note[sym_idx]
    sym_barline_map[sym_barline_map > 0] = 1

    lines = find_lines(sym_barline_map)
    line_box = filter_barlines(lines, min_height_unit_ratio)
    print(f"Detected barlines: {len(line_box)}")

    return line_box


def detect_barlines_ml(
    img_path: str, unet_model_path: str, segnet_model_path: str, output_dir: str
):
    group_map = None  # Initialize group_map
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
    get_bbox(notehead_pred)

    # --- Step 3: Dilate symbol masks to remove more noise ---
    kernel = np.ones((5, 5), np.uint8)
    stems_rests_pred_dilated = cv2.dilate(stems_rests_pred, kernel, iterations=1)
    notehead_pred_dilated = cv2.dilate(notehead_pred, kernel, iterations=1)
    clefs_keys_pred_dilated = cv2.dilate(clefs_keys_pred, kernel, iterations=1)

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

    # --- Step 5a: Extract noteheads ---
    print("Extracting noteheads...")
    notes = note_extract()
    layers.register_layer("notes", np.array(notes))

    # --- Step 5b: Register note_id layer ---
    print("Registering note_id layer...")
    layers.register_layer("note_id", np.zeros(symbols_pred.shape, dtype=np.int64) - 1)
    register_note_id()

    # --- Step 5c: Extract note groups to get group_map ---
    print("Extracting note groups...")
    note_groups, group_map = group_extract()
    layers.register_layer("note_groups", np.array(note_groups))
    layers.register_layer("group_map", group_map)

    # --- Step 6: Barline detection logic ---
    print("Detecting barlines...")
    barline_coords = parse_barlines(group_map, stems_rests_pred, symbols_pred)

    # --- Step 7: Visualization and Output ---
    original_img = Image.open(img_path).convert("RGB")
    original_img_cv = np.array(original_img)
    # Convert RGB to BGR for OpenCV
    original_img_cv = original_img_cv[:, :, ::-1].copy()

    # Scale the coordinates back to the original image size
    resized_h, resized_w = unet_map.shape[:2]
    original_w, original_h = original_img.size
    scale_x = original_w / resized_w
    scale_y = original_h / resized_h

    scaled_barline_coords = []
    for box in barline_coords:
        x1, y1, x2, y2 = box
        scaled_box = (int(x1 * scale_x), int(y1 * scale_y), int(x2 * scale_x), int(y2 * scale_y))
        scaled_barline_coords.append(scaled_box)

    img_with_boxes = draw_barlines_on_image(
        original_img_cv, scaled_barline_coords, color=(0, 0, 255)
    )

    # Save the debug image
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    output_filename = os.path.splitext(os.path.basename(img_path))[0]
    output_path = os.path.join(output_dir, f"{output_filename}_detected_ml_barlines.png")
    Image.fromarray(cv2.cvtColor(img_with_boxes, cv2.COLOR_BGR2RGB)).save(output_path)
    print(f"Detected barlines saved to {output_path}")

    # Save debug images of intermediate steps
    # Image.fromarray((mix * 255).astype(np.uint8)).save(os.path.join(output_dir, "debug_mix.png"))
    Image.fromarray((staff_pred * 255).astype(np.uint8)).save(
        os.path.join(output_dir, "debug_staff_pred.png")
    )
    Image.fromarray((symbols_coarse * 255).astype(np.uint8)).save(
        os.path.join(output_dir, "debug_symbols_coarse.png")
    )
    Image.fromarray((stems_rests_pred * 255).astype(np.uint8)).save(
        os.path.join(output_dir, "debug_stems_rests.png")
    )
    Image.fromarray((notehead_pred * 255).astype(np.uint8)).save(
        os.path.join(output_dir, "debug_notehead.png")
    )
    Image.fromarray((clefs_keys_pred * 255).astype(np.uint8)).save(
        os.path.join(output_dir, "debug_clefs_keys.png")
    )

    symbols_pred.copy()
    # draw_bounding_boxes(symbols_final, notehead_bboxes, color=(1,1,1))
    # Image.fromarray((symbols_final * 255).astype(np.uint8)).save(os.path.join(output_dir, "debug_symbols_final.png"))

    return barline_coords


if __name__ == "__main__":
    """
    このスクリプトが直接実行された場合に、テスト実行するためのメイン関数
    """
    # --- 設定項目 ---
    # 入力画像のパス
    img_path = "data/evaluation/images/page_3.png"
    # oemerの事前学習済みモデルのパス
    unet_model_path = "/workspace/src/archive/oemer/oemer_src/oemer/checkpoints/unet_big"
    segnet_model_path = "/workspace/src/archive/oemer/oemer_src/oemer/checkpoints/seg_net"
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
        barline_coords = detect_barlines_ml(
            img_path, unet_model_path, segnet_model_path, output_dir
        )
        print("\nBarline detection process completed successfully.")
        print(f"Output image saved in '{output_dir}' directory.")
    except Exception as e:
        print(f"\nAn error occurred during barline detection: {e}")
