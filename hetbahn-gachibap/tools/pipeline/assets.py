"""Build product cutouts (real product photos only) and KV-derived fallback logos.

All product imagery in the film comes from refs/ photos (real Hetbahn packaging),
so the container silhouette is the real one by construction.
"""
from pathlib import Path
import numpy as np
import cv2
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "work" / "assets"
OUT.mkdir(parents=True, exist_ok=True)


def grabcut(img_rgb, rect, bg_hint=None, iters=8):
    bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    mask = np.zeros(bgr.shape[:2], np.uint8)
    mask[:] = cv2.GC_BGD
    x, y, w, h = rect
    mask[y:y + h, x:x + w] = cv2.GC_PR_FGD
    if bg_hint is not None:
        mask[bg_hint & (mask == cv2.GC_PR_FGD)] = cv2.GC_PR_BGD
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    cv2.grabCut(bgr, mask, None, bgd, fgd, iters, cv2.GC_INIT_WITH_MASK)
    fg = ((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)).astype(np.uint8)
    # keep largest component, fill holes
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fg)
    if n > 1:
        k = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        fg = (lab == k).astype(np.uint8)
    cnts, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    filled = np.zeros_like(fg)
    cv2.drawContours(filled, cnts, -1, 1, -1)
    a = cv2.GaussianBlur(filled.astype(np.float32), (0, 0), 1.0)
    return np.clip(a, 0, 1)


def save_rgba(rgb, alpha, path, pad=6):
    ys, xs = np.where(alpha > 0.02)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, alpha.shape[0])
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, alpha.shape[1])
    rgba = np.dstack([rgb, (alpha * 255).astype(np.uint8)])[y0:y1, x0:x1]
    Image.fromarray(rgba, "RGBA").save(path)
    return rgba


def upscale_rgba(path, factor=2):
    im = Image.open(path)
    im = im.resize((im.width * factor, im.height * factor), Image.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    im.save(path)


def product_closed():
    """refs/02 left: real Hetbahn lid, 3/4 front-top view, pull-tab front-left."""
    im = np.array(Image.open(ROOT / "refs/02_product_front.jpeg").convert("RGB"))
    sub = im[:, :388].copy()
    white = (sub.min(axis=2) > 246)
    white[250:, 383:] = True  # neighbouring container photo
    a = grabcut(sub, (4, 8, 382, 390), bg_hint=white)
    save_rgba(sub, a, OUT / "bowl_closed.png")
    upscale_rgba(OUT / "bowl_closed.png", 2)


def product_side():
    """refs/02 bottom right: real empty container side view (20 facets) for silhouette QA."""
    im = np.array(Image.open(ROOT / "refs/02_product_front.jpeg").convert("RGB"))
    sub = im[240:404, 370:668].copy()
    white = (sub.min(axis=2) > 246)
    a = grabcut(sub, (8, 10, 285, 150), bg_hint=white)
    save_rgba(sub, a, OUT / "bowl_side.png")


def product_open():
    """KV poster bowl: real Hetbahn, lid peeled back, rice visible."""
    im = np.array(Image.open(ROOT / "refs/01_KV_poster.jpeg").convert("RGB"))
    sub = im[1110:1530, 340:1040].copy().astype(np.int32)
    r, g, b = sub[..., 0], sub[..., 1], sub[..., 2]
    reddish = (r - g > 70) & (r - b > 60)
    a = grabcut(sub.astype(np.uint8), (18, 22, 675, 392), bg_hint=reddish)
    save_rgba(sub.astype(np.uint8), a, OUT / "bowl_open.png")
    upscale_rgba(OUT / "bowl_open.png", 2)


def lid_front():
    """refs/04: real lid face-on (for macro/peel shots)."""
    im = np.array(Image.open(ROOT / "refs/04_container_lid_inside.jpeg").convert("RGB"))
    sub = im[30:340, 120:420].copy()
    a = grabcut(sub, (6, 6, 290, 300))
    save_rgba(sub, a, OUT / "lid_front.png")
    upscale_rgba(OUT / "lid_front.png", 3)


def kv_logo(box, name, scale=5):
    im = np.array(Image.open(ROOT / "refs/01_KV_poster.jpeg").convert("RGB")).astype(np.float32)
    x0, y0, x1, y1 = box
    g = im[y0:y1, x0:x1, 1]
    a = np.clip((g - 55) / (225 - 55), 0, 1)
    h, w = a.shape
    big = cv2.resize(a, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
    big = cv2.GaussianBlur(big, (0, 0), scale * 0.35)
    big = np.clip((big - 0.5) * 3.2 + 0.5, 0, 1)  # crisp vector-like edge
    rgba = np.zeros((h * scale, w * scale, 4), np.uint8)
    rgba[..., :3] = 255
    rgba[..., 3] = (big * 255).astype(np.uint8)
    ys, xs = np.where(rgba[..., 3] > 10)
    rgba = rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    Image.fromarray(rgba, "RGBA").save(OUT / name)


def fix_ring(name):
    """The KV screenshot is low-res, so the thin ring of the round logo breaks up.
    Refit that ring geometrically (centre/radius/width measured from the logo itself)."""
    im = np.array(Image.open(OUT / name))
    a = im[..., 3].astype(np.float32) / 255
    h, w = a.shape
    cy, cx = h / 2, w / 2
    yy, xx = np.mgrid[0:h, 0:w]
    rr = np.hypot(yy - cy, xx - cx)
    outer = rr > min(h, w) * 0.40
    r_vals = rr[outer & (a > 0.5)]
    r_out = np.percentile(r_vals, 97) if r_vals.size else min(h, w) / 2 - 2
    thick = max(3.0, min(h, w) * 0.012)
    ring = np.clip(1 - np.abs(rr - (r_out - thick / 2)) / (thick / 2) + 0.5, 0, 1)
    inner = np.where(rr < r_out - thick * 2.2, a, 0)
    im[..., 3] = (np.maximum(inner, ring) * 255).astype(np.uint8)
    Image.fromarray(im, "RGBA").save(OUT / name)


def logos():
    """Official logo PNGs in assets/ win; otherwise extract white logos from the official KV."""
    kv_logo((110, 82, 206, 186), "logo_hetbahn_kv.png")
    kv_logo((243, 84, 347, 186), "logo_hetbahn30_kv.png")
    fix_ring("logo_hetbahn_kv.png")


def resolve_logos():
    off1, off2 = ROOT / "assets/logo_hetbahn.png", ROOT / "assets/logo_hetbahn30.png"
    if off1.exists() and off2.exists():
        return off1, off2, "official"
    return OUT / "logo_hetbahn_kv.png", OUT / "logo_hetbahn30_kv.png", "kv_extract"


if __name__ == "__main__":
    product_closed(); product_side(); product_open(); lid_front(); logos()
    for p in sorted(OUT.glob("*.png")):
        print(p.name, Image.open(p).size)
