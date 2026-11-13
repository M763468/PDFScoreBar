"""Render both final PDFs and compare pixels (labels/annotations geometry)."""
import sys, fitz, numpy as np
a, b = fitz.open(sys.argv[1]), fitz.open(sys.argv[2])
for i, (pa, pb) in enumerate(zip(a, b)):
    ia = np.frombuffer(pa.get_pixmap(dpi=150).samples, np.uint8)
    ib = np.frombuffer(pb.get_pixmap(dpi=150).samples, np.uint8)
    diff = np.abs(ia.astype(int) - ib.astype(int))
    print(f"page {i+1}: pixels={ia.size} differing={(diff>0).sum()} max={diff.max()}")
    print("text a:", len(pa.get_text()), "b:", len(pb.get_text()), "annots:", len(list(pa.annots())), len(list(pb.annots())))
    print("xobjects/ocgs a:", len(a.get_ocgs() or {}), "b:", len(b.get_ocgs() or {}))
