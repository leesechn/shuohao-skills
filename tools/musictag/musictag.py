#!/usr/bin/env python3
"""musictag.py - a-Shell(iPadOS)용 음원 다운로드/태깅 도구.

  python3 musictag.py <링크>          묻지 않고 바로 저장 (가장 빠름)
  python3 musictag.py <링크> --ask    항목을 하나씩 확인하며 저장
  python3 musictag.py                 링크를 물어본 뒤 하나씩 확인
  python3 musictag.py edit 곡.m4a     기존 파일 태그 수정
  python3 musictag.py show 곡.m4a     태그 요약 출력
  옵션: --debug (traceback), --country JP,KR,US
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

DOCS = Path.home() / "Documents"
OUT_DIR = DOCS / "music"
TMP_DIR = DOCS / "musictagtmp"
COUNTRIES = ["JP", "KR", "US"]
TIMEOUT = 20
DEBUG = False
QUOTES = "“”‘’«»「」'\"`"
ZW = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)
TRACKING = {"si", "pp", "feature", "ab_channel", "utm_source", "utm_medium",
            "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
BAD_CHARS = '/\\:*?"<>|'
FIELDS = [("title", "제목"), ("artist", "아티스트"), ("album_artist", "앨범 아티스트"),
          ("album", "앨범"), ("date", "발매일(YYYY-MM-DD)"), ("genre", "장르"),
          ("track", "트랙 번호"), ("composer", "작곡가"), ("comment", "코멘트")]
MP4KEYS = {"title": "\xa9nam", "artist": "\xa9ART", "album_artist": "aART",
           "album": "\xa9alb", "date": "\xa9day", "genre": "\xa9gen",
           "composer": "\xa9wrt", "comment": "\xa9cmt", "lyrics": "\xa9lyr"}
NOISE = re.compile(r"\[[^\]]*\]|\([^)]*\)|【[^】]*】|[「」『』《》]")
WORDS = re.compile(r"(?i)\b(official|music\s*video|mv|m/v|lyrics?|audio|hd|4k|"
                   r"full\s*ver\.?|live|teaser|가사|공식|뮤직비디오)\b")

note = print

def fail(msg, hint="", exc=None, stop=False):
    """한국어 한 줄 요약 + 다음 행동 안내. traceback은 --debug에서만."""
    note("오류: " + msg)
    if hint:
        note("  -> " + hint)
    if exc is not None and DEBUG:
        import traceback
        traceback.print_exception(type(exc), exc, exc.__traceback__)
    if stop:
        raise SystemExit(1)

def die(msg, hint="", exc=None):
    fail(msg, hint, exc, stop=True)

def ask(label, default=""):
    try:
        got = input(f"{label}{f' [{default}]' if default else ''} (Enter=유지): ").strip()
    except EOFError:
        return default
    return got or default

def is_link(text):
    """명령어가 아니라 링크로 보이는가."""
    t = (text or "").strip().strip(QUOTES)
    return t.startswith(("http://", "https://")) or "youtu" in t.lower()

def clean_url(raw):
    """앞뒤 공백/휘어진 따옴표와 ?si= 같은 추적 파라미터 제거."""
    s = unicodedata.normalize("NFKC", raw or "")
    s = "".join(c for c in s if c not in QUOTES and not c.isspace()).translate(ZW)
    if not s:
        return ""
    p = urllib.parse.urlsplit(s)
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
         if k.lower() not in TRACKING]
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(q), ""))

def clean_lyrics(text):
    """제로폭 공백(U+200B 등)과 줄 끝 공백 제거."""
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n").translate(ZW)
    return "\n".join(line.rstrip() for line in t.split("\n")).strip("\n")

def safe_filename(artist, title, maxlen=80):
    """'아티스트 - 제목' -> 파일 앱에서 안전한 이름."""
    base = f"{artist} - {title}".strip().strip("-").strip()
    base = "".join(" " if c in BAD_CHARS else c for c in base).translate(ZW)
    base = re.sub(r"\s+", "_", base.strip()).strip("._")
    return base[:maxlen].strip("._") or "untitled"

def unique_path(folder, stem, ext=".m4a"):
    """같은 이름이 있으면 _2, _3을 붙인다."""
    path, n = folder / (stem + ext), 2
    while path.exists():
        path = folder / f"{stem}_{n}{ext}"
        n += 1
    return path

def build_query(title):
    """영상 제목에서 MV/Official/괄호 등을 걷어내 검색어를 만든다."""
    t = WORDS.sub(" ", NOISE.sub(" ", title or ""))
    t = re.sub(r"\s+", " ", re.sub(r"[|/•·\-–—_~!@#$^&*+=]+", " ", t)).strip()
    return t or re.sub(r"\s+", " ", (title or "")).strip()

def http_get(url, timeout=None):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as resp:  # noqa: S310
        return resp.read()

def itunes_url(term, country, limit=5):
    return "https://itunes.apple.com/search?" + urllib.parse.urlencode(
        {"term": term, "entity": "song", "limit": limit, "country": country})

def itunes_search(term, countries=None, limit=5):
    for country in countries or COUNTRIES:
        try:
            results = json.loads(http_get(itunes_url(term, country, limit)).decode("utf-8")).get("results", [])
        except Exception as exc:  # noqa: BLE001
            fail(f"iTunes 검색 실패({country}).", "네트워크 상태를 확인하세요.", exc)
            continue
        if results:
            return results, country
    return [], ""

def meta_from_result(r):
    return {"title": r.get("trackName", ""), "artist": r.get("artistName", ""),
            "album_artist": r.get("artistName", ""), "album": r.get("collectionName", ""),
            "date": (r.get("releaseDate") or "")[:10], "genre": r.get("primaryGenreName", ""),
            "track": str(r.get("trackNumber") or ""), "track_total": str(r.get("trackCount") or ""),
            "artwork": r.get("artworkUrl100", ""), "composer": "", "comment": ""}

def blank_meta(title="", artist=""):
    m = dict.fromkeys([k for k, _ in FIELDS], "")
    m.update({"title": title, "artist": artist, "album_artist": artist,
              "track_total": "", "artwork": ""})
    return m

def choose_meta(query, fb_title, fb_artist, countries=None):
    """후보 5개를 번호로 보여준다. 0=직접 입력, s=검색어 다시."""
    while True:
        results, country = itunes_search(query, countries)
        if not results:
            note("검색 결과가 없습니다. 직접 입력으로 넘어갑니다.")
            return blank_meta(fb_title, fb_artist)
        note(f"\n[{country}] '{query}' 검색 결과")
        for i, r in enumerate(results, 1):
            note(f"  {i}. {r.get('artistName', '?')} - {r.get('trackName', '?')}"
                 f"  ({r.get('collectionName', '?')}, {(r.get('releaseDate') or '')[:4]})")
        pick = ask("번호 선택 (0=직접 입력, s=검색어 다시)", "1")
        if pick.lower() == "s":
            query = ask("검색어", query)
        elif pick == "0":
            return blank_meta(fb_title, fb_artist)
        elif pick.isdigit() and 1 <= int(pick) <= len(results):
            return meta_from_result(results[int(pick) - 1])
        else:
            note("번호를 다시 입력하세요.")

def confirm_meta(meta):
    note("\n항목마다 Enter=유지, 입력=수정 (작곡가/코멘트는 비워도 됩니다)")
    for key, label in FIELDS:
        meta[key] = ask(label, meta.get(key, ""))
    if meta.get("track") and not str(meta["track"]).isdigit():
        note("트랙 번호가 숫자가 아니라 비워 둡니다.")
        meta["track"] = ""
    return meta

def image_kind(data):
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return ""

def get_cover(meta, video_id="", docs=None, local=True):
    """1) 로컬 cover 파일 2) iTunes 600x600 3) 유튜브 썸네일 순."""
    docs = docs or DOCS
    for name in ("cover.jpg", "cover.jpeg", "cover.png", "cover.webp") if local else ():
        path = docs / name
        if not path.exists():
            continue
        data = path.read_bytes()
        kind = image_kind(data)
        if kind in ("jpeg", "png"):
            note(f"커버: {name} 사용")
            return data, kind
        note(f"커버: {name}은(는) webp 등 미지원 형식이라 건너뜁니다.")
    urls = []
    if meta.get("artwork"):
        urls.append(re.sub(r"/\d+x\d+bb", "/600x600bb", meta["artwork"]))
    if video_id:
        urls += [f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
                 f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"]
    for url in urls:
        try:
            data = http_get(url)
        except Exception as exc:  # noqa: BLE001
            fail("커버 이미지를 받지 못했습니다.", "다음 후보로 넘어갑니다.", exc)
            continue
        kind = image_kind(data)
        if kind in ("jpeg", "png"):
            note("커버: " + url.rsplit("/", 1)[-1] + " 사용")
            return data, kind
        note("커버: webp 등 미지원 형식이라 건너뜁니다.")
    note("커버: 찾지 못했습니다. 커버 없이 진행합니다.")
    return None, ""

def take_lyrics(docs=None):
    """~/Documents/lyrics.txt만 사용. 읽은 뒤 lyrics_used.txt로 이름 변경."""
    docs = docs or DOCS
    src = docs / "lyrics.txt"
    if not src.exists():
        return ""
    try:
        text = clean_lyrics(src.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        fail("lyrics.txt를 읽지 못했습니다.", "파일을 UTF-8로 저장했는지 확인하세요.", exc)
        return ""
    try:
        src.replace(unique_path(docs, "lyrics_used", ".txt"))
    except OSError as exc:
        fail("lyrics.txt 이름 변경 실패.", "다음 곡에 섞이지 않게 직접 옮기세요.", exc)
    note(f"가사: lyrics.txt {len(text.splitlines())}줄 삽입")
    return text

def write_tags(path, meta, cover=None, cover_kind="jpeg", lyrics=None):
    from mutagen.mp4 import MP4, MP4Cover
    audio = MP4(str(path))
    if audio.tags is None:
        audio.add_tags()
    tags, values = audio.tags, dict(meta)
    if lyrics is not None:
        values["lyrics"] = lyrics
    for key, mp4key in MP4KEYS.items():
        if key not in values:
            continue
        val = str(values.get(key) or "")
        if val:
            tags[mp4key] = [val]
        elif mp4key in tags:
            del tags[mp4key]
    track, total = str(meta.get("track") or ""), str(meta.get("track_total") or "")
    if track.isdigit():
        tags["trkn"] = [(int(track), int(total) if total.isdigit() else 0)]
    elif "trkn" in tags:
        del tags["trkn"]
    if cover:
        fmt = MP4Cover.FORMAT_PNG if cover_kind == "png" else MP4Cover.FORMAT_JPEG
        tags["covr"] = [MP4Cover(cover, imageformat=fmt)]
    audio.save()

def read_tags(path):
    from mutagen.mp4 import MP4
    tags = MP4(str(path)).tags or {}
    meta = {k: (tags.get(v, [""])[0] if tags.get(v) else "") for k, v in MP4KEYS.items()}
    trkn = (tags.get("trkn") or [(0, 0)])[0]
    meta["track"] = str(trkn[0] or "")
    meta["track_total"] = str(trkn[1] or "")
    meta["has_cover"] = bool(tags.get("covr"))
    return meta

def resolve(name):
    for cand in (Path(name), OUT_DIR / name, DOCS / name):
        if cand.exists():
            return cand
    die(f"'{name}' 파일을 찾을 수 없습니다.",
        "~/Documents 또는 ~/Documents/music 안의 파일명을 확인하세요.")

def cmd_show(name):
    meta = read_tags(resolve(name))
    for key, label in FIELDS:
        note(f"{label}: {meta.get(key) or '-'}")
    lines = (meta.get("lyrics") or "").splitlines()
    note(f"가사: {lines[0] if lines else '-'} ... (총 {len(lines)}줄)")
    note("커버: " + ("있음" if meta.get("has_cover") else "없음"))

def cmd_edit(name):
    path = resolve(name)
    cmd_show(name)
    meta = confirm_meta(read_tags(path))
    cover, kind = (None, "")
    if ask("커버를 교체할까요? (y/n)", "n").lower().startswith("y"):
        cover, kind = get_cover({})
    write_tags(path, meta, cover, kind, take_lyrics() or None)
    note(f"완료: {path}")

def download(url, hooks=None):
    """yt-dlp를 라이브러리로 호출. ffmpeg 후처리 없이 m4a 원본만 받는다.

    hooks: yt-dlp progress_hooks. 다운로드가 시작되는 순간 제목을 알 수 있어
    곡 정보 검색을 다운로드와 겹쳐 돌릴 수 있다.
    """
    try:
        import yt_dlp
    except ImportError as exc:
        die("yt-dlp를 불러오지 못했습니다.",
            "a-Shell에서 'pip install -U yt-dlp' 실행 후 다시 시도하세요.", exc)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    for old in TMP_DIR.glob("tmpaudio*"):
        old.unlink()
    opts = {"format": "bestaudio[ext=m4a]/bestaudio", "noplaylist": True,
            "outtmpl": str(TMP_DIR / "tmpaudio.%(ext)s"),
            "quiet": True, "no_warnings": True, "noprogress": True,
            "progress_hooks": list(hooks or [])}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:  # noqa: BLE001
        die("다운로드에 실패했습니다.",
            "'pip install -U yt-dlp'로 업데이트하거나 링크를 다시 확인하세요.", exc)
    files = sorted(TMP_DIR.glob("tmpaudio*"))
    if not files:
        die("받은 파일을 찾지 못했습니다.", "링크를 확인하고 다시 실행하세요.")
    return files[0], info

def auto_meta(query, fb_title, fb_artist, countries=None):
    """묻지 않고 첫 번째 검색 결과를 쓴다."""
    results, country = itunes_search(query, countries)
    if not results:
        note("곡 정보를 찾지 못해 영상 제목을 그대로 씁니다.")
        return blank_meta(fb_title, fb_artist)
    meta = meta_from_result(results[0])
    note(f"[{country}] {meta['artist']} - {meta['title']} ({meta['album']})")
    return meta

def progress(d):
    if d.get("status") != "downloading":
        return
    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
    done = d.get("downloaded_bytes") or 0
    if total:
        print(f"\r받는 중 {min(99, int(done * 100 / total))}%", end="", flush=True)

def cmd_download(countries=None, url=None, auto=False):
    url = clean_url(url or ask("유튜브 링크를 붙여넣고 Enter", ""))
    if not url:
        die("링크가 비어 있습니다.", "다시 실행해 링크를 붙여넣으세요.")
    note("다운로드 중...")
    tmp, info = download(url, hooks=[progress])
    title, uploader = info.get("title", ""), info.get("uploader", "")
    video_id = "".join(c for c in info.get("id", "") if c.isalnum() or c in "-_")
    note(f"\r영상: {title} / {uploader}")
    if auto:
        meta = auto_meta(build_query(title), title, uploader, countries)
    else:
        meta = confirm_meta(choose_meta(build_query(title), title, uploader, countries))
    cover, kind = get_cover(meta, video_id)
    try:
        write_tags(tmp, meta, cover, kind, take_lyrics())
    except Exception as exc:  # noqa: BLE001
        die("태그를 쓰지 못했습니다.", "m4a가 아닌 형식으로 받았을 수 있습니다. 다시 시도하세요.", exc)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = unique_path(OUT_DIR, safe_filename(meta.get("artist", ""), meta.get("title", "")))
    tmp.replace(dest)
    for old in TMP_DIR.glob("tmpaudio*"):
        old.unlink()
    note(f"\n저장 완료: {dest}")

def main(argv=None):
    global DEBUG
    args = list(sys.argv[1:] if argv is None else argv)
    DEBUG = "--debug" in args
    ask_mode = "--ask" in args
    args = [a for a in args if a not in ("--debug", "--ask")]
    countries = None
    if "--country" in args:
        i = args.index("--country")
        if i + 1 < len(args):
            countries = [c.strip().upper() for c in args[i + 1].split(",") if c.strip()]
        del args[i:i + 2]
    try:
        cmd = args[0] if args else ""
        if cmd in ("show", "edit"):
            if len(args) < 2:
                die("파일명을 함께 입력하세요.", f"예: python3 musictag.py {cmd} 곡.m4a")
            (cmd_show if cmd == "show" else cmd_edit)(args[1])
        elif is_link(cmd):
            # 링크를 붙여 넣으면 묻지 않고 바로 저장한다. --ask면 하나씩 확인
            cmd_download(countries, url=cmd, auto=not ask_mode)
        elif cmd:
            die(f"알 수 없는 명령 '{cmd}'.",
                "사용법: python3 musictag.py [링크 | edit 곡.m4a | show 곡.m4a]")
        else:
            cmd_download(countries)
    except KeyboardInterrupt:
        note("\n중단했습니다.")
        return 1
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception as exc:  # noqa: BLE001
        fail("예상치 못한 문제가 생겼습니다.", "--debug를 붙여 다시 실행하면 자세히 보입니다.", exc)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
