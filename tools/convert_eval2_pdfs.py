from pathlib import Path

import fitz  # PyMuPDF

PDF_DIR = Path("data/evaluation2/pdfs")
IMG_DIR = Path("data/evaluation2/images")

PDFS = [
    "Shosrakovich-Sym5-Va.pdf",
    "Shostakovich-Festival_Overture_Va.pdf",
    "Sibelius-Violin_Concerto-Viola.pdf",
]


def convert_pdf(pdf_name):
    pdf_path = PDF_DIR / pdf_name
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return

    # Create dir name from PDF stem
    stem = pdf_path.stem
    out_dir = IMG_DIR / stem
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Converting {pdf_name} to {out_dir}...")

    doc = fitz.open(pdf_path)
    # Target scale: roughly 3000px wide. A4 is ~600pt. So scale ~5.0.
    mat = fitz.Matrix(5, 5)

    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=mat)
        # Format: page_001.png
        out_name = f"page_{i + 1:03d}.png"
        out_path = out_dir / out_name
        pix.save(out_path)
        print(f"  Saved {out_name}")

    print(f"Done: {out_dir}")


def main():
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    for pdf in PDFS:
        convert_pdf(pdf)


if __name__ == "__main__":
    main()
