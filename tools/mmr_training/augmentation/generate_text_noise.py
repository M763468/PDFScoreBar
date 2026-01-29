import random
from pathlib import Path

import cv2


def overlay_text(image, text_list, font_scale_range=(0.5, 1.2), thickness_range=(1, 2)):
    """
    Overlays random text on the image, avoiding the exact center (where H-Bar usually is).
    Respects constraints:
    - Text can be partially cut off (out of bounds).
    - Text should not be completely inside the staff lines (conceptually),
      but since we don't have staff coordinates here, we'll randomize vertical position
      to favor top/bottom areas, or crossing the staff, but avoiding 'hidden inside'.
      Actually, 'hidden inside staff' usually means small text between lines.
      We will simulate standard musical text placement (Above, Below, or Large across).
    """
    h, w = image.shape[:2]
    img_aug = image.copy()

    text = random.choice(text_list)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = random.uniform(*font_scale_range)
    thickness = random.randint(*thickness_range)

    (text_w, text_h), baseline = cv2.getTextSize(text, font, scale, thickness)

    # Logic for placement:
    # 1. Above staff (Top area)
    # 2. Below staff (Bottom area)
    # 3. Crossing (Large text like 'div.') - allowed.
    # Constraint: "Not completely hidden inside staff".
    # Since we don't know staff pos, we assume staff is roughly vertically centered.
    # We will try to place text such that it is either clearly above/below, or large enough.

    pos_type = random.choice(["top", "bottom", "cross"])

    if pos_type == "top":
        # Text bottom sits near top 1/3
        y = random.randint(0, h // 3)
    elif pos_type == "bottom":
        # Text top sits near bottom 2/3
        y = random.randint(h * 2 // 3, h + text_h)
    else:  # cross
        # Random Y, allowing cutoff
        y = random.randint(-text_h // 2, h + text_h // 2)

    # X position: Random, allowing cutoff (partial visibility)
    # Range: from -text_w/2 to w - text_w/2
    x = random.randint(-text_w // 2, w - text_w // 4)

    # Color: Black (assumed grayscale or bgr image where ink is dark)
    # If image is white bg, text should be black (0,0,0)
    # Check avg color to be sure? usually score is white bg.
    color = (0, 0, 0)

    cv2.putText(img_aug, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)

    return img_aug


def augment_dataset(data_root, output_root, aug_factor=5):
    """
    Reads Positive samples (train/1), generates augmented versions with text,
    and saves them to output_root/train/1.
    Also copies original Negatives and Positives.
    """
    data_root = Path(data_root)
    output_root = Path(output_root)

    # Setup Output
    (output_root / "train" / "0").mkdir(parents=True, exist_ok=True)
    (output_root / "train" / "1").mkdir(parents=True, exist_ok=True)

    # Musical terms often found in scores
    terms = [
        "pizz.",
        "arco",
        "div.",
        "unis.",
        "solo",
        "tutti",
        "a 2",
        "cresc.",
        "dim.",
        "espress.",
        "dolce",
        "sempre",
        "sim.",
        "f",
        "p",
        "mf",
        "mp",
        "ff",
        "pp",
        "sfz",
        "Allegro",
        "Andante",
        "Largo",
        "Presto",
        "Moderato",
        "Tempo I",
        "Cadenza",
        "G.P.",
        "V.S.",
        "attacca",
    ]

    # 1. Copy Negatives (train/0) - No augmentation needed for now, or maybe minimal?
    # Actually, we should keep Negatives as is to maintain "Non-H-Bar" features.
    print("Copying Negatives...")
    for img_path in (data_root / "train" / "0").glob("*.jpg"):
        img = cv2.imread(str(img_path))
        if img is not None:
            cv2.imwrite(str(output_root / "train" / "0" / img_path.name), img)

    # 2. Process Positives (train/1)
    print(f"Augmenting Positives (Factor: {aug_factor})...")
    for img_path in (data_root / "train" / "1").glob("*.jpg"):
        img = cv2.imread(str(img_path))
        if img is None:
            continue

        # Save Original
        cv2.imwrite(str(output_root / "train" / "1" / img_path.name), img)

        # Generate Augmented Versions
        for i in range(aug_factor):
            aug_img = overlay_text(img, terms)

            # Save with suffix
            new_name = f"{img_path.stem}_aug_text_{i}{img_path.suffix}"
            cv2.imwrite(str(output_root / "train" / "1" / new_name), aug_img)

    print("Augmentation Complete.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--factor", type=int, default=5)
    args = parser.parse_args()

    augment_dataset(args.input, args.output, args.factor)
