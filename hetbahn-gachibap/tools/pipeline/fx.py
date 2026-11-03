"""Shared drawing primitives. Every effect is a pure function of timeline time t."""
from functools import lru_cache
from pathlib import Path
import math
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
W, H = 1080, 1920
FPS = 30

# palette (CLAUDE.md / prompt section 4)
RICE = (0xF8, 0xF7, 0xF2)
SEOUL = (0x1C, 0x27, 0x33)
TUNG = (0xE9, 0xA8, 0x5B)
NYC = (0xDD, 0xE7, 0xEC)
DAY = (0xA9, 0xC2, 0xD1)
INK = (0x1A, 0x1A, 0x1A)
RED = (0xB5, 0x2A, 0x23)
YEL = (0xFF, 0xFC, 0x87)
GOLD = (0xF6, 0xB9, 0x4A)
IVORY = (0xEF, 0xE6, 0xD2)
AMBER = (0xF2, 0x9A, 0x2E)

FONT = {
    "title": str(ROOT / "fonts/BlackHanSans-Regular.ttf"),
    "body": str(ROOT / "fonts/GowunDodum-Regular.ttf"),
    "end": str(ROOT / "fonts/GowunBatang-Bold.ttf"),
    "endr": str(ROOT / "fonts/GowunBatang-Regular.ttf"),
}


def c01(c):
    return np.array(c, np.float32) / 255.0


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def spring(t, k=300.0, c=30.0, m=1.0):
    """Damped spring step response (stiffness 300, damping 30)."""
    if t <= 0:
        return 0.0
    w0 = math.sqrt(k / m)
    z = c / (2 * math.sqrt(k * m))
    if z >= 1:
        return 1 - math.exp(-w0 * t) * (1 + w0 * t)
    wd = w0 * math.sqrt(1 - z * z)
    return 1 - math.exp(-z * w0 * t) * (math.cos(wd * t) + (z * w0 / wd) * math.sin(wd * t))


def pop(t, k=420.0, c=16.0):
    """Bouncier spring for pop-in stickers."""
    return spring(t, k, c)


# ---------------------------------------------------------------- images
@lru_cache(maxsize=64)
def load_rgb(path):
    im = Image.open(ROOT / path).convert("RGB")
    return np.asarray(im, np.float32) / 255.0


@lru_cache(maxsize=64)
def load_rgba(path):
    im = Image.open(ROOT / path).convert("RGBA")
    return np.asarray(im, np.float32) / 255.0


def cover(img, w, h, zoom=1.0, cx=0.5, cy=0.5, rot=0.0):
    """Fill a w*h frame with img (cover fit), zoom>1 pushes in, cx/cy pan centre (0..1)."""
    ih, iw = img.shape[:2]
    s = max(w / iw, h / ih) * zoom
    ccx, ccy = cx * iw, cy * ih
    # keep inside image
    half_w, half_h = w / (2 * s), h / (2 * s)
    ccx = min(max(ccx, half_w), iw - half_w)
    ccy = min(max(ccy, half_h), ih - half_h)
    a = math.cos(rot) * s
    b = math.sin(rot) * s
    M = np.array([[a, -b, w / 2 - (a * ccx - b * ccy)], [b, a, h / 2 - (b * ccx + a * ccy)]], np.float32)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)


def place(dst, rgba, cx, cy, width, rot=0.0, alpha=1.0, tint=None, anchor="center"):
    """Composite rgba (float) centred at (cx,cy) with given pixel width."""
    if alpha <= 0.001 or width < 2:
        return dst
    ih, iw = rgba.shape[:2]
    s = width / iw
    ax, ay = iw / 2, (ih if anchor == "bottom" else ih / 2)
    a, b = math.cos(rot) * s, math.sin(rot) * s
    hh, ww = dst.shape[:2]
    M = np.array([[a, -b, cx - (a * ax - b * ay)], [b, a, cy - (b * ax + a * ay)]], np.float32)
    # only warp into the bounding box for speed
    corners = np.array([[0, 0, 1], [iw, 0, 1], [0, ih, 1], [iw, ih, 1]], np.float32) @ M.T
    x0 = int(max(math.floor(corners[:, 0].min()) - 2, 0))
    x1 = int(min(math.ceil(corners[:, 0].max()) + 2, ww))
    y0 = int(max(math.floor(corners[:, 1].min()) - 2, 0))
    y1 = int(min(math.ceil(corners[:, 1].max()) + 2, hh))
    if x1 <= x0 or y1 <= y0:
        return dst
    M2 = M.copy()
    M2[0, 2] -= x0
    M2[1, 2] -= y0
    layer = cv2.warpAffine(rgba, M2, (x1 - x0, y1 - y0), flags=cv2.INTER_CUBIC,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    col = layer[..., :3]
    if tint is not None:
        col = np.clip(col * np.array(tint, np.float32), 0, 1)
    al = np.clip(layer[..., 3:4] * alpha, 0, 1)
    region = dst[y0:y1, x0:x1]
    dst[y0:y1, x0:x1] = region * (1 - al) + col * al
    return dst


def add_layer(dst, layer_rgb, mask):
    m = mask[..., None] if mask.ndim == 2 else mask
    return dst * (1 - m) + layer_rgb * m


def soft_shadow(dst, cx, cy, w, h, strength=0.35, blur=0.25):
    hh, ww = dst.shape[:2]
    pad = int(max(w, h) * 0.8)
    x0, x1 = int(max(cx - w / 2 - pad, 0)), int(min(cx + w / 2 + pad, ww))
    y0, y1 = int(max(cy - h / 2 - pad, 0)), int(min(cy + h / 2 + pad, hh))
    if x1 <= x0 or y1 <= y0:
        return dst
    m = np.zeros((y1 - y0, x1 - x0), np.float32)
    cv2.ellipse(m, (int(cx - x0), int(cy - y0)), (int(w / 2), int(h / 2)), 0, 0, 360, 1.0, -1)
    m = cv2.GaussianBlur(m, (0, 0), max(w * blur * 0.5, 1))
    dst[y0:y1, x0:x1] *= (1 - strength * m)[..., None]
    return dst


# ---------------------------------------------------------------- text
@lru_cache(maxsize=512)
def text_rgba(text, font="body", size=48, color=(26, 26, 26), stroke=0, stroke_color=(0, 0, 0)):
    f = ImageFont.truetype(FONT[font], size)
    bbox = f.getbbox(text, stroke_width=stroke)
    w, h = bbox[2] - bbox[0] + 8, bbox[3] - bbox[1] + 8
    im = Image.new("RGBA", (max(w, 1), max(h, 1)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((4 - bbox[0], 4 - bbox[1]), text, font=f, fill=tuple(color) + (255,),
           stroke_width=stroke, stroke_fill=tuple(stroke_color) + (255,))
    return np.asarray(im, np.float32) / 255.0


def text_width(text, font="body", size=48):
    f = ImageFont.truetype(FONT[font], size)
    b = f.getbbox(text)
    return b[2] - b[0]


def put_text(dst, text, x, y, font="body", size=48, color=INK, alpha=1.0, anchor="mm", scale=1.0, rot=0.0,
             stroke=0, stroke_color=(0x6E, 0x12, 0x0E)):
    t = text_rgba(text, font, size, tuple(color), stroke, tuple(stroke_color)) if stroke else text_rgba(text, font, size, tuple(color))
    h, w = t.shape[:2]
    if anchor == "mm":
        cx, cy = x, y
    elif anchor == "lm":
        cx, cy = x + w * scale / 2, y
    else:  # rm
        cx, cy = x - w * scale / 2, y
    return place(dst, t, cx, cy, w * scale, rot=rot, alpha=alpha)


@lru_cache(maxsize=64)
def halftone_text(text, size, fill=(255, 255, 255), shadow=(0x7A, 0x14, 0x10), spans=None):
    """Card title: Black Han Sans + halftone drop shadow (KV style). spans: ((start,end,color),...)"""
    f = ImageFont.truetype(FONT["title"], size)
    bbox = f.getbbox(text)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = int(size * 0.35)
    Wc, Hc = tw + pad * 2, th + pad * 2
    base = Image.new("L", (Wc, Hc), 0)
    ImageDraw.Draw(base).text((pad - bbox[0], pad - bbox[1]), text, font=f, fill=255)
    m = np.asarray(base, np.float32) / 255
    # halftone shadow offset down-right
    off = max(int(size * 0.07), 3)
    sh = np.zeros_like(m)
    sh[off:, off:] = m[:-off, :-off]
    sh = cv2.dilate(sh, np.ones((3, 3)), iterations=max(1, size // 60))
    step = max(int(size * 0.07), 5)
    yy, xx = np.mgrid[0:Hc, 0:Wc]
    dots = (((xx % step) - step / 2) ** 2 + ((yy % step) - step / 2) ** 2) < (step * 0.36) ** 2
    shadow_mask = np.clip(sh * dots - m, 0, 1)
    rgba = np.zeros((Hc, Wc, 4), np.float32)
    rgba[..., :3] = c01(shadow)
    rgba[..., 3] = shadow_mask
    col = np.ones((Hc, Wc, 3), np.float32) * c01(fill)
    if spans:
        for (s, e, c) in spans:
            x_s = pad + f.getlength(text[:s])
            x_e = pad + f.getlength(text[:e])
            col[:, int(x_s):int(x_e) + 2] = c01(c)
    rgba[..., :3] = rgba[..., :3] * (1 - m[..., None]) + col * m[..., None]
    rgba[..., 3] = np.maximum(rgba[..., 3], m)
    return rgba


# ---------------------------------------------------------------- noise / grain
@lru_cache(maxsize=4)
def fbm(h, w, seed=7, octaves=5):
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        gh, gw = max(2, h // (256 >> o)), max(2, w // (256 >> o))
        g = rng.random((gh + 1, gw + 1)).astype(np.float32)
        out += amp * cv2.resize(g, (w, h), interpolation=cv2.INTER_CUBIC)
        tot += amp
        amp *= 0.5
    out /= tot
    return (out - out.min()) / (out.max() - out.min() + 1e-6)


@lru_cache(maxsize=2)
def grain_bank(n=12, seed=3):
    rng = np.random.default_rng(seed)
    bank = []
    for _ in range(n):
        g = rng.normal(0, 1, (H // 2, W // 2)).astype(np.float32)
        g = cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR)
        bank.append(g)
    return bank


def finish(frame, t, grain=0.022, halation=0.10):
    """Film finish: halation on highlights + grain. Applied to photographic shots."""
    if halation > 0:
        small = cv2.resize(frame, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
        hi = np.clip(small - 0.78, 0, 1) * 3.0
        hi = cv2.GaussianBlur(hi, (0, 0), 6)
        hi = cv2.resize(hi, (W, H), interpolation=cv2.INTER_LINEAR)
        frame = frame + halation * hi * np.array([1.0, 0.82, 0.68], np.float32)
    if grain > 0:
        g = grain_bank()[int(t * FPS) % 12]
        lum = frame.mean(axis=2, keepdims=True)
        frame = frame + grain * g[..., None] * (0.6 + 0.4 * (1 - lum))
    return np.clip(frame, 0, 1)


# ---------------------------------------------------------------- KV card background
@lru_cache(maxsize=4)
def kv_background(w=W, h=H, seed=1):
    """Red full field + halftone dot gradient (radial, KV refs/01)."""
    bg = np.ones((h, w, 3), np.float32) * c01(RED)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # radial glow centre and dot density
    cy, cx = h * 0.44, w * 0.5
    r = np.hypot((xx - cx) / w, (yy - cy) / h)
    glow = np.clip(1 - r * 1.9, 0, 1) ** 1.6
    bg += glow[..., None] * np.array([0.10, 0.03, 0.02], np.float32)
    step = 18
    gx = (xx % step) - step / 2
    gy = (yy % step) - step / 2
    d = np.hypot(gx, gy)
    # dots: bright near the centre glow, and a second band at the bottom (like KV)
    bottom = np.clip((yy / h - 0.70) / 0.30, 0, 1)
    rad = step * 0.42 * np.clip(glow * 0.9, 0, 1) + step * 0.30 * bottom * (0.5 + 0.5 * np.sin(xx / w * 9.0 + 1.3) ** 2)
    dots = np.clip(rad - d + 0.5, 0, 1)
    dot_col = np.where(bottom[..., None] > 0.01, np.array([0.80, 0.30, 0.27], np.float32), np.array([1.0, 0.86, 0.84], np.float32))
    bg = bg * (1 - dots[..., None] * 0.55) + dot_col * dots[..., None] * 0.55
    return np.clip(bg, 0, 1)


def gold_trail(dst, t, t0, dur, cx=W / 2, cy=H * 0.45, rx=430, ry=170, turns=1.35, tilt=-0.18, width=7, phase=0.0):
    """Golden orbit line drawn on over time (KV gold trajectory). Pure function of t."""
    p = ease_out((t - t0) / dur) if dur > 0 else 1.0
    if p <= 0:
        return dst
    n = 260
    th = np.linspace(phase, phase + 2 * math.pi * turns * p, n)
    x = cx + rx * np.cos(th)
    y = cy + ry * np.sin(th) + (th - phase) * -55
    ct, st = math.cos(tilt), math.sin(tilt)
    X = cx + (x - cx) * ct - (y - cy) * st
    Y = cy + (x - cx) * st + (y - cy) * ct
    Hh, Ww = dst.shape[:2]
    layer = np.zeros((Hh // 2, Ww // 2), np.float32)
    pts = np.stack([X / 2, Y / 2], 1).astype(np.int32)
    for i in range(len(pts) - 1):
        a = 0.25 + 0.75 * (i / n)
        cv2.line(layer, tuple(pts[i]), tuple(pts[i + 1]), a, max(1, width // 2), cv2.LINE_AA)
    glow = cv2.GaussianBlur(layer, (0, 0), 6)
    core = cv2.resize(layer, (Ww, Hh), interpolation=cv2.INTER_LINEAR)
    glow = cv2.resize(glow, (Ww, Hh), interpolation=cv2.INTER_LINEAR)
    gc = np.array([1.0, 0.78, 0.35], np.float32)
    dst = dst + glow[..., None] * gc * 0.9 + core[..., None] * np.array([1.0, 0.93, 0.70], np.float32) * 0.9
    # head sparkle
    hx, hy = X[-1], Y[-1]
    sparkle(dst, hx, hy, 34, 1.0)
    return np.clip(dst, 0, 1)


def sparkle(dst, x, y, size, a=1.0, color=(1.0, 0.97, 0.88)):
    """4-point star (not an orb)."""
    if a <= 0.01:
        return dst
    s = int(size)
    x0, y0 = int(x - s), int(y - s)
    if x0 < 0 or y0 < 0 or x0 + 2 * s >= dst.shape[1] or y0 + 2 * s >= dst.shape[0]:
        return dst
    yy, xx = np.mgrid[-s:s, -s:s].astype(np.float32) / s
    star = np.clip(1 - (np.abs(xx) ** 0.5 + np.abs(yy) ** 0.5) * 1.15, 0, 1) ** 1.5
    region = dst[y0:y0 + 2 * s, x0:x0 + 2 * s]
    region[:] = np.clip(region + star[..., None] * np.array(color, np.float32) * a, 0, 1)
    return dst


# ---------------------------------------------------------------- steam
_SPR = {}


def _splat(layer, x, y, r, a, hard=False, asp=1.0):
    """Additive gaussian splat (overlapping puffs accumulate density); asp > 1 stretches it vertically (wisps)."""
    ri = int(r * 2.2 * max(1.0, asp)) + 1
    key = (ri, round(r, 1), hard, round(asp, 1))
    if key not in _SPR:
        yy, xx = np.mgrid[-ri:ri + 1, -ri:ri + 1].astype(np.float32)
        d2 = (xx ** 2) / (r * r) + (yy ** 2) / ((r * asp) ** 2)
        _SPR[key] = np.clip(1.2 - d2 ** 1.5, 0, 1) if hard else np.exp(-d2 * 1.2)
    spr = _SPR[key]
    h, w = layer.shape
    xi, yi = int(x), int(y)
    x0, y0, x1, y1 = xi - ri, yi - ri, xi + ri + 1, yi + ri + 1
    sx0, sy0 = max(0, -x0), max(0, -y0)
    x0c, y0c, x1c, y1c = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
    if x1c <= x0c or y1c <= y0c:
        return
    layer[y0c:y1c, x0c:x1c] += spr[sy0:sy0 + (y1c - y0c), sx0:sx0 + (x1c - x0c)] * a


def steam(dst, t, t0, sources, seed=11, n=140, strength=1.0, rise=320, spread=60, cotton=False, burst=True,
          tint=(1, 1, 1), max_age=2.2):
    """Seeded steam particles. pos = p0 + rise*age + curl-ish(p0, age)*amp*age.
    sources: list of (x, y, width). Pure function of t."""
    if t < t0:
        return dst
    rng = np.random.default_rng(seed)
    Hh, Ww = dst.shape[:2]
    layer = np.zeros((Hh // 4, Ww // 4), np.float32)
    k = len(sources)
    births = rng.uniform(0, 3.5, n)
    if burst:
        births[: n // 3] = rng.uniform(0, 0.4, n // 3)  # 0.4 s burst
    lane = rng.integers(0, k, n)
    ox = rng.uniform(-0.5, 0.5, n)
    ph = rng.uniform(0, 6.28, n)
    sp = rng.uniform(0.75, 1.25, n)
    el = t - t0
    for i in range(n):
        age = el - births[i]
        if age < 0 or age > max_age:
            continue
        sx, sy, sw = sources[lane[i]]
        x = sx + ox[i] * sw * 0.7
        y = sy
        a = age * sp[i]
        cx = x + math.sin(ph[i] + a * 2.1 + x * 0.01) * spread * a * 0.6 + math.sin(a * 3.7 + ph[i]) * 10 * a
        cy = y - rise * a - 40 * a * a
        life = age / max_age
        alpha = (1 - life) ** 1.4 * min(1.0, age / 0.15)
        if cotton:
            r = (14 + 46 * a) * 1.6
            _splat(layer, cx / 4, cy / 4, max(1.5, r / 4), alpha * 0.55, hard=True)
        else:  # thin laminar wisps that thin out and curl at the edges
            r = 6 + 20 * a
            _splat(layer, cx / 4, cy / 4, max(1.2, r / 4), alpha * 0.42, asp=2.2 - 0.8 * min(1.0, a))
    layer = cv2.GaussianBlur(layer, (0, 0), 1.2 if not cotton else 1.0)
    layer = cv2.resize(layer, (dst.shape[1], dst.shape[0]), interpolation=cv2.INTER_LINEAR)
    m = np.clip(1 - np.exp(-layer * strength * (1.5 if cotton else 1.0)), 0, 0.92)
    col = np.array(tint, np.float32)
    return dst * (1 - m[..., None]) + col * m[..., None]


# ---------------------------------------------------------------- product overlays
def link_mark(dst, x, y, size, heat=0.0, flash=0.0, rot=-0.35):
    """Embossed rice-grain mark next to the red badge; ivory -> amber (thermochromic concept)."""
    col = c01(IVORY) * (1 - heat) + c01(AMBER) * heat
    col = np.clip(col + flash * 0.25, 0, 1)
    s = int(size * 2.4)
    x0, y0 = int(x - s), int(y - s)
    if x0 < 0 or y0 < 0 or x0 + 2 * s > dst.shape[1] or y0 + 2 * s > dst.shape[0]:
        return dst
    m = np.zeros((2 * s, 2 * s), np.float32)
    cv2.ellipse(m, (s, s), (int(size * 0.42), int(size * 0.72)), math.degrees(rot), 0, 360, 1.0, -1, cv2.LINE_AA)
    m = cv2.GaussianBlur(m, (0, 0), 0.8)
    em = np.zeros_like(m)
    em[2:, 2:] = m[:-2, :-2]  # emboss shadow
    region = dst[y0:y0 + 2 * s, x0:x0 + 2 * s]
    region *= (1 - 0.18 * np.clip(em - m, 0, 1))[..., None]
    g = heat * 0.55 + flash * 0.7
    if g > 0:
        halo = cv2.GaussianBlur(m, (0, 0), size * 0.55) * g
        region += halo[..., None] * c01(AMBER) * 0.9
    region[:] = region * (1 - m[..., None]) + col * m[..., None]
    hl = np.zeros_like(m)
    cv2.ellipse(hl, (s - int(size * 0.12), s - int(size * 0.3)), (max(1, int(size * 0.1)), max(1, int(size * 0.22))),
                math.degrees(rot), 0, 360, 1.0, -1, cv2.LINE_AA)
    region += cv2.GaussianBlur(hl, (0, 0), 1.0)[..., None] * 0.35
    np.clip(region, 0, 1, out=region)
    return dst


# geometry of the real product cutouts (pixel coords in work/assets/*)
BOWL_CLOSED = dict(path="work/assets/bowl_closed210.png", size=(1342, 718), mark=(275.8, 103.9), tab=(101.4, 468.2))
OPEN_DY = -29.0  # open photo centre vs closed composite centre, in source px (same 1342 px width)


def mark_xy(cx, cy, width):
    """Link-mark position for a closed bowl placed centred at (cx, cy) with given width."""
    w0, h0 = BOWL_CLOSED["size"]
    k = width / w0
    return cx + (BOWL_CLOSED["mark"][0] - w0 / 2) * k, cy + (BOWL_CLOSED["mark"][1] - h0 / 2) * k


def mark_size(width):
    return max(6, int(width * 0.045))


def open_center(cx, cy, width):
    return cx, cy + OPEN_DY * width / BOWL_CLOSED["size"][0]
LID_FRONT = dict(path="work/assets/lid_front.png", badge=(295, 353), badge_r=(140, 160))
BOWL_OPEN = dict(path="work/assets/bowl_open.png")


def bowl_closed_img(lift=0.0, dome=0.0):
    """Real closed bowl. lift (source px) peels the front-left pull-tab corner of the film up around a hinge:
    the flap is cut from the photo, rotated/raised, the gap under it is shaded (caller springs it back)."""
    img = load_rgba(BOWL_CLOSED["path"])
    if lift <= 0.01 and dome <= 0.001:
        return img
    h, w = img.shape[:2]
    out = img.copy()
    if dome > 0:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        cx, cy = w * 0.5, h * 0.36
        r = np.hypot((xx - cx) / (w * 0.5), (yy - cy) / (h * 0.36))
        bulge = np.clip(1 - r, 0, 1) ** 2
        out = cv2.remap(out, xx, yy + bulge * dome * 10, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    if lift > 0.5:
        tx, ty = BOWL_CLOSED["tab"]
        R = 260.0
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        d = np.hypot(xx - tx, (yy - ty) * 1.4)
        lid_zone = (yy < h * 0.80).astype(np.float32)
        m = np.clip((R - d) / 25.0, 0, 1) * lid_zone * out[..., 3]
        flap = out * m[..., None]
        # hinge = far edge of the flap; rotate the flap up about it
        hx, hy = tx + R * 0.75, ty - R * 0.35
        ang = -min(lift, 120) * 0.0022
        M = cv2.getRotationMatrix2D((hx, hy), math.degrees(ang), 1.0)
        M[1, 2] -= lift
        M[0, 2] -= lift * 0.15
        flap_t = cv2.warpAffine(flap, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
        # gap under the raised film: the inner rim shows, darker
        gap = m * np.clip(lift / 30.0, 0, 1)
        out[..., :3] *= (1 - 0.20 * gap)[..., None]
        # contact shadow of the flap
        sh = cv2.GaussianBlur(flap_t[..., 3], (0, 0), 6)
        sh = np.roll(sh, int(lift * 0.6), axis=0)
        out[..., :3] *= (1 - 0.14 * np.clip(sh, 0, 1))[..., None]
        fa = flap_t[..., 3:4]
        # underside of the film is slightly brighter (white back of the lid) near the edge
        flap_col = np.clip(flap_t[..., :3] / np.maximum(fa, 1e-4) * 1.02, 0, 1)
        out[..., :3] = out[..., :3] * (1 - fa) + flap_col * fa
        out[..., 3:4] = np.maximum(out[..., 3:4], fa)
    return out


def ui_card(w, h, r, color, shadow=0.25):
    """Rounded card rgba with soft shadow."""
    pad = 30
    m = np.zeros((h + 2 * pad, w + 2 * pad), np.float32)
    cv2.rectangle(m, (pad + r, pad), (pad + w - r, pad + h), 1, -1)
    cv2.rectangle(m, (pad, pad + r), (pad + w, pad + h - r), 1, -1)
    for (cx, cy) in [(pad + r, pad + r), (pad + w - r, pad + r), (pad + r, pad + h - r), (pad + w - r, pad + h - r)]:
        cv2.circle(m, (cx, cy), r, 1, -1, cv2.LINE_AA)
    sh = cv2.GaussianBlur(np.roll(m, 10, axis=0), (0, 0), 14) * shadow
    rgba = np.zeros(m.shape + (4,), np.float32)
    rgba[..., :3] = c01(color)
    rgba[..., 3] = np.maximum(m, sh)
    rgba[..., :3] = rgba[..., :3] * (m / np.maximum(rgba[..., 3], 1e-4))[..., None]
    return rgba
