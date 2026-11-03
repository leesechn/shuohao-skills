"""Re-render only some time ranges of an already rendered silent video, then mux with the current mix.
usage: python3 tools/pipeline/patch.py real 6.0-8.333 27.667-29.667"""
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import film
from fx import W, H, FPS
from build import WORK, OUT, NAMES, ROOT


def main(v, ranges):
    src = WORK / f"{v}_video.mp4"
    tmp = WORK / f"{v}_video_patched.mp4"
    rr = [tuple(float(x) for x in r.split("-")) for r in ranges]
    dec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", str(src), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt",
                            "yuv420p", str(tmp)], stdin=subprocess.PIPE)
    n = int(round(film.DUR * FPS))
    sz = W * H * 3
    redone = 0
    for i in range(n):
        buf = dec.stdout.read(sz)
        t = i / FPS
        if any(a - 1e-6 <= t < b for a, b in rr):
            buf = (film.frame(v, t) * 255 + 0.5).astype(np.uint8).tobytes()
            redone += 1
        enc.stdin.write(buf)
    enc.stdin.close(); enc.wait(); dec.wait()
    tmp.replace(src)
    from audio import build as build_audio
    wav = ROOT / "work/audio/mix.wav"
    build_audio(wav)
    out = OUT / NAMES[v]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-i", str(wav), "-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-t", f"{film.DUR:.3f}",
                    str(out)], check=True)
    print(v, "patched frames:", redone, "->", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
