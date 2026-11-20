"""Detect red (and optionally blue) ink clusters (seals/stamps) on a page. Returns normalized boxes."""
import numpy as np
from compat import fitz
from collections import deque

def color_boxes(page, color="red", dpi=40, min_px=12, pad=0.008):
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3).astype(int)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    if color == "red":
        m = (R > 120) & (R - G > 30) & (R - B > 20)
    else:
        m = (B > 100) & (B - R > 40) & (B - G > 15)
    # dilate a little to join seal strokes
    k = 2
    md = m.copy()
    for dy in range(-k, k + 1):
        for dx in range(-k, k + 1):
            md |= np.roll(np.roll(m, dy, 0), dx, 1)
    H, W = md.shape
    seen = np.zeros_like(md)
    boxes = []
    for y in range(H):
        for x in range(W):
            if md[y, x] and not seen[y, x]:
                q = deque([(y, x)]); seen[y, x] = 1
                ys, xs, cnt = [y, y], [x, x], 0
                while q:
                    cy, cx = q.popleft(); cnt += m[cy, cx]
                    ys[0] = min(ys[0], cy); ys[1] = max(ys[1], cy); xs[0] = min(xs[0], cx); xs[1] = max(xs[1], cx)
                    for ny, nx in ((cy+1, cx), (cy-1, cx), (cy, cx+1), (cy, cx-1)):
                        if 0 <= ny < H and 0 <= nx < W and md[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = 1; q.append((ny, nx))
                if cnt >= min_px:
                    boxes.append([max(0, xs[0]/W - pad), max(0, ys[0]/H - pad), min(1, (xs[1]+1)/W + pad), min(1, (ys[1]+1)/H + pad), int(cnt)])
    return boxes


def _components(m):
    H, W = m.shape
    seen = np.zeros_like(m)
    comps = []
    ys_, xs_ = np.nonzero(m)
    for y, x in zip(ys_, xs_):
        if seen[y, x]:
            continue
        q = deque([(y, x)]); seen[y, x] = 1
        y0 = y1 = y; x0 = x1 = x; cnt = 0
        while q:
            cy, cx = q.popleft(); cnt += 1
            y0 = min(y0, cy); y1 = max(y1, cy); x0 = min(x0, cx); x1 = max(x1, cx)
            for ny, nx in ((cy+1, cx), (cy-1, cx), (cy, cx+1), (cy, cx-1)):
                if 0 <= ny < H and 0 <= nx < W and m[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = 1; q.append((ny, nx))
        comps.append((x0, y0, x1 + 1, y1 + 1, cnt))
    return comps


def handwriting_boxes(page, text_boxes, dpi=50):
    """dark-ink blobs (signatures / handwriting) that are not OCR text and not table rules."""
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    H, W = a.shape
    m = a < 120
    for b in text_boxes:  # erase recognised text
        x0, y0, x1, y1 = int((b[0] - .004) * W), int((b[1] - .003) * H), int((b[2] + .004) * W) + 1, int((b[3] + .003) * H) + 1
        m[max(0, y0):y1, max(0, x0):x1] = False
    # erase long straight rules (table lines)
    rows = m.sum(1); cols = m.sum(0)
    for y in range(H):
        if rows[y] > W * 0.15:
            m[y, :] = False
    for x in range(W):
        if cols[x] > H * 0.15:
            m[:, x] = False
    # dilate to join strokes
    md = m.copy()
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-3, -2, -1, 0, 1, 2, 3):
            md |= np.roll(np.roll(m, dy, 0), dx, 1)
    out = []
    for x0, y0, x1, y1, cnt in _components(md):
        w, h = (x1 - x0) / W, (y1 - y0) / H
        ink = m[y0:y1, x0:x1].sum()
        if w < 0.04 or h < 0.012 or w > 0.45 or h > 0.25 or ink < 25:
            continue
        if ink / max(1, (x1 - x0) * (y1 - y0)) > 0.35:
            continue
        out.append([x0 / W - .006, y0 / H - .006, x1 / W + .006, y1 / H + .006])
    return out


def ink_boxes(page, text_boxes, dpi=60, cell=5):
    """Everything on a scanned page that is ink but not recognised text and not a table rule: seals (also faint
    grey ones), signatures, stamps, logos, handwriting, text the OCR missed.
    -> [{"r": box, "dens": share of the box that is ink, "mean": mean grey of the ink (255 = white)}]"""
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).astype(int)
    H, W = a.shape
    m = a < int(np.median(a)) - 18                 # anything clearly darker than the paper
    for b in text_boxes:
        x0, y0, x1, y1 = int((b[0] - .006) * W), int((b[1] - .004) * H), int((b[2] + .006) * W) + 1, int((b[3] + .004) * H) + 1
        m[max(0, y0):y1, max(0, x0):x1] = False
    dark = a < 150
    m[dark.sum(1) > W * 0.15, :] = False           # table rules
    m[:, dark.sum(0) > H * 0.15] = False
    gh, gw = H // cell, W // cell
    g = m[:gh * cell, :gw * cell].reshape(gh, cell, gw, cell).sum((1, 3))
    out = []
    for x0, y0, x1, y1, _ in _components(g >= 3):
        w, h = (x1 - x0) / gw, (y1 - y0) / gh
        sub = m[y0 * cell:y1 * cell, x0 * cell:x1 * cell]
        ink = int(sub.sum())
        if w < 0.03 or h < 0.02 or ink < 60:
            continue
        out.append({"r": [round(float(max(0, x0 / gw - .004)), 4), round(float(max(0, y0 / gh - .004)), 4),
                          round(float(min(1, x1 / gw + .004)), 4), round(float(min(1, y1 / gh + .004)), 4)],
                    "dens": round(float(ink / max(1, sub.size)), 3), "mean": int(a[y0 * cell:y1 * cell, x0 * cell:x1 * cell][sub].mean())})
    return out


def edge_seal_like(b):
    """a faint, sparse mark at the left / right page edge: what a cross-page seal fragment looks like"""
    r = b["r"]
    w, h, cx = r[2] - r[0], r[3] - r[1], (r[0] + r[2]) / 2
    return (cx < 0.12 or cx > 0.88) and 0.025 <= w <= 0.16 and 0.04 <= h <= 0.30 and b["dens"] <= 0.40 \
        and b["mean"] >= 140 and r[1] > 0.03 and r[3] < 0.97
