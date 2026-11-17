"""Procedural synthetic music-notation tiles and reproducible degradations (Issue #533).

All content is drawn by this module with OpenCV primitives and OpenCV's built-in Hershey
fonts. No score PDF, evaluation image, ground truth or third-party image is read, so the
training pairs have first-party provenance. Dimensions follow common engraving proportions
(staff space 1.4-2.2 mm, i.e. about 20-31 px at the 360 dpi pipeline input).

``make_pair(seed)`` is deterministic: the same seed gives the same HR/LR pair.
HR is the clean anti-aliased rendering at 4x the LR resolution (the SR target).
"""

from __future__ import annotations

import math

import cv2
import numpy as np

SCALE = 4
HERSHEY = (
    cv2.FONT_HERSHEY_SIMPLEX,
    cv2.FONT_HERSHEY_DUPLEX,
    cv2.FONT_HERSHEY_COMPLEX,
    cv2.FONT_HERSHEY_TRIPLEX,
    cv2.FONT_HERSHEY_COMPLEX_SMALL,
    cv2.FONT_HERSHEY_SCRIPT_SIMPLEX,
    cv2.FONT_HERSHEY_SCRIPT_COMPLEX,
)
SHIFT = 4  # sub-pixel precision for cv2 drawing
ONE = 1 << SHIFT


def _p(x: float, y: float) -> tuple[int, int]:
    return int(round(x * ONE)), int(round(y * ONE))


def _line(img, x1, y1, x2, y2, w):
    cv2.line(img, _p(x1, y1), _p(x2, y2), 0, max(1, int(round(w))), cv2.LINE_AA, SHIFT)


def _poly(img, pts):
    arr = np.array([_p(x, y) for x, y in pts], np.int32)
    cv2.fillPoly(img, [arr], 0, cv2.LINE_AA, SHIFT)


def _ellipse(img, cx, cy, ax, ay, angle, filled, w):
    cv2.ellipse(
        img,
        _p(cx, cy),
        _p(ax, ay),
        angle,
        0,
        360,
        0,
        -1 if filled else max(1, int(round(w))),
        cv2.LINE_AA,
        SHIFT,
    )


def _text(img, rng, x, y, sp):
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:;-()"
    s = "".join(rng.choice(list(chars), size=int(rng.integers(1, 9))))
    font = HERSHEY[int(rng.integers(len(HERSHEY)))]
    scale = sp * rng.uniform(0.02, 0.05)
    thick = max(1, int(round(sp * rng.uniform(0.06, 0.16))))
    cv2.putText(img, s, (int(x), int(y)), font, scale, 0, thick, cv2.LINE_AA)


def _staff(img, rng, y0, sp, x0, x1, lw):
    for i in range(5):
        _line(img, x0, y0 + i * sp, x1, y0 + i * sp, lw)


def _note(img, rng, x, y_top, sp, lw, stem_dir):
    pos = int(rng.integers(-6, 15))  # half-space steps from top line
    cy = y_top + pos * sp / 2
    ax, ay = sp * 0.62, sp * 0.45
    filled = rng.random() < 0.75
    _ellipse(img, x, cy, ax, ay, -20, filled, lw * 1.6)
    # ledger lines
    for k in range(-2, pos - 1, -2) if pos < 0 else []:
        yy = y_top + k * sp / 2
        _line(img, x - sp, yy, x + sp, yy, lw)
    for k in range(10, pos + 1, 2) if pos > 8 else []:
        yy = y_top + k * sp / 2
        _line(img, x - sp, yy, x + sp, yy, lw)
    stem_len = sp * rng.uniform(3.0, 3.8)
    sw = sp * rng.uniform(0.09, 0.14)
    if stem_dir > 0:
        sx = x + ax * 0.95
        _line(img, sx, cy, sx, cy - stem_len, sw)
        end = (sx, cy - stem_len)
    else:
        sx = x - ax * 0.95
        _line(img, sx, cy, sx, cy + stem_len, sw)
        end = (sx, cy + stem_len)
    if rng.random() < 0.15:  # augmentation dot
        _ellipse(img, x + sp * 1.1, cy - sp * 0.2, sp * 0.16, sp * 0.16, 0, True, 1)
    return end


def _beam(img, a, b, sp, n):
    thick = sp * 0.48
    d = sp * 0.75
    for i in range(n):
        off = i * d * (1 if a[1] < 0 else 1)
        _poly(
            img,
            [
                (a[0], a[1] + off),
                (b[0], b[1] + off),
                (b[0], b[1] + off + thick),
                (a[0], a[1] + off + thick),
            ],
        )


def _barline(img, rng, x, y0, y1, sp):
    kind = rng.random()
    thin = sp * rng.uniform(0.12, 0.2)
    if kind < 0.75:
        _line(img, x, y0, x, y1, thin)
    elif kind < 0.9:
        _line(img, x, y0, x, y1, thin)
        _line(img, x + sp * 0.6, y0, x + sp * 0.6, y1, thin)
    else:
        _line(img, x, y0, x, y1, thin)
        _poly(img, [(x + sp * 0.5, y0), (x + sp * 1.0, y0), (x + sp * 1.0, y1), (x + sp * 0.5, y1)])


def _slur(img, rng, x0, x1, y, sp, lw):
    h = sp * rng.uniform(0.8, 2.5) * (1 if rng.random() < 0.5 else -1)
    pts = []
    for t in np.linspace(0, 1, 40):
        pts.append((x0 + (x1 - x0) * t, y - 4 * h * t * (1 - t)))
    arr = np.array([_p(px, py) for px, py in pts], np.int32)
    cv2.polylines(img, [arr], False, 0, max(1, int(round(lw * 1.4))), cv2.LINE_AA, SHIFT)


def _hairpin(img, x0, x1, y, sp, lw):
    o = sp * 0.6
    _line(img, x0, y, x1, y - o, lw)
    _line(img, x0, y, x1, y + o, lw)


def render_tile(rng: np.random.Generator, size: int = 1024) -> np.ndarray:
    """Render one HR grayscale tile (0 ink .. 255 paper)."""
    img = np.full((size, size), 255, np.uint8)
    sp = rng.uniform(20, 31) * SCALE  # staff space in HR px
    if rng.random() < 0.3:  # smaller cue/ossia-like staves and text-heavy regions
        sp *= rng.uniform(0.6, 0.85)
    lw = sp * rng.uniform(0.09, 0.16)
    gap = sp * rng.uniform(3.5, 9)
    y = rng.uniform(-6 * sp, sp)
    systems = []
    while y < size + sp:
        x0 = rng.uniform(-sp * 4, size * 0.2) if rng.random() < 0.3 else -10
        x1 = size + 10 if rng.random() < 0.8 else rng.uniform(size * 0.6, size)
        _staff(img, rng, y, sp, x0, x1, lw)
        systems.append((y, x0, x1))
        y += 4 * sp + gap
    for y_top, x0, x1 in systems:
        x = x0 + sp * rng.uniform(1, 3)
        pending = []
        while x < x1 - sp:
            r = rng.random()
            if r < 0.5:
                end = _note(img, rng, x, y_top, sp, lw, 1 if rng.random() < 0.5 else -1)
                pending.append(end)
                if len(pending) >= 2 and rng.random() < 0.35:
                    _beam(img, pending[-2], pending[-1], sp, int(rng.integers(1, 3)))
                    pending = []
                x += sp * rng.uniform(1.1, 2.8)
            elif r < 0.64:
                y_end = y_top + 4 * sp
                if rng.random() < 0.25:  # system connector over the gap
                    y_end += gap + 4 * sp
                _barline(img, rng, x, y_top, y_end, sp)
                pending = []
                x += sp * rng.uniform(1.0, 2.5)
            elif r < 0.8:
                _text(img, rng, x, y_top + rng.uniform(-2.5, 6.5) * sp, sp)
                x += sp * rng.uniform(2, 5)
            elif r < 0.86:
                _slur(
                    img, rng, x, x + sp * rng.uniform(3, 9), y_top + rng.uniform(-2, 6) * sp, sp, lw
                )
                x += sp * rng.uniform(1, 3)
            elif r < 0.9:
                _hairpin(img, x, x + sp * rng.uniform(3, 8), y_top + 6.5 * sp, sp, lw)
                x += sp * rng.uniform(1, 3)
            else:
                # rest-like / accidental-like block glyphs
                w, h = sp * rng.uniform(0.3, 1.0), sp * rng.uniform(0.4, 2.5)
                cy = y_top + rng.uniform(0.5, 3.5) * sp
                if rng.random() < 0.5:
                    _poly(
                        img,
                        [
                            (x, cy - h / 2),
                            (x + w, cy - h / 2),
                            (x + w, cy + h / 2),
                            (x, cy + h / 2),
                        ],
                    )
                else:
                    _line(img, x, cy - h, x, cy + h, lw * 1.2)
                    _line(img, x + w, cy - h * 0.9, x + w, cy + h * 1.1, lw * 1.2)
                    _line(img, x - w * 0.3, cy - sp * 0.3, x + w * 1.3, cy - sp * 0.5, sp * 0.4)
                x += sp * rng.uniform(1.2, 2.5)
    if rng.random() < 0.3:  # mild rotation (scan skew)
        ang = rng.uniform(-0.6, 0.6)
        m = cv2.getRotationMatrix2D((size / 2, size / 2), ang, 1.0)
        img = cv2.warpAffine(img, m, (size, size), flags=cv2.INTER_LINEAR, borderValue=255)
    return img


def _jpeg(img, q):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(q)])
    return cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)


def degrade(rng: np.random.Generator, hr: np.ndarray) -> np.ndarray:
    """Reproducible LR (1/SCALE) degradation of an HR tile."""
    h, w = hr.shape
    lr_size = (w // SCALE, h // SCALE)
    x = hr.astype(np.float32)
    if rng.random() < 0.5:
        # Scanned 1-bit source: binarize at a source resolution, then resample to LR grid.
        src = rng.uniform(0.6, 2.2)  # source resolution relative to LR
        sz = (max(8, int(lr_size[0] * src)), max(8, int(lr_size[1] * src)))
        if rng.random() < 0.6:
            x = cv2.GaussianBlur(x, (0, 0), rng.uniform(0.5, 2.5))
        s = cv2.resize(x, sz, interpolation=cv2.INTER_AREA)
        s = np.where(s < rng.uniform(100, 170), 0.0, 255.0).astype(np.float32)
        interp = [cv2.INTER_AREA, cv2.INTER_LINEAR, cv2.INTER_CUBIC, cv2.INTER_NEAREST][
            int(rng.integers(4))
        ]
        if src > 1:
            interp = cv2.INTER_AREA if rng.random() < 0.7 else cv2.INTER_LINEAR
        lr = cv2.resize(s, lr_size, interpolation=interp)
    else:
        if rng.random() < 0.7:
            x = cv2.GaussianBlur(x, (0, 0), rng.uniform(0.3, 3.0))
        lr = cv2.resize(x, lr_size, interpolation=cv2.INTER_AREA)
    if rng.random() < 0.4:
        lr = cv2.GaussianBlur(lr, (0, 0), rng.uniform(0.3, 0.9))
    ink, paper = rng.uniform(0, 70), rng.uniform(205, 255)
    lr = ink + (paper - ink) * (lr / 255.0)
    if rng.random() < 0.6:
        lr = lr + rng.normal(0, rng.uniform(1, 7), lr.shape)
    if rng.random() < 0.15:
        n = int(rng.integers(1, 30))
        ys, xs = rng.integers(0, lr.shape[0], n), rng.integers(0, lr.shape[1], n)
        lr[ys, xs] = rng.uniform(0, 120, n)
    lr = np.clip(lr, 0, 255).round().astype(np.uint8)
    if rng.random() < 0.6:
        lr = _jpeg(lr, rng.uniform(45, 95))
    return lr


def make_pair(seed: int, size: int = 1024) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    hr = render_tile(rng, size)
    lr = degrade(rng, hr)
    return hr, lr


if __name__ == "__main__":  # preview
    import sys

    out = sys.argv[1]
    tiles = []
    for s in range(6):
        hr, lr = make_pair(s)
        up = cv2.resize(lr, hr.shape[::-1], interpolation=cv2.INTER_NEAREST)
        tiles.append(np.hstack([up, hr]))
    cv2.imwrite(out, np.vstack(tiles[:3]))
    print("ok", math.pi > 3)
