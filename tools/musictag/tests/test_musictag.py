"""musictag.py 테스트. 실제 유튜브 다운로드와 iTunes 호출은 전부 mock."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from mutagen.mp4 import MP4

import musictag as m

SRC = Path(m.__file__)


# ------------------------------------------------------------ 링크 / 문자열 정리
@pytest.mark.parametrize(("raw", "want"), [
    ("  https://youtu.be/AAA  ", "https://youtu.be/AAA"),
    ("“https://youtu.be/AAA?si=xyz”", "https://youtu.be/AAA"),
    ("'https://youtu.be/AAA'", "https://youtu.be/AAA"),
    ("https://www.youtube.com/watch?v=AAA&si=x&feature=share",
     "https://www.youtube.com/watch?v=AAA"),
    ("https://www.youtube.com/watch?v=AAA&t=30", "https://www.youtube.com/watch?v=AAA&t=30"),
    ("https://youtu.be/AAA#fragment", "https://youtu.be/AAA"),
    ("   ", ""),
])
def test_clean_url(raw, want):
    assert m.clean_url(raw) == want


def test_clean_lyrics_strips_zero_width_and_trailing_space():
    raw = "1，​\r\n두   \r\n﻿셋   \n\n"
    assert m.clean_lyrics(raw) == "1，\n두\n셋"


def test_clean_lyrics_empty():
    assert m.clean_lyrics("") == ""


@pytest.mark.parametrize(("artist", "title", "want"), [
    ("Artist", "Song", "Artist_-_Song"),
    ('A/B\\C:D*E?F"G<H>I|J', "T", "A_B_C_D_E_F_G_H_I_J_-_T"),
    ("  Artist  ", "  Song   Name ", "Artist_-_Song_Name"),
    ("", "", "untitled"),
])
def test_safe_filename(artist, title, want):
    assert m.safe_filename(artist, title) == want


def test_safe_filename_length_limit():
    name = m.safe_filename("A" * 60, "B" * 60)
    assert len(name) <= 80


def test_unique_path_suffixes(tmp_path):
    assert m.unique_path(tmp_path, "song").name == "song.m4a"
    (tmp_path / "song.m4a").touch()
    assert m.unique_path(tmp_path, "song").name == "song_2.m4a"
    (tmp_path / "song_2.m4a").touch()
    assert m.unique_path(tmp_path, "song").name == "song_3.m4a"


@pytest.mark.parametrize(("title", "want"), [
    ("[MV] Artist - Song (Official Music Video)", "Artist Song"),
    ("「제목」 Artist 【공식】", "제목 Artist"),
    ("Artist - Song MV", "Artist Song"),
    ("(Official)", "(Official)"),
])
def test_build_query(title, want):
    assert m.build_query(title) == want


@pytest.mark.parametrize(("data", "want"), [
    (b"\xff\xd8\xff\xe0rest", "jpeg"),
    (b"\x89PNG\r\n\x1a\nrest", "png"),
    (b"RIFF1234WEBPVP8 ", "webp"),
    (b"GIF89a", ""),
])
def test_image_kind(data, want):
    assert m.image_kind(data) == want


# ------------------------------------------------------------ 태그 쓰기 / 읽기
FULL = {"title": "곲", "artist": "가수", "album_artist": "가수",
        "album": "앨범", "date": "2021-03-04", "genre": "J-Pop",
        "track": "7", "track_total": "12", "composer": "작곡", "comment": "메모"}


def test_write_then_read_tags(silent_m4a):
    m.write_tags(silent_m4a, FULL, b"\xff\xd8\xff" + b"\x00" * 32, "jpeg", "1마디\n2마디")
    got = m.read_tags(silent_m4a)
    for key, want in FULL.items():
        assert got[key] == want
    assert got["lyrics"] == "1마디\n2마디"
    assert got["has_cover"] is True


def test_write_tags_uses_expected_mp4_keys(silent_m4a):
    m.write_tags(silent_m4a, FULL, None, "", "가사")
    tags = MP4(str(silent_m4a)).tags
    assert tags["\xa9nam"] == ["곲"] and tags["\xa9ART"] == ["가수"]
    assert tags["aART"] == ["가수"] and tags["\xa9alb"] == ["앨범"]
    assert tags["\xa9day"] == ["2021-03-04"] and tags["\xa9gen"] == ["J-Pop"]
    assert tags["\xa9wrt"] == ["작곡"] and tags["\xa9cmt"] == ["메모"]
    assert tags["\xa9lyr"] == ["가사"] and tags["trkn"] == [(7, 12)]


def test_cover_format_png_vs_jpeg(silent_m4a):
    from mutagen.mp4 import MP4Cover
    m.write_tags(silent_m4a, FULL, b"\x89PNG\r\n\x1a\n" + b"\x00" * 16, "png")
    assert MP4(str(silent_m4a)).tags["covr"][0].imageformat == MP4Cover.FORMAT_PNG
    m.write_tags(silent_m4a, FULL, b"\xff\xd8\xff" + b"\x00" * 16, "jpeg")
    assert MP4(str(silent_m4a)).tags["covr"][0].imageformat == MP4Cover.FORMAT_JPEG


def test_empty_values_remove_tags(silent_m4a):
    m.write_tags(silent_m4a, FULL, None, "", "가사")
    blank = dict.fromkeys(FULL, "")
    m.write_tags(silent_m4a, blank, None, "", "")
    tags = MP4(str(silent_m4a)).tags
    assert "\xa9nam" not in tags and "trkn" not in tags and "\xa9lyr" not in tags


def test_lyrics_none_keeps_existing(silent_m4a):
    m.write_tags(silent_m4a, FULL, None, "", "유지될가사")
    m.write_tags(silent_m4a, FULL, None, "", None)
    assert m.read_tags(silent_m4a)["lyrics"] == "유지될가사"


def test_non_numeric_track_is_dropped(silent_m4a):
    meta = dict(FULL, track="일곱", track_total="")
    m.write_tags(silent_m4a, meta, None, "", "")
    assert "trkn" not in MP4(str(silent_m4a)).tags


# ------------------------------------------------------------ 커버 / 가사 파일
def test_get_cover_prefers_local_file(tmp_path, monkeypatch):
    (tmp_path / "cover.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 8)
    monkeypatch.setattr(m, "http_get", lambda url: pytest.fail("network used"))
    data, kind = m.get_cover({"artwork": "https://x/100x100bb.jpg"}, "VID", docs=tmp_path)
    assert kind == "jpeg" and data.startswith(b"\xff\xd8\xff")


def test_get_cover_skips_webp_then_uses_itunes_600(tmp_path, monkeypatch):
    (tmp_path / "cover.jpg").write_bytes(b"RIFF1234WEBPVP8 ")
    seen = []

    def fake_get(url):
        seen.append(url)
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 8

    monkeypatch.setattr(m, "http_get", fake_get)
    data, kind = m.get_cover({"artwork": "https://x/y/100x100bb.jpg"}, "VID", docs=tmp_path)
    assert seen == ["https://x/y/600x600bb.jpg"] and kind == "png"


def test_get_cover_falls_back_to_youtube_thumbnails(tmp_path, monkeypatch):
    seen = []

    def fake_get(url):
        seen.append(url)
        if "maxresdefault" in url:
            raise OSError("404")
        return b"\xff\xd8\xff" + b"\x00" * 8

    monkeypatch.setattr(m, "http_get", fake_get)
    data, kind = m.get_cover({}, "VID", docs=tmp_path)
    assert seen == ["https://i.ytimg.com/vi/VID/maxresdefault.jpg",
                    "https://i.ytimg.com/vi/VID/hqdefault.jpg"]
    assert kind == "jpeg"


def test_get_cover_returns_none_when_nothing_found(tmp_path):
    assert m.get_cover({}, "", docs=tmp_path) == (None, "")


def test_take_lyrics_reads_cleans_and_renames(tmp_path):
    (tmp_path / "lyrics.txt").write_text("한줄 ​ \n둘째줄  \n", encoding="utf-8")
    assert m.take_lyrics(docs=tmp_path) == "한줄\n둘째줄"
    assert not (tmp_path / "lyrics.txt").exists()
    assert (tmp_path / "lyrics_used.txt").exists()


def test_take_lyrics_missing_file(tmp_path):
    assert m.take_lyrics(docs=tmp_path) == ""


def test_take_lyrics_second_run_does_not_overwrite(tmp_path):
    for _ in range(2):
        (tmp_path / "lyrics.txt").write_text("x", encoding="utf-8")
        m.take_lyrics(docs=tmp_path)
    assert (tmp_path / "lyrics_used_2.txt").exists()


# ------------------------------------------------------------ iTunes (mock)
SAMPLE = {"trackName": "Song", "artistName": "Artist", "collectionName": "Album",
          "releaseDate": "2021-03-04T12:00:00Z", "primaryGenreName": "J-Pop",
          "trackNumber": 7, "trackCount": 12, "artworkUrl100": "https://x/100x100bb.jpg"}


def test_itunes_search_tries_countries_in_order(monkeypatch):
    calls = []

    def fake_get(url):
        calls.append(url)
        hit = "country=US" in url
        return json.dumps({"results": [SAMPLE] if hit else []}).encode()

    monkeypatch.setattr(m, "http_get", fake_get)
    results, country = m.itunes_search("q")
    assert country == "US" and results == [SAMPLE]
    assert ["JP", "KR", "US"] == [u.split("country=")[1] for u in calls]


def test_meta_from_result_maps_fields():
    meta = m.meta_from_result(SAMPLE)
    assert meta["date"] == "2021-03-04" and meta["track"] == "7"
    assert meta["track_total"] == "12" and meta["genre"] == "J-Pop"


def test_choose_meta_picks_candidate(monkeypatch):
    monkeypatch.setattr(m, "itunes_search", lambda *a, **k: ([SAMPLE], "JP"))
    monkeypatch.setattr(m, "ask", lambda *a, **k: "1")
    assert m.choose_meta("q", "t", "a")["title"] == "Song"


def test_choose_meta_zero_switches_to_manual(monkeypatch):
    monkeypatch.setattr(m, "itunes_search", lambda *a, **k: ([SAMPLE], "JP"))
    monkeypatch.setattr(m, "ask", lambda *a, **k: "0")
    meta = m.choose_meta("q", "영상제목", "채널")
    assert meta["title"] == "영상제목" and meta["artist"] == "채널"


def test_choose_meta_no_result_falls_back(monkeypatch):
    monkeypatch.setattr(m, "itunes_search", lambda *a, **k: ([], ""))
    assert m.choose_meta("q", "T", "A")["title"] == "T"


def test_main_rejects_unknown_command(capsys):
    assert m.main(["bogus"]) == 1
    assert "알 수 없는 명령" in capsys.readouterr().out


def test_main_show_requires_filename(capsys):
    assert m.main(["show"]) == 1
    assert "파일명" in capsys.readouterr().out


# ------------------------------------------------------------ a-Shell 제약 검사
def test_source_has_no_subprocess_or_shell_calls():
    """a-Shell에서 불안정하므로 subprocess/os.system 호출이 없어야 한다."""
    source = SRC.read_text(encoding="utf-8")
    banned = ("subprocess", "os.system", "os.popen", "os.spawn", "os.exec",
              "pty.spawn", "commands.getoutput")
    for word in banned:
        assert word not in source, f"{word} 사용 금지"
    tree = ast.parse(source)
    imported = {n.names[0].name.split(".")[0] for n in ast.walk(tree)
                if isinstance(n, ast.Import)}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree)
                 if isinstance(n, ast.ImportFrom)}
    allowed = {"json", "re", "sys", "unicodedata", "urllib", "pathlib",
               "__future__", "traceback", "mutagen", "yt_dlp"}
    assert imported <= allowed, f"허용되지 않은 import: {imported - allowed}"
