"""Issue #506: render both final PDFs and compare pixels (labels/annotations geometry).

Usage: compare_pdf_render.py <a.pdf> <b.pdf>
Fails (exit 1) when page counts or rendered page sizes differ instead of silently
truncating to the shorter document (review of PR #531). Pixel differences are reported,
not gated: the exact gate lives in compare_semantic.py.
"""
import sys

import fitz
import numpy as np

a, b = fitz.open(sys.argv[1]), fitz.open(sys.argv[2])
print(f"page_count a: {len(a)} b: {len(b)}")
if len(a) != len(b) or len(a) == 0:
    print("FAIL: page count differs or is zero")
    raise SystemExit(1)
print("xobjects/ocgs a:", len(a.get_ocgs() or {}), "b:", len(b.get_ocgs() or {}))
failed = False
for i, (pa, pb) in enumerate(zip(a, b)):
    xa, xb = pa.get_pixmap(dpi=150), pb.get_pixmap(dpi=150)
    if (xa.width, xa.height, xa.n) != (xb.width, xb.height, xb.n):
        print(f"page {i+1}: FAIL rendered size a={xa.width}x{xa.height}x{xa.n} b={xb.width}x{xb.height}x{xb.n}")
        failed = True
        continue
    ia = np.frombuffer(xa.samples, np.uint8)
    ib = np.frombuffer(xb.samples, np.uint8)
    diff = np.abs(ia.astype(int) - ib.astype(int))
    print(f"page {i+1}: pixels={ia.size} differing={(diff>0).sum()} max={diff.max()} rotation={pa.rotation},{pb.rotation}")
    print("text a:", len(pa.get_text()), "b:", len(pb.get_text()), "annots:", len(list(pa.annots())), len(list(pb.annots())))
    failed |= pa.rotation != pb.rotation
raise SystemExit(1 if failed else 0)
