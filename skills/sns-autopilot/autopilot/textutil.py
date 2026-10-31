"""중복 판정용 텍스트 유틸 (표준 라이브러리만)."""
from __future__ import annotations

import json
import re
import unicodedata

NUM_RE = re.compile(r"(\d[\d,\.]*)\s*(만|억|천|万|億|千|k|K|M|%|원|円|엔|명|人|件|개|배|倍)?")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"https?://\S+", "", s)
    return re.sub(r"[\s\W_]+", "", s)


def ngrams(s: str, n: int = 3) -> set[str]:
    s = norm(s)
    return {s[i:i + n] for i in range(max(1, len(s) - n + 1))} if s else set()


def jaccard(a: str, b: str, n: int = 3) -> float:
    A, B = ngrams(a, n), ngrams(b, n)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def to_number(raw: str, unit: str | None) -> float:
    v = float(raw.replace(",", ""))
    mult = {"만": 1e4, "万": 1e4, "억": 1e8, "億": 1e8, "천": 1e3, "千": 1e3,
            "k": 1e3, "K": 1e3, "M": 1e6}
    return v * mult.get(unit or "", 1)


def extract_numbers(text: str) -> list[dict]:
    """초안 속 '실적 숫자' 후보 추출. 날짜·시간 같은 잡음은 단위 없는 2자리 이하면 버린다."""
    out = []
    for m in NUM_RE.finditer(text):
        raw, unit = m.group(1).rstrip(".,"), m.group(2)
        if not raw or (unit is None and len(raw.replace(",", "")) <= 2):
            continue
        try:
            out.append({"raw": m.group(0).strip(), "value": to_number(raw, unit), "unit": unit})
        except ValueError:
            continue
    return out


def composition_signature(comp: dict) -> str:
    keys = ("subject", "angle", "layout", "palette", "text_position", "background")
    return json.dumps({k: str(comp.get(k, "")).strip().lower() for k in keys}, ensure_ascii=False, sort_keys=True)


def composition_similarity(a: dict, b: dict) -> float:
    keys = ("subject", "angle", "layout", "palette", "text_position", "background")
    hit = sum(1 for k in keys if str(a.get(k, "")).strip().lower() == str(b.get(k, "")).strip().lower()
              and str(a.get(k, "")).strip())
    return hit / len(keys)


def dhash(path: str, size: int = 8) -> str | None:
    """Pillow가 있으면 perceptual dHash, 없으면 None (구도 대장만으로 판정)."""
    try:
        from PIL import Image
    except ImportError:
        return None
    img = Image.open(path).convert("L").resize((size + 1, size))
    px = list(img.getdata())
    bits = "".join("1" if px[r * (size + 1) + c] > px[r * (size + 1) + c + 1] else "0"
                   for r in range(size) for c in range(size))
    return f"{int(bits, 2):0{size * size // 4}x}"


def hamming(h1: str, h2: str) -> int:
    return bin(int(h1, 16) ^ int(h2, 16)).count("1")
