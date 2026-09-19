"""musictag_app.py 테스트. 네트워크와 yt-dlp는 전부 mock."""
from __future__ import annotations

import base64
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import musictag as core
import musictag_app as app
from conftest import imported_modules, silent_m4a_bytes, used_names

JPEG = b"\xff\xd8\xff" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
SAMPLE = {"trackName": "Song", "artistName": "Artist", "collectionName": "Album",
          "releaseDate": "2021-03-04T12:00:00Z", "primaryGenreName": "J-Pop",
          "trackNumber": 7, "trackCount": 12, "artworkUrl100": "https://x/y/100x100bb.jpg"}


@pytest.fixture()
def api(tmp_path):
    return app.Api(docs=tmp_path, out_dir=tmp_path / "music")


def wait(api_obj, jid, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        state = api_obj.job(jid)["state"]
        if state != "working":
            return state
        time.sleep(0.02)
    raise AssertionError("작업이 끝나지 않음")


def fake_download(tmp_path):
    def _dl(url, hooks=None):
        tmp = tmp_path / "tmpaudio.m4a"
        tmp.write_bytes(silent_m4a_bytes())
        return tmp, {"title": "[MV] Artist - Song (Official)", "uploader": "Chan", "id": "VID123"}
    return _dl


# ------------------------------------------------------------ 접속 키
def test_get_key_is_created_once(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "KEY_FILE", tmp_path / ".musictag_key")
    first = app.get_key()
    assert first and app.get_key() == first


# ------------------------------------------------------------ 다운로드 작업
def test_start_rejects_empty_url(api):
    assert "error" in api.start({"url": "   "})


def test_start_cleans_url_before_download(api, tmp_path, monkeypatch):
    seen = []

    def _dl(url, hooks=None):
        seen.append(url)
        return fake_download(tmp_path)(url, hooks)

    monkeypatch.setattr(core, "download", _dl)
    monkeypatch.setattr(app, "itunes_parallel", lambda *a, **k: ([SAMPLE], "JP"))
    jid = api.start({"url": "“https://youtu.be/VID123?si=x”"})["job"]
    assert wait(api, jid) == "ready"
    assert seen == ["https://youtu.be/VID123"]


def test_job_returns_candidates_and_blank(api, tmp_path, monkeypatch):
    monkeypatch.setattr(core, "download", fake_download(tmp_path))
    monkeypatch.setattr(app, "itunes_parallel", lambda *a, **k: ([SAMPLE], "JP"))
    jid = api.start({"url": "https://youtu.be/VID123"})["job"]
    assert wait(api, jid) == "ready"
    data = api.job(jid)
    assert data["video"] == {"title": "[MV] Artist - Song (Official)",
                             "uploader": "Chan", "id": "VID123"}
    assert data["query"] == "Artist Song"
    cand = data["candidates"][0]
    assert cand["title"] == "Song" and cand["art"].endswith("300x300bb.jpg")
    assert data["blank"]["title"] == "[MV] Artist - Song (Official)"


def test_job_reports_download_failure_in_korean(api, monkeypatch):
    def boom(url, hooks=None):
        core.die("다운로드에 실패했습니다.", "링크를 다시 확인하세요.")

    monkeypatch.setattr(core, "download", boom)
    jid = api.start({"url": "https://youtu.be/BAD"})["job"]
    assert wait(api, jid) == "error"
    assert any("오류" in line for line in api.job(jid)["log"])


def test_unknown_job(api):
    assert "error" in api.job("nope")


def test_search_requires_query(api):
    assert "error" in api.search({"query": "  "})


def test_search_passes_country_order(api, monkeypatch):
    seen = {}

    def fake(term, countries=None, limit=5):
        seen["countries"] = countries
        return [SAMPLE], "KR"

    monkeypatch.setattr(app, "itunes_parallel", fake)
    out = api.search({"query": "abc", "countries": ["KR", "US"]})
    assert seen["countries"] == ["KR", "US"] and out["candidates"][0]["country"] == "KR"


# ------------------------------------------------------------ 속도: 병렬 조회
def test_itunes_parallel_keeps_priority_order(monkeypatch):
    """JP가 비면 KR, KR도 비면 US. 동시에 던져도 우선순위는 그대로."""
    def fake(url, timeout=None):
        hit = "country=KR" in url or "country=US" in url
        return json.dumps({"results": [SAMPLE] if hit else []}).encode()

    monkeypatch.setattr(core, "http_get", fake)
    results, country = app.itunes_parallel("q")
    assert country == "KR" and results == [SAMPLE]


def test_itunes_parallel_is_actually_concurrent(monkeypatch):
    """순차라면 3개 x 0.3초 = 0.9초. 동시라면 0.3초 근처에서 끝나야 한다."""
    def slow(url, timeout=None):
        time.sleep(0.3)
        return json.dumps({"results": [SAMPLE] if "country=US" in url else []}).encode()

    monkeypatch.setattr(core, "http_get", slow)
    started = time.monotonic()
    results, country = app.itunes_parallel("q")
    elapsed = time.monotonic() - started
    assert country == "US" and results == [SAMPLE]
    assert elapsed < 0.6, f"병렬이 아님: {elapsed:.2f}초"


def test_itunes_parallel_survives_failures(monkeypatch):
    def boom(url, timeout=None):
        raise OSError("네트워크 없음")

    monkeypatch.setattr(core, "http_get", boom)
    assert app.itunes_parallel("q") == ([], "")


# ------------------------------------------------------------ 속도: 겹쳐 받기
def hooked_download(tmp_path, hold):
    """제목을 먼저 알리고, 다운로드는 hold가 풀릴 때까지 끌고 간다."""
    def _dl(url, hooks=None):
        info = {"title": "Artist - Song", "uploader": "Chan", "id": "VID123"}
        for hook in hooks or []:
            hook({"status": "downloading", "info_dict": info,
                  "downloaded_bytes": 30, "total_bytes": 100})
        hold.wait(5)
        tmp = tmp_path / "tmpaudio.m4a"
        tmp.write_bytes(silent_m4a_bytes())
        return tmp, info
    return _dl


def test_candidates_appear_before_download_finishes(api, tmp_path, monkeypatch):
    """예전에는 다운로드가 끝나야 후보가 떴다. 이제는 받는 도중에 떠야 한다."""
    hold = threading.Event()
    monkeypatch.setattr(core, "download", hooked_download(tmp_path, hold))
    monkeypatch.setattr(app, "itunes_parallel", lambda *a, **k: ([SAMPLE], "JP"))
    jid = api.start({"url": "https://youtu.be/VID123"})["job"]

    end = time.time() + 5
    while time.time() < end and api.job(jid)["state"] != "ready":
        time.sleep(0.02)
    data = api.job(jid)
    assert data["state"] == "ready", "다운로드 중에 후보가 뜨지 않음"
    assert data["dl"] == "running", "다운로드가 이미 끝나버려 겹치기를 검증하지 못함"
    assert data["candidates"] and data["pct"] == 30
    hold.set()
    assert wait(api, jid) == "ready"


def test_save_waits_for_download_then_times_out(api, tmp_path, monkeypatch):
    hold = threading.Event()
    monkeypatch.setattr(core, "download", hooked_download(tmp_path, hold))
    monkeypatch.setattr(app, "itunes_parallel", lambda *a, **k: ([SAMPLE], "JP"))
    monkeypatch.setattr(app, "SAVE_WAIT", 0.1)
    jid = api.start({"url": "https://youtu.be/VID123"})["job"]
    time.sleep(0.1)
    out = api.save({"job": jid, "meta": {"title": "T", "artist": "A"}})
    assert "아직" in out["error"]
    hold.set()


def test_progress_percent_is_reported(api, tmp_path, monkeypatch):
    hold = threading.Event()
    hold.set()
    monkeypatch.setattr(core, "download", hooked_download(tmp_path, hold))
    monkeypatch.setattr(app, "itunes_parallel", lambda *a, **k: ([SAMPLE], "JP"))
    jid = api.start({"url": "https://youtu.be/VID123"})["job"]
    assert wait(api, jid) == "ready"
    end = time.time() + 5           # 검색 스레드가 먼저 끝날 수 있어 다운로드 완료를 따로 기다린다
    while time.time() < end and api.job(jid)["dl"] == "running":
        time.sleep(0.02)
    assert api.job(jid)["dl"] == "done" and api.job(jid)["pct"] == 100


# ------------------------------------------------------------ 커버 선택
def test_cover_upload_accepts_jpeg_and_png(api):
    for raw, kind in ((JPEG, "jpeg"), (PNG, "png")):
        payload = {"mode": "upload", "data": "data:image/x;base64," + base64.b64encode(raw).decode()}
        cover, warn = api._cover(payload, {}, "")
        assert cover == (raw, kind) and warn == ""


def test_cover_upload_rejects_webp(api):
    raw = base64.b64encode(b"RIFF1234WEBPVP8 ").decode()
    cover, warn = api._cover({"mode": "upload", "data": raw}, {}, "")
    assert cover is None and "JPEG" in warn


def test_cover_upload_rejects_broken_base64(api):
    cover, warn = api._cover({"mode": "upload", "data": "!!!not base64!!!"}, {}, "")
    assert cover is None and warn


def test_cover_none(api):
    assert api._cover({"mode": "none"}, {"artwork": "https://x/100x100bb.jpg"}, "V") == (None, "")


def test_cover_itunes_ignores_local_cover_file(api, tmp_path, monkeypatch):
    """앱에서는 '앨범 아트'를 고르면 남아 있는 cover.jpg가 끼어들면 안 된다."""
    (tmp_path / "cover.jpg").write_bytes(JPEG)
    monkeypatch.setattr(core, "http_get", lambda url: PNG)
    cover, _ = api._cover({"mode": "itunes"}, {"artwork": "https://x/y/100x100bb.jpg"}, "V")
    assert cover == (PNG, "png")


def test_cover_youtube_uses_thumbnail(api, monkeypatch):
    seen = []
    monkeypatch.setattr(core, "http_get", lambda url: (seen.append(url), JPEG)[1])
    cover, _ = api._cover({"mode": "youtube"}, {"artwork": "https://x/y/100x100bb.jpg"}, "VID")
    assert cover == (JPEG, "jpeg")
    assert seen == ["https://i.ytimg.com/vi/VID/maxresdefault.jpg"]


# ------------------------------------------------------------ 저장 / 보관함
def _saved(api_obj, tmp_path, monkeypatch, **over):
    monkeypatch.setattr(core, "download", fake_download(tmp_path))
    monkeypatch.setattr(app, "itunes_parallel", lambda *a, **k: ([SAMPLE], "JP"))
    jid = api_obj.start({"url": "https://youtu.be/VID123"})["job"]
    wait(api_obj, jid)
    meta = dict(api_obj.job(jid)["candidates"][0])
    meta.update(over)
    return api_obj.save({"job": jid, "meta": meta, "lyrics": "한줄 ​\n둘 ",
                         "cover": {"mode": "upload",
                                   "data": base64.b64encode(JPEG).decode()}})


def test_save_writes_tags_and_filename(api, tmp_path, monkeypatch):
    out = _saved(api, tmp_path, monkeypatch)
    assert out["name"] == "Artist_-_Song.m4a"
    saved = api.out_dir / out["name"]
    tags = core.read_tags(saved)
    assert tags["title"] == "Song" and tags["artist"] == "Artist"
    assert tags["track"] == "7" and tags["track_total"] == "12"
    assert tags["lyrics"] == "한줄\n둘" and tags["has_cover"] is True
    assert not (tmp_path / "tmpaudio.m4a").exists()


def test_save_sanitizes_filename(api, tmp_path, monkeypatch):
    out = _saved(api, tmp_path, monkeypatch, artist="A/B", title="X: Y")
    assert out["name"] == "A_B_-_X_Y.m4a"


def test_save_without_job(api):
    assert "error" in api.save({"job": "nope", "meta": {}})


def test_library_track_update_remove(api, tmp_path, monkeypatch):
    name = _saved(api, tmp_path, monkeypatch)["name"]

    items = api.library()["items"]
    assert len(items) == 1 and items[0]["title"] == "Song" and items[0]["cover"] is True

    track = api.track(name)
    assert track["meta"]["album"] == "Album" and "has_cover" not in track["meta"]

    meta = dict(track["meta"], title="새제목", artist="새가수")
    out = api.update({"name": name, "meta": meta, "lyrics": "", "rename": True})
    assert out["name"] == "새가수_-_새제목.m4a"
    assert core.read_tags(api.out_dir / out["name"])["lyrics"] == ""

    assert api.art(out["name"]) == JPEG
    assert api.remove({"name": out["name"]}) == {"ok": True}
    assert api.library()["items"] == []


def test_update_keeps_cover_when_not_touched(api, tmp_path, monkeypatch):
    name = _saved(api, tmp_path, monkeypatch)["name"]
    api.update({"name": name, "meta": api.track(name)["meta"], "lyrics": "x"})
    assert core.read_tags(api.out_dir / name)["has_cover"] is True


def test_library_caches_tag_reads(api, tmp_path, monkeypatch):
    """보관함을 열 때마다 모든 파일을 다시 파싱하면 곡이 늘수록 느려진다."""
    _saved(api, tmp_path, monkeypatch)
    api.library()  # 캐시 채우기
    calls = []
    real = core.read_tags
    monkeypatch.setattr(core, "read_tags", lambda p: (calls.append(p), real(p))[1])
    api.library()
    api.library()
    assert len(calls) == 0, "캐시가 먹지 않음"

    saved = next(api.out_dir.glob("*.m4a"))
    api.update({"name": saved.name, "meta": {"title": "바뀜", "artist": "A"}})
    api.library()
    assert len(calls) == 1, "파일이 바뀌었는데 캐시를 그대로 씀"


def test_library_item_has_version_for_cache_busting(api, tmp_path, monkeypatch):
    _saved(api, tmp_path, monkeypatch)
    assert api.library()["items"][0]["v"] > 0


def test_missing_file_errors(api):
    assert "error" in api.track("nope.m4a")
    assert "error" in api.update({"name": "nope.m4a", "meta": {}})
    assert "error" in api.remove({"name": "nope.m4a"})
    assert api.art("nope.m4a") is None


def test_path_traversal_is_blocked(api, tmp_path):
    (tmp_path / "secret.m4a").write_bytes(silent_m4a_bytes())
    assert "error" in api.track("../secret.m4a")


# ------------------------------------------------------------ 실행 옵션
@pytest.mark.parametrize(("args", "want"), [
    ([], (8080, "127.0.0.1")),
    (["--port", "9000"], (9000, "127.0.0.1")),
    (["--port", "abc"], (8080, "127.0.0.1")),
    (["--lan"], (8080, "0.0.0.0")),
    (["--host", "192.168.0.5"], (8080, "192.168.0.5")),
    (["--lan", "--port", "8081"], (8081, "0.0.0.0")),
    (["--host"], (8080, "127.0.0.1")),
])
def test_parse_args(args, want):
    assert app.parse_args(args) == want


def test_default_bind_is_loopback_only():
    """옵션을 주지 않으면 이 기기 밖에서는 접속되지 않아야 한다."""
    assert app.parse_args([])[1] == "127.0.0.1"


def test_lan_ip_returns_string():
    assert isinstance(app.lan_ip(), str)


# ------------------------------------------------------------ 아이콘 / HTTP
def test_app_icon_is_png():
    data = app.app_icon(32)
    assert core.image_kind(data) == "png" and len(data) > 60


@pytest.fixture()
def server(tmp_path, monkeypatch):
    from http.server import ThreadingHTTPServer

    class H(app.Handler):
        pass

    H.api, H.key = app.Api(docs=tmp_path, out_dir=tmp_path / "music"), "testkey"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", H.api
    httpd.shutdown()
    httpd.server_close()


def fetch(url):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.status, resp.read(), resp.headers.get("Content-Type", "")


def test_http_page_requires_key(server):
    base, _ = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        fetch(base + "/")
    assert exc.value.code == 403


def test_http_api_requires_key(server):
    base, _ = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        fetch(base + "/api/library?k=wrong")
    assert exc.value.code == 403


def test_http_serves_page_and_icon(server):
    base, _ = server
    status, body, ctype = fetch(base + "/?k=testkey")
    assert status == 200 and b"musictag" in body and "text/html" in ctype
    status, body, ctype = fetch(base + "/icon.png")
    assert status == 200 and core.image_kind(body) == "png"


def test_http_library_and_post(server, tmp_path, monkeypatch):
    base, _ = server
    status, body, _ = fetch(base + "/api/library?k=testkey")
    assert status == 200 and json.loads(body) == {"items": []}
    req = urllib.request.Request(base + "/api/start?k=testkey",
                                 data=json.dumps({"url": ""}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert "error" in json.loads(resp.read())


def test_http_unknown_route(server):
    base, _ = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        fetch(base + "/api/nope?k=testkey")
    assert exc.value.code == 404


# ------------------------------------------------------------ a-Shell 제약
def test_app_source_has_no_subprocess_or_shell_calls():
    source = Path(app.__file__).read_text(encoding="utf-8")
    banned = ("subprocess", "os.system", "os.popen", "os.spawn", "pty.spawn")
    for name in used_names(source):
        assert not name.startswith(banned), f"{name} 사용 금지"
    allowed = {"base64", "json", "re", "secrets", "socket", "struct", "sys", "threading",
               "zlib", "urllib", "http", "pathlib", "__future__", "musictag", "mutagen"}
    extra = imported_modules(source) - allowed
    assert not extra, f"허용되지 않은 import: {extra}"


def test_page_has_no_external_resources():
    """오프라인에서도 열려야 하므로 CDN/외부 폰트를 쓰지 않는다."""
    page = app.PAGE
    for bad in ("cdn.", "googleapis", "unpkg", "jsdelivr", "<script src", "@import"):
        assert bad not in page, f"외부 리소스 금지: {bad}"
