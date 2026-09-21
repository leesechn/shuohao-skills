"""musictag.py 테스트. 실제 유튜브 다운로드와 iTunes 호출은 전부 mock."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from mutagen.mp4 import MP4

import musictag as m
from conftest import imported_modules, used_names

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


@pytest.mark.parametrize(("raw", "want"), [
    # 단축어에서 한 겹 인코딩된 채 도착
    ("https%3A%2F%2Fyoutu.be%2FGM2I0OzVS3o%3Fsi%3DCXHgR6ombGTZN4qV",
     "https://youtu.be/GM2I0OzVS3o"),
    # 두 겹 인코딩된 채 도착
    ("https%253A%252F%252Fyoutu.be%252FGM2I0OzVS3o", "https://youtu.be/GM2I0OzVS3o"),
    # 네 겹까지도 되돌린다 (단축어 인코딩 횟수를 헷갈려도 동작하도록)
    ("https%2525253A%2525252F%2525252Fyoutu.be%2525252FGM2I0OzVS3o",
     "https://youtu.be/GM2I0OzVS3o"),
    # 인코딩 안 된 보통 링크는 그대로
    ("https://youtu.be/GM2I0OzVS3o", "https://youtu.be/GM2I0OzVS3o"),
])
def test_clean_url_decodes_shortcut_encoding(raw, want):
    assert m.clean_url(raw) == want


@pytest.mark.parametrize(("raw", "want"), [
    # 단축어가 '//' 때문에 잘리지 않게 https:// 를 떼고 넘긴 경우
    ("youtu.be/GM2I0OzVS3o?si=UrXVbFqLb932C3f5", "https://youtu.be/GM2I0OzVS3o"),
    ("www.youtube.com/watch?v=GM2I0OzVS3o&t=5", "https://www.youtube.com/watch?v=GM2I0OzVS3o&t=5"),
    ("//youtu.be/GM2I0OzVS3o", "https://youtu.be/GM2I0OzVS3o"),
])
def test_clean_url_adds_missing_scheme(raw, want):
    assert m.clean_url(raw) == want


def test_scheme_less_link_passes_check(capsys):
    assert m.check_link(m.clean_url("youtu.be/GM2I0OzVS3o")) is None


def test_clean_url_leaves_unrelated_percent_alone():
    """'://'가 인코딩돼 있지 않으면 %는 건드리지 않는다."""
    url = "https://www.youtube.com/watch?v=AAAAAAAAAAA&q=a%2Bb"
    assert m.clean_url(url) == url


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


# ------------------------------------------------------------ mp3 (ID3)
def test_mp3_write_then_read(silent_mp3):
    m.write_tags(silent_mp3, FULL, b"\xff\xd8\xff" + b"\x00" * 32, "jpeg", "1\ub9c8\ub514\n2\ub9c8\ub514")
    got = m.read_tags(silent_mp3)
    for key, want in FULL.items():
        assert got[key] == want, key
    assert got["lyrics"] == "1\ub9c8\ub514\n2\ub9c8\ub514" and got["has_cover"] is True


def test_mp3_is_detected_by_extension(silent_mp3, silent_m4a):
    assert m.is_mp3(silent_mp3) is True
    assert m.is_mp3(silent_m4a) is False


@pytest.mark.parametrize("fixture", ["silent_m4a", "silent_mp3"])
def test_cover_none_keeps_and_empty_deletes(fixture, request):
    path = request.getfixturevalue(fixture)
    m.write_tags(path, FULL, b"\xff\xd8\xff" + b"\x00" * 32, "jpeg", "\uac00\uc0ac")
    m.write_tags(path, FULL, None, "", None)          # 그대로
    assert m.read_tags(path)["has_cover"] is True
    m.write_tags(path, FULL, b"", "", None)           # 삭제
    got = m.read_tags(path)
    assert got["has_cover"] is False and got["lyrics"] == "\uac00\uc0ac"


def test_newest_audio_picks_latest(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(m, "DOCS", tmp_path)
    (tmp_path / "old.m4a").write_bytes(b"x")
    (tmp_path / "new.mp3").write_bytes(b"y")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    os.utime(tmp_path / "old.m4a", (1, 1))
    assert m.newest_audio().name == "new.mp3"


def test_newest_audio_none_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "DOCS", tmp_path)
    assert m.newest_audio() is None


def test_target_without_name_uses_newest(tmp_path, monkeypatch, silent_m4a):
    monkeypatch.setattr(m, "DOCS", tmp_path)
    dest = tmp_path / "shared.m4a"
    dest.write_bytes(silent_m4a.read_bytes())
    assert m.target(None) == dest


def test_target_errors_without_any_audio(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(m, "DOCS", tmp_path)
    with pytest.raises(SystemExit):
        m.target(None)
    assert "\ucc3e\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4" in capsys.readouterr().out


# ------------------------------------------------------------ 수기 편집 (tags.txt)
def _setup_tagfile(tmp_path, monkeypatch, silent_m4a):
    monkeypatch.setattr(m, "DOCS", tmp_path)
    monkeypatch.setattr(m, "OUT_DIR", tmp_path / "music")
    monkeypatch.setattr(m, "TAGFILE", tmp_path / "tags.txt")
    song = tmp_path / "\uc5b4\ub5a4\ub178\ub798.m4a"
    song.write_bytes(silent_m4a.read_bytes())
    m.write_tags(song, dict.fromkeys([k for k, _ in m.FIELDS], ""), None, "", "\uae30\uc874 \uac00\uc0ac")
    return song


def test_tags_export_then_apply_roundtrip(tmp_path, monkeypatch, silent_m4a):
    song = _setup_tagfile(tmp_path, monkeypatch, silent_m4a)
    m.cmd_tags(song.name)

    text = m.TAGFILE.read_text(encoding="utf-8")
    assert f"\ud30c\uc77c: {song.name}" in text and "\uac00\uc0ac:" in text
    text = (text.replace("\uc81c\ubaa9: ", "\uc81c\ubaa9: \ub0b4\uac00 \uc4f4 \uc81c\ubaa9")
                .replace("\uc544\ud2f0\uc2a4\ud2b8: ", "\uc544\ud2f0\uc2a4\ud2b8: \ub0b4\uac00 \uc4f4 \uac00\uc218")
                .replace("\ud2b8\ub799 \ubc88\ud638: ", "\ud2b8\ub799 \ubc88\ud638: 3")
                .replace("  \uae30\uc874 \uac00\uc0ac", "  \uccab \uc904\n  \ub458\uc9f8 \uc904"))
    m.TAGFILE.write_text(text, encoding="utf-8")

    m.cmd_apply()
    saved = next((tmp_path / "music").glob("*.m4a"))
    assert saved.name == "\ub0b4\uac00_\uc4f4_\uac00\uc218_-_\ub0b4\uac00_\uc4f4_\uc81c\ubaa9.m4a"
    got = m.read_tags(saved)
    assert got["title"] == "\ub0b4\uac00 \uc4f4 \uc81c\ubaa9" and got["artist"] == "\ub0b4\uac00 \uc4f4 \uac00\uc218"
    assert got["track"] == "3"
    assert got["lyrics"] == "\uccab \uc904\n\ub458\uc9f8 \uc904"


def test_apply_without_tagfile_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(m, "TAGFILE", tmp_path / "tags.txt")
    with pytest.raises(SystemExit):
        m.cmd_apply()
    assert "tags.txt" in capsys.readouterr().out


def test_parse_tagfile_ignores_comments_and_blank_lines():
    meta, lyrics, opts = m.parse_tagfile(
        "\ud30c\uc77c: a.m4a\n# \uc124\uba85\n\n\uc81c\ubaa9: \uacf2\n\ucee4\ubc84: \uc0ad\uc81c   # \uc8fc\uc11d\n\uac00\uc0ac:\n  \ud55c \uc904\n")
    assert meta["title"] == "\uacf2" and opts["\ucee4\ubc84"] == "\uc0ad\uc81c"
    assert opts["\ud30c\uc77c"] == "a.m4a" and lyrics == "\ud55c \uc904"


@pytest.mark.parametrize(("choice", "want"), [
    ("\uadf8\ub300\ub85c", None), ("\uc0ad\uc81c", b""),
])
def test_cover_choice_keep_and_delete(choice, want):
    assert m.cover_from_choice(choice, {})[0] == want


def test_cover_choice_album_art(monkeypatch):
    monkeypatch.setattr(m, "itunes_search", lambda *a, **k: ([SAMPLE], "JP"))
    monkeypatch.setattr(m, "get_cover", lambda *a, **k: (b"\xff\xd8\xffIMG", "jpeg"))
    assert m.cover_from_choice("\uc568\ubc94\uc544\ud2b8", {"artist": "A", "title": "S"})[0] == b"\xff\xd8\xffIMG"


def test_cover_choice_album_art_not_found(monkeypatch, capsys):
    monkeypatch.setattr(m, "itunes_search", lambda *a, **k: ([], ""))
    assert m.cover_from_choice("\uc568\ubc94\uc544\ud2b8", {"artist": "A", "title": "S"}) == (None, "")
    assert "\ucc3e\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4" in capsys.readouterr().out


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


def test_get_cover_local_false_skips_local_files(tmp_path, monkeypatch):
    (tmp_path / "cover.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 8)
    monkeypatch.setattr(m, "http_get", lambda url: b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    data, kind = m.get_cover({"artwork": "https://x/y/100x100bb.jpg"}, "",
                             docs=tmp_path, local=False)
    assert kind == "png"


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


@pytest.mark.parametrize(("text", "want"), [
    ("https://youtu.be/AAA", True),
    ("http://x/y", True),
    ("“youtu.be/AAA”", True),
    ("https://www.youtube.com/watch?v=AAA", True),
    ("show", False),
    ("edit", False),
    ("song.m4a", False),
    ("", False),
])
def test_is_link(text, want):
    assert m.is_link(text) is want


@pytest.mark.parametrize(("url", "want"), [
    ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=5", "dQw4w9WgXcQ"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/xxxxxxxx", "xxxxxxxx"),
    ("https://example.com/a.mp3", ""),
])
def test_video_id(url, want):
    assert m.video_id(url) == want


@pytest.mark.parametrize("url", [
    "https://youtu.be/xxxxxxxx",                     # 설명서 예시를 그대로 넣은 경우
    "https://www.youtube.com/watch?v=xxxxxxxxxxx",   # 11글자지만 한 글자 반복
    "https://youtu.be/abc",
])
def test_check_link_rejects_fake_ids(url, capsys):
    with pytest.raises(SystemExit):
        m.check_link(url)
    out = capsys.readouterr().out
    assert "실제 영상 주소가 아닙니다" in out and "11글자" in out


@pytest.mark.parametrize("url", [
    "https://youtu.be/dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://example.com/song.mp3",   # 유튜브가 아니면 통과시킨다
])
def test_check_link_allows_real_links(url):
    assert m.check_link(url) is None


def test_read_link_from_text_file(tmp_path):
    f = tmp_path / "link.txt"
    f.write_text("\n\n  https://youtu.be/dQw4w9WgXcQ  \n", encoding="utf-8")
    assert m.read_link(str(f)) == "https://youtu.be/dQw4w9WgXcQ"
    assert m.is_link(str(f)) is True


def test_link_txt_is_used_without_any_argument(tmp_path, monkeypatch, silent_m4a):
    """단축어가 link.txt만 남겨도, 인자 없이 실행해 질문 없이 저장돼야 한다."""
    monkeypatch.setattr(m, "DOCS", tmp_path)
    monkeypatch.setattr(m, "OUT_DIR", tmp_path / "music")
    monkeypatch.setattr(m, "TMP_DIR", tmp_path / "tmp")
    monkeypatch.setattr(m, "ask", lambda *a, **k: pytest.fail("질문이 나왔다"))
    monkeypatch.setattr(m, "itunes_search", lambda *a, **k: ([SAMPLE], "JP"))
    monkeypatch.setattr(m, "get_cover", lambda *a, **k: (None, ""))
    (tmp_path / "link.txt").write_text(
        "https://youtu.be/dQw4w9WgXcQ?si=abc\n", encoding="utf-8")

    def fake_download(url, hooks=None):
        assert url == "https://youtu.be/dQw4w9WgXcQ"
        dest = tmp_path / "tmpaudio.m4a"
        dest.write_bytes(silent_m4a.read_bytes())
        return dest, {"title": "Artist - Song", "uploader": "Chan", "id": "dQw4w9WgXcQ"}

    monkeypatch.setattr(m, "download", fake_download)
    assert m.main([]) == 0
    assert (tmp_path / "music" / "Artist_-_Song.m4a").exists()


def test_link_txt_path_as_argument(tmp_path, monkeypatch):
    f = tmp_path / "link.txt"
    f.write_text("https://youtu.be/dQw4w9WgXcQ\n", encoding="utf-8")
    assert m.read_link(str(f)) == "https://youtu.be/dQw4w9WgXcQ"


def test_read_link_without_argument_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "DOCS", tmp_path)
    assert m.read_link("") == ""
    (tmp_path / "link.txt").write_text("\n  https://youtu.be/dQw4w9WgXcQ  \n", encoding="utf-8")
    assert m.read_link("") == "https://youtu.be/dQw4w9WgXcQ"


def test_link_txt_with_saved_html_still_finds_the_link(tmp_path, monkeypatch):
    """단축어의 '파일 저장'이 웹페이지를 통째로 저장해도 링크를 건져야 한다."""
    monkeypatch.setattr(m, "DOCS", tmp_path)
    (tmp_path / "link.txt").write_text(
        '<!DOCTYPE html><html><head>[not a url]</head>'
        '<script>var u="https://www.youtube.com/watch?v=GM2I0OzVS3o&pp=x";</script></html>',
        encoding="utf-8")
    assert m.read_link("") == "https://www.youtube.com/watch?v=GM2I0OzVS3o"


def test_clean_url_survives_garbage(capsys):
    """알아볼 수 없는 입력에 죽지 않고 원인을 말해야 한다."""
    assert m.clean_url("<!DOCTYPE html>[broken") == ""
    assert "\ub9c1\ud06c\ub97c \uc54c\uc544\ubcfc \uc218 \uc5c6\uc2b5\ub2c8\ub2e4" in capsys.readouterr().out


def test_read_link_passes_through_plain_url():
    assert m.read_link("https://youtu.be/AAA") == "https://youtu.be/AAA"


def test_fake_link_is_rejected_before_download(tmp_path, monkeypatch, capsys):
    """예시 주소를 넣으면 다운로드를 시도조차 하지 않아야 한다."""
    monkeypatch.setattr(m, "download", lambda *a, **k: pytest.fail("다운로드를 시도했다"))
    monkeypatch.setattr(m, "OUT_DIR", tmp_path / "music")
    assert m.main(["https://youtu.be/xxxxxxxx"]) == 1
    assert "11글자" in capsys.readouterr().out


@pytest.mark.parametrize(("message", "expect"), [
    ("ERROR: Unsupported URL: https://x", "이 주소로는 받을 수 없습니다."),
    ("Sign in to confirm your age", "비공개"),
    ("HTTP Error 500", "다운로드에 실패했습니다."),
])
def test_download_errors_are_explained(monkeypatch, tmp_path, capsys, message, expect):
    monkeypatch.setattr(m, "TMP_DIR", tmp_path / "tmp")

    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True):
            raise RuntimeError(message)

    import sys as _sys
    import types
    fake = types.ModuleType("yt_dlp")
    fake.YoutubeDL = FakeYDL
    monkeypatch.setitem(_sys.modules, "yt_dlp", fake)
    with pytest.raises(SystemExit):
        m.download("https://youtu.be/dQw4w9WgXcQ")
    assert expect in capsys.readouterr().out


def test_auto_meta_takes_first_result(monkeypatch):
    monkeypatch.setattr(m, "itunes_search", lambda *a, **k: ([SAMPLE], "JP"))
    monkeypatch.setattr(m, "ask", lambda *a, **k: pytest.fail("물어보면 안 된다"))
    assert m.auto_meta("q", "T", "A")["title"] == "Song"


def test_auto_meta_falls_back_without_results(monkeypatch):
    monkeypatch.setattr(m, "itunes_search", lambda *a, **k: ([], ""))
    assert m.auto_meta("q", "영상제목", "채널")["title"] == "영상제목"


def test_link_argument_saves_without_any_prompt(tmp_path, monkeypatch, silent_m4a):
    """링크만 붙이면 질문 없이 파일이 나와야 한다."""
    monkeypatch.setattr(m, "OUT_DIR", tmp_path / "music")
    monkeypatch.setattr(m, "TMP_DIR", tmp_path / "tmp")
    monkeypatch.setattr(m, "DOCS", tmp_path)
    monkeypatch.setattr(m, "ask", lambda *a, **k: pytest.fail("질문이 나왔다"))
    monkeypatch.setattr(m, "itunes_search", lambda *a, **k: ([SAMPLE], "JP"))
    monkeypatch.setattr(m, "get_cover", lambda *a, **k: (None, ""))

    def fake_download(url, hooks=None):
        assert url == "https://youtu.be/dQw4w9WgXcQ"
        dest = tmp_path / "tmpaudio.m4a"
        dest.write_bytes(silent_m4a.read_bytes())
        return dest, {"title": "[MV] Artist - Song", "uploader": "Chan", "id": "dQw4w9WgXcQ"}

    monkeypatch.setattr(m, "download", fake_download)
    assert m.main(["https://youtu.be/dQw4w9WgXcQ?si=x"]) == 0
    saved = tmp_path / "music" / "Artist_-_Song.m4a"
    assert saved.exists() and m.read_tags(saved)["album"] == "Album"


def test_progress_hook_prints_percent(capsys):
    m.progress({"status": "downloading", "downloaded_bytes": 25, "total_bytes": 100})
    assert "25%" in capsys.readouterr().out
    m.progress({"status": "finished"})


def test_unexpected_error_shows_type_and_message(monkeypatch, capsys):
    """메시지만 보고도 원인을 좁힐 수 있어야 한다."""
    def boom(*a, **k):
        raise ValueError("뭔가 터짐")

    monkeypatch.setattr(m, "cmd_download", boom)
    assert m.main([]) == 1
    out = capsys.readouterr().out
    assert "[ValueError]" in out and "뭔가 터짐" in out


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
    banned = ("subprocess", "os.system", "os.popen", "os.spawn", "os.exec", "pty.spawn")
    used = used_names(source)
    for name in used:
        assert not name.startswith(banned), f"{name} 사용 금지"
    allowed = {"json", "re", "sys", "unicodedata", "urllib", "pathlib",
               "__future__", "traceback", "mutagen", "yt_dlp"}
    extra = imported_modules(source) - allowed
    assert not extra, f"허용되지 않은 import: {extra}"
