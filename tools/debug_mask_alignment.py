import argparse
import json

import cv2


def debug_mask_alignment(
    image_path, mask_path, numbering_json_path, output_path, target_measure_idx=None
):
    """
    Visualizes the alignment between the original image and the mask.
    Draws the measure bbox on the original image, and overlays the corresponding
    area from the mask (scaled to fit).
    """
    print(f"Loading image: {image_path}")
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not load image {image_path}")
        return

    print(f"Loading mask: {mask_path}")
    mask = cv2.imread(mask_path)
    if mask is None:
        print(f"Error: Could not load mask {mask_path}")
        return

    print(f"Loading numbering: {numbering_json_path}")
    with open(numbering_json_path, "r") as f:
        data = json.load(f)

    # Calculate scale factors
    img_h, img_w = img.shape[:2]
    mask_h, mask_w = mask.shape[:2]
    scale_x = mask_w / img_w
    scale_y = mask_h / img_h

    print(f"Image Size: {img_w}x{img_h}")
    print(f"Mask Size: {mask_w}x{mask_h}")
    print(f"Scale Factors (Mask/Image): x={scale_x:.4f}, y={scale_y:.4f}")

    # Create visualization image (copy of original)
    vis_img = img.copy()

    # If mask is grayscale, make it 3-channel for overlay
    if len(mask.shape) == 2:
        mask_vis = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    else:
        mask_vis = mask.copy()

    # Find measures
    measures = []
    for page in data["pages"]:
        for system in page["systems"]:
            for measure in system["measures"]:
                measures.append(measure)

    print(f"Total measures: {len(measures)}")

    # If target index is provided, filter
    if target_measure_idx is not None:
        if target_measure_idx < 0 or target_measure_idx >= len(measures):
            print(f"Error: Target measure index {target_measure_idx} out of range.")
            return
        measures_to_draw = [measures[target_measure_idx]]
        print(f"Visualizing ONLY Measure Index: {target_measure_idx}")
    else:
        # Draw all measures (or a subset)
        measures_to_draw = measures
        print("Visualizing ALL measures.")

    for i, m in enumerate(measures_to_draw):
        bbox = m["bbox"]  # [x1, y1, x2, y2]
        x1, y1, x2, y2 = bbox

        # 1. Draw BBox on original image (Green)
        cv2.rectangle(vis_img, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # 2. Extract corresponding patch from Mask
        mx1 = int(x1 * scale_x)
        my1 = int(y1 * scale_y)
        mx2 = int(x2 * scale_x)
        my2 = int(y2 * scale_y)

        # Clamp to mask bounds
        mx1 = max(0, mx1)
        my1 = max(0, my1)
        mx2 = min(mask_w, mx2)
        my2 = min(mask_h, my2)

        if mx2 > mx1 and my2 > my1:
            mask_patch = mask_vis[my1:my2, mx1:mx2]

            # Resize mask patch back to original image bbox size for overlay
            target_w = x2 - x1
            target_h = y2 - y1

            if target_w > 0 and target_h > 0:
                resized_mask_patch = cv2.resize(
                    mask_patch, (target_w, target_h), interpolation=cv2.INTER_NEAREST
                )

                # Overlay: Blend mask patch with original image
                # We'll put the mask patch "inside" the green box with 50% opacity
                roi = vis_img[y1:y2, x1:x2]

                # Careful with dimensions if rounding errors occurred
                ph, pw = resized_mask_patch.shape[:2]
                rh, rw = roi.shape[:2]

                # Crop to match smallest dimensions
                h_match = min(ph, rh)
                w_match = min(pw, rw)

                if h_match > 0 and w_match > 0:
                    blend = cv2.addWeighted(
                        roi[:h_match, :w_match], 0.5, resized_mask_patch[:h_match, :w_match], 0.5, 0
                    )
                    vis_img[y1 : y1 + h_match, x1 : x1 + w_match] = blend

    cv2.imwrite(output_path, vis_img)
    print(f"Saved visualization to: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug mask alignment")
    parser.add_argument("--image", required=True, help="Path to original image")
    parser.add_argument("--mask", required=True, help="Path to mask image")
    parser.add_argument("--numbering-json", required=True, help="Path to numbering json")
    parser.add_argument("--output", required=True, help="Path to output image")
    parser.add_argument(
        "--measure-idx", type=int, default=None, help="Specific measure index to visualize"
    )

    args = parser.parse_args()
    debug_mask_alignment(args.image, args.mask, args.numbering_json, args.output, args.measure_idx)
