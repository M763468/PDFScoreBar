import sys, fitz, numpy as np, cv2
a, b, out = fitz.open(sys.argv[1]), fitz.open(sys.argv[2]), sys.argv[3]
pa, pb = a[0].get_pixmap(dpi=150), b[0].get_pixmap(dpi=150)
ia = np.frombuffer(pa.samples, np.uint8).reshape(pa.h, pa.w, pa.n)[..., :3]
ib = np.frombuffer(pb.samples, np.uint8).reshape(pb.h, pb.w, pb.n)[..., :3]
m = (np.abs(ia.astype(int) - ib.astype(int)).max(axis=2) > 0).astype(np.uint8)
n, lab, stats, _ = cv2.connectedComponentsWithStats(cv2.dilate(m, np.ones((9, 9), np.uint8)))
print("regions", n - 1)
for x, y, w, h, area in sorted(stats[1:].tolist(), key=lambda s: -s[4])[:12]:
    print(f"  x={x} y={y} w={w} h={h}")
vis = ib.copy(); vis[m > 0] = (0, 0, 255)
cv2.imwrite(out, cv2.cvtColor(vis, cv2.COLOR_RGB2BGR))
