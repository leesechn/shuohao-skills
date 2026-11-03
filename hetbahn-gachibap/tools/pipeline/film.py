"""햇반 같이밥: 33 s, 9:16, 1080x1920, 30 fps. 15 shots on a 90 BPM grid.

Every frame is a pure function of (version, t). version: "real" | "mini".
Product imagery = real Hetbahn photos from refs/ (cut out in assets.py).
People/places = AI stills in work/stills (Figma AI / Runway, see proof ledger).
"""
import math
import numpy as np
import cv2

from fx import (W, H, FPS, RICE, SEOUL, TUNG, NYC, DAY, INK, RED, YEL, IVORY, AMBER,
                c01, clamp, ease_out, ease_in_out, spring, pop, load_rgb, load_rgba, cover, place,
                soft_shadow, text_rgba, put_text, text_width, halftone_text, fbm, finish, kv_background,
                gold_trail, sparkle, steam, link_mark, bowl_closed_img, ui_card, BOWL_CLOSED, LID_FRONT,
                BOWL_OPEN)
from assets import resolve_logos

BEAT = 60 / 90  # 0.6667 s
CUTS = [0.0, 4, 6, 9, 12.5, 15, 18, 20, 24, 28, 32, 34, 38, 41.5, 44.5, 49.5]  # in beats
CUTS = [round(b * BEAT, 4) for b in CUTS]
SHOTS = ["S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09", "S10", "S11", "S12", "S13", "S14", "S15"]
DUR = CUTS[-1]  # 33.0 s
HALF = H // 2

# placements of the real product on AI stills (still pixel coords): cx, base_y, width
PLACE = {
    "S04a_real": (512, 935, 390), "S04b_real": (512, 935, 390),
    "S04a_mini": (512, 738, 300), "S04b_mini": (430, 722, 300),
    "S10_real": [(282, 858, 118), (500, 858, 118)], "S10_mini": [(300, 905, 120), (470, 905, 120)],
    "S12a_real": [(560, 585, 175), (790, 575, 175)], "S12b_real": [(590, 625, 175), (975, 650, 175)],
    "S12c_real": [(470, 700, 175), (950, 690, 175)],
    "S12a_mini": [(520, 545, 150), (860, 545, 150)], "S12b_mini": [(520, 500, 150), (860, 500, 150)],
    "S12c_mini": [(560, 520, 130), (905, 568, 140)],
}

LOGO1, LOGO2, LOGO_SRC = resolve_logos()


def shot_at(t):
    for i in range(len(SHOTS)):
        if t < CUTS[i + 1] or i == len(SHOTS) - 1:
            return SHOTS[i], t - CUTS[i], CUTS[i + 1] - CUTS[i]
    return SHOTS[-1], 0, 1


def still(v, name):
    ext = "jpg" if name == "S10" and v == "real" else "png"
    return load_rgb(f"work/stills/{name}_{v}.{ext}")


def paper(frame, v, t):
    """Miniature version: craft-paper texture on code-drawn graphics."""
    if v != "mini":
        return frame
    n = fbm(H // 4, W // 4, seed=21, octaves=4)
    n = cv2.resize(n, (W, H))
    return np.clip(frame * (0.93 + 0.09 * n[..., None]), 0, 1)


# =================================================================== chat UI
CHAT_LOG = [
    ("2016. 3. 2.", "언제 밥 한번 먹자", "ㅇㅇ 언제 한번 ㅋㅋ"),
    ("2018. 9. 14.", "언제 밥 한번 먹자", "ㅇㅇ 언제 한번 ㅋㅋ"),
    ("2021. 12. 24.", "언제 밥 한번 먹자", "ㅇㅇ 언제 한번 ㅋㅋ"),
    ("2024. 5. 8.", "언제 밥 한번 먹자", "ㅇㅇ 언제 한번 ㅋㅋ"),
    ("2026. 11. 13.", "언제 밥 한번 먹자", "ㅇㅇ 언제 한번 ㅋㅋ"),
]


def bubble(text, mine, size=58):
    t = text_rgba(text, "body", size, (255, 255, 255) if mine else INK)
    th, tw = t.shape[:2]
    w, h = tw + 64, th + 40
    card = ui_card(w, h, 34, SEOUL if mine else (255, 255, 255), shadow=0.10 if mine else 0.18)
    ch, cw = card.shape[:2]
    oy, ox = (ch - th) // 2 - 4, (cw - tw) // 2
    a = t[..., 3:4]
    card[oy:oy + th, ox:ox + tw, :3] = card[oy:oy + th, ox:ox + tw, :3] * (1 - a) + t[..., :3] * a
    return card


_bub = {}


def get_bubble(text, mine, size=58):
    k = (text, mine, size)
    if k not in _bub:
        _bub[k] = bubble(text, mine, size)
    return _bub[k]


def chat_header(f, name="준호", sub="뉴욕"):
    f[250:400] = f[250:400] * 0.0 + np.array([0.985, 0.982, 0.97], np.float32)
    put_text(f, name, 120, 310, "body", 54, INK, anchor="lm")
    put_text(f, sub, 122, 362, "body", 32, (110, 110, 110), anchor="lm")
    f[398:401] = c01((225, 222, 214))
    return f


def chat_stack(f, t, scroll, items_visible, appear_times):
    """Draw chat items from the bottom up, offset by scroll (px)."""
    y = 1530 + scroll
    rows = []
    for i, (date, a, b) in enumerate(CHAT_LOG[:items_visible]):
        rows.append(("date", date, i))
        rows.append(("me", a, i))
        rows.append(("you", b, i))
    # lay out top->bottom from a start computed backward
    heights = {"date": 60, "me": 128, "you": 128}
    total = sum(heights[r[0]] for r in rows)
    y0 = y - total
    for kind, text, i in rows:
        hgt = heights[kind]
        ta = appear_times[i] if i < len(appear_times) else -1
        k = 1.0 if ta < 0 else clamp(spring(t - ta - (0.0 if kind != "you" else 0.18)))
        if kind == "date":
            if 400 < y0 + 35 < 1650:
                put_text(f, text, W / 2, y0 + 30, "body", 34, (130, 128, 122), alpha=min(1, k * 1.5))
        else:
            b = get_bubble(text, kind == "me")
            bw = b.shape[1]
            cx = (W - 60 - bw / 2 + 30) if kind == "me" else (60 + bw / 2 - 30)
            cy = y0 + hgt / 2
            if 380 < cy and cy + b.shape[0] / 2 + (1 - k) * 40 <= 1580 and k > 0.01:  # keep Reels safe area
                place(f, b, cx, cy + (1 - k) * 40, bw * (0.85 + 0.15 * k), alpha=min(1, k * 1.6))
        y0 += hgt
    return f


def s01(v, t, d):
    f = np.ones((H, W, 3), np.float32) * c01(RICE)
    # chat already complete at frame 0 (thumbnail); 2024 & 2026 entries land on beats
    appear = [-1, -1, -1, -1, BEAT * 1.5]
    vis = 5
    scroll = 316 * (1 - spring(t - BEAT * 1.5))  # the 2026 message lands and pushes the stack up
    zoom = 1.0 + 0.05 * ease_in_out(t / d)
    chat_stack(f, t, scroll, vis, appear)
    chat_header(f)
    # macro push-in
    f = cover(f, W, H, zoom=zoom, cx=0.5, cy=0.62)
    return paper(f, v, t)


def s02(v, t, d):
    f = kv_background().copy()
    f = gold_trail(f, t, -0.3, 1.1, cy=H * 0.47, phase=0.6)
    k = pop(t - 0.05)
    title = halftone_text("10년째 빈말.", 190, spans=((5, 7, YEL),))
    place(f, title, W / 2, H * 0.47, title.shape[1] * (0.6 + 0.4 * k), alpha=min(1, k * 2), rot=-0.03 * (1 - k))
    for i, (x, y) in enumerate([(220, 640), (880, 760), (840, 1220)]):
        sparkle(f, x, y, 26 + 8 * math.sin(t * 9 + i), 0.9 * clamp((t - 0.1 * i) * 3))
    f = cover(f, W, H, zoom=1.0 + 0.10 * ease_in_out(t / d), rot=0.02 * ease_in_out(t / d))
    return paper(f, v, t)


def s03(v, t, d):
    """Typing 'let's eat sometime' -> delete -> press '같이밥 보내기' -> pair box splits."""
    f = np.ones((H, W, 3), np.float32) * c01(RICE)
    if t < 1.05:
        chat_stack(f, 0, -360, 5, [])
        chat_header(f)
        # input bar
        bar = ui_card(940, 110, 55, (255, 255, 255), shadow=0.18)
        place(f, bar, W / 2, 1490, bar.shape[1])
        full = "언제 밥 한번 먹자"
        n_type = int(clamp(t / 0.42) * len(full))
        n_del = int(clamp((t - 0.48) / 0.25) * len(full))
        txt = full[:max(0, n_type - n_del)]
        if txt:
            put_text(f, txt, 110, 1490, "body", 46, INK, anchor="lm")
        caret_x = 112 + (text_width(txt, "body", 46) if txt else 0)
        if int(t * 6) % 2 == 0:
            f[1462:1518, int(caret_x):int(caret_x) + 4] = c01(INK)
        # 같이밥 보내기 button (appears after delete, pressed on beat)
        kb = pop(t - 0.72)
        press = 1 - 0.08 * math.exp(-((t - 0.95) / 0.05) ** 2)
        btn = ui_card(470, 120, 60, RED, shadow=0.3)
        lab = text_rgba("같이밥 보내기", "title", 54, (255, 255, 255))
        bh, bw = lab.shape[:2]
        oy, ox = (btn.shape[0] - bh) // 2, (btn.shape[1] - bw) // 2
        btn = btn.copy()
        a = lab[..., 3:4]
        btn[oy:oy + bh, ox:ox + bw, :3] = btn[oy:oy + bh, ox:ox + bw, :3] * (1 - a) + lab[..., :3] * a
        if kb > 0.01:
            place(f, btn, W / 2, 1330, btn.shape[1] * kb * press, alpha=min(1, kb * 2))
        f = cover(f, W, H, zoom=1.0 + 0.08 * ease_in_out(t / 1.05), cx=0.5, cy=0.70)
        return paper(f, v, t)
    # ---- pair box: two real bowls in a clear sleeve; sleeve slides off; one drops to NY
    u = t - 1.05
    split = ease_in_out((u - 0.35) / 0.55)
    top_col = c01(RICE) * (1 - split) + c01(SEOUL) * split
    bot_col = c01(RICE) * (1 - split) + c01(NYC) * split
    f[:HALF] = top_col
    f[HALF:] = bot_col
    bowl = load_rgba(BOWL_CLOSED["path"])
    bw = 430
    # positions: start side-by-side at centre, end Seoul upper / NY lower
    p = ease_in_out((u - 0.25) / 0.6)
    x1 = W / 2 - 230 * (1 - p)
    y1 = H * 0.5 - (H * 0.25) * p
    x2 = W / 2 + 230 * (1 - p)
    yfall = H * 0.5 + (H * 0.25) * (p ** 1.6)
    for (x, y) in [(x1, y1), (x2, yfall)]:
        soft_shadow(f, x, y + 120, bw * 0.8, 50, 0.25)
        place(f, bowl, x, y, bw)
    # link marks face each other and light once
    blink = math.exp(-((u - 0.18) / 0.08) ** 2)
    for (x, y) in [(x1, y1), (x2, yfall)]:
        mx = x + (85 - 380) * bw / 760
        my = y + (184 - 278) * bw / 760
        link_mark(f, int(mx), int(my), 18, heat=0.3 * blink, flash=blink)
    # clear sleeve sliding off upward
    sl = ease_in_out(u / 0.32)
    sleeve = np.zeros((H, W), np.float32)
    sy = int(H * 0.5 - 220 - sl * 1100)
    cv2.rectangle(sleeve, (W // 2 - 500, sy), (W // 2 + 500, sy + 440), 1, -1)
    sleeve = cv2.GaussianBlur(sleeve, (0, 0), 3)
    f += sleeve[..., None] * 0.035
    edge = np.abs(cv2.Sobel(sleeve, cv2.CV_32F, 0, 1)) + np.abs(cv2.Sobel(sleeve, cv2.CV_32F, 1, 0))
    f += np.clip(edge * 2, 0, 0.5)[..., None]
    # fall trajectory -> becomes the split line
    if p > 0.05:
        line = np.zeros((H, W), np.float32)
        lw = int(W * ease_out((u - 0.5) / 0.4))
        cv2.line(line, (W // 2 - lw // 2, HALF), (W // 2 + lw // 2, HALF), 1, 4, cv2.LINE_AA)
        line = cv2.GaussianBlur(line, (0, 0), 2)
        f = f * (1 - line[..., None]) + line[..., None] * np.array([1, 1, 1], np.float32)
    put_text(f, "서울 21:00", 150, 330, "body", 40, (240, 240, 240), alpha=split, anchor="lm")
    put_text(f, "뉴욕 08:00", 150, HALF + 90, "body", 40, INK, alpha=split, anchor="lm")
    return paper(f, v, t)


# =================================================================== split helpers
def still_to_frame(name, v, w, h, zoom, cx, cy):
    """Return transform (s, ox, oy) that cover() applies so composites can follow the camera."""
    img = still(v, name)
    ih, iw = img.shape[:2]
    s = max(w / iw, h / ih) * zoom
    ccx, ccy = cx * iw, cy * ih
    half_w, half_h = w / (2 * s), h / (2 * s)
    ccx = min(max(ccx, half_w), iw - half_w)
    ccy = min(max(ccy, half_h), ih - half_h)
    return s, w / 2 - s * ccx, h / 2 - s * ccy


def half_with_bowl(v, name, t, d, z0, z1, cy, lift=0.0, heat=0.0, flash=0.0, tint=(1, 1, 1), dome=0.0):
    z = z0 + (z1 - z0) * ease_in_out(t / d)
    img = still(v, name)
    f = cover(img, W, HALF, zoom=z, cx=0.5, cy=cy)
    s, ox, oy = still_to_frame(name, v, W, HALF, z, 0.5, cy)
    bx, by, bw = PLACE[f"{name}_{v}"]
    bowl = bowl_closed_img(lift=lift, dome=dome)
    bh = bowl.shape[0] * bw / bowl.shape[1]
    X, Y, BW = ox + s * bx, oy + s * (by - bh / 2), s * bw
    soft_shadow(f, X, oy + s * by, BW * 0.95, BW * 0.16, 0.45)
    place(f, bowl, X, Y, BW, tint=tint)
    k = BW / bowl.shape[1]
    mx = X + (85 - bowl.shape[1] / 2) * k
    my = Y + (184 - bowl.shape[0] / 2) * k
    link_mark(f, int(mx), int(my), max(8, int(22 * k * 1.9)), heat=heat, flash=flash)
    return f, (X, Y, BW)


def s04(v, t, d):
    """Mirror split: each tries to open alone; the tab springs back with a tiny snap."""
    f = np.zeros((H, W, 3), np.float32)
    # tab pull at 0.85 s, snap at 1.15 s (same beat, both cities)
    pull = ease_out((t - 0.70) / 0.35) * (1 - ease_in_out((t - 1.08) / 0.07))
    over = 0.0
    if t > 1.15:
        over = -math.exp(-(t - 1.15) * 9) * math.sin((t - 1.15) * 40) * 6
    lift = max(0.0, pull * 46 + over)
    bl = 0.0
    for c in (1.35, 1.65):
        bl = max(bl, math.exp(-((t - c) / 0.06) ** 2))
    top, (X1, Y1, B1) = half_with_bowl(v, "S04a", t, d, 1.0, 1.10, 0.52, lift=lift, flash=bl, heat=0.15,
                                        tint=(1.05, 0.96, 0.84))
    bot, (X2, Y2, B2) = half_with_bowl(v, "S04b", t, d, 1.0, 1.10, 0.52, lift=lift, flash=bl, heat=0.15,
                                        tint=(0.94, 0.98, 1.05))
    f[:HALF] = top
    f[HALF:] = bot
    f[HALF - 2:HALF + 2] = 1.0
    # '톡' lettering on the snap (code type, same beat)
    k = pop(t - 1.15)
    if t > 1.15:
        a = clamp(1 - (t - 1.75) * 3)
        tx1, ty1 = X1 - B1 * 0.42, Y1 + B1 * 0.05
        tk = text_rgba("톡", "title", 130, YEL, 8, INK)
        place(f, tk, tx1 - 30, Y1 - B1 * 0.30, tk.shape[1] * (0.5 + 0.5 * k), rot=0.2, alpha=a)
        tk2 = text_rgba("톡", "title", 130, (255, 255, 255), 8, RED)
        place(f, tk2, X2 + B2 * 0.40, HALF + Y2 - B2 * 0.62, tk2.shape[1] * (0.5 + 0.5 * k), rot=0.2, alpha=a)
    # link mark points to its partner: tiny chevrons up / down on blinks
    if bl > 0.05:
        for (x, y, dirn) in [(X1, Y1, 1), (X2, HALF + Y2, -1)]:
            k2 = B1 / 760
            mx = x + (85 - 380) * k2
            my = y + (184 - 278) * k2 + dirn * 60
            pts = np.array([[mx - 16, my - dirn * 10], [mx, my + dirn * 8], [mx + 16, my - dirn * 10]], np.int32)
            cv2.polylines(f, [pts], False, tuple(float(x) * bl for x in c01(AMBER)), 5, cv2.LINE_AA)
    put_text(f, "서울 21:00", 150, 300, "body", 38, (245, 245, 245), anchor="lm")
    put_text(f, "뉴욕 08:00", 150, HALF + 70, "body", 38, (250, 250, 250), anchor="lm")
    return finish(f, t, grain=0.02 if v == "real" else 0.012)


def s05(v, t, d):
    """Both look at their phones at once: '지금?' / '지금.'"""
    top, _ = half_with_bowl(v, "S04a", t, d, 1.12, 1.30, 0.45, tint=(1.05, 0.96, 0.84))
    bot, _ = half_with_bowl(v, "S04b", t, d, 1.12, 1.30, 0.45, tint=(0.94, 0.98, 1.05))
    f = np.zeros((H, W, 3), np.float32)
    f[:HALF] = top * 0.55 + c01(SEOUL) * 0.12
    f[HALF:] = bot * 0.55 + c01(NYC) * 0.15
    f[HALF - 2:HALF + 2] = 1.0
    # phone cards
    for i, (cy, who, msg, ta) in enumerate([(HALF * 0.55, "서연", "지금?", 0.15), (HALF + HALF * 0.45, "준호", "지금.", 0.15 + BEAT)]):
        k = spring(t - (0.0 if i == 0 else 0.1))
        card = ui_card(640, 380, 44, (250, 249, 245), shadow=0.35)
        cy = cy - 50 * ease_in_out(t / d) * (1 if i == 0 else -1)
        place(f, card, W / 2, cy + (1 - k) * 120, card.shape[1], alpha=min(1, k * 2))
        if k > 0.3:
            put_text(f, who, W / 2 - 250, cy - 120 + (1 - k) * 120, "body", 34, (120, 120, 120), anchor="lm")
            kb = spring(t - ta)
            b = get_bubble(msg, i == 0, 72)
            place(f, b, W / 2, cy + 30 + (1 - k) * 120 + (1 - kb) * 40, b.shape[1] * (0.8 + 0.2 * kb), alpha=min(1, kb * 2))
    put_text(f, "서울 21:00", 150, 300, "body", 38, (245, 245, 245), anchor="lm")
    put_text(f, "뉴욕 08:00", 150, HALF + 70, "body", 38, (250, 250, 250), anchor="lm")
    return finish(f, t, grain=0.02, halation=0.06)


def microwave(dst, y0, h, warm, t, digit, bowl_rot, glow):
    """Code-drawn microwave front with the real bowl on the turntable."""
    body = ui_card(900, 560, 46, (232, 229, 222) if warm else (240, 243, 245), shadow=0.35)
    cy = y0 + h / 2 + 30
    place(dst, body, W / 2, cy, body.shape[1])
    # window
    wx0, wy0, ww, wh = W / 2 - 400, cy - 230, 600, 460
    win = np.zeros((int(wh), int(ww), 3), np.float32)
    yy, xx = np.mgrid[0:int(wh), 0:int(ww)].astype(np.float32)
    r = np.hypot((xx - ww * 0.5) / ww, (yy - wh * 0.6) / wh)
    inner = c01((240, 170, 90)) if warm else c01((235, 190, 120))
    win[:] = np.clip((1 - r * 1.6), 0, 1)[..., None] * inner * (0.55 + 0.45 * glow) + c01((28, 24, 22)) * 0.6
    patch = dst[int(wy0):int(wy0 + wh), int(wx0):int(wx0 + ww)]
    m = np.zeros((int(wh), int(ww)), np.float32)
    cv2.rectangle(m, (18, 18), (int(ww) - 18, int(wh) - 18), 1, -1)
    m = cv2.GaussianBlur(m, (0, 0), 3)
    patch[:] = patch * (1 - m[..., None]) + win * m[..., None]
    # turntable + real bowl
    cv2.ellipse(patch, (int(ww / 2), int(wh * 0.78)), (210, 34), 0, 0, 360, (0.55, 0.45, 0.36), -1, cv2.LINE_AA)
    bowl = bowl_closed_img(dome=glow)
    place(dst, bowl, W / 2 - 100 + math.sin(bowl_rot) * 6, cy + 30, 330 * (1 + 0.01 * math.sin(bowl_rot * 2)))
    # door grid sheen
    sheen = np.zeros_like(m)
    cv2.line(sheen, (40, int(wh) - 40), (int(ww) - 120, 40), 1, 40)
    sheen = cv2.GaussianBlur(sheen, (0, 0), 20)
    patch += sheen[..., None] * 0.05
    # display
    disp = ui_card(150, 110, 16, (20, 22, 24), shadow=0.0)
    place(dst, disp, W / 2 + 330, cy - 160, disp.shape[1])
    if digit:
        put_text(dst, digit, W / 2 + 330, cy - 160, "title", 84, AMBER)
    for k in range(3):
        cv2.circle(dst, (int(W / 2 + 330), int(cy - 30 + k * 85)), 26, (0.78, 0.76, 0.72), -1, cv2.LINE_AA)
    return dst


def s06(v, t, d):
    f = np.zeros((H, W, 3), np.float32)
    f[:HALF] = c01(SEOUL)
    f[HALF:] = c01(NYC)
    # subtle background gradients (window light)
    yy = np.linspace(0, 1, HALF, dtype=np.float32)[:, None, None]
    f[:HALF] += (1 - yy) * c01(TUNG) * 0.10
    f[HALF:] += yy * c01(DAY) * 0.10
    n = int(t / BEAT)
    digit = ["3", "2", "1"][min(n, 2)]
    pk = pop(t - n * BEAT)
    zoom = 1.0 + 0.06 * ease_in_out(t / d)
    top = f[:HALF].copy()
    bot = f[HALF:].copy()
    microwave(top, 0, HALF, True, t, digit, t * 4, glow=t / d)
    microwave(bot, 0, HALF, False, t, digit, t * 4, glow=t / d)
    f[:HALF] = cover(top, W, HALF, zoom=zoom)
    f[HALF:] = cover(bot, W, HALF, zoom=zoom)
    f[HALF - 2:HALF + 2] = 1.0
    # big beat numerals over the split line (code type)
    put_text(f, digit, W / 2, HALF, "title", 260, YEL, alpha=clamp(1.3 - (t - n * BEAT) * 2.2), scale=0.7 + 0.3 * pk)
    return finish(f, t, grain=0.018, halation=0.08)


def s07(v, t, d):
    """'Ding' at the same frame; both link marks turn amber."""
    f = np.zeros((H, W, 3), np.float32)
    lid = load_rgba(LID_FRONT["path"])
    heat = clamp(t / 0.22)
    z = 1.0 + 0.10 * ease_in_out(t / d)
    for i, (y0, warm) in enumerate([(0, True), (HALF, False)]):
        half = np.zeros((HALF, W, 3), np.float32)
        yy, xx = np.mgrid[0:HALF, 0:W].astype(np.float32)
        r = np.hypot((xx - W / 2) / W, (yy - HALF * 0.55) / HALF)
        base = c01(SEOUL) * 0.9 + c01(TUNG) * np.clip(1 - r * 1.5, 0, 1)[..., None] * 0.55 if warm else \
            c01(NYC) * 0.85 + c01((255, 255, 255)) * np.clip(1 - r * 1.5, 0, 1)[..., None] * 0.20
        half[:] = base
        lw = 640 * z
        cx, cy = W / 2, HALF * 0.53
        place(half, lid, cx, cy, lw, tint=(1.05, 0.95, 0.82) if warm else (0.95, 0.99, 1.06))
        k = lw / lid.shape[1]
        mx = cx + (195 - lid.shape[1] / 2) * k
        my = cy + (200 - lid.shape[0] / 2) * k
        link_mark(half, int(mx), int(my), int(30 * z), heat=heat, flash=math.exp(-((t - 0.05) / 0.1) ** 2))
        half = steam(half, t, 0.0, [(cx - lw * 0.35, cy - lw * 0.42, 120), (cx + lw * 0.35, cy - lw * 0.42, 120)],
                     seed=31 + i, n=40, strength=0.3, rise=120, cotton=False, burst=False, max_age=1.4)
        f[y0:y0 + HALF] = half
    f[HALF - 2:HALF + 2] = 1.0
    put_text(f, "띵", W - 170, 360, "title", 110, YEL, alpha=clamp(1.4 - t * 1.2), scale=0.6 + 0.4 * pop(t), rot=0.15)
    put_text(f, "띵", W - 170, HALF + 160, "title", 110, RED, alpha=clamp(1.4 - t * 1.2), scale=0.6 + 0.4 * pop(t), rot=0.15)
    return finish(f, t, grain=0.02, halation=0.12)


def peel_half(v, t, warm, seed):
    """Overhead macro of the real lid; this time the film releases and curls back."""
    half = np.zeros((HALF, W, 3), np.float32)
    bg = still(v, "S04a" if warm else "S04b")
    bgc = cover(bg, W, HALF, zoom=2.4, cx=0.5, cy=0.88)
    bgc = cv2.GaussianBlur(bgc, (0, 0), 14)
    half[:] = bgc * 0.9
    bw = 760 * (1 + 0.16 * ease_in_out(t / 2.67))
    cx, cy = W / 2, HALF * 0.52
    closed = load_rgba(BOWL_CLOSED["path"])
    opened = load_rgba(BOWL_OPEN["path"])
    tint = (1.05, 0.96, 0.85) if warm else (0.95, 0.99, 1.05)
    soft_shadow(half, cx, cy + bw * 0.33, bw * 0.95, bw * 0.12, 0.5)
    p = ease_in_out((t - 0.35) / 0.75)  # peel progress
    # open state underneath (scaled to the same container width)
    ow = bw * 1.04
    lay_o = np.zeros_like(half)
    lay_o[:] = half
    place(lay_o, opened, cx + bw * 0.02, cy + bw * 0.03, ow, tint=tint)
    lay_c = half.copy()
    place(lay_c, closed, cx, cy, bw, tint=tint)
    k = bw / closed.shape[1]
    link_mark(lay_c, int(cx + (85 - closed.shape[1] / 2) * k), int(cy + (184 - closed.shape[0] / 2) * k),
              int(32 * k * 1.9), heat=1.0)
    if p <= 0:
        out = lay_c
    else:
        yy, xx = np.mgrid[0:HALF, 0:W].astype(np.float32)
        # peel front moves diagonally from the front-left tab to the back-right
        dirx, diry = 0.78, -0.62
        start = (cx - bw * 0.55) * dirx + (cy + bw * 0.35) * diry
        end = (cx + bw * 0.6) * dirx + (cy - bw * 0.45) * diry
        front = start + (end - start) * p
        proj = xx * dirx + yy * diry
        m = np.clip((front - proj) / 6, 0, 1)  # 1 = peeled
        out = lay_c * (1 - m[..., None]) + lay_o * m[..., None]
        # curling roll at the front: radius shrinks as it travels
        rad = 46 * (1 - 0.6 * p)
        band = np.clip(1 - np.abs(proj - front - rad * 0.4) / rad, 0, 1)
        inside = np.zeros((HALF, W), np.float32)
        place_mask = lay_c.copy()
        # restrict roll to the lid footprint
        fp = np.zeros((HALF, W), np.float32)
        cv2.ellipse(fp, (int(cx), int(cy - bw * 0.02)), (int(bw * 0.5), int(bw * 0.38)), 0, 0, 360, 1, -1)
        band = band * fp * (1 if p < 0.98 else 0)
        shade = 0.88 + 0.12 * np.sin(np.clip((proj - front) / rad, -1, 1) * math.pi / 2)
        roll_col = np.ones(3, np.float32) * 0.97
        out = out * (1 - band[..., None]) + (roll_col * shade[..., None]) * band[..., None]
        # condensation sparkle on the underside
        rng = np.random.default_rng(seed)
        for _ in range(16):
            sx = rng.uniform(-0.45, 0.45) * bw + cx
            sy = rng.uniform(-0.3, 0.3) * bw + cy
            if abs(sx * dirx + sy * diry - front) < rad * 1.2 and 0.05 < p < 0.97:
                sparkle(out, sx, sy, 10 + rng.uniform(0, 8), 0.8)
    # steam burst 0.4 s then column
    out = steam(out, t, 0.75, [(cx + bw * 0.14, cy - bw * 0.02, bw * 0.42)], seed=seed, n=190, strength=1.3,
                rise=150, spread=55, cotton=(v == "mini"), burst=True, max_age=2.0)
    return out


def s08(v, t, d):
    f = np.zeros((H, W, 3), np.float32)
    f[:HALF] = peel_half(v, t, True, 41)
    f[HALF:] = peel_half(v, t, False, 42)
    f[HALF - 2:HALF + 2] = 1.0
    return finish(f, t, grain=0.02, halation=0.14)


def s09(v, t, d):
    """Signature 1: steam columns gather on the seam and melt it (fbm threshold mask)."""
    a = s08(v, t + 2.67, 2.67)
    b = table_frame(v, 0.0, 2.67, zoom=1.30 - 0.14 * ease_in_out(t / d))
    n = fbm(H, W, seed=5)
    dist = np.abs(np.arange(H, dtype=np.float32) - HALF)[:, None] / (H * 0.5)
    field = dist + 0.35 * (n - 0.5)
    thr = -0.12 + 1.35 * ease_in_out(t / (d * 0.92))
    soft = 0.06
    m = np.clip((thr - field) / soft, 0, 1)
    edge = np.clip(1 - np.abs(thr - field) / 0.07, 0, 1) * (thr < 1.2)
    edge = cv2.GaussianBlur(edge, (0, 0), 9)
    f = a * (1 - m[..., None]) + b * m[..., None]
    f = f * (1 - edge[..., None] * 0.55) + edge[..., None] * np.array([1.0, 0.98, 0.94], np.float32) * 0.55
    # light motes travelling along the steam between the halves (tiny, not orbs)
    rng = np.random.default_rng(9)
    for i in range(40):
        ph = rng.uniform(0, 1)
        x = rng.uniform(150, W - 150)
        yph = (ph + t * 0.45 * (1 if i % 2 else -1)) % 1.0
        y = HALF + (yph - 0.5) * 900
        sparkle(f, x + math.sin(t * 3 + i) * 20, y, 8, 0.6 * clamp(t * 2) * (1 - clamp((t - 2.2) * 2)))
    return finish(np.clip(f, 0, 1), t, grain=0.02, halation=0.12)


def table_frame(v, t, d, zoom=None):
    name = "S10"
    z = zoom if zoom is not None else 1.16 - 0.16 * ease_in_out(t / d)
    img = still(v, name)
    f = cover(img, W, H, zoom=z, cx=0.5, cy=0.56)
    # the two lights meet softly on the centre line (blend the hard seam of the still)
    blur = cv2.GaussianBlur(f, (0, 0), sigmaX=38, sigmaY=0.1)
    xs = np.arange(W, dtype=np.float32)
    bm = np.clip(1 - np.abs(xs - W / 2) / 70, 0, 1)[None, :, None]
    f = f * (1 - bm) + blur * bm
    s, ox, oy = still_to_frame(name, v, W, H, z, 0.5, 0.56)
    opened = load_rgba(BOWL_OPEN["path"])
    for i, (bx, by, bw) in enumerate(PLACE[f"{name}_{v}"]):
        bh = opened.shape[0] * bw / opened.shape[1]
        X, Y, BW = ox + s * bx, oy + s * (by - bh / 2), s * bw
        soft_shadow(f, X, oy + s * by, BW * 0.9, BW * 0.14, 0.4)
        o = opened[:, ::-1] if i == 1 else opened
        place(f, o, X, Y, BW, tint=(1.04, 0.96, 0.86) if i == 0 else (0.95, 0.99, 1.04))
        f = steam(f, t + 1.0, 0.0, [(X, Y - BW * 0.1, BW * 0.5)], seed=51 + i, n=40, strength=0.55, rise=170,
                  spread=30, cotton=(v == "mini"), burst=False, max_age=1.8)
    return f


def s10(v, t, d):
    f = table_frame(v, t, d)
    return finish(f, t, grain=0.022, halation=0.12)


def s11(v, t, d):
    img = still(v, "S11")
    bg = cv2.GaussianBlur(cover(img, W, H, zoom=1.0), (0, 0), 30) * 0.85
    z = 1.0 + 0.07 * ease_in_out(t / d)
    band = cover(img, 1300, 1300, zoom=z, cx=0.5, cy=0.5)
    f = bg.copy()
    y0 = (H - 1300) // 2
    band_c = band[:, 110:110 + W]
    m = np.ones((1300, W), np.float32)
    ramp = np.linspace(0, 1, 120, dtype=np.float32)
    m[:120] *= ramp[:, None]
    m[-120:] *= ramp[::-1][:, None]
    f[y0:y0 + 1300] = f[y0:y0 + 1300] * (1 - m[..., None]) + band_c * m[..., None]
    clink = 0.40
    fl = math.exp(-((t - clink) / 0.07) ** 2)
    sparkle(f, W / 2, y0 + 1300 * 0.47, 60 * (0.5 + fl), fl)
    return finish(f, t, grain=0.02, halation=0.14)


def s12(v, t, d):
    """Everyday montage: 3 pairs; alone-locked bowls open together on one beat; seams melt with steam."""
    f = np.zeros((H, W, 3), np.float32)
    bh = H // 3
    closed = load_rgba(BOWL_CLOSED["path"])
    opened = load_rgba(BOWL_OPEN["path"])
    t_open = BEAT * 2.0
    for r, name in enumerate(["S12a", "S12b", "S12c"]):
        img = still(v, name)
        z = 1.0 + 0.12 * ease_in_out(t / d)
        band = cover(img, W, bh, zoom=z)
        s, ox, oy = still_to_frame(name, v, W, bh, z, 0.5, 0.5)
        k_in = spring(t - r * BEAT * 0.5)
        for i, (bx, by, bw) in enumerate(PLACE[f"{name}_{v}"]):
            bw = bw * 1.35
            X, BW = ox + s * bx, s * bw
            is_open = t >= t_open
            src = opened if is_open else closed
            hh = src.shape[0] * bw / src.shape[1]
            Y = oy + s * (by - hh / 2)
            soft_shadow(band, X, oy + s * by, BW * 0.9, BW * 0.14, 0.4)
            place(band, src, X, Y + (1 - k_in) * 40, BW, alpha=clamp(k_in * 2))
            if not is_open:
                kk = BW / closed.shape[1]
                link_mark(band, int(X + (85 - closed.shape[1] / 2) * kk), int(Y + (184 - closed.shape[0] / 2) * kk),
                          max(6, int(22 * kk * 1.9)), heat=clamp((t - t_open + 0.4) / 0.4))
            band = steam(band, t, t_open, [(X, Y - BW * 0.15, BW * 0.5)], seed=60 + r * 2 + i, n=40, strength=0.9,
                         rise=180, spread=30, cotton=(v == "mini"), burst=True, max_age=1.4)
        # vertical seam melts after opening
        melt = ease_in_out((t - t_open - 0.1) / 0.6)
        seam_w = int(6 + 260 * melt)
        xs = np.arange(W, dtype=np.float32)
        nz = fbm(bh, W, seed=70 + r)
        mm = np.clip(1 - (np.abs(xs[None, :] - W / 2) / max(seam_w, 1) + 0.4 * (nz - 0.5)), 0, 1) * (0.9 if melt > 0 else 0)
        if melt <= 0:
            band[:, W // 2 - 2:W // 2 + 2] = 1.0
        else:
            band = band * (1 - mm[..., None] * 0.6) + mm[..., None] * np.array([1.0, 0.97, 0.92], np.float32) * 0.6
        f[r * bh:(r + 1) * bh] = band
        if r > 0:
            f[r * bh - 3:r * bh + 3] = c01(RICE)
    return finish(f, t, grain=0.02, halation=0.10)


# =================================================================== 20-facet container line art
def facet_bowl(dst, cx, cy, R, h_ratio=0.42, tilt=0.42, col=(1, 1, 1), lw=4, fill=None):
    n = 20
    th = np.linspace(0, 2 * math.pi, n, endpoint=False) + math.pi / n
    top = np.stack([cx + R * np.cos(th), cy + R * np.sin(th) * tilt], 1)
    rb = R * 0.74
    hh = R * h_ratio
    bot = np.stack([cx + rb * np.cos(th), cy + hh + rb * np.sin(th) * tilt], 1)
    if fill is not None:
        for i in range(n):
            j = (i + 1) % n
            if math.sin(th[i]) > -0.05 or math.sin(th[j]) > -0.05:
                quad = np.array([top[i], top[j], bot[j], bot[i]], np.int32)
                shade = 0.82 + 0.18 * math.cos(th[i] - 0.9)
                cv2.fillPoly(dst, [quad], tuple(float(c) * shade for c in fill), cv2.LINE_AA)
    rim = R * 1.12
    cv2.ellipse(dst, (int(cx), int(cy)), (int(rim), int(rim * tilt)), 0, 0, 360, col, lw, cv2.LINE_AA)
    cv2.polylines(dst, [top.astype(np.int32)], True, col, lw, cv2.LINE_AA)
    for i in range(n):
        if math.sin(th[i]) > -0.05:
            cv2.line(dst, tuple(top[i].astype(int)), tuple(bot[i].astype(int)), col, max(2, lw - 1), cv2.LINE_AA)
    cv2.polylines(dst, [bot[np.sin(th) > -0.2].astype(np.int32)], False, col, lw, cv2.LINE_AA)
    return dst


LAYERS = [("같이밥 링크층", True), ("인쇄층", False), ("강도 보강층", False), ("산소 차단층", False), ("접착층", False)]


def exploded(dst, cx, cy, R, t, labels=True, size=40):
    """Real 4-layer barrier film (refs/03) + a fifth concept 'link' layer on top."""
    facet_bowl(dst, cx, cy + 40, R, col=(1, 1, 1), lw=4, fill=(0.93, 0.91, 0.88))
    for i in range(4, -1, -1):
        name, concept = LAYERS[i]
        k = ease_out((t - 0.1 * (4 - i)) / 0.6)
        y = cy - 40 - (5 - i) * 78 * k
        col = c01(AMBER) if concept else np.array([1.0, 1.0, 1.0], np.float32) * (0.97 - 0.04 * i)
        ov = dst.copy()
        cv2.ellipse(ov, (int(cx), int(y)), (int(R * 1.12), int(R * 1.12 * 0.30)), 0, 0, 360, tuple(float(c) for c in col), -1, cv2.LINE_AA)
        a = (0.85 if concept else 0.55) * k
        dst[:] = dst * (1 - a) + ov * a
        cv2.ellipse(dst, (int(cx), int(y)), (int(R * 1.12), int(R * 1.12 * 0.30)), 0, 0, 360, (1, 1, 1), 2, cv2.LINE_AA)
        if labels and k > 0.5:
            lx = cx + R * 1.12 + 30
            cv2.line(dst, (int(cx + R * 1.12 - 6), int(y)), (int(lx - 6), int(y)), (1, 1, 1), 2, cv2.LINE_AA)
            put_text(dst, name + (" (콘셉트)" if concept else ""), lx, y, "body", size,
                     YEL if concept else (255, 255, 255), alpha=clamp((k - 0.5) * 3), anchor="lm")
    return dst


def s13(v, t, d):
    f = kv_background().copy()
    k = pop(t)
    title = halftone_text("혼자선 안 열립니다.", 128)
    place(f, title, W / 2, 400, title.shape[1] * (0.7 + 0.3 * k), alpha=min(1, k * 2))
    exploded(f, 330, 1010, 220, t * 1.3, labels=True, size=42)
    # nine-cell promise calendar
    cells = int(clamp((t - 0.6) / 1.1) * 9 + 0.999)
    x0, y0, cw = 150, 1330, 82
    for i in range(9):
        on = i < cells
        cv2.rectangle(f, (x0 + i * (cw + 8), y0), (x0 + i * (cw + 8) + cw, y0 + cw), (1, 1, 1), -1 if on else 3, cv2.LINE_AA)
        if on:
            put_text(f, f"{i + 1}", x0 + i * (cw + 8) + cw / 2, y0 + cw / 2, "title", 44, RED)
    put_text(f, "약속 기한 9개월, 지나면 혼자서도 열려요.", W / 2, 1490, "body", 46, (255, 255, 255))
    put_text(f, "실제 햇반 실온 보관 9개월 · 4중 차단 필름 · 20각 용기", W / 2, 1548, "body", 30, (255, 225, 220))
    f = cover(f, W, H, zoom=1.0 + 0.07 * ease_in_out(t / d), cy=0.52)
    return paper(f, v, t)


def s14(v, t, d):
    """Signature 3: '언제 밥 한번 먹자' -> '언제나 같이 밥 먹자'."""
    f = np.ones((H, W, 3), np.float32) * c01(RICE)
    # callback: the ten years of empty promises drift up behind, faded
    ghost = np.ones((H, W, 3), np.float32) * c01(RICE)
    chat_stack(ghost, 0, 316 - 420 * ease_in_out(t / d), 5, [])
    f = f * 0.84 + cv2.GaussianBlur(ghost, (0, 0), 2.5) * 0.16
    size = 76
    stages = [
        (0.00, [("언제 밥 한번 먹자", (255, 255, 255))]),
        (0.45, [("언제 밥 ", (255, 255, 255)), ("한번", (150, 160, 170)), (" 먹자", (255, 255, 255))]),
        (0.70, [("언제 밥 먹자", (255, 255, 255))]),
        (0.95, [("언제", (255, 255, 255)), ("나", YEL), (" 같이 밥 먹자", (255, 255, 255))]),
    ]
    cur = stages[0][1]
    for ts, s in stages:
        if t >= ts:
            cur = s
    total = sum(text_width(s, "body", size) for s, _ in cur)
    bw, bhh = total + 120, 170
    card = ui_card(int(bw), bhh, 70, SEOUL, shadow=0.25)
    k = spring(t)
    pk = pop(t - 0.95)
    sc = 1.0 + 0.06 * pk * math.exp(-max(0, t - 1.2) * 2)
    cy = H * 0.48
    place(f, card, W / 2, cy, card.shape[1] * sc)
    x = W / 2 - total * sc / 2
    for s, col in cur:
        tw = text_width(s, "body", size)
        strike = (s == "한번")
        put_text(f, s, x, cy, "body", size, col, anchor="lm", scale=sc)
        if strike:
            pr = clamp((t - 0.45) / 0.2)
            cv2.line(f, (int(x), int(cy)), (int(x + tw * sc * pr), int(cy)), (1, 0.99, 0.53), 6, cv2.LINE_AA)
        x += tw * sc
    if t > 0.95:
        sparkle(f, W / 2 - total * sc / 2 + text_width("언제", "body", size) * sc + 30, cy - 70, 26 * pk, pk)
    put_text(f, "서연", W / 2 + bw / 2 - 40, cy - 130, "body", 34, (130, 128, 122), anchor="rm", alpha=k)
    f = cover(f, W, H, zoom=1.10 - 0.10 * ease_in_out(t / d))
    return paper(f, v, t)


def s15(v, t, d):
    f = kv_background().copy()
    f = gold_trail(f, t, -0.4, 1.4, cy=H * 0.40, rx=470, ry=150, phase=1.2, width=6)
    l1 = load_rgba(str(LOGO1))
    l2 = load_rgba(str(LOGO2))
    # logos inside safe area top (y > 250)
    place(f, l1, W / 2 - 120, 345, 150)
    f[290:400, W // 2 - 2:W // 2 + 1] = 1.0
    place(f, l2, W / 2 + 110, 345, 160)
    k = pop(t - 0.1)
    t1 = halftone_text("빈말을 진짜로 짓다.", 120, spans=((4, 6, YEL),))
    place(f, t1, W / 2, 640, t1.shape[1] * (0.75 + 0.25 * k), alpha=min(1, k * 2))
    # real pair: two closed bowls touching, link marks lit toward each other
    bowl = load_rgba(BOWL_CLOSED["path"])
    for i, x in enumerate([W / 2 - 205, W / 2 + 205]):
        kb = spring(t - 0.25 - 0.1 * i)
        y = 1060 + (1 - kb) * 80
        soft_shadow(f, x, y + 150, 380, 60, 0.35)
        place(f, bowl, x, y, 400, alpha=min(1, kb * 2))
        kk = 400 / bowl.shape[1]
        link_mark(f, int(x + (85 - bowl.shape[1] / 2) * kk), int(y + (184 - bowl.shape[0] / 2) * kk), 22,
                  heat=1.0, flash=0.4 + 0.3 * math.sin(t * 4 + i * 3))
    k2 = pop(t - 0.5)
    t2 = halftone_text("햇반 같이밥", 104)
    place(f, t2, W / 2, 1360, t2.shape[1] * (0.8 + 0.2 * k2), alpha=min(1, k2 * 2))
    put_text(f, "미래 햇반 콘셉트 · AI 활용 제작", W / 2, 1500, "body", 38, (255, 236, 232), alpha=clamp((t - 0.6) * 3))
    for i, (x, y) in enumerate([(170, 560), (920, 480), (900, 1250), (160, 1200)]):
        sparkle(f, x, y, 22 + 8 * math.sin(t * 5 + i * 1.7), 0.8)
    f = cover(f, W, H, zoom=1.0 + 0.012 * t)
    return paper(f, v, t)


FUN = dict(S01=s01, S02=s02, S03=s03, S04=s04, S05=s05, S06=s06, S07=s07, S08=s08, S09=s09, S10=s10, S11=s11,
           S12=s12, S13=s13, S14=s14, S15=s15)


def frame(v, t):
    if v == "mini":
        t = math.floor(t * 12) / 12.0  # 12 fps stop-motion "on twos" (picture only; sound stays smooth)
    sid, lt, d = shot_at(t)
    f = FUN[sid](v, lt, d)
    return np.clip(f, 0, 1)
