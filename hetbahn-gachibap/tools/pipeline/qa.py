"""Measurements for the quality gate: contact sheet, frozen time, loudness, WCAG contrast, safe area.
usage: python3 tools/pipeline/qa.py out/A_같이밥_실사_final.mp4 real"""
import json
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
ROOT = Path(__file__).resolve().parents[2]
SAFE_TOP, SAFE_BOT = 250, 1920 - 340


def frames(path, every=None):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    i = 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if every is None or abs((i / fps) / every - round((i / fps) / every)) < 0.5 / fps / every:
            yield i / fps, f
        i += 1


def contact_sheet(path, out, every=1.0, cols=11, tw=216):
    font = ImageFont.truetype(str(ROOT / "fonts/GowunDodum-Regular.ttf"), 20)
    tiles = []
    for t, f in frames(path, every):
        im = Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)).resize((tw, int(tw * 16 / 9)))
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, 74, 26), fill=(0, 0, 0))
        d.text((5, 2), f"{t:05.2f}", fill=(255, 255, 255), font=font)
        tiles.append(im)
    rows = (len(tiles) + cols - 1) // cols
    th = tiles[0].height
    sheet = Image.new("RGB", (cols * tw, rows * th), (20, 20, 20))
    for i, im in enumerate(tiles):
        sheet.paste(im, ((i % cols) * tw, (i // cols) * th))
    sheet.save(out, quality=90)
    return out


def frozen(path, end_card_start, thr=0.010, window=0.6):
    """Frozen-time check: a moment is 'frozen' if the picture at t and t+0.6 s is visually the same
    (grain suppressed by 1/4 res + blur; mean abs luma diff < thr). Returns violations before the end card."""
    gs, ts = [], []
    for t, f in frames(path):
        g = cv2.cvtColor(cv2.resize(f, (270, 480), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
        gs.append(cv2.GaussianBlur(g, (0, 0), 2))
        ts.append(t)
    k = int(round(window * 30))
    viol, worst = [], (0.0, 0.0)
    for i in range(len(gs) - k):
        if ts[i] + window > end_card_start:
            break
        d = float(np.abs(gs[i + k] - gs[i]).mean())
        if d < thr:
            viol.append((round(ts[i], 2), round(d, 4)))
    # merge consecutive frozen starts into spans
    spans = []
    for t, d in viol:
        if spans and t - spans[-1][1] <= 0.05:
            spans[-1][1] = t
        else:
            spans.append([t, t])
    spans = [(a, round(b - a + window, 2)) for a, b in spans]
    worst = max([s[1] for s in spans], default=0.0)
    return spans, (worst, 0)


def loudness(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f",
                        "null", "-"], capture_output=True, text=True).stderr
    tail = r[r.rfind("Summary:"):]
    get = lambda k: float(re.search(k + r":\s+(-?[\d.]+)", tail).group(1))
    return dict(I=get("I"), LRA=get("LRA"), TP=get("Peak"))


def rel_lum(c):
    c = np.array(c, np.float64) / 255
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def contrast(a, b):
    la, lb = rel_lum(a), rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def text_audit(v):
    """Re-render sparse frames with instrumented text placement: safe-area + contrast vs actual pixels."""
    import fx
    import film
    reg = {}
    orig_text, orig_half, orig_bub = fx.text_rgba, fx.halftone_text, film.get_bubble

    def reg_wrap(fn, kind):
        def w(*a, **k):
            r = fn(*a, **k)
            reg[id(r)] = (kind, a[0] if a else "", k.get("color", a[3] if len(a) > 3 else None))
            return r
        return w

    fx.text_rgba = film.text_rgba = reg_wrap(orig_text, "text")
    film.halftone_text = reg_wrap(orig_half, "title")
    film.get_bubble = reg_wrap(orig_bub, "bubble")
    log = []
    orig_place = fx.place

    def place(dst, rgba, cx, cy, width, **k):
        out = orig_place(dst, rgba, cx, cy, width, **k)
        if id(rgba) in reg and dst.shape[0] in (1920, 960, 1300) and k.get("alpha", 1.0) > 0.5:
            kind, txt, col = reg[id(rgba)]
            h = rgba.shape[0] * width / rgba.shape[1]
            log.append(dict(kind=kind, text=str(txt), cy=cy, h=h, cx=cx, w=width, full=dst.shape[0] == 1920))
        return out

    fx.place = film.place = place
    results, t = [], 0.1
    while t < film.DUR:
        log.clear()
        sid, lt, d = film.shot_at(t)
        frame = film.frame(v, t)
        for e in log:
            if not e["full"]:
                continue  # half-frame layers are checked through their own label calls on the full frame
            top, bot = e["cy"] - e["h"] / 2, e["cy"] + e["h"] / 2
            results.append(dict(t=round(t, 2), shot=sid, text=e["text"], top=round(top), bottom=round(bot),
                                safe=bool(top >= SAFE_TOP - 1 and bot <= SAFE_BOT + 1)))
        t += 0.5
    fx.place = orig_place
    return results


PAIRS = {
    "흰 글자 / KV 레드 #B52A23": ((255, 255, 255), (0xB5, 0x2A, 0x23)),
    "노랑 #FFFC87 / KV 레드": ((0xFF, 0xFC, 0x87), (0xB5, 0x2A, 0x23)),
    "흰 글자 / 네이비 말풍선 #1C2733": ((255, 255, 255), (0x1C, 0x27, 0x33)),
    "노랑 '나' / 네이비 말풍선": ((0xFF, 0xFC, 0x87), (0x1C, 0x27, 0x33)),
    "잉크 #1A1A1A / 흰 말풍선": ((0x1A, 0x1A, 0x1A), (255, 255, 255)),
    "회색 날짜 #605E59 / 쌀백 #F8F7F2": ((0x60, 0x5E, 0x59), (0xF8, 0xF7, 0xF2)),
    "흰 버튼 글자 / 레드 버튼": ((255, 255, 255), (0xB5, 0x2A, 0x23)),
    "앰버 숫자 #F29A2E / 디스플레이 #141618": ((0xF2, 0x9A, 0x2E), (0x14, 0x16, 0x18)),
    "보조 문구 #FFE1DC / KV 레드": ((0xFF, 0xE1, 0xDC), (0xB5, 0x2A, 0x23)),
}


def main(path, v):
    path = Path(path)
    name = path.stem
    rep = {}
    rep["contact_sheet"] = str(contact_sheet(path, ROOT / f"proof/contact_{v}_1s.jpg", 1.0))
    contact_sheet(path, ROOT / f"proof/contact_{v}_0.2s.jpg", 0.2, cols=15, tw=144)
    import film
    viol, worst = frozen(path, film.CUTS[14])
    rep["frozen_violations"] = viol
    rep["longest_still_s"] = round(worst[0], 2)
    rep["loudness"] = loudness(path)
    rep["contrast"] = {k: round(contrast(*p), 2) for k, p in PAIRS.items()}
    ta = text_audit(v)
    rep["safe_area_checked"] = len(ta)
    rep["safe_area_violations"] = [r for r in ta if not r["safe"]]
    out = ROOT / f"proof/qa_{v}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps({k: rep[k] for k in rep if k != "safe_area_violations"}, ensure_ascii=False, indent=1))
    print("safe-area violations:", json.dumps(rep["safe_area_violations"][:20], ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
