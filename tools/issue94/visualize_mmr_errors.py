"""
MMR Error Visualization and Inspection Tool (Local Diagnostics for Issue #94)

This script parses the MMR evaluation results, collects all error cases
(FN/missed, mismatch/skip_mismatch, FP/unexpected), aggregates them into
error_cases_summary.json, and generates overlay images highlighting the errors.

Note:
    This script is for local diagnosis. The generated overlay images should NOT
    be committed to the repository. Only commit this script and the small summary JSON
    if requested.
"""

import glob
import json
import os

from PIL import Image, ImageDraw, ImageFont


def get_ttf_font(size=40):
    # Try to find a standard TTF font on Linux
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    # Fallback to scanning /usr/share/fonts
    if not any(os.path.exists(p) for p in font_paths):
        system_ttfs = glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
        if system_ttfs:
            font_paths.insert(0, system_ttfs[0])

    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def draw_thick_rectangle(draw, bbox, color, width=6):
    xmin, ymin, xmax, ymax = bbox
    for i in range(width):
        draw.rectangle([xmin - i, ymin - i, xmax + i, ymax + i], outline=color)


def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    eval_summary_path = os.path.join(
        repo_root, "logs/issue94_mmr_current_state/eval/aggregated_eval_summary.json"
    )
    if not os.path.exists(eval_summary_path):
        print(f"Error: Aggregated summary not found at {eval_summary_path}")
        return

    with open(eval_summary_path, "r") as f:
        aggregated = json.load(f)

    # Output directories
    out_inspect_dir = os.path.join(repo_root, "logs/issue94_mmr_current_state/error_inspection")
    out_visual_dir = os.path.join(repo_root, "logs/issue94_mmr_current_state/error_visualization")
    os.makedirs(out_inspect_dir, exist_ok=True)
    os.makedirs(out_visual_dir, exist_ok=True)

    error_cases = []
    font = get_ttf_font(40)

    for page_entry in aggregated.get("pages", []):
        page_id = page_entry["page_id"]
        # Check if the page has any errors
        has_error = (
            page_entry["missed"] > 0 or page_entry["mismatch"] > 0 or page_entry["unexpected"] > 0
        )
        if not has_error:
            continue

        print(f"Processing error page: {page_id}")

        # Load page-specific eval summary
        page_summary_path = os.path.join(
            repo_root, f"logs/issue94_mmr_current_state/eval/{page_id}/mmr_eval_summary.json"
        )
        if not os.path.exists(page_summary_path):
            print(f"  Warning: Summary not found for {page_id}")
            continue

        with open(page_summary_path, "r") as f:
            page_summary = json.load(f)

        # Load numbering base JSON
        num_base_rel = page_summary["inputs"]["numbering_json"]
        numbering_base_path = os.path.join(repo_root, num_base_rel)
        numbering_base = None
        if os.path.exists(numbering_base_path):
            with open(numbering_base_path, "r") as f:
                numbering_base = json.load(f)
        else:
            print(f"  Warning: numbering_base.json not found at {numbering_base_path}")

        # Load page image
        img_rel = page_summary["inputs"]["image"]
        img_path = os.path.join(repo_root, img_rel)
        if not os.path.exists(img_path):
            # Fallback check under stage_e_full_pipeline/images
            img_path = os.path.join(
                repo_root,
                "logs/issue120_e2e_recovery/stage_e_full_pipeline/images",
                os.path.basename(img_rel),
            )

        image_loaded = False
        img = None
        if os.path.exists(img_path):
            try:
                img = Image.open(img_path).convert("RGB")
                image_loaded = True
            except Exception as e:
                print(f"  Failed to load image {img_path}: {e}")
        else:
            print(f"  Warning: Image not found at {img_path}")

        # Helper path references for JSON outputs
        expected_fixture_rel = f"tests/fixtures/expected_overrides_{page_id}.json"
        expected_fixture_path = os.path.join(repo_root, expected_fixture_rel)
        if not os.path.exists(expected_fixture_path):
            expected_fixture_rel = None

        detected_overrides_rel = f"logs/issue94_mmr_current_state/eval/{page_id}/mmr_overrides.json"

        # Track category overlays
        page_errors = []

        # Process missed (FN)
        for entry in page_summary.get("missed", []):
            key = entry["key"]
            expected_skip = entry["expected_skip"]
            classification_hint = entry.get("classification_hint")

            case = {
                "page_id": page_id,
                "image": os.path.basename(img_rel),
                "category": "missed",
                "key": key,
                "expected_skip": expected_skip,
                "detected_skip": None,
                "expected_rest_count": expected_skip + 1,
                "detected_rest_count": None,
                "classification_hint": classification_hint,
                "numbering_base_json": num_base_rel,
                "expected_fixture": expected_fixture_rel,
                "detected_overrides_json": detected_overrides_rel,
            }
            error_cases.append(case)
            page_errors.append(case)

        # Process skip_mismatch
        for entry in page_summary.get("skip_mismatch", []):
            key = entry["key"]
            expected_skip = entry["expected_skip"]
            detected_skip = entry["detected_skip"]
            classification_hint = entry.get("classification_hint")

            case = {
                "page_id": page_id,
                "image": os.path.basename(img_rel),
                "category": "skip_mismatch",
                "key": key,
                "expected_skip": expected_skip,
                "detected_skip": detected_skip,
                "expected_rest_count": expected_skip + 1,
                "detected_rest_count": detected_skip + 1,
                "classification_hint": classification_hint,
                "numbering_base_json": num_base_rel,
                "expected_fixture": expected_fixture_rel,
                "detected_overrides_json": detected_overrides_rel,
            }
            error_cases.append(case)
            page_errors.append(case)

        # Process unexpected (FP)
        for entry in page_summary.get("unexpected", []):
            key = entry["key"]
            detected_skip = entry.get("detected_skip")
            if detected_skip is None:
                # In unexpected, it might be in "skip" attribute
                detected_skip = entry.get("skip")
            classification_hint = entry.get("classification_hint")

            case = {
                "page_id": page_id,
                "image": os.path.basename(img_rel),
                "category": "unexpected",
                "key": key,
                "expected_skip": None,
                "detected_skip": detected_skip,
                "expected_rest_count": None,
                "detected_rest_count": (detected_skip + 1) if detected_skip is not None else None,
                "classification_hint": classification_hint,
                "numbering_base_json": num_base_rel,
                "expected_fixture": expected_fixture_rel,
                "detected_overrides_json": detected_overrides_rel,
            }
            error_cases.append(case)
            page_errors.append(case)

        # Draw overlays if image and numbering base are loaded
        if image_loaded and numbering_base:
            categories_on_page = set(e["category"] for e in page_errors)

            for cat in categories_on_page:
                # Copy the original image
                cat_img = img.copy()
                cat_draw = ImageDraw.Draw(cat_img)

                cat_errors = [e for e in page_errors if e["category"] == cat]
                for err in cat_errors:
                    key = err["key"]
                    cat_name = err["category"]

                    # Resolve color
                    if cat_name == "missed":
                        color = (255, 0, 0)  # Red
                        label = f"[FN] Missed (Expected Rest: {err['expected_rest_count']})"
                    elif cat_name == "skip_mismatch":
                        color = (255, 140, 0)  # Dark Orange
                        label = f"[Mismatch] ExpRest: {err['expected_rest_count']}, DetRest: {err['detected_rest_count']}"
                    else:
                        color = (147, 112, 219)  # Medium Purple
                        label = f"[FP] Unexpected (Detected Rest: {err['detected_rest_count']})"

                    # Find bbox from numbering base
                    system_idx = key[1]
                    measure_idx = key[2]

                    bbox = None
                    bbox_type = "Measure"

                    try:
                        systems = numbering_base["pages"][0]["systems"]
                        if system_idx < len(systems):
                            system_data = systems[system_idx]
                            measures = system_data.get("measures", [])
                            if measure_idx < len(measures):
                                bbox = measures[measure_idx].get("bbox")
                            else:
                                # Fallback to staff bbox
                                staves = system_data.get("staves", [])
                                if staves:
                                    bbox = staves[0].get("bbox")
                                    bbox_type = "Staff Fallback"
                    except Exception as e:
                        print(f"  Error extracting bbox for key {key}: {e}")

                    if bbox:
                        # Draw bbox rectangle
                        draw_thick_rectangle(cat_draw, bbox, color, width=8)
                        # Draw label text above/below the rectangle
                        tx, ty = bbox[0], max(0, bbox[1] - 50)

                        # Draw background box for text legibility
                        if hasattr(cat_draw, "textbbox"):
                            text_w, text_h = (
                                cat_draw.textsize(label, font=font)
                                if hasattr(cat_draw, "textsize")
                                else (400, 40)
                            )
                        else:
                            text_w, text_h = 600, 50

                        cat_draw.rectangle(
                            [tx, ty, tx + text_w + 10, ty + text_h + 5], fill=(255, 255, 255)
                        )
                        cat_draw.text((tx + 5, ty + 2), label, fill=color, font=font)
                        print(
                            f"  Drew {cat_name} overlay at system {system_idx}, measure {measure_idx} ({bbox_type} BBox)"
                        )
                    else:
                        print(
                            f"  Could not find bbox for key {key} (System {system_idx}, Measure {measure_idx})"
                        )

                # Save category image
                out_img_name = f"{page_id}_{cat}.png"
                out_img_path = os.path.join(out_visual_dir, out_img_name)
                cat_img.save(out_img_path)
                print(f"  Saved visual overlay to {out_img_path}")

    # Write summary JSON
    summary_out_path = os.path.join(out_inspect_dir, "error_cases_summary.json")
    with open(summary_out_path, "w") as f:
        json.dump(error_cases, f, indent=2)
    print(f"\nSuccessfully wrote error summary to {summary_out_path}")
    print(f"Total error cases found: {len(error_cases)}")


if __name__ == "__main__":
    main()
