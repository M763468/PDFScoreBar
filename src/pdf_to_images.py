import fitz  # PyMuPDF
import os

def convert_pdf_to_images(pdf_path, output_folder):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    doc = fitz.open(pdf_path)
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=300)  # Set DPI for higher resolution
        output_image_path = os.path.join(output_folder, f"page_{i+1:03d}.png")
        pix.save(output_image_path)
        print(f"Saved {output_image_path}")
    doc.close()

if __name__ == "__main__":
    # --- Configuration for Training Data ---
    pdf_file = "data/training/pdfs/IMSLP19910-PMLP01607-Beethoven_Symphony_9_V1.pdf"
    output_dir = "data/training/images"
    print(f"Converting {pdf_file} to images in {output_dir}...")
    convert_pdf_to_images(pdf_file, output_dir)
    print("Conversion complete.")
