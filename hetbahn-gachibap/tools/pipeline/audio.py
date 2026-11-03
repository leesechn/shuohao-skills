"""Score + SFX, synthesised (no samples). 90 BPM, nylon pluck / marimba / light claps,
lift on the 'ding' (12.0 s), back-timed so the last chord lands on the end card (29.667 s)
and rings out to exactly 33.0 s. Output: work/audio/mix.wav (48 kHz stereo), -14 LUFS, TP <= -1 dBTP."""
from pathlib import Path
import numpy as np
from scipy.signal import butter, sosfilt
import pyloudnorm as pyln
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[2]
SR = 48000
DUR = 33.0
BEAT = 60 / 90
N = int(SR * DUR)
rng = np.random.default_rng(90)


def t_arr(d):
    return np.arange(int(SR * d)) / SR


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], btype="band", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, btype="high", fs=SR, output="sos"), x)


def lp(x, f, order=2):
    return sosfilt(butter(order, f, btype="low", fs=SR, output="sos"), x)


def add(buf, sig, at, gain=1.0, pan=0.0):
    i = int(at * SR)
    if i >= buf.shape[0] or i + len(sig) <= 0:
        return
    j = min(buf.shape[0], i + len(sig))
    s = sig[: j - i] * gain
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buf[i:j, 0] += s * l * 1.414
    buf[i:j, 1] += s * r * 1.414


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


# ------------------------------------------------------------- instruments
def pluck(f, d=1.6, bright=0.5):
    """Karplus-Strong nylon pluck."""
    n = int(SR * d)
    p = int(SR / f)
    buf = rng.uniform(-1, 1, p)
    buf = lp(buf, 1500 + 4000 * bright, 1)
    out = np.zeros(n)
    for i in range(n):
        out[i] = buf[i % p]
        buf[i % p] = 0.5 * (buf[i % p] + buf[(i + 1) % p]) * 0.996
    env = np.minimum(1, np.arange(n) / (0.002 * SR))
    return out * env * 0.6


def marimba(f, d=0.9):
    t = t_arr(d)
    s = (np.sin(2 * np.pi * f * t) * np.exp(-t * 5.5)
         + 0.35 * np.sin(2 * np.pi * f * 3.93 * t) * np.exp(-t * 22)
         + 0.12 * np.sin(2 * np.pi * f * 9.2 * t) * np.exp(-t * 45))
    att = np.minimum(1, t / 0.003)
    return s * att * 0.5


def bell(f, d=1.6):
    t = t_arr(d)
    parts = [(1, 1.0, 2.2), (2.76, 0.45, 4.0), (5.40, 0.25, 7.0), (8.93, 0.12, 10.0)]
    s = sum(a * np.sin(2 * np.pi * f * m * t) * np.exp(-t * k) for m, a, k in parts)
    return s * np.minimum(1, t / 0.002) * 0.5


def clap(d=0.25):
    n = int(SR * d)
    x = rng.normal(0, 1, n)
    env = np.zeros(n)
    for o in (0, 0.009, 0.018):
        i = int(o * SR)
        env[i:] += np.exp(-np.arange(n - i) / (0.012 * SR if o < 0.018 else 0.06 * SR))
    return bp(x * env, 900, 3200) * 0.35


def kick(d=0.35):
    t = t_arr(d)
    f = 50 + 70 * np.exp(-t * 30)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 9) * 0.8


def shaker(d=0.08):
    x = rng.normal(0, 1, int(SR * d))
    return hp(x, 6000) * np.exp(-np.arange(len(x)) / (0.015 * SR)) * 0.12


def bass(f, d):
    t = t_arr(d)
    s = np.tanh(1.6 * np.sin(2 * np.pi * f * t)) * np.exp(-t * 1.2)
    return lp(s, 400) * np.minimum(1, t / 0.01) * 0.45


# ------------------------------------------------------------- SFX
def blip(f0=880, f1=1320, d=0.07):
    t = t_arr(d)
    f = f0 + (f1 - f0) * t / d
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / d) * 0.35


def whoosh(d=0.5, lo=300, hi=5000, up=True):
    x = rng.normal(0, 1, int(SR * d))
    out = np.zeros_like(x)
    seg = 32
    L = len(x) // seg
    for k in range(seg):
        fr = k / seg if up else 1 - k / seg
        c = lo * (hi / lo) ** fr
        out[k * L:(k + 1) * L] = bp(x[k * L:(k + 1) * L], c * 0.7, min(c * 1.4, SR / 2 - 100), 1)
    env = np.sin(np.pi * np.linspace(0, 1, len(x))) ** 2
    return out * env * 0.5


def click(d=0.02, f=2500):
    x = rng.normal(0, 1, int(SR * d))
    return bp(x, f * 0.6, f * 1.6) * np.exp(-np.arange(len(x)) / (0.003 * SR)) * 0.5


def snap():
    """Rubbery '톡': pitched pop + tiny click."""
    t = t_arr(0.18)
    f = 650 * np.exp(-t * 12) + 260
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 28)
    return s * 0.8 + np.pad(click(0.01, 3500), (0, len(t) - int(SR * 0.01)))


def hiss(d=1.6):
    x = rng.normal(0, 1, int(SR * d))
    x = hp(x, 2500)
    t = np.linspace(0, 1, len(x))
    env = np.minimum(1, t * d / 0.05) * np.exp(-t * 2.8)
    return x * env * 0.22


def crackle(d=0.8, density=90):
    n = int(SR * d)
    out = np.zeros(n)
    for _ in range(int(density * d)):
        i = rng.integers(0, n - 400)
        c = click(0.006, rng.uniform(1800, 5000)) * rng.uniform(0.2, 0.7)
        out[i:i + len(c)] += c
    return out


def clink():
    t = t_arr(1.0)
    parts = [(2130, 1.0, 9), (3420, 0.6, 12), (5610, 0.4, 16), (7920, 0.25, 22)]
    return sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * k) for f, a, k in parts) * 0.28


def hum(d):
    t = t_arr(d)
    s = 0.6 * np.sin(2 * np.pi * 60 * t) + 0.3 * np.sin(2 * np.pi * 120 * t)
    fan = lp(rng.normal(0, 1, len(t)), 700) * 0.4
    env = np.minimum(1, t / 0.15) * np.minimum(1, (d - t) / 0.05)
    return (s + fan) * env * 0.10


# ------------------------------------------------------------- score
PROG = [(48, [60, 64, 67, 72]), (45, [57, 60, 64, 69]), (41, [57, 60, 65, 69]), (43, [55, 59, 62, 67])]  # C Am F G


def score(buf):
    total_beats = 49.5
    lift = 18  # beat of the ding (12.0 s)
    end = 44.5  # end card cut (29.667 s)
    b = 0.0
    while b < end:
        bar = int(b // 4)
        root, ch = PROG[bar % 4]
        beat_in_bar = b % 4
        tsec = b * BEAT
        pre = b < lift
        countdown = 15 <= b < lift
        # nylon arpeggio on 8ths
        idx = int((b * 2) % 8)
        note = ch[[0, 1, 2, 3, 2, 1, 2, 3][idx]]
        g = 0.22 if pre else 0.30
        if countdown:
            g = 0.10
        add(buf, pluck(midi(note), 1.4, 0.45), tsec, g, pan=-0.25)
        if not pre:
            # marimba melody on beats + offbeat answer
            if beat_in_bar in (0, 1.5, 2, 3.5):
                mel = ch[[3, 2, 1, 2][int(beat_in_bar) % 4]] + 12
                add(buf, marimba(midi(mel)), tsec, 0.28, pan=0.3)
            if beat_in_bar == 0:
                add(buf, kick(), tsec, 0.55)
                add(buf, bass(midi(root - 12 + 12), BEAT * 4), tsec, 0.55)
            if beat_in_bar in (1, 3):
                add(buf, clap(), tsec, 0.55, pan=0.1)
            add(buf, shaker(), tsec + BEAT / 2, 0.8, pan=0.35)
        elif b >= 4 and beat_in_bar == 0 and not countdown:
            add(buf, bass(midi(root), BEAT * 4), tsec, 0.35)
        b += 0.5
    # end chord on the end card + ring out to 33.0
    t_end = end * BEAT
    for k, n in enumerate([48, 55, 60, 64, 67, 72, 76]):
        add(buf, pluck(midi(n), DUR - t_end, 0.55), t_end + k * 0.025, 0.28, pan=-0.3 + k * 0.1)
    add(buf, marimba(midi(84), 1.2), t_end, 0.25, pan=0.3)
    add(buf, bell(midi(88), 2.5), t_end + 0.05, 0.10)
    add(buf, kick(), t_end, 0.5)


def sfx(buf):
    # S01 new message lands on the beat
    add(buf, blip(), 1.0, 0.5, 0.3)
    add(buf, blip(700, 1000), 1.18, 0.35, -0.3)
    # S02 card
    add(buf, whoosh(0.35, 500, 6000), 2.45, 0.6)
    add(buf, blip(400, 900, 0.09), 2.667, 0.6)
    # S03 typing, delete, send, sleeve, drop
    for i in range(9):
        add(buf, click(0.015, 2600), 4.0 + i * 0.046, 0.35, 0.2)
    for i in range(9):
        add(buf, click(0.012, 1900), 4.48 + i * 0.027, 0.3, 0.2)
    add(buf, blip(300, 600, 0.06), 4.95, 0.7)
    add(buf, whoosh(0.3, 2000, 8000), 5.05, 0.35)
    add(buf, whoosh(0.5, 3000, 300, up=False), 5.35, 0.6)
    # S04 tab creak, snap (both cities), blinks
    add(buf, bp(rng.normal(0, 1, int(SR * 0.3)), 700, 2200) * np.linspace(0, 1, int(SR * 0.3)) * 0.12, 6.72, 1.0)
    add(buf, snap(), 7.15, 0.85, -0.2)
    add(buf, snap(), 7.155, 0.75, 0.2)
    add(buf, blip(1600, 1600, 0.05), 7.35, 0.25)
    add(buf, blip(1600, 1600, 0.05), 7.65, 0.25)
    # S05 messages
    add(buf, blip(), 8.333 + 0.15, 0.5, -0.2)
    add(buf, blip(1000, 1500), 8.333 + 0.82, 0.5, 0.2)
    # S06 microwaves
    add(buf, hum(2.0), 10.0, 1.0)
    for k in range(3):
        add(buf, blip(1000, 1000, 0.06), 10.0 + k * BEAT, 0.4)
    # S07 two dings at the same instant
    add(buf, bell(midi(88)), 12.0, 0.55, -0.3)
    add(buf, bell(midi(84)), 12.0, 0.55, 0.3)
    add(buf, bell(midi(88), 1.2), 12.18, 0.35, -0.3)
    add(buf, bell(midi(84), 1.2), 12.18, 0.35, 0.3)
    # S08 film releases + steam
    add(buf, crackle(0.75), 13.333 + 0.35, 0.8)
    add(buf, hiss(1.8), 13.333 + 0.75, 0.9)
    # S09 shimmer
    for k, n in enumerate([84, 88, 91, 96, 91, 88]):
        add(buf, bell(midi(n), 1.0), 16.0 + k * BEAT / 2, 0.10, -0.5 + k * 0.2)
    # S11 spoon clink
    add(buf, clink(), 21.333 + 0.40, 0.75)
    # S12 three bands land, then open together
    for k in range(3):
        add(buf, blip(500, 800, 0.05), 22.667 + k * BEAT * 0.5, 0.35)
    add(buf, crackle(0.4), 24.0, 0.7)
    add(buf, hiss(1.2), 24.05, 0.7)
    # S13 title pop + calendar ticks
    add(buf, blip(400, 900, 0.09), 25.333, 0.5)
    for k in range(9):
        add(buf, click(0.02, 1500), 25.333 + 0.6 + k * 1.1 / 9, 0.45)
    # S14 strike + '나' pop
    add(buf, whoosh(0.2, 1500, 6000), 27.667 + 0.45, 0.4)
    add(buf, bell(midi(91), 0.8), 27.667 + 0.95, 0.25)
    # S15 sparkle
    add(buf, whoosh(0.4, 600, 7000), 29.5, 0.35)


def build(out=ROOT / "work/audio/mix.wav"):
    out.parent.mkdir(parents=True, exist_ok=True)
    mus = np.zeros((N, 2))
    fx = np.zeros((N, 2))
    score(mus)
    sfx(fx)
    # dynamics: quiet hook (dialogue-less), lift at the ding
    tt = np.arange(N) / SR
    ride = np.where(tt < 12.0, 0.55, 1.0)
    ride = np.convolve(ride, np.ones(2400) / 2400, mode="same")
    mix = mus * ride[:, None] + fx * 1.1
    # gentle room
    rev = np.zeros_like(mix)
    for dly, g in [(0.031, 0.22), (0.047, 0.18), (0.071, 0.14), (0.113, 0.10)]:
        k = int(dly * SR)
        rev[k:] += mix[:-k] * g
    mix = mix + lp(rev, 5000) * 0.6
    # end exactly at 33.0 s with a 0.4 s fade
    fade = np.minimum(1, (DUR - tt) / 0.4)[:, None]
    mix *= np.clip(fade, 0, 1)
    meter = pyln.Meter(SR)
    ceil = 10 ** (-2.3 / 20)  # headroom for AAC inter-sample overshoot
    src = mix / (np.abs(mix).max() + 1e-9)
    gain_db = -14.0 - meter.integrated_loudness(src)
    for _ in range(6):  # soft-clip lowers loudness; iterate gain until -14 LUFS after the ceiling
        out_ = np.tanh(src * 10 ** (gain_db / 20) / ceil) * ceil
        err = -14.0 - meter.integrated_loudness(out_)
        if abs(err) < 0.05:
            break
        gain_db += err
    mix = out_
    wavfile.write(out, SR, mix.astype(np.float32))
    return out, meter.integrated_loudness(mix)


if __name__ == "__main__":
    p, l = build()
    print(p, round(l, 2), "LUFS")
