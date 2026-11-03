"""Render the film (real + mini), mux audio, export to out/.
usage: python3 tools/pipeline/build.py [real|mini|all] [--workers 4]"""
import os
import subprocess
import sys
import time
from multiprocessing import Process
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "work" / "render"
OUT = ROOT / "out"
NAMES = {"real": "A_같이밥_실사_final.mp4", "mini": "A_같이밥_미니어처_final.mp4"}


def render_chunk(v, i0, i1, path):
    import film
    from fx import W, H, FPS
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p",
           str(path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(i0, i1):
        f = film.frame(v, i / FPS)
        p.stdin.write((f * 255 + 0.5).astype(np.uint8).tobytes())
    p.stdin.close()
    p.wait()


def build(v, workers=4):
    import film
    from fx import FPS
    from assets import resolve_logos
    _, _, src = resolve_logos()
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    n = int(round(film.DUR * FPS))
    step = (n + workers - 1) // workers
    procs, parts = [], []
    t0 = time.time()
    for k in range(workers):
        a, b = k * step, min(n, (k + 1) * step)
        part = WORK / f"{v}_{k}.mp4"
        parts.append(part)
        pr = Process(target=render_chunk, args=(v, a, b, part))
        pr.start()
        procs.append(pr)
    for pr in procs:
        pr.join()
    lst = WORK / f"{v}_list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    silent = WORK / f"{v}_video.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                    str(silent)], check=True)
    from audio import build as build_audio
    wav = ROOT / "work/audio/mix.wav"
    if not wav.exists():
        build_audio(wav)
    out = OUT / NAMES[v]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(wav), "-map", "0:v", "-map",
                    "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high", "-pix_fmt",
                    "yuv420p", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-t",
                    f"{film.DUR:.3f}", str(out)], check=True)
    print(f"{v}: {out} ({time.time() - t0:.0f}s, logos={src})", flush=True)
    return out


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    w = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else os.cpu_count() or 4
    for v in (["real", "mini"] if which == "all" else [which]):
        build(v, w)
