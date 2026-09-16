import argparse
import hashlib
import json
import re
from pathlib import Path

import cv2


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_input_path(raw_path, source_root=None):
    path = Path(raw_path)
    if path.is_absolute():
        return path
    candidates = []
    if source_root is not None:
        candidates.append(Path(source_root) / path)
    candidates.extend((Path.cwd() / path, path))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else path


def score_id_from_page_name(name):
    return re.sub(r"_page_\d+$", "", str(name))


def page_identity(page, name, numbering_path):
    """Resolve stable score/page identity, preferring explicit config fields."""
    score_id = str(page.get("score_id") or score_id_from_page_name(name))
    page_id = str(page.get("page_id") or extract_page_token(numbering_path, name))
    if not page_id or page_id == "None":
        raise ValueError(f"could not resolve page_id for config entry: {name}")
    return score_id, page_id


def map_global_index_to_bbox(numbering_data):
    """
    Returns a list mapping global_index -> bbox [x1, y1, x2, y2]
    """
    mapping = []
    if "pages" in numbering_data:
        page = numbering_data["pages"][0]
        for system in page["systems"]:
            for measure in system["measures"]:
                mapping.append(measure["bbox"])
    return mapping


def iter_measure_records(numbering_data):
    """Yield system index, local measure index, global index, and source bbox."""
    pages = numbering_data.get("pages", [])
    if not pages:
        return
    global_index = 0
    for system_index, system in enumerate(pages[0].get("systems", [])):
        for measure_index, measure in enumerate(system.get("measures", [])):
            yield system_index, measure_index, global_index, measure["bbox"]
            global_index += 1


def extract_page_token(*candidates):
    for item in candidates:
        if not item:
            continue
        match = re.search(r"(page_\d+)", str(item))
        if match:
            return match.group(1)
    return None


def build_staff_mask_index(staff_mask_roots):
    index = {}
    if not staff_mask_roots:
        return index
    for root in staff_mask_roots:
        root_path = Path(root)
        if not root_path.exists():
            print(f"  [Warn] Staff mask root not found: {root_path}")
            continue
        for mask_path in root_path.rglob("*_debug_3_staff.png"):
            token = extract_page_token(mask_path)
            if token and token not in index:
                index[token] = mask_path
    return index


def load_staff_mask_from_segmentation(seg_path, target_shape):
    seg = cv2.imread(str(seg_path), cv2.IMREAD_UNCHANGED)
    if seg is None:
        return None
    # DeepScores staff label is 165 in the palette index map.
    staff = (seg == 165).astype("uint8") * 255
    if staff.shape[:2] != target_shape:
        staff = cv2.resize(
            staff, (target_shape[1], target_shape[0]), interpolation=cv2.INTER_NEAREST
        )
    return staff


def create_dataset_from_configs(
    config_paths,
    output_root,
    staff_mask_output=None,
    staff_mask_roots=None,
    deepscores_seg_roots=None,
    manifest_output=None,
    source_root=None,
):
    """
    Iterates over pages defined in the provided config files and creates training data.
    """

    # Setup Output
    train_0 = output_root / "train" / "0"  # Normal
    train_1 = output_root / "train" / "1"  # Rest
    train_0.mkdir(parents=True, exist_ok=True)
    train_1.mkdir(parents=True, exist_ok=True)

    count_0 = 0
    count_1 = 0
    manifest_samples = []

    staff_mask_output = Path(staff_mask_output) if staff_mask_output else None
    if staff_mask_output:
        staff_mask_output.mkdir(parents=True, exist_ok=True)

    staff_mask_index = build_staff_mask_index(staff_mask_roots)
    deepscores_seg_roots = [Path(p) for p in deepscores_seg_roots] if deepscores_seg_roots else []

    for config_path in config_paths:
        print(f"Loading config: {config_path}")
        config_path = Path(config_path)
        with open(config_path, "r") as f:
            config = json.load(f)

        pages = config.get("pages", [])
        print(f"  Found {len(pages)} pages.")

        for page in pages:
            name = page["name"]
            print(f"Processing {name}...")

            # 1. Load Ground Truth (rest_gt)
            gt_path = resolve_input_path(page["rest_gt"], source_root)
            if not gt_path.exists():
                print(f"  [Skip] GT not found: {gt_path}")
                continue

            with open(gt_path, "r") as f:
                gt_data = json.load(f)
                overrides = gt_data.get("overrides", [])

            rest_indices = {item["measure_index"]: item["rest_count"] for item in overrides}

            # 2. Load Numbering (for measure bounding boxes)
            if "numbering" not in page:
                print("  [Skip] Numbering path not in config.")
                continue

            numbering_path = resolve_input_path(page["numbering"], source_root)
            if not numbering_path.exists():
                print(f"  [Skip] Numbering file not found: {numbering_path}")
                continue

            with open(numbering_path, "r") as f:
                numbering_data = json.load(f)

            measure_records = list(iter_measure_records(numbering_data))
            score_id, page_id = page_identity(page, name, numbering_path)

            # 3. Load Image
            img_path = resolve_input_path(page["image"], source_root)
            if not img_path.exists():
                print(f"  [Skip] Image not found: {img_path}")
                continue

            img = cv2.imread(str(img_path))
            if img is None:
                print(f"  [Error] Could not read image: {img_path}")
                continue

            h_img, w_img = img.shape[:2]

            staff_mask = None
            staff_mask_path = Path(page["staff_mask"]) if "staff_mask" in page else None
            if staff_mask_path is None or not staff_mask_path.exists():
                page_token = extract_page_token(name, img_path)
                if page_token and page_token in staff_mask_index:
                    staff_mask_path = staff_mask_index[page_token]
            if staff_mask_path and staff_mask_path.exists():
                staff_mask = cv2.imread(str(staff_mask_path), cv2.IMREAD_GRAYSCALE)
                if staff_mask is None:
                    print(f"  [Warn] Could not read staff mask: {staff_mask_path}")
                    staff_mask = None
                elif staff_mask.shape[:2] != (h_img, w_img):
                    staff_mask = cv2.resize(
                        staff_mask, (w_img, h_img), interpolation=cv2.INTER_NEAREST
                    )
            elif deepscores_seg_roots:
                img_stem = img_path.stem
                for seg_root in deepscores_seg_roots:
                    seg_path = seg_root / f"{img_stem}_seg.png"
                    if seg_path.exists():
                        staff_mask = load_staff_mask_from_segmentation(seg_path, (h_img, w_img))
                        if staff_mask is None:
                            print(f"  [Warn] Could not read DeepScores segmentation: {seg_path}")
                        break
            if staff_mask_output is not None and staff_mask is None:
                print(f"  [Warn] Staff mask not found for {name}")

            # 4. Process Measures
            for system_index, measure_index, idx, bbox in measure_records:
                x1, y1, x2, y2 = bbox

                # Label
                label = 1 if idx in rest_indices else 0

                # Crop (with margin)
                margin = 20
                cx1 = max(0, x1 - margin)
                cy1 = max(0, y1 - margin)
                cx2 = min(w_img, x2 + margin)
                cy2 = min(h_img, y2 + margin)

                crop = img[cy1:cy2, cx1:cx2]

                if crop.size == 0:
                    continue

                # Filter extremely small crops
                if crop.shape[0] < 10 or crop.shape[1] < 10:
                    continue

                # Save
                filename = f"{name}_{idx:04d}.jpg"
                target_dir = train_1 if label == 1 else train_0
                cv2.imwrite(str(target_dir / filename), crop)

                if staff_mask is not None and staff_mask_output is not None:
                    mask_crop = staff_mask[cy1:cy2, cx1:cx2]
                    if mask_crop.size > 0:
                        mask_name = f"{Path(filename).stem}_staff.png"
                        cv2.imwrite(str(staff_mask_output / mask_name), mask_crop)

                if label == 1:
                    count_1 += 1
                else:
                    count_0 += 1

                manifest_samples.append(
                    {
                        "sample_id": f"{score_id}::{page_id}::s{system_index}::m{measure_index}",
                        "score_id": score_id,
                        "page_id": page_id,
                        "system_index": system_index,
                        "measure_index": measure_index,
                        "global_measure_index": idx,
                        "image_path": str(img_path.resolve()),
                        "bbox": [x1, y1, x2, y2],
                        "label": label,
                        "provenance": {
                            "generator": "tools/mmr_training/create_mmr_train_data.py",
                            "config_path": str(config_path.resolve()),
                            "config_sha256": sha256_file(config_path),
                            "image_path": str(img_path.resolve()),
                            "image_sha256": sha256_file(img_path),
                            "numbering_path": str(numbering_path.resolve()),
                            "numbering_sha256": sha256_file(numbering_path),
                            "rest_gt_path": str(gt_path.resolve()),
                            "rest_gt_sha256": sha256_file(gt_path),
                        },
                    }
                )

    print("\nDataset Generation Complete.")
    print(f"  Rest Samples (1): {count_1}")
    print(f"  Normal Samples (0): {count_0}")
    print(f"  Output: {output_root}")
    if manifest_output is not None:
        manifest_output = Path(manifest_output)
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(
                {
                    "schema": "issue332.mmr_semantic_source_manifest.v1",
                    "provenance": {
                        "generator": "tools/mmr_training/create_mmr_train_data.py",
                        "config_paths": [str(Path(path).resolve()) for path in config_paths],
                        "source_root": str(Path(source_root).resolve()) if source_root else None,
                        "margin_px": 20,
                        "sample_count": len(manifest_samples),
                    },
                    "samples": manifest_samples,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        print(f"  Manifest: {manifest_output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--configs", nargs="+", type=Path, required=True, help="List of rest_gt config JSON files"
    )
    parser.add_argument("--manifest-output", type=Path, default=None)
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--staff-mask-output",
        type=Path,
        default=None,
        help="Optional output dir for staff mask crops",
    )
    parser.add_argument(
        "--staff-mask-roots",
        nargs="*",
        type=Path,
        default=None,
        help="Roots to scan for *_debug_3_staff.png",
    )
    parser.add_argument(
        "--deepscores-seg-roots",
        nargs="*",
        type=Path,
        default=None,
        help="Roots to scan for DeepScores segmentation *_seg.png",
    )

    args = parser.parse_args()

    create_dataset_from_configs(
        args.configs,
        args.output_root,
        staff_mask_output=args.staff_mask_output,
        staff_mask_roots=args.staff_mask_roots,
        deepscores_seg_roots=args.deepscores_seg_roots,
        manifest_output=args.manifest_output,
        source_root=args.source_root,
    )
