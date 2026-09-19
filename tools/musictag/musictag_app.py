#!/usr/bin/env python3
"""musictag_app.py - musictag.py의 웹 UI (a-Shell 로컬 서버).

  python3 musictag_app.py            # http://127.0.0.1:8080 (이 기기에서만)
  python3 musictag_app.py --port 9000
  python3 musictag_app.py --lan      # 같은 와이파이의 다른 기기에서도 접속

Safari로 열고 '공유 -> 홈 화면에 추가'를 하면 앱처럼 씁니다.
subprocess/셸 호출 없이 표준 라이브러리 http.server만 사용합니다.
"""
from __future__ import annotations

import base64
import json
import re
import secrets
import socket
import struct
import sys
import threading
import urllib.parse
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import musictag as core

KEY_FILE = core.DOCS / ".musictag_key"
_local = threading.local()


def _note(msg):
    log = getattr(_local, "log", None)
    if log is None:
        print(msg, flush=True)
    else:
        log.append(str(msg))


core.note = _note
core.ask = lambda label, default="": default


def get_key() -> str:
    """접속 키. 같은 기기의 다른 앱이 서버를 건드리지 못하게 막는다."""
    try:
        key = KEY_FILE.read_text(encoding="utf-8").strip()
        if key:
            return key
    except OSError:
        pass
    key = secrets.token_urlsafe(9)
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(key, encoding="utf-8")
    return key


SEARCH_TIMEOUT = 8
SAVE_WAIT = 180


def itunes_parallel(term, countries=None, limit=5):
    """국가별 조회를 동시에 던지고, 우선순위 순으로 첫 결과를 고른다.

    순차 조회는 앞 국가가 빌 때마다 왕복이 한 번씩 더 붙는다.
    동시에 던지면 걸리는 시간이 '가장 느린 하나'로 고정된다.
    """
    countries = countries or core.COUNTRIES
    out: dict[str, list] = {}

    def work(country):
        try:
            body = core.http_get(core.itunes_url(term, country, limit), timeout=SEARCH_TIMEOUT)
            out[country] = json.loads(body.decode("utf-8")).get("results", [])
        except Exception:  # noqa: BLE001
            out[country] = []

    threads = [threading.Thread(target=work, args=(c,), daemon=True) for c in countries]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=SEARCH_TIMEOUT + 1)
    for country in countries:
        if out.get(country):
            return out[country], country
    if not out:
        core.fail("곡 정보를 찾지 못했습니다.", "네트워크 상태를 확인하세요.")
    return [], ""


class Api:
    """HTTP와 무관한 순수 로직. 테스트는 이 클래스를 직접 호출한다."""

    def __init__(self, docs=None, out_dir=None):
        self.docs = Path(docs or core.DOCS)
        self.out_dir = Path(out_dir or core.OUT_DIR)
        self.jobs: dict[str, dict] = {}
        self.tag_cache: dict[str, tuple] = {}

    def tags_of(self, path):
        """파일이 바뀌지 않았으면 다시 파싱하지 않는다."""
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        hit = self.tag_cache.get(str(path))
        if hit and hit[0] == stamp:
            return hit[1], stat
        try:
            tags = core.read_tags(path)
        except Exception:  # noqa: BLE001
            tags = {}
        if len(self.tag_cache) > 500:
            self.tag_cache.clear()
        self.tag_cache[str(path)] = (stamp, tags)
        return tags, stat

    # ---------------------------------------------------------- 다운로드 작업
    def start(self, payload):
        url = core.clean_url(payload.get("url", ""))
        if not url:
            return {"error": "링크가 비어 있습니다. 유튜브 링크를 붙여넣어 주세요."}
        jid = secrets.token_urlsafe(6)
        job = {"id": jid, "state": "working", "log": ["다운로드 중..."], "dl": "running",
               "pct": 0, "done": threading.Event(), "url": url, "tmp": None,
               "video": {}, "candidates": []}
        self.jobs[jid] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return {"job": jid}

    def _run(self, job):
        """다운로드가 시작되는 순간 제목을 얻어, 곡 정보 검색을 동시에 돌린다.

        예전에는 다운로드가 끝나야 검색을 시작했다. 이제는 사용자가 후보를
        고르고 태그를 손보는 동안 음원이 뒤에서 계속 내려온다.
        """
        _local.log = job["log"]
        started = threading.Event()

        def hook(d):
            info = d.get("info_dict") or {}
            if d.get("status") != "downloading":
                return
            done, total = d.get("downloaded_bytes") or 0, (
                d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
            job["pct"] = min(99, int(done * 100 / total)) if total else 0
            if not started.is_set() and info.get("title"):
                started.set()
                self._begin_search(job, info)

        try:
            tmp, info = core.download(job["url"], hooks=[hook])
            job["tmp"], job["pct"], job["dl"] = str(tmp), 100, "done"
            if not started.is_set():  # 훅이 한 번도 안 불린 경우
                started.set()
                self._begin_search(job, info).join(SEARCH_TIMEOUT + 2)
        except BaseException as exc:  # noqa: BLE001 - die()의 SystemExit 포함
            if not any(line.startswith("오류") for line in job["log"]):
                core.fail("다운로드에 실패했습니다.",
                          "링크를 확인하거나 a-Shell에서 'pip install -U yt-dlp'를 실행하세요.", exc)
            job["dl"], job["state"] = "error", "error"
        finally:
            job["done"].set()
            _local.log = None

    def _begin_search(self, job, info):
        """제목을 알게 된 즉시 곡 정보 검색을 별도 스레드로 시작한다."""
        vid = "".join(c for c in info.get("id", "") if c.isalnum() or c in "-_")
        job["video"] = {"title": info.get("title", ""),
                        "uploader": info.get("uploader", ""), "id": vid}
        job["query"] = core.build_query(info.get("title", ""))

        def work():
            _local.log = job["log"]
            try:
                job["candidates"] = self._find(job["query"], None)
                if job["state"] == "working":
                    job["state"] = "ready"
            finally:
                _local.log = None

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        return thread

    def _find(self, query, countries):
        results, country = itunes_parallel(query, countries)
        out = []
        for r in results:
            meta = core.meta_from_result(r)
            meta["country"] = country
            meta["art"] = re.sub(r"/\d+x\d+bb", "/300x300bb", meta.get("artwork", ""))
            out.append(meta)
        return out

    def job(self, jid):
        job = self.jobs.get(jid)
        if not job:
            return {"error": "작업을 찾을 수 없습니다. 링크부터 다시 넣어 주세요."}
        return {"state": job["state"], "log": job["log"][-4:], "video": job["video"],
                "dl": job["dl"], "pct": job["pct"],
                "query": job.get("query", ""), "candidates": job["candidates"],
                "blank": core.blank_meta(job["video"].get("title", ""),
                                         job["video"].get("uploader", ""))}

    def search(self, payload):
        query = (payload.get("query") or "").strip()
        if not query:
            return {"error": "검색어를 입력해 주세요."}
        countries = [c for c in (payload.get("countries") or []) if c] or None
        log: list[str] = []
        _local.log = log
        try:
            candidates = self._find(query, countries)
        finally:
            _local.log = None
        return {"candidates": candidates, "log": log}

    # ---------------------------------------------------------- 커버 / 저장
    def _cover(self, choice, meta, video_id):
        mode = (choice or {}).get("mode", "itunes")
        if mode == "none":
            return None, ""
        if mode == "upload":
            raw = (choice.get("data") or "").split(",")[-1]
            try:
                data = base64.b64decode(raw, validate=True)
            except Exception:  # noqa: BLE001
                return None, "사진을 읽지 못했습니다."
            kind = core.image_kind(data)
            if kind not in ("jpeg", "png"):
                return None, "JPEG 또는 PNG만 넣을 수 있습니다. (webp/HEIC 미지원)"
            return (data, kind), ""
        art = meta.get("artwork", "") if mode == "itunes" else ""
        log: list[str] = []
        _local.log = log
        try:
            data, kind = core.get_cover({"artwork": art}, video_id,
                                        docs=self.docs, local=False)
        finally:
            _local.log = None
        return ((data, kind) if data else None), ("" if data else "커버를 찾지 못했습니다.")

    def save(self, payload):
        job = self.jobs.get(payload.get("job", ""))
        if not job:
            return {"error": "받아 둔 음원이 없습니다. 링크부터 다시 넣어 주세요."}
        if not job["done"].wait(timeout=SAVE_WAIT):  # 아직 받는 중이면 기다린다
            return {"error": "다운로드가 아직 끝나지 않았습니다. 잠시 뒤 다시 눌러 주세요."}
        if job["dl"] != "done" or not job.get("tmp"):
            return {"error": "받아 둔 음원이 없습니다. 링크부터 다시 넣어 주세요."}
        tmp = Path(job["tmp"])
        if not tmp.exists():
            return {"error": "임시 파일이 사라졌습니다. 다시 받아 주세요."}
        meta = dict(payload.get("meta") or {})
        cover, warn = self._cover(payload.get("cover"), meta, job["video"].get("id", ""))
        lyrics = core.clean_lyrics(payload.get("lyrics") or "")
        try:
            core.write_tags(tmp, meta, *(cover or (None, "")), lyrics=lyrics)
        except Exception as exc:  # noqa: BLE001
            return {"error": "태그를 쓰지 못했습니다. m4a가 아닌 형식으로 받았을 수 있습니다.",
                    "detail": str(exc)}
        self.out_dir.mkdir(parents=True, exist_ok=True)
        dest = core.unique_path(self.out_dir,
                                core.safe_filename(meta.get("artist", ""), meta.get("title", "")))
        tmp.replace(dest)
        job["state"] = "saved"
        return {"name": dest.name, "warn": warn}

    # ---------------------------------------------------------- 보관함
    def _path(self, name):
        path = (self.out_dir / Path(name).name)
        return path if path.exists() else None

    def library(self):
        self.out_dir.mkdir(parents=True, exist_ok=True)
        items = []
        for path in sorted(self.out_dir.glob("*.m4a")):
            tags, stat = self.tags_of(path)
            items.append({"name": path.name, "title": tags.get("title") or path.stem,
                          "artist": tags.get("artist", ""), "album": tags.get("album", ""),
                          "cover": bool(tags.get("has_cover")), "v": stat.st_mtime_ns})
        return {"items": items}

    def track(self, name):
        path = self._path(name)
        if not path:
            return {"error": "파일을 찾을 수 없습니다."}
        meta = core.read_tags(path)
        meta.pop("has_cover", None)
        return {"name": path.name, "meta": meta}

    def update(self, payload):
        path = self._path(payload.get("name", ""))
        if not path:
            return {"error": "파일을 찾을 수 없습니다."}
        meta = dict(payload.get("meta") or {})
        cover, warn = (None, "")
        if payload.get("cover"):
            cover, warn = self._cover(payload["cover"], meta, "")
        lyrics = payload.get("lyrics")
        lyrics = core.clean_lyrics(lyrics) if lyrics is not None else None
        try:
            core.write_tags(path, meta, *(cover or (None, "")), lyrics=lyrics)
        except Exception as exc:  # noqa: BLE001
            return {"error": "태그를 쓰지 못했습니다.", "detail": str(exc)}
        new = path
        if payload.get("rename"):
            new = core.unique_path(self.out_dir, core.safe_filename(
                meta.get("artist", ""), meta.get("title", "")))
            if new != path:
                path.replace(new)
        return {"name": new.name, "warn": warn}

    def remove(self, payload):
        path = self._path(payload.get("name", ""))
        if not path:
            return {"error": "파일을 찾을 수 없습니다."}
        path.unlink()
        return {"ok": True}

    def art(self, name):
        path = self._path(name)
        if not path:
            return None
        try:
            from mutagen.mp4 import MP4
            covers = (MP4(str(path)).tags or {}).get("covr") or []
        except Exception:  # noqa: BLE001
            return None
        return bytes(covers[0]) if covers else None


def app_icon(size: int = 180) -> bytes:
    """Pillow 없이 만드는 홈 화면 아이콘(PNG)."""
    bg, fg = (17, 17, 19), (245, 245, 247)
    cx, cy, r = size * 0.38, size * 0.68, size * 0.15
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            note_head = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
            stem = size * 0.50 <= x <= size * 0.56 and size * 0.22 <= y <= cy
            flag = size * 0.56 <= x <= size * 0.72 and size * 0.22 <= y <= size * 0.30
            row += bytes(fg if (note_head or stem or flag) else bg)
        rows.append(bytes(row))
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


class Handler(BaseHTTPRequestHandler):
    api: Api
    key: str
    server_version = "musictag"

    def log_message(self, *args):  # 조용히
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", cache="no-store"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data, code=200):
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _authed(self, query):
        return secrets.compare_digest(query.get("k", [""])[0], self.key)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def do_GET(self):  # noqa: N802
        parts = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parts.query)
        if parts.path == "/icon.png":
            return self._send(200, app_icon(), "image/png", "public, max-age=604800")
        if parts.path == "/":
            if not self._authed(query):
                return self._send(403, LOCKED.encode("utf-8"), "text/html; charset=utf-8")
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if not self._authed(query):
            return self._json({"error": "접속 키가 맞지 않습니다."}, 403)
        if parts.path == "/api/job":
            return self._json(self.api.job(query.get("id", [""])[0]))
        if parts.path == "/api/library":
            return self._json(self.api.library())
        if parts.path == "/api/track":
            return self._json(self.api.track(query.get("name", [""])[0]))
        if parts.path == "/api/art":
            data = self.api.art(query.get("name", [""])[0])
            if not data:
                return self._send(404, b"")
            # 주소에 파일 수정 시각(v)이 붙어 있어 바뀌면 자동으로 새로 받는다
            return self._send(200, data, "image/jpeg", "private, max-age=604800")
        return self._json({"error": "없는 주소입니다."}, 404)

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def do_POST(self):  # noqa: N802
        parts = urllib.parse.urlsplit(self.path)
        if not self._authed(urllib.parse.parse_qs(parts.query)):
            return self._json({"error": "접속 키가 맞지 않습니다."}, 403)
        routes = {"/api/start": self.api.start, "/api/search": self.api.search,
                  "/api/save": self.api.save, "/api/update": self.api.update,
                  "/api/remove": self.api.remove}
        handler = routes.get(parts.path)
        if not handler:
            return self._json({"error": "없는 주소입니다."}, 404)
        try:
            return self._json(handler(self._body()))
        except Exception as exc:  # noqa: BLE001
            core.fail("요청을 처리하지 못했습니다.", "a-Shell 화면의 메시지를 확인하세요.", exc)
            return self._json({"error": "요청을 처리하지 못했습니다.", "detail": str(exc)}, 500)


def lan_ip() -> str:
    """이 기기가 같은 와이파이에서 갖는 주소. 패킷은 실제로 나가지 않는다."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 9))  # TEST-NET-1, 라우팅만 확인
        return sock.getsockname()[0]
    except OSError:
        return ""
    finally:
        sock.close()


def serve(port=8080, host="127.0.0.1"):
    Handler.api, Handler.key = Api(), get_key()
    core.OUT_DIR.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((host, port), Handler)
    shared = host not in ("127.0.0.1", "localhost")
    shown = (lan_ip() or host) if shared else host
    print("musictag 앱이 열렸습니다. 브라우저 주소창에 아래 주소를 붙여넣으세요.\n")
    print(f"   http://{shown}:{port}/?k={Handler.key}\n")
    print("'공유 → 홈 화면에 추가'를 하면 앱처럼 쓸 수 있습니다.")
    if shared:
        print("\n[주의] 같은 와이파이의 다른 기기에서도 접속됩니다.")
        print("       암호화되지 않은 http이니 공용 와이파이에서는 쓰지 마세요.")
        print("       주소 끝의 ?k= 키를 아는 기기만 들어올 수 있습니다.")
    print("\na-Shell을 닫으면 서버도 멈춥니다. Split View로 브라우저와 함께 두세요.")
    print("종료: Ctrl+C\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n종료했습니다.")
    finally:
        httpd.server_close()


def parse_args(args):
    """--port / --host / --lan 만 받는다."""
    port, host = 8080, "127.0.0.1"
    if "--port" in args:
        i = args.index("--port")
        if i + 1 < len(args) and args[i + 1].isdigit():
            port = int(args[i + 1])
    if "--host" in args:
        i = args.index("--host")
        if i + 1 < len(args) and not args[i + 1].startswith("-"):
            host = args[i + 1]
    if "--lan" in args:
        host = "0.0.0.0"  # noqa: S104 - 사용자가 명시적으로 요청한 경우만
    return port, host


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    port, host = parse_args(args)
    try:
        serve(port, host)
    except OSError as exc:
        core.fail(f"{port} 포트를 열지 못했습니다.",
                  "이미 실행 중이거나 포트가 막혀 있습니다. --port 8081 로 바꿔 보세요.", exc)
        return 1
    return 0


LOCKED = """<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<body style="font:16px/1.6 -apple-system,sans-serif;padding:2rem;background:#111;color:#eee">
<h3>접속 키가 필요합니다</h3>
<p>a-Shell 화면에 표시된 주소를 <b>통째로</b> 복사해 주소창에 붙여넣으세요.
끝의 <code>?k=...</code> 부분까지 포함해야 합니다.</p></body>"""

PAGE = r"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="musictag">
<meta name="theme-color" content="#111113">
<link rel="apple-touch-icon" href="/icon.png">
<title>musictag</title>
<style>
:root{
  --bg:#f6f6f8; --card:#fff; --text:#16161a; --dim:#75757e; --line:#e3e3e9;
  --accent:#e2494a; --field:#fff; --shadow:0 1px 2px rgba(0,0,0,.06);
}
@media (prefers-color-scheme:dark){:root{
  --bg:#111113; --card:#1c1c20; --text:#f2f2f5; --dim:#96969f; --line:#2c2c33;
  --accent:#ff5f5f; --field:#26262c; --shadow:none;
}}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:var(--bg);color:var(--text);
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif;
  padding:env(safe-area-inset-top) 0 calc(env(safe-area-inset-bottom) + 24px)}
.wrap{max-width:560px;margin:0 auto;padding:0 16px}
header{display:flex;align-items:center;gap:10px;padding:18px 0 10px}
header b{font-size:19px;letter-spacing:-.02em}
header span{color:var(--dim);font-size:13px}
.seg{display:flex;background:var(--line);border-radius:10px;padding:2px;margin-bottom:16px}
.seg button{flex:1;border:0;background:none;color:var(--dim);font:inherit;font-weight:600;
  padding:7px;border-radius:8px}
.seg button[aria-selected=true]{background:var(--card);color:var(--text);box-shadow:var(--shadow)}
.card{background:var(--card);border-radius:14px;padding:16px;margin-bottom:12px;box-shadow:var(--shadow)}
h2{font-size:13px;font-weight:600;color:var(--dim);margin:0 0 10px;letter-spacing:.02em}
input,textarea,select{width:100%;font:inherit;color:var(--text);background:var(--field);
  border:1px solid var(--line);border-radius:10px;padding:11px 12px}
input:focus,textarea:focus,select:focus{outline:2px solid var(--accent);outline-offset:-1px}
textarea{resize:vertical;min-height:96px}
label{display:block;font-size:12px;color:var(--dim);margin:12px 0 5px}
label:first-child{margin-top:0}
.row{display:flex;gap:10px}.row>*{flex:1}
button.go{width:100%;border:0;border-radius:11px;padding:13px;font:inherit;font-weight:600;
  background:var(--accent);color:#fff;margin-top:14px}
button.go:disabled{opacity:.45}
button.ghost{background:none;border:1px solid var(--line);color:var(--text)}
button.mini{border:1px solid var(--line);background:none;color:var(--dim);font:inherit;
  font-size:13px;border-radius:9px;padding:8px 12px;width:auto;margin:0}
.hint{color:var(--dim);font-size:12.5px;margin:8px 0 0}
.err{color:var(--accent);font-size:13px;margin:10px 0 0}
.item{display:flex;gap:12px;align-items:center;padding:10px;border-radius:11px;
  border:1px solid transparent;cursor:pointer}
.item+.item{margin-top:2px}
.item[aria-selected=true]{border-color:var(--accent);background:rgba(226,73,74,.09)}
.item img,.item .ph{width:46px;height:46px;border-radius:7px;object-fit:cover;background:var(--line);flex:none}
.item .t{min-width:0}
.item .t div{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.item .t .s{color:var(--dim);font-size:12.5px}
.cov{display:flex;gap:14px;align-items:center}
.cov img,.cov .ph{width:78px;height:78px;border-radius:10px;object-fit:cover;background:var(--line);flex:none}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chips button{border:1px solid var(--line);background:none;color:var(--dim);font:inherit;
  font-size:13px;padding:7px 11px;border-radius:999px}
.chips button[aria-pressed=true]{border-color:var(--accent);color:var(--accent)}
.bar{height:3px;background:var(--line);border-radius:2px;margin-top:11px;overflow:hidden}
.bar i{display:block;height:100%;width:0;background:var(--accent);transition:width .35s ease}
.spin{width:15px;height:15px;border:2px solid var(--line);border-top-color:var(--accent);
  border-radius:50%;display:inline-block;vertical-align:-2px;animation:s .7s linear infinite}
@keyframes s{to{transform:rotate(360deg)}}
details{margin-top:14px;border-top:1px solid var(--line);padding-top:12px}
summary{font-size:13px;color:var(--dim);list-style:none;cursor:pointer}
summary::-webkit-details-marker{display:none}
summary::after{content:" ⌄"}
details[open] summary::after{content:" ⌃"}
.hide{display:none!important}
.toast{position:fixed;left:50%;bottom:calc(env(safe-area-inset-bottom) + 20px);
  transform:translateX(-50%);background:var(--card);border:1px solid var(--line);
  padding:11px 18px;border-radius:999px;box-shadow:0 6px 24px rgba(0,0,0,.2);font-size:14px}
</style></head>
<body><div class="wrap">
<header><b>musictag</b><span id="sub">유튜브 링크 하나로 태그까지</span></header>

<div class="seg" role="tablist">
  <button role="tab" id="tab-add" aria-selected="true" onclick="tab('add')">추가</button>
  <button role="tab" id="tab-lib" aria-selected="false" onclick="tab('lib')">보관함</button>
</div>

<section id="p-add">
  <div class="card" id="c-url">
    <h2>유튜브 링크</h2>
    <input id="url" type="url" inputmode="url" autocapitalize="off" autocorrect="off"
           placeholder="붙여넣기만 하면 됩니다">
    <button class="go" id="btn-get" onclick="start()">가져오기</button>
    <p class="hint">공백, 따옴표, <code>?si=</code> 같은 꼬리표는 알아서 지웁니다.</p>
    <p class="err hide" id="e-url"></p>
  </div>

  <div class="card hide" id="c-work">
    <span class="spin"></span> <span id="worklog">준비 중...</span>
    <div class="bar"><i id="dlbar"></i></div>
  </div>

  <div class="card hide" id="c-pick">
    <h2>곡 선택</h2>
    <div id="cands"></div>
    <div class="row" style="margin-top:12px">
      <button class="mini" style="flex:1" onclick="manual()">직접 입력</button>
      <button class="mini" style="flex:1" onclick="toggleSearch()">다시 검색</button>
    </div>
    <div class="hide" id="c-again" style="margin-top:12px">
      <input id="q" placeholder="검색어">
      <div class="row" style="margin-top:8px">
        <select id="country">
          <option value="JP,KR,US">일본 → 한국 → 미국</option>
          <option value="KR,JP,US">한국 → 일본 → 미국</option>
          <option value="US,KR,JP">미국 → 한국 → 일본</option>
        </select>
        <button class="mini" onclick="again()">검색</button>
      </div>
    </div>
  </div>

  <div class="card hide" id="c-meta">
    <h2>곡 정보</h2>
    <div id="form"></div>
    <label>가사 (직접 준비한 것만, 비워도 됩니다)</label>
    <textarea id="lyrics" placeholder="붙여넣으면 파일에 함께 저장됩니다"></textarea>
    <h2 style="margin-top:18px">커버</h2>
    <div class="cov">
      <img id="cov" alt="" class="hide"><div id="covph" class="ph"></div>
      <div style="flex:1">
        <div class="chips">
          <button data-m="itunes" onclick="cover('itunes')">앨범 아트</button>
          <button data-m="youtube" onclick="cover('youtube')">썸네일</button>
          <button data-m="upload" onclick="pick()">사진</button>
          <button data-m="none" onclick="cover('none')">없음</button>
        </div>
        <p class="hint" id="covhint">JPEG·PNG만 됩니다.</p>
      </div>
    </div>
    <input id="file" type="file" accept="image/jpeg,image/png" class="hide" onchange="upload(this)">
    <button class="go" id="btn-save" onclick="save()">저장</button>
    <p class="err hide" id="e-save"></p>
  </div>
</section>

<section id="p-lib" class="hide">
  <div class="card"><h2>보관함</h2><div id="lib">불러오는 중...</div></div>
  <div class="card hide" id="c-edit">
    <h2 id="edit-name"></h2>
    <div id="eform"></div>
    <label>가사</label><textarea id="elyrics"></textarea>
    <div class="chips" style="margin-top:12px">
      <button data-m="upload" onclick="epick()">커버 교체</button>
      <button data-m="none" onclick="ecover('none')">커버 삭제</button>
    </div>
    <input id="efile" type="file" accept="image/jpeg,image/png" class="hide" onchange="eupload(this)">
    <p class="hint" id="ecovhint">건드리지 않으면 기존 커버를 유지합니다.</p>
    <button class="go" onclick="esave()">수정 저장</button>
    <button class="go ghost" onclick="edel()">삭제</button>
    <p class="err hide" id="e-edit"></p>
  </div>
</section>
</div>
<script>
const K = new URLSearchParams(location.search).get('k') || '';
const $ = s => document.querySelector(s);
const show = (s, on) => $(s).classList.toggle('hide', !on);
const FIELDS = [['title','제목',1],['artist','아티스트',1],['album','앨범',1],
  ['date','발매일',2],['genre','장르',2],['album_artist','앨범 아티스트',0],
  ['track','트랙',0],['composer','작곡가',0],['comment','코멘트',0]];
let job = null, chosen = null, covMode = 'itunes', covData = null, editing = null, eCov;

async function api(path, body) {
  const url = path + (path.includes('?') ? '&' : '?') + 'k=' + encodeURIComponent(K);
  const r = await fetch(url, body ? {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(body)} : {});
  return r.json();
}
function toast(msg) {
  const t = document.createElement('div');
  t.className = 'toast'; t.textContent = msg; document.body.appendChild(t);
  setTimeout(() => t.remove(), 2600);
}
function err(sel, msg) { const e = $(sel); e.textContent = msg || ''; show(sel, !!msg); }
function tab(which) {
  $('#tab-add').ariaSelected = which === 'add'; $('#tab-lib').ariaSelected = which === 'lib';
  show('#p-add', which === 'add'); show('#p-lib', which === 'lib');
  if (which === 'lib') loadLib();
}
function field(host, k, label, meta) {
  const box = document.createElement('div');
  const l = document.createElement('label'); l.textContent = label;
  const i = document.createElement('input');
  i.id = host.id + '-' + k; i.value = meta[k] || '';
  if (k === 'date') i.placeholder = 'YYYY-MM-DD';
  if (k === 'track') i.inputMode = 'numeric';
  box.append(l, i); return box;
}
function fields(host, meta) {
  host.innerHTML = '';
  const row = document.createElement('div'); row.className = 'row';
  const more = document.createElement('details');
  more.innerHTML = '<summary>세부 정보</summary>';
  for (const [k, label, rank] of FIELDS) {
    const el = field(host, k, label, meta);
    (rank === 1 ? host : rank === 2 ? row : more).append(el);
  }
  host.append(row, more);
}
function collect(host, base) {
  const meta = Object.assign({}, base);
  for (const [k] of FIELDS) meta[k] = $('#' + host + '-' + k).value.trim();
  return meta;
}

/* ---------------- 추가 ---------------- */
async function start() {
  err('#e-url', ''); $('#btn-get').disabled = true;
  show('#c-pick', false); show('#c-meta', false); show('#c-work', true);
  $('#worklog').textContent = '다운로드 중...';
  window.shown = false; $('#dlbar').style.width = '0%';
  const r = await api('/api/start', {url: $('#url').value});
  if (r.error) { show('#c-work', false); $('#btn-get').disabled = false; return err('#e-url', r.error); }
  job = r.job; poll();
}
async function poll() {
  const r = await api('/api/job?id=' + job);
  const pct = r.pct || 0, running = r.dl === 'running';
  $('#worklog').textContent = running ? `음원 받는 중 ${pct}%`
    : ((r.log || []).slice(-1)[0] || '진행 중...');
  $('#dlbar').style.width = (running ? pct : 100) + '%';
  if (r.state === 'error') {
    show('#c-work', false); $('#btn-get').disabled = false;
    return err('#e-url', (r.log || []).join(' '));
  }
  if (r.state === 'ready' && !window.shown) {   // 후보는 다운로드를 기다리지 않는다
    window.shown = true; $('#btn-get').disabled = false;
    $('#sub').textContent = r.video.title || ''; window.vid = r.video.id || '';
    $('#q').value = r.query || ''; window.blank = r.blank;
    render(r.candidates);
  }
  const btn = $('#btn-save');
  btn.disabled = running;
  btn.textContent = running ? `저장 (받는 중 ${pct}%)` : '저장';
  if (r.state === 'working' || running) return setTimeout(poll, window.shown ? 1000 : 400);
  show('#c-work', false);
}
function render(list) {
  const box = $('#cands'); box.innerHTML = '';
  if (!list.length) { box.innerHTML = '<p class="hint">검색 결과가 없습니다. 직접 입력해 주세요.</p>'; }
  list.forEach((m, i) => {
    const el = document.createElement('div');
    el.className = 'item'; el.setAttribute('aria-selected', 'false');
    el.innerHTML = (m.art ? `<img src="${m.art}" alt="">` : '<div class="ph"></div>') +
      `<div class="t"><div>${esc(m.title)}</div>
       <div class="s">${esc(m.artist)} · ${esc(m.album)} · ${esc((m.date||'').slice(0,4))}</div></div>`;
    el.onclick = () => {
      box.querySelectorAll('.item').forEach(n => n.setAttribute('aria-selected', 'false'));
      el.setAttribute('aria-selected', 'true'); use(m);
    };
    box.append(el);
  });
  show('#c-pick', true);
}
const esc = s => (s || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function use(meta) {
  chosen = meta; fields($('#form'), meta);
  cover(meta.artwork ? 'itunes' : 'youtube');
  show('#c-meta', true); $('#c-meta').scrollIntoView({behavior:'smooth', block:'start'});
}
function manual() { use(window.blank || {}); }
function toggleSearch() { $('#c-again').classList.toggle('hide'); }
async function again() {
  const r = await api('/api/search', {query: $('#q').value,
    countries: $('#country').value.split(',')});
  if (r.error) return toast(r.error);
  render(r.candidates || []);
}
function cover(mode) {
  covMode = mode; covData = null;
  document.querySelectorAll('#c-meta .chips button')
    .forEach(b => b.ariaPressed = b.dataset.m === mode);
  const img = $('#cov'), ph = $('#covph');
  let src = '';
  if (mode === 'itunes' && chosen && chosen.artwork) src = chosen.artwork.replace(/\/\d+x\d+bb/, '/600x600bb');
  if (mode === 'youtube' && window.vid) src = 'https://i.ytimg.com/vi/' + window.vid + '/hqdefault.jpg';
  img.onerror = () => { img.classList.add('hide'); ph.classList.remove('hide'); };
  img.classList.toggle('hide', !src); ph.classList.toggle('hide', !!src);
  if (src) img.src = src;
  $('#covhint').textContent = {itunes:'iTunes 앨범 아트 600×600을 씁니다.',
    youtube:'유튜브 썸네일을 씁니다.', upload:'선택한 사진을 씁니다.',
    none:'커버 없이 저장합니다.'}[mode];
}
function pick() { $('#file').click(); }
function upload(input) {
  const f = input.files[0]; if (!f) return;
  const fr = new FileReader();
  fr.onload = () => { covMode = 'upload'; covData = fr.result;
    $('#cov').src = fr.result; show('#cov', true); show('#covph', false);
    document.querySelectorAll('#c-meta .chips button').forEach(b => b.ariaPressed = b.dataset.m === 'upload');
    $('#covhint').textContent = '선택한 사진을 씁니다.'; };
  fr.readAsDataURL(f);
}
async function save() {
  err('#e-save', ''); $('#btn-save').disabled = true;
  const r = await api('/api/save', {job, meta: collect('form', chosen || {}),
    lyrics: $('#lyrics').value, cover: {mode: covMode, data: covData}});
  $('#btn-save').disabled = false; $('#btn-save').textContent = '저장';
  if (r.error) return err('#e-save', r.error + (r.detail ? ' (' + r.detail + ')' : ''));
  if (r.warn) toast(r.warn);
  toast('저장했습니다: ' + r.name);
  $('#url').value = ''; $('#lyrics').value = '';
  show('#c-pick', false); show('#c-meta', false); $('#sub').textContent = '유튜브 링크 하나로 태그까지';
  tab('lib');
}

/* ---------------- 보관함 ---------------- */
async function loadLib() {
  const r = await api('/api/library'); const box = $('#lib'); box.innerHTML = '';
  if (!r.items || !r.items.length) { box.innerHTML = '<p class="hint">아직 저장된 곡이 없습니다.</p>'; return; }
  for (const it of r.items) {
    const el = document.createElement('div'); el.className = 'item';
    el.innerHTML = (it.cover ? `<img src="/api/art?name=${encodeURIComponent(it.name)}&k=${K}&v=${it.v}" alt="" loading="lazy">`
      : '<div class="ph"></div>') +
      `<div class="t"><div>${esc(it.title)}</div><div class="s">${esc(it.artist)} · ${esc(it.album)}</div></div>`;
    el.onclick = () => openTrack(it.name);
    box.append(el);
  }
}
async function openTrack(name) {
  const r = await api('/api/track?name=' + encodeURIComponent(name));
  if (r.error) return toast(r.error);
  editing = r.name; eCov = null; err('#e-edit', '');
  $('#edit-name').textContent = r.name;
  fields($('#eform'), r.meta); $('#elyrics').value = r.meta.lyrics || '';
  $('#ecovhint').textContent = '건드리지 않으면 기존 커버를 유지합니다.';
  show('#c-edit', true); $('#c-edit').scrollIntoView({behavior:'smooth', block:'start'});
}
function epick() { $('#efile').click(); }
function ecover(mode) { eCov = {mode}; $('#ecovhint').textContent = '저장하면 커버를 지웁니다.'; }
function eupload(input) {
  const f = input.files[0]; if (!f) return;
  const fr = new FileReader();
  fr.onload = () => { eCov = {mode:'upload', data: fr.result};
    $('#ecovhint').textContent = '저장하면 선택한 사진으로 바꿉니다.'; };
  fr.readAsDataURL(f);
}
async function esave() {
  const r = await api('/api/update', {name: editing, meta: collect('eform', {}),
    lyrics: $('#elyrics').value, cover: eCov, rename: true});
  if (r.error) return err('#e-edit', r.error + (r.detail ? ' (' + r.detail + ')' : ''));
  if (r.warn) toast(r.warn);
  toast('수정했습니다'); show('#c-edit', false); loadLib();
}
async function edel() {
  if (!confirm(editing + '\n정말 삭제할까요?')) return;
  const r = await api('/api/remove', {name: editing});
  if (r.error) return err('#e-edit', r.error);
  toast('삭제했습니다'); show('#c-edit', false); loadLib();
}
cover('itunes');
</script></body></html>"""

if __name__ == "__main__":
    raise SystemExit(main())
