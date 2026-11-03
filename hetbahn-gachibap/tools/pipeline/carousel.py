"""출품 B: 4:5 (1080x1350) carousel, 5 slides, each a different composition.
Product = real Hetbahn photos (refs/), logos = assets/ official PNGs (fallback: KV extract)."""
import math
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from fx import (RICE, SEOUL, TUNG, NYC, INK, RED, YEL, AMBER, c01, load_rgba, place, soft_shadow, text_rgba,
                put_text, halftone_text, kv_background, gold_trail, sparkle, steam, link_mark, ui_card, fbm,
                BOWL_CLOSED, LID_FRONT, BOWL_OPEN, mark_xy, mark_size, bowl_closed_img, pair_sleeve)
from film import exploded, facet_bowl, get_bubble
from assets import resolve_logos

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "B_캐러셀_4x5"
CW, CH = 1080, 1350
L1, L2, LSRC = resolve_logos()


def tinted(rgba, col):
    out = rgba.copy()
    out[..., :3] = c01(col)
    return out


def logos(dst, y, color=None, size=120):
    l1, l2 = load_rgba(str(L1)), load_rgba(str(L2))
    if color is not None:
        l1, l2 = tinted(l1, color), tinted(l2, color)
    place(dst, l1, CW / 2 - size * 0.78, y, size)
    c = (1, 1, 1) if color is None else tuple(float(_v) for _v in c01(color))
    cv2.line(dst, (CW // 2, int(y - size * 0.36)), (CW // 2, int(y + size * 0.36)), c, 2, cv2.LINE_AA)
    place(dst, l2, CW / 2 + size * 0.74, y, size * 1.07)


def tag(dst, color=(255, 236, 232), y=CH - 60):
    kv = color == (255, 236, 232)
    put_text(dst, "미래 햇반 콘셉트 · AI 활용 제작", CW / 2, y, "body", 30, color, stroke=2 if kv else 0)


def bowl_with_mark(dst, x, y, w, heat=1.0, flip=False, lift=0.0):
    b = bowl_closed_img(lift=lift) if lift else load_rgba(BOWL_CLOSED["path"])
    soft_shadow(dst, x, y + w * 0.36, w * 0.95, w * 0.14, 0.4)
    place(dst, b, x, y, w)
    mx, my = mark_xy(x, y, w)
    link_mark(dst, int(mx), int(my), mark_size(w), heat=heat, flash=0.5 * heat)
    return mx, my


def slide1():
    """Hero, one-point centre: the interlocked pair, marks lit toward each other."""
    f = kv_background(CW, CH).copy()
    f = gold_trail(f, 9, 0, 1, cx=CW / 2, cy=930, rx=480, ry=110, phase=1.0, width=6)
    logos(f, 120, size=110)
    t = halftone_text("혼자선 안 열리는 햇반", 104, spans=((4, 9, YEL),))
    place(f, t, CW / 2, 300, t.shape[1])
    put_text(f, "두 개가 한 쌍, 같이밥 페어", CW / 2, 410, "body", 46, (255, 255, 255), stroke=3)
    # clear sleeve
    sl = ui_card(900, 470, 70, (255, 255, 255), shadow=0.0)
    place(f, sl, CW / 2, 800, sl.shape[1], alpha=0.12)
    m1 = bowl_with_mark(f, CW / 2 - 225, 790, 450, lift=80)
    m2 = bowl_with_mark(f, CW / 2 + 225, 790, 450)
    pair_sleeve(f, CW / 2, 830, 900, 90, "같이밥", "둘이 같이 열어요", col=(0x8E, 0x1C, 0x17))
    tk = text_rgba("톡", "title", 110, YEL, 8, INK)
    place(f, tk, CW / 2 - 400, 700, tk.shape[1], rot=0.2)
    put_text(f, "혼자 당기면 '톡' 하고 다시 붙어요", CW / 2, 1010, "body", 36, (255, 255, 255), stroke=3)
    # amber link arc between the two marks (thin, not an orb)
    pts = []
    for i in range(41):
        u = i / 40
        x = m1[0] + (m2[0] - m1[0]) * u
        y = m1[1] - math.sin(u * math.pi) * 90
        pts.append((int(x), int(y)))
    cv2.polylines(f, [np.array(pts, np.int32)], False, tuple(float(_v) for _v in c01(YEL)), 4, cv2.LINE_AA)
    put_text(f, "짝과 같은 순간 데워야 열립니다", CW / 2, 1120, "title", 54, YEL)
    tag(f)
    for (x, y) in [(150, 620), (950, 560), (930, 1010)]:
        sparkle(f, x, y, 26, 0.9)
    return f


def slide2():
    """Exploded view, side-isometric: real 4-layer film + concept 5th link layer + real 20-facet bowl."""
    f = kv_background(CW, CH).copy()
    t = halftone_text("다섯 번째 층, 같이밥 링크층", 84, spans=((7, 13, YEL),))
    place(f, t, CW / 2, 170, t.shape[1])
    put_text(f, "실제 햇반 4중 차단 필름 위에 한 층을 더하는 콘셉트", CW / 2, 262, "body", 36, (255, 236, 232), stroke=3)
    exploded(f, 360, 800, 210, 9.0, labels=True, size=40)
    # facts vs concept
    card = ui_card(940, 250, 36, (255, 255, 255), shadow=0.2)
    place(f, card, CW / 2, 1125, card.shape[1])
    put_text(f, "실제", 120, 1080, "title", 40, RED, anchor="lm")
    put_text(f, "4중 차단 필름 · 3중 차단 용기 · 20각 내압 구조", 230, 1080, "body", 34, INK, anchor="lm")
    put_text(f, "콘셉트", 120, 1160, "title", 40, (0xB0, 0x60, 0x10), anchor="lm")
    put_text(f, "감온 잉크 마크 + 동시 가열 신호 칩", 270, 1160, "body", 34, INK, anchor="lm")
    put_text(f, "짝이 같은 순간 데워졌을 때만 접착층이 풀림", 270, 1215, "body", 30, (90, 90, 90), anchor="lm")
    put_text(f, "필름 4층 구성은 CJ제일제당 공개 포장 기술 도해 기준", CW / 2, 1282, "body", 26, (255, 225, 220), stroke=2)
    tag(f, y=CH - 28)
    return f


def slide3():
    """How it works, 3 vertical tiers joined by a steam curve."""
    f = np.ones((CH, CW, 3), np.float32) * c01(RICE)
    put_text(f, "같이밥, 이렇게 씁니다", CW / 2, 110, "title", 76, RED)
    tiers = [(330, "빈말 대신 페어를 보낸다"), (690, "짝과 같은 순간 데운다"), (1050, "같이 열린다")]
    # steam curve connecting the tiers (visual grammar)
    pts = []
    for i in range(200):
        u = i / 199
        y = 250 + u * 930
        x = 160 + math.sin(u * math.pi * 3) * 50
        pts.append((int(x), int(y)))
    lay = np.zeros((CH, CW), np.float32)
    cv2.polylines(lay, [np.array(pts, np.int32)], False, 1.0, 14, cv2.LINE_AA)
    lay = cv2.GaussianBlur(lay, (0, 0), 6)
    f = f * (1 - lay[..., None] * 0.5) + c01((205, 205, 205)) * lay[..., None] * 0.5
    for i, (y, label) in enumerate(tiers):
        cv2.circle(f, (pts[int((y - 250) / 930 * 199)][0], y), 16, tuple(float(_v) for _v in c01(RED)), -1, cv2.LINE_AA)
        put_text(f, label, 230, y - 120, "title", 48, INK, anchor="lm")
    # tier 1: chat bubble + send button + pair
    b = get_bubble("언제 밥 한번 먹자", True, 40)
    place(f, b, 410, 340, b.shape[1], alpha=0.35)
    cv2.line(f, (270, 340), (550, 340), tuple(float(_v) for _v in c01(RED)), 4, cv2.LINE_AA)
    btn = ui_card(300, 80, 40, RED, shadow=0.2)
    place(f, btn, 400, 430, btn.shape[1])
    put_text(f, "같이밥 보내기", 400, 430, "title", 38, (255, 255, 255))
    bowl_with_mark(f, 760, 330, 240, heat=0.4)
    bowl_with_mark(f, 930, 400, 200, heat=0.4)
    # tier 2: two cities, same moment
    for k, (x, col, lab, tcol) in enumerate([(470, SEOUL, "서울 21:00", (255, 255, 255)), (820, NYC, "뉴욕 07:00", INK)]):
        card = ui_card(320, 230, 30, col, shadow=0.2)
        place(f, card, x, 720, card.shape[1])
        put_text(f, lab, x, 640, "body", 32, tcol)
        bowl_with_mark(f, x, 735, 210, heat=1.0)
    put_text(f, "=", 645, 720, "title", 70, RED)
    # tier 3: opened bowls, steam merging
    ob = load_rgba(BOWL_OPEN["path"])
    for x in (520, 820):
        soft_shadow(f, x, 1110, 260, 40, 0.35)
        place(f, ob, x, 1060, 280)
    f = steam(f, 2.5, 0.0, [(520, 1010, 110), (820, 1010, 110)], seed=5, n=90, strength=0.8, rise=30, spread=30,
              burst=False, max_age=2.2, tint=(0.97, 0.97, 0.97))
    tag(f, color=(110, 110, 110), y=CH - 40)
    return f


def slide4():
    """Promise deadline, 9-cell calendar grammar."""
    f = kv_background(CW, CH).copy()
    t = halftone_text("약속 기한 9개월", 108, spans=((6, 9, YEL),))
    place(f, t, CW / 2, 160, t.shape[1])
    put_text(f, "햇반의 실제 실온 보관 기간이 곧 약속 기한", CW / 2, 262, "body", 38, (255, 236, 232), stroke=3)
    x0, y0, cs, g = 110, 340, 170, 16
    for i in range(9):
        r, c = divmod(i, 3)
        x, y = x0 + c * (cs + g), y0 + r * (cs + g)
        last = i == 8
        cv2.rectangle(f, (x, y), (x + cs, y + cs), (1, 1, 1), -1 if not last else 4, cv2.LINE_AA)
        put_text(f, f"{i + 1}개월", x + cs / 2, y + cs / 2, "title", 40, RED if not last else (255, 255, 255))
    # lid that opened on its own after 9 months, with the printed promise
    bowl_with_mark(f, 845, 560, 330, heat=0.0)
    sticker = ui_card(200, 84, 18, (255, 255, 255), shadow=0.3)
    place(f, sticker, 900, 455, sticker.shape[1], rot=-0.10)
    stamp = text_rgba("다음엔 꼭", "end", 40, RED)
    place(f, stamp, 900, 455, stamp.shape[1], rot=-0.10)
    put_text(f, "9개월이 지나면 혼자서도 열리고", CW / 2, 980, "title", 52, (255, 255, 255))
    put_text(f, "뚜껑에 '다음엔 꼭'이 남습니다", CW / 2, 1050, "title", 52, YEL)
    put_text(f, "기다리던 밥은 그대로 먹을 수 있어 버려지는 밥이 없습니다", CW / 2, 1140, "body", 34, (255, 236, 232), stroke=3)
    tag(f)
    return f


def slide5():
    """End, white-space typography."""
    f = np.ones((CH, CW, 3), np.float32) * c01(RICE)
    logos(f, 230, color=RED, size=120)
    t = text_rgba("빈말을 진짜로 짓다.", "end", 96, INK)
    place(f, t, CW / 2, 620, t.shape[1])
    cv2.line(f, (CW // 2 - 60, 720), (CW // 2 + 60, 720), tuple(float(_v) for _v in c01(RED)), 4, cv2.LINE_AA)
    put_text(f, "햇반 같이밥", CW / 2, 800, "title", 64, RED)
    put_text(f, "혼자선 안 열리는 햇반, 누구랑 열래?", CW / 2, 880, "body", 38, (90, 90, 90))
    bowl_with_mark(f, CW / 2 - 120, 1080, 230)
    bowl_with_mark(f, CW / 2 + 120, 1080, 230)
    pair_sleeve(f, CW / 2, 1100, 480, 56, "같이밥", "둘이 같이", col=RED)
    tag(f, color=(120, 120, 120), y=CH - 50)
    return f


def save(img, path):
    Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)).save(path)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    names = ["1_히어로.png", "2_분해도.png", "3_사용법.png", "4_약속기한.png", "5_엔드.png"]
    paths = []
    for fn, name in zip([slide1, slide2, slide3, slide4, slide5], names):
        p = OUT / name
        save(fn(), p)
        paths.append(p)
        print(p)
    z = OUT.parent / "B_캐러셀_4x5.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in paths:
            zf.write(p, p.name)
    print(z, "logos:", LSRC)


if __name__ == "__main__":
    main()
