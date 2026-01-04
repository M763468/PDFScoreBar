import json
import cv2
import sys
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    # Load JSON
    with open(args.json) as f:
        data = json.load(f)

    # Load Image
    img = cv2.imread(args.image)
    if img is None:
        print(f"Failed to load image: {args.image}")
        sys.exit(1)

    # Draw Systems
    for page in data["pages"]:
        for i, system in enumerate(page["systems"]):
            staves = system["staves"]
            if not staves:
                continue
            
            # Compute system bbox
            x1 = min(s["bbox"][0] for s in staves)
            y1 = min(s["bbox"][1] for s in staves)
            x2 = max(s["bbox"][2] for s in staves)
            y2 = max(s["bbox"][3] for s in staves)

            # Draw Box
            color = (0, 0, 255) # Red for system box
            if len(staves) > 1:
                color = (0, 255, 0) # Green for multi-staff
            
            cv2.rectangle(img, (x1-10, y1-10), (x2+10, y2+10), color, 2)
            
            # Label
            label = f"Sys {i+1}: {len(staves)} staves"
            cv2.putText(img, label, (x1, y1-15), cv2.FONT_HERSHEY_SIMPLEX, 
                        1.0, color, 2, cv2.LINE_AA)

            # Draw connections if multi-staff
            if len(staves) > 1:
                for j in range(len(staves)-1):
                    s_curr = staves[j]
                    s_next = staves[j+1]
                    
                    # Draw line connecting them to show they are grouped
                    cy1 = (s_curr["bbox"][1] + s_curr["bbox"][3]) // 2
                    cy2 = (s_next["bbox"][1] + s_next["bbox"][3]) // 2
                    cx = (s_curr["bbox"][0] + s_curr["bbox"][2]) // 2
                    
                    cv2.line(img, (cx, cy1), (cx, cy2), (255, 0, 255), 2)

    cv2.imwrite(args.output, img)
    print(f"Saved visualization to {args.output}")

if __name__ == "__main__":
    main()
