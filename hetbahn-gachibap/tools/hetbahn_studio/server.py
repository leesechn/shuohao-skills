"""hetbahn_studio: MCP server (stdio) for the 햇반 같이밥 project.

Wraps the Gemini API (image / video) so every generation gets the LOCK sentences verbatim and every call is
written to the proof ledger. Music falls back to the project's deterministic synth (tools/pipeline/audio.py).
Key: environment variable GEMINI_API_KEY only. It is never logged, returned, or written to disk.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

try:  # MCP Python SDK v2
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # v1
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
LOCKS = json.loads((HERE / "locks.json").read_text(encoding="utf-8"))
LEDGER = ROOT / "proof" / "생성원장.jsonl"
API = "https://generativelanguage.googleapis.com/v1beta"
IMAGE_MODEL = os.environ.get("HB_IMAGE_MODEL", "gemini-2.5-flash-image")  # 불확실: 모델 이름은 수시로 바뀜
VIDEO_MODEL = os.environ.get("HB_VIDEO_MODEL", "veo-3.1-generate-preview")  # 불확실

mcp = _Server("hetbahn_studio")


class HBError(ToolError):
    """Error whose message (next action included) is shown to the agent."""


# ------------------------------------------------------------------ helpers
def _key() -> str:
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if not k or k.startswith("${"):
        raise HBError("GEMINI_API_KEY가 없습니다. claude.ai/code 환경 설정 > 환경변수에 새로 발급한 키를 넣고 세션을 다시 여세요. "
                      "키 없이 가능한 도구: hb_contact_sheet, hb_logo_composite, hb_ledger_export, hb_music(로컬 합성).")
    return k


def _scrub(text: str) -> str:
    k = os.environ.get("GEMINI_API_KEY", "")
    return text.replace(k, "***") if k else text


def _post(url: str, body: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": _key()})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        msg = _scrub(e.read().decode(errors="ignore"))[:400]
        if e.code == 429:
            retry = e.headers.get("Retry-After", "60")
            at = datetime.fromtimestamp(time.time() + int(retry)).strftime("%H:%M")
            raise HBError(f"할당량 초과: {at} 이후 재시도. 그동안 다른 컷을 먼저 진행하세요.") from None
        raise HBError(f"Gemini API 오류 {e.code}: {msg}. 모델 이름(HB_IMAGE_MODEL/HB_VIDEO_MODEL)과 키 권한을 확인하세요.") from None


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"x-goog-api-key": _key()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _ledger(entry: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _compose(prompt: str, lock: list[str]) -> str:
    """LOCK sentences are copied verbatim: scene first, then PRODUCT/CAST, then STYLE last."""
    parts = [prompt.strip()]
    for k in lock:
        if k not in LOCKS:
            raise HBError(f"알 수 없는 LOCK '{k}'. 사용 가능: {', '.join(LOCKS)}")
    parts += [LOCKS[k] for k in lock if not k.startswith("STYLE")]
    parts += [LOCKS[k] for k in lock if k.startswith("STYLE")]
    return " ".join(parts)


def _img_part(path: str) -> dict:
    p = (ROOT / path) if not Path(path).is_absolute() else Path(path)
    if not p.exists():
        raise HBError(f"레퍼런스 파일 없음: {path}. refs/ 아래 경로를 쓰세요.")
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return {"inline_data": {"mime_type": mime, "data": base64.b64encode(p.read_bytes()).decode()}}


# ------------------------------------------------------------------ tools
@mcp.tool()
def hb_still(shot_id: str = Field(description="컷 ID, 예: S04a"),
             prompt: str = Field(description="장면 묘사(영문). LOCK 문장은 자동으로 붙는다"),
             lock: list[str] = Field(default=["PRODUCT", "STYLE"], description="PRODUCT, S, N, STYLE, STYLE_MINI"),
             refs: list[str] = Field(default=["refs/02_product_front.jpeg", "refs/04_container_lid_inside.jpeg"],
                                     description="이미지 레퍼런스 경로(레포 기준)"),
             n: int = Field(default=3, ge=1, le=4, description="안 개수"),
             aspect: Literal["1:1", "9:16", "4:5", "16:9"] = "1:1") -> dict:
    """첫 프레임 스틸 생성. LOCK을 그대로 붙여 Gemini 이미지 모델로 n안 생성, work/stills/<shot_id>_tN.png 저장, 원장 기록."""
    full = _compose(prompt, lock)
    out_dir = ROOT / "work" / "stills"
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for i in range(1, n + 1):
        body = {"contents": [{"parts": [{"text": full}] + [_img_part(r) for r in refs]}],
                "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}}
        res = _post(f"{API}/models/{IMAGE_MODEL}:generateContent", body)
        data = None
        for c in res.get("candidates", []):
            for p in c.get("content", {}).get("parts", []):
                d = p.get("inlineData") or p.get("inline_data")
                if d:
                    data = d["data"]
        if not data:
            raise HBError("이미지가 반환되지 않았습니다(안전 필터 또는 모델 변경). 프롬프트에서 인물 묘사를 줄이거나 모델을 바꾸세요.")
        f = out_dir / f"{shot_id}_t{i}.png"
        f.write_bytes(base64.b64decode(data))
        files.append(str(f.relative_to(ROOT)))
    _ledger({"tool": "hb_still", "service": "Google Gemini API", "model": IMAGE_MODEL, "shot": shot_id,
             "prompt": full, "refs": refs, "aspect": aspect, "files": files})
    return {"files": files, "prompt_used": full}


@mcp.tool()
def hb_clip(shot_id: str = Field(description="컷 ID"),
            first_frame: str = Field(description="첫 프레임 이미지 경로"),
            prompt: str = Field(description="카메라 4슬롯 + 행동 1개 + 오디오. 꼬리문은 자동"),
            end_frame: str | None = Field(default=None, description="끝 프레임(선택)"),
            seconds: int = Field(default=5, ge=4, le=8),
            takes: int = Field(default=3, ge=1, le=4)) -> dict:
    """I2V 클립 생성(Veo). 할당량 초과면 재개 시각을 돌려준다. work/clips/<shot_id>_tN.mp4."""
    full = prompt.strip() + " " + LOCKS["I2V_TAIL"]
    out_dir = ROOT / "work" / "clips"
    out_dir.mkdir(parents=True, exist_ok=True)
    img = _img_part(first_frame)["inline_data"]
    files = []
    for i in range(1, takes + 1):
        inst = {"prompt": full, "image": {"bytesBase64Encoded": img["data"], "mimeType": img["mime_type"]}}
        if end_frame:
            e = _img_part(end_frame)["inline_data"]
            inst["lastFrame"] = {"bytesBase64Encoded": e["data"], "mimeType": e["mime_type"]}
        op = _post(f"{API}/models/{VIDEO_MODEL}:predictLongRunning",
                   {"instances": [inst], "parameters": {"aspectRatio": "9:16", "durationSeconds": seconds}})
        name = op.get("name")
        for _ in range(90):
            st = json.loads(_get(f"{API}/{name}"))
            if st.get("done"):
                break
            time.sleep(10)
        else:
            raise HBError(f"영상 생성 대기 시간 초과(작업 {name}). 잠시 후 같은 작업 이름으로 다시 확인하세요.")
        if "error" in st:
            raise HBError(f"영상 생성 실패: {_scrub(json.dumps(st['error'], ensure_ascii=False))[:300]}")
        uri = st["response"]["generateVideoResponse"]["generatedSamples"][0]["video"]["uri"]
        f = out_dir / f"{shot_id}_t{i}.mp4"
        f.write_bytes(_get(uri, timeout=300))
        files.append(str(f.relative_to(ROOT)))
        _ledger({"tool": "hb_clip", "service": "Google Gemini API", "model": VIDEO_MODEL, "shot": shot_id,
                 "prompt": full, "first_frame": first_frame, "end_frame": end_frame, "job": name, "files": [files[-1]]})
    return {"files": files}


@mcp.tool()
def hb_music(brief: str = Field(default="nylon guitar pluck, marimba, light handclaps, lift on the ding"),
             seconds: float = Field(default=33.0), bpm: int = Field(default=90)) -> dict:
    """배경음악 + 효과음 믹스(-14 LUFS). 현재 로컬 합성기(tools/pipeline/audio.py, 90 BPM 백타이밍)로 생성. 키 불필요."""
    if abs(seconds - 33.0) > 0.01 or bpm != 90:
        raise HBError("로컬 합성기는 본편 타임라인(33.0초, 90 BPM)에 고정돼 있습니다. tools/pipeline/film.py의 CUTS를 바꾼 뒤 audio.py를 수정하세요.")
    sys.path.insert(0, str(ROOT / "tools" / "pipeline"))
    from audio import build
    out, lufs = build(ROOT / "work" / "audio" / "mix.wav")
    _ledger({"tool": "hb_music", "service": "local synth (numpy)", "model": "Karplus-Strong + additive", "brief": brief,
             "files": [str(Path(out).relative_to(ROOT))], "lufs": round(lufs, 2)})
    return {"file": str(Path(out).relative_to(ROOT)), "lufs": round(lufs, 2)}


@mcp.tool()
def hb_contact_sheet(path: str = Field(description="영상 경로"), every: float = Field(default=0.2, gt=0)) -> dict:
    """ffmpeg/OpenCV로 타임코드 contact sheet(jpg) 생성. 키 불필요."""
    sys.path.insert(0, str(ROOT / "tools" / "pipeline"))
    from qa import contact_sheet
    src = ROOT / path
    if not src.exists():
        raise HBError(f"영상 없음: {path}. out/ 아래 최종본 경로를 쓰세요.")
    out = ROOT / "proof" / f"contact_{src.stem}_{every}s.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    contact_sheet(src, out, every, cols=15 if every < 0.5 else 11, tw=144 if every < 0.5 else 216)
    return {"file": str(out.relative_to(ROOT))}


@mcp.tool()
def hb_logo_composite(image: str = Field(description="합성할 PNG/JPG 경로"),
                      layout: Literal["top_center", "bottom_center"] = "top_center",
                      width: int = Field(default=300, ge=80, le=900)) -> dict:
    """assets/의 공식 로고 PNG 2종만 합성. 둘 중 하나라도 없으면 오류로 중단(로고 AI 생성 금지)."""
    l1, l2 = ROOT / "assets" / "logo_hetbahn.png", ROOT / "assets" / "logo_hetbahn30.png"
    if not (l1.exists() and l2.exists()):
        raise HBError("공식 로고 PNG가 없습니다: assets/logo_hetbahn.png, assets/logo_hetbahn30.png 를 넣은 뒤 다시 실행하세요. export 중단.")
    from PIL import Image
    base = Image.open(ROOT / image).convert("RGBA")
    a, b = Image.open(l1).convert("RGBA"), Image.open(l2).convert("RGBA")
    h = int(width * 0.42)
    a = a.resize((int(a.width * h / a.height), h), Image.LANCZOS)
    b = b.resize((int(b.width * h / b.height), h), Image.LANCZOS)
    gap = int(h * 0.35)
    total = a.width + gap + b.width
    y = 270 if layout == "top_center" else base.height - 340 - h - 20
    x = (base.width - total) // 2
    base.alpha_composite(a, (x, y))
    base.alpha_composite(b, (x + a.width + gap, y))
    out = (ROOT / image).with_name((ROOT / image).stem + "_logo.png")
    base.save(out)
    _ledger({"tool": "hb_logo_composite", "service": "local (Pillow)", "files": [str(out.relative_to(ROOT))],
             "logos": [str(l1.relative_to(ROOT)), str(l2.relative_to(ROOT))]})
    return {"file": str(out.relative_to(ROOT))}


@mcp.tool()
def hb_ledger_export() -> dict:
    """proof/생성원장.jsonl을 사람이 읽는 proof/생성원장.txt로 내보낸다(시각·서비스·모델·프롬프트 전문·job·파일)."""
    if not LEDGER.exists():
        raise HBError("원장이 비어 있습니다. 생성 도구를 먼저 실행하세요.")
    lines = []
    for i, raw in enumerate(LEDGER.read_text(encoding="utf-8").splitlines(), 1):
        e = json.loads(raw)
        lines.append(f"[{i}] {e.get('time')} | {e.get('service')} | {e.get('model', '')} | {e.get('shot', e.get('tool'))}")
        if e.get("prompt"):
            lines.append(f"    프롬프트: {e['prompt']}")
        for k in ("job", "refs", "files", "seed", "aspect", "note"):
            if e.get(k):
                lines.append(f"    {k}: {e[k]}")
    out = LEDGER.with_suffix(".txt")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"file": str(out.relative_to(ROOT)), "entries": i}


if __name__ == "__main__":
    mcp.run()
