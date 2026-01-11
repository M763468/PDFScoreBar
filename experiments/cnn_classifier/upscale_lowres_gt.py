
import json
from pathlib import Path
import cv2
import numpy as np
import torch
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer

def upscale_page(image_path, gt_path, output_image_path, output_gt_path, scale=4.0):
    print(f"Upscaling {image_path.name} by {scale}x using RealESRGAN...")
    
    # Image
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Failed to load {image_path}")
    
    # Setup RealESRGAN
    model_name = 'RealESRGAN_x4plus'
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
    
    upsampler = RealESRGANer(
        scale=4,
        model_path='https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth',
        model=model,
        tile=0,
        tile_pad=10,
        pre_pad=0,
        half=False, # Use fp32 for safety on CPU/mixed
        device=device,
    )
    
    # Upscale
    output_img, _ = upsampler.enhance(img, outscale=scale)
    h, w = output_img.shape[:2]
    
    cv2.imwrite(str(output_image_path), output_img)
    print(f"  Saved SR image ({w}x{h}) to {output_image_path}")
    
    # GT
    with open(gt_path, 'r') as f:
        data = json.load(f)
        
    new_data = []
    for item in data:
        new_item = item.copy()
        if "barline_location" in item:
            x1, y1, x2, y2 = item["barline_location"]
            new_box = [
                int(round(x1 * scale)),
                int(round(y1 * scale)),
                int(round(x2 * scale)),
                int(round(y2 * scale))
            ]
            new_item["barline_location"] = new_box
        
        if "number_location" in item:
            nx1, ny1, nx2, ny2 = item["number_location"]
            if nx1 != 0 or nx2 != 0:
                 new_num = [
                    int(round(nx1 * scale)),
                    int(round(ny1 * scale)),
                    int(round(nx2 * scale)),
                    int(round(ny2 * scale))
                 ]
                 new_item["number_location"] = new_num
                 
        new_data.append(new_item)
        
    with open(output_gt_path, 'w') as f:
        json.dump(new_data, f, indent=2)
    print(f"  Saved GT to {output_gt_path}")

def main():
    root = Path("/home/masaki_muramatsu/ws_PDFScoreBar_training")
    
    # Angerer Paths
    subdir = "data/evaluation"
    img_rel = "images/page_3.png"
    gt_rel = "annotations/page_003/boxes_sorted_v20260111.json"
    
    out_img_rel = "images/page_3_x4.png"
    out_gt_rel = "annotations/page_003/boxes_sorted_v20260111_x4.json"
    
    upscale_page(
        root / subdir / img_rel,
        root / subdir / gt_rel,
        root / subdir / out_img_rel,
        root / subdir / out_gt_rel,
        scale=4.0
    )

if __name__ == "__main__":
    main()
