"""테스트 픽스처: ffmpeg 없이 만든 아주 짧은 무음 m4a."""
from __future__ import annotations

import ast
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _atom(name: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + name + payload


def silent_m4a_bytes(timescale: int = 44100, samples: int = 1024) -> bytes:
    """mutagen이 읽을 수 있는 최소 MP4(무음, 샘플 0개) 바이트열."""
    matrix = struct.pack(">9i", 0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000)
    mvhd = _atom(b"mvhd", struct.pack(">IIIII", 0, 0, 0, 1000, samples * 1000 // timescale)
                 + struct.pack(">IHH", 0x00010000, 0x0100, 0) + b"\x00" * 8
                 + matrix + b"\x00" * 24 + struct.pack(">I", 2))
    tkhd = _atom(b"tkhd", struct.pack(">IIIIII", 0x0F, 0, 0, 1, 0, samples * 1000 // timescale)
                 + b"\x00" * 8 + struct.pack(">HHHH", 0, 0, 0x0100, 0)
                 + matrix + struct.pack(">II", 0, 0))
    mdhd = _atom(b"mdhd", struct.pack(">IIIIIHH", 0, 0, 0, timescale, samples, 0x55C4, 0))
    hdlr = _atom(b"hdlr", struct.pack(">I", 0) + b"\x00" * 4 + b"soun" + b"\x00" * 12 + b"\x00")
    smhd = _atom(b"smhd", struct.pack(">IHH", 0, 0, 0))
    dref = _atom(b"dref", struct.pack(">II", 0, 1) + _atom(b"url ", struct.pack(">I", 1)))
    dinf = _atom(b"dinf", dref)
    dsi = b"\x05\x02\x12\x10"                       # AAC-LC 44.1k stereo
    dcd = b"\x04" + bytes([13 + len(dsi)]) + b"\x40\x15" + b"\x00" * 3 \
        + struct.pack(">II", 0, 0) + dsi
    sl = b"\x06\x01\x02"
    esd = b"\x03" + bytes([3 + len(dcd) + len(sl)]) + b"\x00\x00\x00" + dcd + sl
    esds = _atom(b"esds", struct.pack(">I", 0) + esd)
    mp4a = _atom(b"mp4a", b"\x00" * 6 + struct.pack(">H", 1) + b"\x00" * 8
                 + struct.pack(">HHHHI", 2, 16, 0, 0, timescale << 16) + esds)
    stbl = _atom(b"stbl", _atom(b"stsd", struct.pack(">II", 0, 1) + mp4a)
                 + _atom(b"stts", struct.pack(">II", 0, 0))
                 + _atom(b"stsc", struct.pack(">II", 0, 0))
                 + _atom(b"stsz", struct.pack(">III", 0, 0, 0))
                 + _atom(b"stco", struct.pack(">II", 0, 0)))
    minf = _atom(b"minf", smhd + dinf + stbl)
    mdia = _atom(b"mdia", mdhd + hdlr + minf)
    moov = _atom(b"moov", mvhd + _atom(b"trak", tkhd + mdia))
    ftyp = _atom(b"ftyp", b"M4A " + struct.pack(">I", 0) + b"M4A mp42isom")
    return ftyp + moov + _atom(b"mdat", b"")


@pytest.fixture()
def silent_m4a(tmp_path: Path) -> Path:
    path = tmp_path / "silent.m4a"
    path.write_bytes(silent_m4a_bytes())
    return path


def _dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def used_names(source: str) -> set[str]:
    """코드에서 실제로 참조한 이름들(주석·독스트링 제외)."""
    tree = ast.parse(source)
    return {n for n in (_dotted(x) for x in ast.walk(tree)) if n}


def imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    mods = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    mods |= {(n.module or "").split(".")[0] for n in ast.walk(tree)
             if isinstance(n, ast.ImportFrom)}
    return mods


@pytest.fixture()
def silent_mp3(tmp_path: Path) -> Path:
    """태그 시험용 최소 mp3(프레임 헤더 + 무음)."""
    path = tmp_path / "silent.mp3"
    path.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 2048)
    return path
