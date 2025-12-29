import cv2
import os
import torch
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer

# Use the anime model (optimized for line drawings) or the general x4plus model?
# Anime model is often better for sharp lines.
MODEL_NAME = 'RealESRGAN_x4plus' # Or RealESRGAN_x4plus_anime_6B
SCALE = 4

INPUT_PATH = "/workspace/data/workbench/sr_test_crop.png"
OUTPUT_PATH = "/workspace/data/workbench/sr_test_crop_upscaled.png"

def main():
    if not os.path.exists(INPUT_PATH):
        print(f"Error: {INPUT_PATH} not found.")
        return

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")

    # Load model
    # We need to manually define the model arch if we use the underlying library classes,
    # OR we can let RealESRGANer handle it if we have the weights.
    # Typically RealESRGANer downloads weights automatically.
    
    # Standard x4plus model
    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
    netscale = 4
    
    # If using anime model (RealESRGAN_x4plus_anime_6B)
    # model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=6, num_grow_ch=32, scale=4)

    upsampler = RealESRGANer(
        scale=netscale,
        model_path='https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth',
        model=model,
        tile=0, # 0 for no tile, or size like 512
        tile_pad=10,
        pre_pad=0,
        half=True, # Use fp16
        device=device,
    )

    img = cv2.imread(INPUT_PATH, cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"Error: Could not read {INPUT_PATH}")
        return

    try:
        output, _ = upsampler.enhance(img, outscale=SCALE)
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        cv2.imwrite(OUTPUT_PATH, output)
        print(f"Saved upscaled image to {OUTPUT_PATH}")
    except Exception as e:
        print(f"Error during inference: {e}")

if __name__ == "__main__":
    main()
