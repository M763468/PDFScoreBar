import argparse
from pathlib import Path

import cv2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--bbox", type=int, nargs=4, required=True, help="x1 y1 x2 y2")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--margin", type=int, default=50)
    args = parser.parse_args()

    img = cv2.imread(str(args.image))
    if img is None:
        print("Error reading image")
        return

    x1, y1, x2, y2 = args.bbox
    h, w = img.shape[:2]

    cx1 = max(0, x1 - args.margin)
    cy1 = max(0, y1 - args.margin)
    cx2 = min(w, x2 + args.margin)
    cy2 = min(h, y2 + args.margin)

    crop = img[cy1:cy2, cx1:cx2]
    cv2.rectangle(crop, (x1 - cx1, y1 - cy1), (x2 - cx1, y2 - cy1), (0, 0, 255), 2)

    cv2.imwrite(str(args.output), crop)
    print(f"Saved crop to {args.output}")


if __name__ == "__main__":
    main()
