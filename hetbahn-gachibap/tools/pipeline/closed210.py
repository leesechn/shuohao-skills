"""Closed 210 g Hetbahn in 3/4 view, built only from real photos so open/closed states match:
container = KV bowl (refs/01) below the rim, lid = real 210 g lid (refs/04) projected onto the rim ellipse."""
from pathlib import Path
import sys
import numpy as np
import cv2
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
A = ROOT / "work" / "assets"
RIM = dict(cx=672, cy=322, a=664, b=250)  # rim ellipse in bowl_open.png pixels


def build(cy=RIM["cy"], b=RIM["b"], out=A / "bowl_closed210.png"):
    o = np.asarray(Image.open(A / "bowl_open.png")).astype(np.float32) / 255
    lid = np.asarray(Image.open(A / "lid_front.png")).astype(np.float32) / 255
    h, w = o.shape[:2]
    cx, a = RIM["cx"], RIM["a"]
    # erode the lid alpha a little (removes the light fringe of the cut-out)
    la = cv2.erode(lid[..., 3], np.ones((5, 5), np.uint8))
    la = cv2.GaussianBlur(la, (0, 0), 1.0)
    lid = lid.copy(); lid[..., 3] = la
    ys, xs = np.where(la > 0.5)
    lx0, lx1, ly0, ly1 = xs.min(), xs.max(), ys.min(), ys.max()
    # map lid bbox -> rim ellipse bbox (affine squash, slight shear for the 3/4 view)
    src = np.float32([[lx0, ly0], [lx1, ly0], [lx0, ly1]])
    dst = np.float32([[cx - a, cy - b], [cx + a, cy - b], [cx - a, cy + b]])
    M = cv2.getAffineTransform(src, dst)
    pad_top = 0
    lw = cv2.warpAffine(lid, M, (w, h), flags=cv2.INTER_CUBIC, borderValue=(0, 0, 0, 0))
    # container part: keep the open-bowl pixels only below the rim centre line, lid covers the rest
    yy = np.arange(h)[:, None]
    keep = (yy >= cy).astype(np.float32)
    keep = cv2.GaussianBlur(np.repeat(keep, w, 1), (0, 0), 2)
    base = o.copy()
    base[..., 3] *= keep
    # rim flange visible as a thin band in front of the lid edge
    out_img = base.copy()
    la_w = lw[..., 3:4]
    shade = 0.97 - 0.06 * (yy[..., None] - (cy - b)) / (2 * b)
    out_img[..., :3] = base[..., :3] * base[..., 3:4] * (1 - la_w) + lw[..., :3] * np.clip(shade, 0.85, 1) * la_w
    out_img[..., 3:4] = np.clip(base[..., 3:4] * (1 - la_w) + la_w, 0, 1)
    out_img[..., :3] = out_img[..., :3] / np.maximum(out_img[..., 3:4], 1e-4)
    # thin lid edge line
    ring = np.zeros((h, w), np.float32)
    cv2.ellipse(ring, (cx, cy), (a - 2, b - 2), 0, 0, 180, 1.0, 3, cv2.LINE_AA)
    out_img[..., :3] *= (1 - 0.10 * ring[..., None])
    # crop to content
    ys, xs = np.where(out_img[..., 3] > 0.02)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    crop = out_img[y0:y1, x0:x1]
    Image.fromarray((np.clip(crop, 0, 1) * 255).astype(np.uint8), "RGBA").save(out)
    # where the lid badge and tab ended up (for link mark / tab lift)
    def mp(x, y):
        v = M @ np.array([x, y, 1.0])
        return float(v[0] - x0), float(v[1] - y0)
    meta = dict(size=(int(x1 - x0), int(y1 - y0)), badge=mp(295, 353), mark=mp(195, 200), tab=mp(lx0 + 60, ly1 - 60),
                open_offset=(-float(x0), -float(y0)))
    (A / "bowl_closed210.json").write_text(__import__("json").dumps(meta))
    return meta


if __name__ == "__main__":
    print(build())
