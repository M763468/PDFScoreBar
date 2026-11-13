import sys, fitz, numpy as np, cv2
a, b, out = fitz.open(sys.argv[1]), fitz.open(sys.argv[2]), sys.argv[3]
def img(d):
    p = d[0].get_pixmap(dpi=300, clip=fitz.Rect(60, 270, 100, 860))
    return np.frombuffer(p.samples, np.uint8).reshape(p.h, p.w, p.n)[..., :3]
ia, ib = img(a), img(b)
cv2.imwrite(out, cv2.cvtColor(np.hstack([ia, np.full((ia.shape[0], 10, 3), 128, np.uint8), ib]), cv2.COLOR_RGB2BGR))
for d, name in ((a, "docker"), (b, "native")):
    for xref in range(1, d.xref_length()):
        t = d.xref_object(xref, compressed=True)
        if "/Font" in t and "/BaseFont" in t: print(name, xref, t[:160])
