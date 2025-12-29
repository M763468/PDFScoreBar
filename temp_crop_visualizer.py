import cv2
import argparse
import sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="Path to the input image.")
    parser.add_argument("--bbox", required=True, nargs=4, type=int, help="Bounding box: x1 y1 x2 y2")
    parser.add_argument("--output", required=True, help="Path to save the cropped image.")
    parser.add_argument("--pad", type=int, default=30, help="Padding around the bbox.")
    args = parser.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        print(f"Error: Could not read image at {args.image}", file=sys.stderr)
        sys.exit(1)

    h, w = img.shape[:2]
    x1, y1, x2, y2 = args.bbox

    # Add padding and clamp to image dimensions
    crop_x1 = max(0, x1 - args.pad)
    crop_y1 = max(0, y1 - args.pad)
    crop_x2 = min(w, x2 + args.pad)
    crop_y2 = min(h, y2 + args.pad)

    # Crop the image
    cropped_img = img[crop_y1:crop_y2, crop_x1:crop_x2]

    # Save the cropped image
    if not cv2.imwrite(args.output, cropped_img):
        print(f"Error: Failed to save image to {args.output}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Saved cropped image to {args.output}")

if __name__ == "__main__":
    main()
