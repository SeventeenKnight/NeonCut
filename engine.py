"""NeonCut – Engine: Projektmodell, Medien, Rendering, Audio (gestreamt), Untertitel, Export."""
from __future__ import annotations

import copy
import math
import os
import queue
import threading
import time
import urllib.request
import uuid
from collections import OrderedDict
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen,
                           QRadialGradient)

SR = 48000
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".wmv", ".flv", ".mts", ".ts", ".3gp"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus", ".wma"}
ALL_EXT = VIDEO_EXT | IMAGE_EXT | AUDIO_EXT
IMAGE_DUR = 3.0
MIN_LEN = 0.1
ASPECTS = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1), "4:5": (4, 5), "21:9": (21, 9)}
KINDS = ("video", "overlay", "text", "audio")


def new_id():
    return uuid.uuid4().hex[:10]


# ════════════════════════════════════════════════════════════════════════════
#  Projektmodell
# ════════════════════════════════════════════════════════════════════════════
def new_project():
    return {"version": 2, "name": "Unbenanntes Projekt", "aspect": "16:9", "bg": "blur",
            "bg_color": "#000000", "media": {}, "video": [], "overlay": [], "text": [], "audio": []}


def fix_project(p):
    base = new_project()
    base.update(p)
    for c in base["video"] + base["overlay"]:
        c.setdefault("chroma", {"on": False, "color": "#00ff00", "tol": 0.3, "soft": 0.12})
        c.setdefault("blend", "normal")
    return base


def canvas_size(aspect, short=1080):
    a, b = ASPECTS.get(aspect, (16, 9))
    if a >= b:
        return int(round(short * a / b / 2) * 2), short
    return short, int(round(short * b / a / 2) * 2)


def video_clip(media):
    dur = media["duration"] if media["kind"] == "video" else IMAGE_DUR
    return {"id": new_id(), "media": media["id"], "in": 0.0, "out": float(dur), "speed": 1.0,
            "volume": 1.0, "mute": False, "denoise": False, "fade_in": 0.0, "fade_out": 0.0,
            "scale": 1.0, "x": 0.0, "y": 0.0, "rot": 0.0, "opacity": 1.0, "flip": False,
            "filter": "none", "filter_amt": 1.0,
            "adj": {"bright": 0.0, "contrast": 0.0, "sat": 0.0, "temp": 0.0, "vignette": 0.0},
            "effect": "none", "trans": {"type": "none", "dur": 0.6},
            "chroma": {"on": False, "color": "#00ff00", "tol": 0.3, "soft": 0.12}, "blend": "normal"}


def overlay_clip(media, start):
    c = video_clip(media)
    c.update(start=float(start), scale=0.42, x=0.26, y=-0.22)
    return c


def audio_clip(media, start):
    return {"id": new_id(), "media": media["id"], "start": float(start), "in": 0.0,
            "out": float(media["duration"]), "volume": 1.0, "fade_in": 0.0, "fade_out": 0.0,
            "denoise": False}


TEXT_PRESETS = {
    "title":    dict(label="Titel", font="Segoe UI", bold=True, size=110, color="#ffffff",
                     stroke="#000000", stroke_w=7, shadow=True),
    "subtitle": dict(label="Untertitel", font="Segoe UI", bold=True, size=54, color="#ffffff",
                     box=True, box_color="#000000", box_alpha=0.62, y=0.36),
    "neon":     dict(label="Neon", font="Segoe UI", bold=True, size=104, color="#ffffff",
                     glow="#ff3fd8"),
    "meme":     dict(label="Meme", font="Impact", bold=False, size=124, color="#ffffff",
                     stroke="#000000", stroke_w=9, y=-0.34),
    "yellow":   dict(label="Highlight", font="Segoe UI Black", bold=True, size=100, color="#ffd60a",
                     stroke="#000000", stroke_w=8, shadow=True),
    "minimal":  dict(label="Minimal", font="Segoe UI Light", bold=False, size=70, color="#ffffff",
                     shadow=True),
    "label":    dict(label="Etikett", font="Segoe UI", bold=True, size=60, color="#111111",
                     box=True, box_color="#ffffff", box_alpha=1.0),
    "outline":  dict(label="Kontur", font="Segoe UI Black", bold=True, size=116, color="#00000000",
                     stroke="#ffffff", stroke_w=4),
    "caption":  dict(label="Auto-Untertitel", font="Segoe UI Black", bold=True, size=64, color="#ffffff",
                     stroke="#000000", stroke_w=6, y=0.34, anim_in="pop", anim_out="none"),
}

STICKERS = ["😂", "🔥", "❤️", "👍", "😎", "🎉", "💯", "😱", "✨", "⭐", "👀", "🤯", "💀", "🙏", "😍", "🥳",
            "🚀", "⚡", "😭", "👑", "🎮", "📢", "✅", "❌", "🤣", "😡", "🤔", "👏", "💥", "🎵", "💸", "🏆"]


def text_clip(start, preset="title", text=None):
    p = TEXT_PRESETS.get(preset, TEXT_PRESETS["title"])
    c = {"id": new_id(), "text": text or p["label"], "start": float(start), "dur": 3.0,
         "font": "Segoe UI", "bold": True, "italic": False, "size": 96, "color": "#ffffff",
         "stroke": "#000000", "stroke_w": 0, "box": False, "box_color": "#000000", "box_alpha": 0.6,
         "glow": "", "shadow": False, "x": 0.0, "y": 0.0, "anim_in": "pop", "anim_out": "fade"}
    c.update({k: v for k, v in p.items() if k != "label"})
    return c


def sticker_clip(start, emoji):
    c = text_clip(start, "title", emoji)
    c.update(font="Segoe UI Emoji", size=240, stroke_w=0, shadow=False, sticker=True, bold=False,
             x=0.25, y=-0.15, anim_in="pop", anim_out="pop")
    return c


def clip_len(c):
    return max(MIN_LEN, (c["out"] - c["in"]) / c.get("speed", 1.0))


def layout(proj):
    res, t = [], 0.0
    for c in proj["video"]:
        d = clip_len(c)
        res.append((c, t, t + d))
        t += d
    return res


def span(proj, kind, c):
    if kind == "video":
        for x in layout(proj):
            if x[0] is c:
                return x[1], x[2]
    if kind == "overlay":
        return c["start"], c["start"] + clip_len(c)
    if kind == "text":
        return c["start"], c["start"] + c["dur"]
    return c["start"], c["start"] + c["out"] - c["in"]


def trans_dur(proj, lay, i):
    if i < 0 or i + 1 >= len(lay):
        return 0.0
    tr = lay[i][0].get("trans", {})
    if tr.get("type", "none") == "none":
        return 0.0
    da = lay[i][2] - lay[i][1]
    db = lay[i + 1][2] - lay[i + 1][1]
    return max(0.05, min(tr.get("dur", 0.6), da * 0.9, db * 0.9))


def duration(proj):
    end = layout(proj)[-1][2] if proj["video"] else 0.0
    for c in proj.get("overlay", []):
        end = max(end, c["start"] + clip_len(c))
    for c in proj["text"]:
        end = max(end, c["start"] + c["dur"])
    for c in proj["audio"]:
        end = max(end, c["start"] + (c["out"] - c["in"]))
    return end


def find_clip(proj, cid):
    for kind in KINDS:
        for c in proj.get(kind, []):
            if c["id"] == cid:
                return kind, c
    return None, None


# ════════════════════════════════════════════════════════════════════════════
#  Filter, Effekte, Übergänge, Mischmodi
# ════════════════════════════════════════════════════════════════════════════
FILTERS = {
    "none":    ("Original", {}),
    "cinema":  ("Kino", dict(contrast=0.18, sat=-0.12, temp=-0.1, ts=(-0.02, 0.03, 0.07), th=(0.07, 0.03, -0.03))),
    "warm":    ("Warm", dict(temp=0.45, sat=0.1, bright=0.03)),
    "cold":    ("Kalt", dict(temp=-0.45, sat=-0.05)),
    "vivid":   ("Lebendig", dict(sat=0.45, contrast=0.12)),
    "vintage": ("Vintage", dict(lift=0.08, contrast=-0.1, sat=-0.3, temp=0.28)),
    "matte":   ("Matt", dict(lift=0.1, contrast=-0.15, sat=-0.1)),
    "pastel":  ("Pastell", dict(lift=0.06, sat=-0.22, bright=0.08, contrast=-0.08)),
    "neon":    ("Neon", dict(sat=0.6, contrast=0.2, ts=(0.06, 0.0, 0.1), th=(0.0, 0.04, 0.06))),
    "bw":      ("Schwarzweiß", dict(sat=-1.0, contrast=0.15)),
    "noir":    ("Noir", dict(sat=-1.0, contrast=0.45, bright=-0.05)),
    "sepia":   ("Sepia", dict(sepia=1.0, contrast=0.05)),
}

EFFECTS = {
    "none": "Keiner", "zoom_in": "Zoom rein", "zoom_out": "Zoom raus", "shake": "Wackeln",
    "pulse": "Pulsieren", "rgb": "RGB-Split", "glitch": "Glitch", "flash": "Blitz",
    "vhs": "Retro-VHS", "blur_in": "Unschärfe rein",
}

TRANSITIONS = {
    "none": "Keiner", "fade": "Überblenden", "black": "Schwarzblende", "white": "Weißblende",
    "slide_l": "Schieben", "slide_up": "Hochschieben", "zoom": "Zoom", "wipe": "Wischen",
    "spin": "Drehen", "flash": "Blitz",
}

BLENDS = {
    "normal": ("Normal", QPainter.CompositionMode_SourceOver),
    "screen": ("Negativ multiplizieren", QPainter.CompositionMode_Screen),
    "multiply": ("Multiplizieren", QPainter.CompositionMode_Multiply),
    "overlay": ("Überlagern", QPainter.CompositionMode_Overlay),
    "lighten": ("Aufhellen", QPainter.CompositionMode_Lighten),
    "darken": ("Abdunkeln", QPainter.CompositionMode_Darken),
    "add": ("Addieren", QPainter.CompositionMode_Plus),
}

_lut_cache: OrderedDict = OrderedDict()


def _color_params(c):
    p = FILTERS.get(c.get("filter", "none"), FILTERS["none"])[1]
    amt = c.get("filter_amt", 1.0)
    adj = c.get("adj", {})
    ts = tuple(v * amt for v in p.get("ts", (0, 0, 0)))
    th = tuple(v * amt for v in p.get("th", (0, 0, 0)))
    return (round(p.get("bright", 0) * amt + adj.get("bright", 0) * 0.3, 4),
            round(p.get("contrast", 0) * amt + adj.get("contrast", 0) * 0.6, 4),
            round(p.get("sat", 0) * amt + adj.get("sat", 0), 4),
            round(p.get("temp", 0) * amt + adj.get("temp", 0), 4),
            round(p.get("lift", 0) * amt, 4),
            round(p.get("sepia", 0) * amt, 4), ts, th)


def _lut(bright, contrast, temp, lift, ts, th):
    key = (bright, contrast, temp, lift, ts, th)
    if key in _lut_cache:
        _lut_cache.move_to_end(key)
        return _lut_cache[key]
    v = np.linspace(0, 1, 256)
    base = (v + bright - 0.5) * (1 + contrast) + 0.5
    base = base * (1 - lift) + lift
    luts = []
    for ch in range(3):
        x = base + (temp * 0.09, temp * 0.012, -temp * 0.09)[ch]
        x = x + ts[ch] * (1 - v) ** 2 + th[ch] * v ** 2
        luts.append(np.clip(x * 255 + 0.5, 0, 255).astype(np.uint8))
    lut = np.stack(luts)
    _lut_cache[key] = lut
    if len(_lut_cache) > 64:
        _lut_cache.popitem(last=False)
    return lut


def apply_color(arr, c):
    bright, contrast, sat, temp, lift, sepia, ts, th = _color_params(c)
    if bright or contrast or temp or lift or any(ts) or any(th):
        lut = _lut(bright, contrast, temp, lift, ts, th)
        out = np.empty_like(arr)
        for ch in range(3):
            out[..., ch] = lut[ch][arr[..., ch]]
        arr = out
    if sat or sepia:
        f = arr.astype(np.float32)
        lum = f @ np.array([0.299, 0.587, 0.114], np.float32)
        if sat:
            f = lum[..., None] + (f - lum[..., None]) * (1 + sat)
        if sepia:
            sep = lum[..., None] * np.array([1.07, 0.74, 0.43], np.float32)
            f = f * (1 - sepia) + sep * sepia
        arr = np.clip(f, 0, 255).astype(np.uint8)
    return arr


def chroma_key(arr, ck):
    """RGB → RGBA: Farbe (z. B. Greenscreen) transparent machen, mit Farbsaum-Entfernung."""
    key = QColor(ck.get("color", "#00ff00"))
    kr, kg, kb = key.red(), key.green(), key.blue()
    f = arr.astype(np.float32)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    cb = -0.1687 * r - 0.3313 * g + 0.5 * b
    cr = 0.5 * r - 0.4187 * g - 0.0813 * b
    kcb = -0.1687 * kr - 0.3313 * kg + 0.5 * kb
    kcr = 0.5 * kr - 0.4187 * kg - 0.0813 * kb
    dist = np.sqrt((cb - kcb) ** 2 + (cr - kcr) ** 2) / 180.0
    tol, soft = ck.get("tol", 0.3), max(0.01, ck.get("soft", 0.12))
    a = np.clip((dist - tol) / soft, 0, 1)
    out = np.empty(arr.shape[:2] + (4,), np.uint8)
    rgb = f
    if kg > kr and kg > kb:
        rgb = f.copy()
        rgb[..., 1] = np.where(a < 1, np.minimum(g, np.maximum(r, b) + 8), g)
    elif kb > kr and kb > kg:
        rgb = f.copy()
        rgb[..., 2] = np.where(a < 1, np.minimum(b, np.maximum(r, g) + 8), b)
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[..., 3] = (a * 255).astype(np.uint8)
    return out


def frame_effect(arr, c, local):
    eff = c.get("effect", "none")
    if eff in ("rgb", "glitch", "vhs"):
        h, w, _ = arr.shape
        k = {"rgb": 0.009, "glitch": 0.006, "vhs": 0.004}[eff]
        s = max(1, int(w * k * (0.6 + 0.4 * math.sin(local * 7))))
        out = arr.copy()
        out[:, s:, 0] = arr[:, :-s, 0]
        out[:, :-s, 2] = arr[:, s:, 2]
        if eff == "glitch":
            rng = np.random.default_rng(int(local * 12))
            if rng.random() < 0.55:
                for _ in range(int(rng.integers(2, 6))):
                    y0 = int(rng.integers(0, h))
                    hh = int(rng.integers(max(1, h // 40), max(2, h // 9)))
                    out[y0:y0 + hh] = np.roll(out[y0:y0 + hh], int(rng.integers(-w // 10, w // 10)), axis=1)
        return out
    return arr


def effect_transform(c, local, dur, W, H):
    eff = c.get("effect", "none")
    p = max(0.0, min(1.0, local / max(dur, 1e-6)))
    if eff == "zoom_in":
        return 1 + 0.18 * p, 0, 0
    if eff == "zoom_out":
        return 1.18 - 0.18 * p, 0, 0
    if eff == "shake":
        return (1.04, (math.sin(local * 37) * 0.6 + math.sin(local * 23.3) * 0.4) * W * 0.01,
                (math.sin(local * 31) * 0.6 + math.cos(local * 19.7) * 0.4) * H * 0.01)
    if eff == "pulse":
        return 1 + 0.045 * (0.5 + 0.5 * math.sin(local * math.tau * 2)) ** 2, 0, 0
    return 1.0, 0, 0


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = max(0.0, min(1.0, x))
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def back(x):
    x = max(0.0, min(1.0, x))
    c1 = 1.70158
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


# ════════════════════════════════════════════════════════════════════════════
#  Medien
# ════════════════════════════════════════════════════════════════════════════
def rgb_to_qimage(arr):
    arr = np.ascontiguousarray(arr)
    h, w, ch = arr.shape
    fmt = QImage.Format_RGBA8888 if ch == 4 else QImage.Format_RGB888
    return QImage(arr.data, w, h, ch * w, fmt).copy()


def qimage_to_rgb(img):
    img = img.convertToFormat(QImage.Format_RGB888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    buf = np.frombuffer(img.constBits(), np.uint8, count=bpl * h)
    return buf.reshape(h, bpl)[:, :w * 3].reshape(h, w, 3).copy()


def _even(x):
    return max(2, int(x) // 2 * 2)


def _real_video_stream(c):
    for s in c.streams.video:
        if not (s.disposition & av.stream.Disposition.attached_pic):
            return s
    return None


def probe(path):
    path = Path(path)
    ext = path.suffix.lower()
    m = {"id": new_id(), "path": str(path), "name": path.name, "rotk": 0, "fps": 30.0}
    if ext in IMAGE_EXT:
        img = QImage(str(path))
        if img.isNull():
            raise ValueError("Bild konnte nicht gelesen werden")
        m.update(kind="image", w=img.width(), h=img.height(), duration=IMAGE_DUR, has_audio=False)
        return m
    c = av.open(str(path))
    try:
        vs = _real_video_stream(c)
        aus = c.streams.audio[0] if c.streams.audio else None
        dur = c.duration / 1e6 if c.duration else 0.0
        if not dur and vs is not None and vs.duration:
            dur = float(vs.duration * vs.time_base)
        if not dur and aus is not None and aus.duration:
            dur = float(aus.duration * aus.time_base)
        if vs is not None and ext not in AUDIO_EXT:
            w, h = vs.codec_context.width, vs.codec_context.height
            rotk = 0
            try:
                for f in c.decode(vs):
                    rotk = int(round((getattr(f, "rotation", 0) or 0) / 90)) % 4
                    break
            except Exception:
                pass
            if rotk % 2:
                w, h = h, w
            m.update(kind="video", w=w, h=h, duration=max(dur, 0.1), has_audio=aus is not None,
                     rotk=rotk, fps=float(vs.average_rate or 30))
        elif aus is not None:
            m.update(kind="audio", w=0, h=0, duration=max(dur, 0.1), has_audio=True)
        else:
            raise ValueError("Keine Video- oder Tonspur gefunden")
    finally:
        c.close()
    return m


def _time_origin(c):
    """Zeitnullpunkt einer Datei: Start der Videospur (sonst der Tonspur) – hält Bild und Ton synchron."""
    vs = _real_video_stream(c)
    s = vs if vs is not None else (c.streams.audio[0] if c.streams.audio else None)
    if s is not None and s.start_time is not None:
        return float(s.start_time * s.time_base)
    return 0.0


def decode_range(path, t0, t1, rate=16000, layout_="mono"):
    """Ton eines Zeitbereichs dekodieren (z. B. 16 kHz mono für die Spracherkennung)."""
    c = av.open(str(path))
    try:
        if not c.streams.audio:
            return np.zeros((0,), np.float32)
        s = c.streams.audio[0]
        origin = _time_origin(c)
        tb = float(s.time_base)
        c.seek(max(0, int((t0 + origin) / tb)), stream=s, backward=True)
        rs = av.AudioResampler(format="fltp", layout=layout_, rate=rate)
        n_total = int((t1 - t0) * rate)
        out = np.zeros((n_total,), np.float32)
        pos = None
        for f in c.decode(s):
            if pos is None:
                ft = f.time if f.time is not None else t0 + origin
                pos = int(round((ft - origin - t0) * rate))
            for g in rs.resample(f):
                a = g.to_ndarray()[0]
                lo, hi = max(pos, 0), min(pos + len(a), n_total)
                if hi > lo:
                    out[lo:hi] = a[lo - pos:hi - pos]
                pos += len(a)
            if pos >= n_total:
                break
        return out
    finally:
        c.close()


def noise_profile(a, n_fft=1024):
    win = np.hanning(n_fft).astype(np.float32)
    prof = []
    for ch in range(a.shape[1]):
        x = a[:, ch]
        if len(x) < n_fft * 4:
            prof.append(np.zeros(n_fft // 2 + 1, np.float32))
            continue
        frames = np.lib.stride_tricks.sliding_window_view(np.pad(x, (0, n_fft)), n_fft)[::256]
        sel = frames[np.linspace(0, len(frames) - 1, min(1500, len(frames))).astype(int)]
        prof.append(np.percentile(np.abs(np.fft.rfft(sel * win, axis=1)), 12, axis=0))
    return prof


def denoise_audio(a, prof=None):
    """Spektrale Rauschunterdrückung."""
    n_fft, hop = 1024, 256
    win = np.hanning(n_fft).astype(np.float32)
    prof = prof if prof is not None else noise_profile(a, n_fft)
    out = np.zeros_like(a)
    w2 = win ** 2
    for ch in range(a.shape[1]):
        x = a[:, ch]
        if len(x) < n_fft * 2:
            out[:, ch] = x
            continue
        xp = np.pad(x, (0, n_fft))
        frames = np.lib.stride_tricks.sliding_window_view(xp, n_fft)[::hop]
        y = np.zeros(len(xp), np.float32)
        wsum = np.zeros(len(xp), np.float32)
        for c0 in range(0, len(frames), 4096):
            S = np.fft.rfft(frames[c0:c0 + 4096] * win, axis=1)
            mag = np.abs(S)
            gain = np.clip((mag - prof[ch] * 2.0) / (mag + 1e-9), 0.06, 1.0)
            gain[1:-1] = (gain[:-2] + gain[1:-1] * 2 + gain[2:]) / 4
            Y = np.fft.irfft(S * gain, n=n_fft, axis=1).astype(np.float32) * win
            for k in range(len(Y)):
                s = (c0 + k) * hop
                y[s:s + n_fft] += Y[k]
                wsum[s:s + n_fft] += w2
        out[:, ch] = (y / np.maximum(wsum, 1e-3))[:len(x)]
    return out


class AudioSource:
    """Ton einer Datei, der in 8-Sekunden-Stücken nach Bedarf dekodiert wird (beliebig lange Videos)."""
    CH = SR * 8
    MAX = 48

    def __init__(self, path):
        self.path = str(path)
        self.c = None
        self.dlock = threading.Lock()
        self.clock = threading.Lock()
        self.cache: OrderedDict = OrderedDict()
        self.prof = None
        self.broken = False

    def _open(self):
        if self.c is None:
            self.c = av.open(self.path)
            self.s = self.c.streams.audio[0]
            self.tb = float(self.s.time_base)
            self.origin = _time_origin(self.c)

    def close(self):
        with self.dlock:
            if self.c is not None:
                try:
                    self.c.close()
                except Exception:
                    pass
                self.c = None

    def _decode(self, k):
        base = k * self.CH
        out = np.zeros((self.CH, 2), np.float32)
        with self.dlock:
            try:
                self._open()
                t0 = base / SR
                self.c.seek(max(0, int((t0 + self.origin) / self.tb)), stream=self.s, backward=True)
                rs = av.AudioResampler(format="fltp", layout="stereo", rate=SR)
                pos = None
                for f in self.c.decode(self.s):
                    if pos is None:
                        ft = f.time if f.time is not None else t0 + self.origin
                        pos = int(round((ft - self.origin) * SR))
                    for g in rs.resample(f):
                        a = g.to_ndarray().T
                        lo, hi = max(pos, base), min(pos + len(a), base + self.CH)
                        if hi > lo:
                            out[lo - base:hi - base] = a[lo - pos:hi - pos]
                        pos += len(a)
                    if pos >= base + self.CH:
                        break
            except Exception:
                try:
                    if self.c is not None:
                        self.c.close()
                except Exception:
                    pass
                self.c = None
        return out

    def chunk(self, k, dn=False, block=True):
        key = (k, dn)
        with self.clock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
        if not block:
            return None
        if dn:
            pad = 4096
            raw = self.chunk(k, False)
            prev = self.chunk(k - 1, False)[-pad:] if k > 0 else np.zeros((pad, 2), np.float32)
            nxt = self.chunk(k + 1, False)[:pad]
            if self.prof is None:
                self.prof = noise_profile(np.concatenate([self.chunk(i, False) for i in range(3)]))
            arr = denoise_audio(np.concatenate([prev, raw, nxt]), self.prof)[pad:pad + self.CH]
        else:
            arr = self._decode(k)
        with self.clock:
            self.cache[key] = arr
            while len(self.cache) > self.MAX:
                self.cache.popitem(last=False)
        return arr

    def read(self, idx, dn=False, block=True, request=None):
        out = np.zeros((len(idx), 2), np.float32)
        if not len(idx):
            return out
        ks = idx // self.CH
        for k in np.unique(ks):
            k = int(k)
            arr = self.chunk(k, dn, block)
            if arr is None:
                if request:
                    request(self, k, dn)
                continue
            m = ks == k
            out[m] = arr[idx[m] - k * self.CH]
        return out


class MediaStore(QObject):
    """Thumbnails, Wellenformen und Ton – alles im Hintergrund."""
    ready = Signal(str)

    def __init__(self):
        super().__init__()
        self.thumbs: dict[str, list] = {}
        self.poster: dict[str, QImage] = {}
        self.peaks: dict[str, np.ndarray] = {}
        self.sources: dict[str, AudioSource] = {}
        self.loading: set[str] = set()
        self._img_full: dict[str, QImage] = {}
        self._img_cache: OrderedDict = OrderedDict()
        self.lock = threading.Lock()
        self.q: queue.Queue = queue.Queue()
        self.pending: set = set()
        threading.Thread(target=self._worker, daemon=True).start()

    # ── Laden ───────────────────────────────────────────────────────────────
    def load(self, media):
        mid = media["id"]
        if media.get("has_audio") and mid not in self.sources:
            self.sources[mid] = AudioSource(media["path"])
        if mid in self.loading or mid in self.thumbs:
            return
        self.loading.add(mid)
        threading.Thread(target=self._load, args=(dict(media),), daemon=True).start()

    def _load(self, m):
        mid = m["id"]
        try:
            if m["kind"] == "image":
                th = QImage(m["path"]).scaledToHeight(90, Qt.SmoothTransformation)
                self.thumbs[mid] = [(0.0, th)]
                self.poster[mid] = th
            elif m["kind"] == "video":
                self._video_thumbs(m)
            else:
                self.thumbs[mid] = []
        except Exception:
            self.thumbs.setdefault(mid, [])
        finally:
            self.loading.discard(mid)
            self.ready.emit(mid)
        if m.get("has_audio"):
            try:
                self._peaks(m)
            except Exception:
                pass
            self.ready.emit(mid)

    def _peaks(self, m):
        """Wellenform: ganzer Ton bei 8 kHz mono, 50 Werte pro Sekunde – schrittweise sichtbar."""
        c = av.open(m["path"])
        try:
            s = c.streams.audio[0]
            s.thread_type = "AUTO"
            rs = av.AudioResampler(format="fltp", layout="mono", rate=8000)
            blk = 160
            vals, rest = [], np.zeros(0, np.float32)
            last_emit = time.monotonic()
            for f in c.decode(s):
                for g in rs.resample(f):
                    a = np.concatenate([rest, np.abs(g.to_ndarray()[0])])
                    n = len(a) // blk
                    if n:
                        vals.append(a[:n * blk].reshape(n, blk).max(axis=1))
                    rest = a[n * blk:]
                if time.monotonic() - last_emit > 1.5 and vals:
                    self.peaks[m["id"]] = np.concatenate(vals)
                    self.ready.emit(m["id"])
                    last_emit = time.monotonic()
            if vals:
                self.peaks[m["id"]] = np.concatenate(vals)
        finally:
            c.close()

    def _video_thumbs(self, m):
        c = av.open(m["path"])
        try:
            s = _real_video_stream(c)
            s.thread_type = "AUTO"
            tb = float(s.time_base)
            t0 = float(s.start_time * s.time_base) if s.start_time else 0.0
            dur = m["duration"]
            n = int(max(1, min(60, dur / 1.5)))
            times = np.linspace(0, max(0, dur - 0.1), n) if n > 1 else [0.0]
            h = 90
            w = _even(h * m["w"] / max(1, m["h"]))
            rw, rh = (h, w) if m.get("rotk", 0) % 2 else (w, h)
            out = []
            for t in times:
                try:
                    c.seek(max(0, int((t + t0) / tb)), stream=s, backward=True)
                    got = None
                    for k, f in enumerate(c.decode(s)):
                        got = f
                        ft = f.time - t0 if f.time is not None else t
                        if ft >= t - 0.05 or k > 40:
                            break
                except Exception:
                    continue
                if got is None:
                    continue
                arr = got.reformat(width=rw, height=rh, format="rgb24").to_ndarray()
                if m.get("rotk"):
                    arr = np.ascontiguousarray(np.rot90(arr, m["rotk"]))
                img = rgb_to_qimage(arr)
                out.append((float(t), img))
                if len(out) == 1:
                    self.poster[m["id"]] = img
                    self.thumbs[m["id"]] = list(out)
                    self.ready.emit(m["id"])
            self.thumbs[m["id"]] = out
        finally:
            c.close()

    def thumb_at(self, mid, t):
        th = self.thumbs.get(mid)
        if not th:
            return None
        best = th[0][1]
        for tt, img in th:
            if tt <= t + 0.01:
                best = img
            else:
                break
        return best

    # ── Ton ─────────────────────────────────────────────────────────────────
    def _worker(self):
        while True:
            src, k, dn = self.q.get()
            try:
                src.chunk(k, dn, True)
            except Exception:
                pass
            self.pending.discard((id(src), k, dn))

    def request(self, src, k, dn):
        key = (id(src), k, dn)
        if key not in self.pending and k >= 0:
            self.pending.add(key)
            self.q.put((src, k, dn))

    def read(self, mid, idx, dn=False, block=True):
        src = self.sources.get(mid)
        if src is None:
            return None
        return src.read(idx, dn, block, None if block else self.request)

    def prefetch(self, proj, t, ahead=6.0, block=False):
        """Lädt den Ton der nächsten Sekunden vor (verhindert Aussetzer)."""
        for kind, c, s, e, speed in audible(proj):
            if e <= t or s >= t + ahead:
                continue
            src = self.sources.get(c["media"])
            if src is None:
                continue
            a = c["in"] + max(0.0, t - s) * speed
            b = c["in"] + (min(e, t + ahead) - s) * speed
            for k in range(int(a * SR) // AudioSource.CH, int(b * SR) // AudioSource.CH + 1):
                if block:
                    src.chunk(k, c.get("denoise", False), True)
                else:
                    with src.clock:
                        have = (k, c.get("denoise", False)) in src.cache
                    if not have:
                        self.request(src, k, c.get("denoise", False))

    def image_array(self, media, w, h):
        key = (media["id"], w, h)
        with self.lock:
            if key in self._img_cache:
                self._img_cache.move_to_end(key)
                return self._img_cache[key]
            full = self._img_full.get(media["id"])
            if full is None:
                full = QImage(media["path"]).convertToFormat(QImage.Format_RGB888)
                self._img_full[media["id"]] = full
            arr = qimage_to_rgb(full.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
            self._img_cache[key] = arr
            if len(self._img_cache) > 12:
                self._img_cache.popitem(last=False)
            return arr


class VideoDecoder:
    def __init__(self, path, rotk=0):
        self.c = av.open(str(path))
        self.s = _real_video_stream(self.c)
        self.s.thread_type = "AUTO"
        self.tb = float(self.s.time_base)
        self.t0 = float(self.s.start_time * self.s.time_base) if self.s.start_time else 0.0
        self.rotk = rotk
        self.gen = None
        self.cur = self.nxt = None
        self.cur_t = self.nxt_t = 0.0
        self.cache_key = None
        self.cache_arr = None
        self.eof = False

    def close(self):
        try:
            self.c.close()
        except Exception:
            pass

    def _ftime(self, f):
        if f.time is not None:
            return f.time - self.t0
        return (f.pts or 0) * self.tb - self.t0

    def _seek(self, t):
        self.c.seek(max(0, int((t + self.t0) / self.tb)), stream=self.s, backward=True)
        self.gen = self.c.decode(self.s)
        self.cur = self.nxt = None
        self.eof = False

    def get(self, t, w, h):
        if self.gen is None or self.cur is None or t < self.cur_t - 1e-3 or t > self.cur_t + 2.5:
            self._seek(t)
        while not self.eof:
            if self.nxt is None:
                try:
                    f = next(self.gen)
                except Exception:
                    self.eof = True
                    break
                self.nxt, self.nxt_t = f, self._ftime(f)
            if self.cur is None or self.nxt_t <= t + 1e-4:
                self.cur, self.cur_t = self.nxt, self.nxt_t
                self.nxt = None
            else:
                break
        if self.cur is None:
            return None
        key = (id(self.cur), self.cur_t, w, h)
        if key == self.cache_key:
            return self.cache_arr
        rw, rh = (h, w) if self.rotk % 2 else (w, h)
        arr = self.cur.reformat(width=rw, height=rh, format="rgb24").to_ndarray()
        if self.rotk:
            arr = np.ascontiguousarray(np.rot90(arr, self.rotk))
        self.cache_key, self.cache_arr = key, arr
        return arr


def source_frame(media, t, max_side=1920):
    """Ein Originalbild aus einer Videodatei (für Standbilder)."""
    mw, mh = media["w"], media["h"]
    k = min(1.0, max_side / max(mw, mh))
    d = VideoDecoder(media["path"], media.get("rotk", 0))
    try:
        arr = d.get(max(0.0, min(t, media["duration"] - 0.05)), _even(mw * k), _even(mh * k))
    finally:
        d.close()
    return None if arr is None else rgb_to_qimage(arr)


# ════════════════════════════════════════════════════════════════════════════
#  Rendering
# ════════════════════════════════════════════════════════════════════════════
_scan_cache = {}


def _scanlines(W, H):
    key = (W, H)
    if key not in _scan_cache:
        img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        step = max(2, H // 240)
        for y in range(0, H, step * 2):
            p.fillRect(0, y, W, step, QColor(0, 0, 0, 55))
        p.end()
        _scan_cache.clear()
        _scan_cache[key] = img
    return _scan_cache[key]


def _box_blur(a, r, passes=3):
    for _ in range(passes):
        for axis in (0, 1):
            pad = [(0, 0)] * 3
            pad[axis] = (r, r)
            ap = np.pad(a, pad, mode="edge")
            cs = np.cumsum(ap, axis=axis, dtype=np.float32)
            cs = np.concatenate([np.zeros_like(np.take(cs, [0], axis=axis)), cs], axis=axis)
            n = a.shape[axis]
            a = (np.take(cs, np.arange(2 * r + 1, n + 2 * r + 1), axis=axis)
                 - np.take(cs, np.arange(0, n), axis=axis)) / (2 * r + 1)
    return a


def blurred_bg(qimg, W, H):
    tw = 96
    th = max(8, int(tw * H / max(1, W)))
    small = qimg.scaled(tw, th, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    arr = _box_blur(qimage_to_rgb(small).astype(np.float32), 3)
    return rgb_to_qimage(np.clip(arr, 0, 255).astype(np.uint8))


def text_layout(tc, W, H):
    k = H / 1080
    font = QFont(tc.get("font", "Segoe UI"))
    font.setPixelSize(max(1, int(tc.get("size", 96) * k)))
    font.setBold(tc.get("bold", True))
    font.setItalic(tc.get("italic", False))
    fm = QFontMetricsF(font)
    lines = (tc.get("text") or " ").split("\n")
    lh = fm.height() * 1.05
    widths = [fm.horizontalAdvance(l) for l in lines]
    return font, fm, lines, widths, lh, (max(widths) if widths else 0), lh * len(lines)


def draw_text(p: QPainter, tc, t, W, H, rects=None, force=False):
    local = t - tc["start"]
    dur = tc["dur"]
    if not force and not (0 <= local < dur):
        return
    k = H / 1080
    font, fm, lines, widths, lh, maxw, total = text_layout(tc, W, H)
    text_lines = lines
    opacity, scale, dy = 1.0, 1.0, 0.0
    if not force:
        ain, aout = min(0.4, dur / 3), min(0.35, dur / 3)
        a = tc.get("anim_in", "none")
        pin = local / ain if ain > 0 else 1
        if a == "fade":
            opacity *= ease(pin)
        elif a == "pop":
            scale *= 0.5 + 0.5 * back(pin)
            opacity *= min(1, pin * 2.5)
        elif a == "slide":
            dy += (1 - ease(pin)) * 0.07 * H
            opacity *= ease(pin)
        elif a == "type":
            full = "\n".join(lines)
            span_ = max(0.05, min(dur * 0.6, 0.045 * len(full)))
            n = int(len(full) * min(1.0, local / span_))
            text_lines = (full[:n] or "").split("\n")
        b = tc.get("anim_out", "none")
        pout = (dur - local) / aout if aout > 0 else 1
        if b == "fade":
            opacity *= ease(pout)
        elif b == "pop":
            scale *= 0.6 + 0.4 * ease(pout)
            opacity *= ease(pout)
        elif b == "slide":
            dy += (1 - ease(pout)) * 0.07 * H
            opacity *= ease(pout)
    cx = W / 2 + tc.get("x", 0) * W
    cy = H / 2 + tc.get("y", 0) * H + dy
    pad = (0.32 * tc.get("size", 96) * k) if tc.get("box") else 0
    if rects is not None:
        rects[tc["id"]] = QRectF(cx - maxw / 2 - pad - 6 * k, cy - total / 2 - pad * 0.6 - 6 * k,
                                 maxw + 2 * pad + 12 * k, total + 1.2 * pad + 12 * k)
    if opacity <= 0.005:
        return
    p.save()
    p.translate(cx, cy)
    p.scale(scale, scale)
    p.setOpacity(p.opacity() * opacity)
    if tc.get("sticker"):
        p.setFont(font)
        p.setPen(QColor("#ffffff"))
        for i, line in enumerate(text_lines):
            p.drawText(QRectF(-maxw, i * lh - total / 2, 2 * maxw, lh), Qt.AlignCenter, line)
        p.restore()
        return
    path = QPainterPath()
    for i, line in enumerate(text_lines):
        w = fm.horizontalAdvance(line)
        path.addText(-w / 2, i * lh + fm.ascent() + (lh - fm.height()) / 2 - total / 2, font, line)
    if tc.get("box"):
        bc = QColor(tc.get("box_color", "#000000"))
        bc.setAlphaF(max(0.0, min(1.0, tc.get("box_alpha", 0.6))))
        p.setPen(Qt.NoPen)
        p.setBrush(bc)
        p.drawRoundedRect(QRectF(-maxw / 2 - pad, -total / 2 - pad * 0.6, maxw + 2 * pad, total + 1.2 * pad),
                          pad * 0.45, pad * 0.45)
    fx = tc.get("_fx", 1.0)
    if tc.get("shadow"):
        p.fillPath(path.translated(3 * k * fx, 5 * k * fx), QColor(0, 0, 0, 120))
    glow = tc.get("glow")
    if glow:
        for wdt, a in ((30, 0.10), (19, 0.16), (10, 0.3)):
            gc = QColor(glow)
            gc.setAlphaF(a)
            p.strokePath(path, QPen(gc, wdt * k * fx, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    sw = tc.get("stroke_w", 0)
    if sw > 0:
        p.strokePath(path, QPen(QColor(tc.get("stroke", "#000000")), sw * 2 * k, Qt.SolidLine,
                                Qt.RoundCap, Qt.RoundJoin))
    p.fillPath(path, QColor(tc.get("color", "#ffffff")))
    p.restore()


class Renderer:
    def __init__(self, store: MediaStore, max_decoders=8):
        self.store = store
        self.decoders: OrderedDict = OrderedDict()
        self.max_decoders = max_decoders
        self.rects: dict[str, QRectF] = {}

    def close(self):
        for d in self.decoders.values():
            d.close()
        self.decoders.clear()

    def _decoder(self, key, media):
        d = self.decoders.get(key)
        if d is None:
            d = VideoDecoder(media["path"], media.get("rotk", 0))
            self.decoders[key] = d
            while len(self.decoders) > self.max_decoders:
                _, old = self.decoders.popitem(last=False)
                old.close()
        else:
            self.decoders.move_to_end(key)
        return d

    def _frame(self, media, key, src, w, h):
        if media["kind"] == "image":
            return self.store.image_array(media, w, h)
        src = max(0.0, min(src, media["duration"] - 0.02))
        try:
            return self._decoder(key, media).get(src, w, h)
        except Exception:
            d = self.decoders.pop(key, None)
            if d:
                d.close()
            return None

    def render(self, proj, t, W, H, preview=False):
        img = QImage(W, H, QImage.Format_RGB32)
        img.fill(QColor(0, 0, 0))
        self.rects = {}
        p = QPainter(img)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        lay = layout(proj)
        idx = None
        for i, (c, s, e) in enumerate(lay):
            if s <= t < e:
                idx = i
                break
        if idx is None and lay and abs(t - lay[-1][2]) < 1e-3:
            idx = len(lay) - 1
        if idx is not None:
            A = None
            td = trans_dur(proj, lay, idx)
            if td and t >= lay[idx][2] - td / 2:
                A, B, pr = idx, idx + 1, (t - (lay[idx][2] - td / 2)) / td
            else:
                td = trans_dur(proj, lay, idx - 1)
                if td and t < lay[idx][1] + td / 2:
                    A, B, pr = idx - 1, idx, (t - (lay[idx][1] - td / 2)) / td
            if A is None:
                self._layer(p, proj, lay[idx], t, W, H)
            else:
                self._transition(p, proj, lay[A], lay[B], t, W, H, max(0.0, min(1.0, pr)))
        for c in proj.get("overlay", []):
            s = c["start"]
            e = s + clip_len(c)
            if s <= t < e:
                self._layer(p, proj, (c, s, e), t, W, H, overlay=True)
        for tc in proj["text"]:
            draw_text(p, tc, t, W, H, self.rects)
        p.end()
        return img

    def _transition(self, p, proj, la, lb, t, W, H, pr):
        typ = la[0]["trans"]["type"]
        e = ease_io(pr)
        if typ == "fade":
            self._layer(p, proj, la, t, W, H)
            self._layer(p, proj, lb, t, W, H, alpha=e)
        elif typ in ("black", "white", "flash"):
            col = QColor(0, 0, 0) if typ == "black" else QColor(255, 255, 255)
            if typ == "flash":
                self._layer(p, proj, la if pr < 0.5 else lb, t, W, H)
                amt = 1 - abs(pr - 0.5) * 2
            elif pr < 0.5:
                self._layer(p, proj, la, t, W, H)
                amt = pr * 2
            else:
                self._layer(p, proj, lb, t, W, H)
                amt = (1 - pr) * 2
            col.setAlphaF(max(0.0, min(1.0, amt)))
            p.fillRect(0, 0, W, H, col)
        elif typ == "slide_l":
            self._layer(p, proj, la, t, W, H, dx=-e * W)
            self._layer(p, proj, lb, t, W, H, dx=(1 - e) * W)
        elif typ == "slide_up":
            self._layer(p, proj, la, t, W, H, dy=-e * H)
            self._layer(p, proj, lb, t, W, H, dy=(1 - e) * H)
        elif typ == "zoom":
            self._layer(p, proj, la, t, W, H, scale=1 + e * 0.6)
            self._layer(p, proj, lb, t, W, H, alpha=e, scale=0.85 + 0.15 * e)
        elif typ == "wipe":
            self._layer(p, proj, la, t, W, H)
            p.save()
            p.setClipRect(QRectF(0, 0, W * e, H))
            self._layer(p, proj, lb, t, W, H)
            p.restore()
        elif typ == "spin":
            self._layer(p, proj, la, t, W, H, rot=e * 120, scale=1 - 0.6 * e, alpha=1 - e)
            self._layer(p, proj, lb, t, W, H, rot=(e - 1) * 120, scale=0.4 + 0.6 * e, alpha=e)
        else:
            self._layer(p, proj, la if pr < 0.5 else lb, t, W, H)

    def _layer(self, p, proj, lay_item, t, W, H, alpha=1.0, dx=0.0, dy=0.0, scale=1.0, rot=0.0, overlay=False):
        c, start, end = lay_item
        media = proj["media"].get(c["media"])
        if not media:
            return
        local = t - start
        dur = end - start
        a = alpha * c.get("opacity", 1.0)
        if c.get("fade_in", 0) > 0:
            a *= max(0.0, min(1.0, local / c["fade_in"]))
        if c.get("fade_out", 0) > 0:
            a *= max(0.0, min(1.0, (end - t) / c["fade_out"]))
        if a <= 0.003:
            return
        src = c["in"] + local * c.get("speed", 1.0)
        mw, mh = max(1, media["w"]), max(1, media["h"])
        es, edx, edy = effect_transform(c, local, dur, W, H)
        s0 = min(W / mw, H / mh)
        sc = c.get("scale", 1.0) * es * scale
        disp_w, disp_h = mw * s0 * sc, mh * s0 * sc
        dw = _even(min(mw, max(2, disp_w)))
        dh = _even(min(mh, max(2, disp_h)))
        if c.get("effect") == "blur_in":
            bf = max(1.0, 18 * (1 - ease(local / 0.8)))
            dw, dh = _even(max(2, dw / bf)), _even(max(2, dh / bf))
        arr = self._frame(media, c["id"], src, dw, dh)
        if arr is None:
            return
        arr = frame_effect(apply_color(arr, c), c, local)
        ck = c.get("chroma") or {}
        qimg = rgb_to_qimage(chroma_key(arr, ck) if ck.get("on") else arr)
        p.save()
        p.setClipRect(QRectF(dx, dy, W, H), Qt.IntersectClip)
        p.setOpacity(p.opacity() * a)
        if not overlay:
            bg = proj.get("bg", "blur")
            if bg == "blur":
                small = blurred_bg(rgb_to_qimage(arr[..., :3]) if ck.get("on") else qimg, W, H)
                sw, sh = small.width(), small.height()
                cover = max(W / sw, H / sh) * 1.04
                p.drawImage(QRectF(W / 2 - sw * cover / 2 + dx, H / 2 - sh * cover / 2 + dy, sw * cover,
                                   sh * cover), small)
                p.fillRect(QRectF(dx, dy, W, H), QColor(0, 0, 0, 70))
            elif bg == "color":
                p.fillRect(QRectF(dx, dy, W, H), QColor(proj.get("bg_color", "#000000")))
            else:
                p.fillRect(QRectF(dx, dy, W, H), QColor(0, 0, 0))
        cx = W / 2 + c.get("x", 0) * W + dx + edx
        cy = H / 2 + c.get("y", 0) * H + dy + edy
        p.translate(cx, cy)
        p.rotate(c.get("rot", 0) + rot)
        if c.get("flip"):
            p.scale(-1, 1)
        mode = BLENDS.get(c.get("blend", "normal"), BLENDS["normal"])[1]
        p.setCompositionMode(mode)
        p.drawImage(QRectF(-disp_w / 2, -disp_h / 2, disp_w, disp_h), qimg)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.resetTransform()
        self.rects[c["id"]] = QRectF(cx - disp_w / 2, cy - disp_h / 2, disp_w, disp_h)
        vig = c.get("adj", {}).get("vignette", 0)
        if vig > 0 and not overlay:
            g = QRadialGradient(QPointF(W / 2 + dx, H / 2 + dy), math.hypot(W, H) / 2)
            g.setColorAt(0.35, QColor(0, 0, 0, 0))
            g.setColorAt(1.0, QColor(0, 0, 0, int(min(1, vig) * 235)))
            p.fillRect(QRectF(dx, dy, W, H), g)
        eff = c.get("effect", "none")
        if eff == "vhs":
            p.drawImage(QPointF(dx, dy), _scanlines(W, H))
        elif eff == "flash" and local < 0.4:
            p.fillRect(QRectF(dx, dy, W, H), QColor(255, 255, 255, int(255 * (1 - local / 0.4))))
        p.restore()


# ════════════════════════════════════════════════════════════════════════════
#  Audio-Mix
# ════════════════════════════════════════════════════════════════════════════
def audible(proj):
    """Alle Clips mit Ton: (art, clip, start, ende, tempo)."""
    res = []
    media = proj["media"]
    if not proj.get("mute_video"):
        for c, s, e in layout(proj):
            m = media.get(c["media"])
            if m and m.get("has_audio") and not c.get("mute") and c.get("volume", 1) > 0:
                res.append(("video", c, s, e, c.get("speed", 1.0)))
    for c in proj.get("overlay", []):
        m = media.get(c["media"])
        if m and m.get("has_audio") and not c.get("mute") and c.get("volume", 1) > 0:
            res.append(("overlay", c, c["start"], c["start"] + clip_len(c), c.get("speed", 1.0)))
    for c in proj["audio"]:
        if c.get("volume", 1) > 0:
            res.append(("audio", c, c["start"], c["start"] + c["out"] - c["in"], 1.0))
    return res


def mix_audio(proj, store: MediaStore, t0, n, block=True):
    out = np.zeros((n, 2), np.float32)
    t1 = t0 + n / SR
    for kind, c, start, end, speed in audible(proj):
        if end <= t0 or start >= t1:
            continue
        i0 = max(0, int(math.ceil((start - t0) * SR)))
        i1 = min(n, int((end - t0) * SR))
        if i1 <= i0:
            continue
        tl = t0 + np.arange(i0, i1) / SR
        local = tl - start
        idx = ((c["in"] + local * speed) * SR).astype(np.int64)
        valid = idx >= 0
        if not valid.any():
            continue
        seg = np.zeros((len(tl), 2), np.float32)
        data = store.read(c["media"], idx[valid], c.get("denoise", False), block)
        if data is None:
            continue
        seg[valid] = data
        g = np.full(len(tl), c.get("volume", 1.0), np.float32)
        g *= np.clip(local / max(c.get("fade_in", 0), 0.006), 0, 1)
        g *= np.clip((end - tl) / max(c.get("fade_out", 0), 0.006), 0, 1)
        out[i0:i1] += seg * g[:, None]
    np.clip(out, -1.0, 1.0, out=out)
    return out


class Player(QObject):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.proj = None
        self.pos = 0.0
        self.playing = False
        self.stream = None
        self._ref = None
        self._last_prefetch = 0.0
        self.gain = 1.0

    def play(self):
        if self.playing or self.proj is None:
            return
        if self.pos >= duration(self.proj) - 0.03:
            self.pos = 0.0
        try:
            self.store.prefetch(self.proj, self.pos, 1.5, block=True)
        except Exception:
            pass
        self.playing = True
        try:
            import sounddevice as sd
            self.stream = sd.OutputStream(samplerate=SR, channels=2, dtype="float32",
                                          blocksize=1024, latency="high", callback=self._cb)
            self.stream.start()
            self._ref = None
        except Exception:
            self.stream = None
            self._ref = (time.monotonic(), self.pos)

    def _cb(self, out, frames, t, status):
        if not self.playing:
            out.fill(0)
            return
        try:
            out[:] = np.clip(mix_audio(self.proj, self.store, self.pos, frames, block=False) * self.gain, -1, 1)
        except Exception:
            out.fill(0)
        self.pos += frames / SR

    def tick(self):
        """Regelmäßig aus dem GUI-Thread aufrufen: lädt den kommenden Ton vor."""
        now = time.monotonic()
        if self.playing and now - self._last_prefetch > 0.25:
            self._last_prefetch = now
            try:
                self.store.prefetch(self.proj, self.current(), 8.0)
            except Exception:
                pass

    def pause(self):
        self.playing = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        self.pos = self.current()
        self._ref = None

    def current(self):
        if self.playing and self._ref is not None:
            return self._ref[1] + time.monotonic() - self._ref[0]
        return self.pos

    def seek(self, t):
        self.pos = max(0.0, t)
        if self._ref is not None:
            self._ref = (time.monotonic(), self.pos)
        try:
            self.store.prefetch(self.proj, self.pos, 3.0)
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════════
#  Auto-Untertitel (faster-whisper, läuft lokal)
# ════════════════════════════════════════════════════════════════════════════
WHISPER_MODELS = {"base": ("Schnell", "Systran/faster-whisper-base", 145),
                  "small": ("Genau", "Systran/faster-whisper-small", 465)}
WHISPER_FILES = ("config.json", "tokenizer.json", "vocabulary.txt", "model.bin")


def whisper_available():
    try:
        import ctranslate2  # noqa: F401
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def model_ready(root, size):
    d = Path(root) / size
    return all((d / f).exists() for f in WHISPER_FILES)


def download_model(root, size, progress=None, cancel=lambda: False):
    d = Path(root) / size
    d.mkdir(parents=True, exist_ok=True)
    repo = WHISPER_MODELS[size][1]
    for f in WHISPER_FILES:
        dest = d / f
        if dest.exists():
            continue
        tmp = dest.with_suffix(dest.suffix + ".part")
        req = urllib.request.Request(f"https://huggingface.co/{repo}/resolve/main/{f}",
                                     headers={"User-Agent": "NeonCut"})
        with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as out:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                if cancel():
                    raise RuntimeError("Abgebrochen")
                buf = r.read(1 << 16)
                if not buf:
                    break
                out.write(buf)
                done += len(buf)
                if progress and f == "model.bin" and total:
                    progress(done / total)
        tmp.replace(dest)
    return d


def caption_lines(segs, max_chars=32, max_dur=3.0):
    lines = []
    for s, e, text, words in segs:
        if not words:
            if text:
                lines.append([s, e, text])
            continue
        cur, cs = [], None
        for ws, we, w in words:
            w = w.strip()
            if not w:
                continue
            if cs is None:
                cs = ws
            cand = " ".join([x[2] for x in cur] + [w])
            if cur and (len(cand) > max_chars or we - cs > max_dur or cur[-1][2][-1:] in ".!?"):
                lines.append([cs, cur[-1][1], " ".join(x[2] for x in cur)])
                cur, cs = [], ws
            cur.append((ws, we, w))
        if cur:
            lines.append([cs, cur[-1][1], " ".join(x[2] for x in cur)])
    for i in range(len(lines) - 1):
        if 0 < lines[i + 1][0] - lines[i][1] < 0.35:
            lines[i][1] = lines[i + 1][0]
    return [tuple(l) for l in lines if l[1] - l[0] > 0.05]


class CaptionJob(QThread):
    status = Signal(str, float)
    finished_ok = Signal(bool, str, list)

    def __init__(self, root, size, items, language):
        """items: Liste (media_pfad, src_in, src_out, timeline_start, tempo)"""
        super().__init__()
        self.root, self.size, self.items, self.language = root, size, items, language
        self.cancel = False

    def run(self):
        try:
            if not model_ready(self.root, self.size):
                self.status.emit("Lade Spracherkennungs-Modell herunter (einmalig) …", 0.0)
                download_model(self.root, self.size, lambda f: self.status.emit(
                    f"Lade Modell herunter … {f:.0%}", f * 0.3), lambda: self.cancel)
            self.status.emit("Starte Spracherkennung …", 0.3)
            from faster_whisper import WhisperModel
            model = WhisperModel(str(Path(self.root) / self.size), device="cpu", compute_type="int8",
                                 cpu_threads=max(2, (os.cpu_count() or 4) - 1))
            total = sum(max(0.01, b - a) for _, a, b, _, _ in self.items)
            done = 0.0
            result, lang = [], None
            for path, a, b, tl_start, speed in self.items:
                audio = decode_range(path, a, b)
                if not len(audio) or self.cancel:
                    done += b - a
                    continue
                segs, info = model.transcribe(audio, language=self.language, word_timestamps=True,
                                              vad_filter=False, beam_size=5,
                                              condition_on_previous_text=False)
                lang = lang or info.language
                raw = []
                for s in segs:
                    if self.cancel:
                        break
                    raw.append((s.start, s.end, s.text.strip(),
                                [(w.start, w.end, w.word) for w in (s.words or [])]))
                    self.status.emit(f"Erkenne Sprache … „{s.text.strip()[:40]}“",
                                     0.3 + 0.7 * min(1.0, (done + s.end) / total))
                for s, e, text in caption_lines(raw):
                    result.append((tl_start + s / speed, tl_start + e / speed, text))
                done += b - a
            if self.cancel:
                self.finished_ok.emit(False, "Abgebrochen", [])
            else:
                self.finished_ok.emit(True, lang or "", result)
        except Exception as e:
            self.finished_ok.emit(False, str(e), [])


# ════════════════════════════════════════════════════════════════════════════
#  Export
# ════════════════════════════════════════════════════════════════════════════
class ExportJob(QThread):
    progress = Signal(float, float, QImage)
    finished_ok = Signal(bool, str)

    def __init__(self, proj, store, path, W, H, fps, quality, encoder):
        super().__init__()
        self.proj = copy.deepcopy(proj)
        self.store, self.path = store, str(path)
        self.W, self.H, self.fps = W, H, fps
        self.quality, self.encoder = quality, encoder
        self.cancel = False
        self.used_encoder = encoder

    def run(self):
        order = ["h264_nvenc", "libx264"] if self.encoder == "auto" else [self.encoder]
        if self.encoder == "h264_nvenc":
            order.append("libx264")
        last = ""
        for codec in order:
            try:
                ok = self._export(codec)
                self.used_encoder = codec
                if ok:
                    self.finished_ok.emit(True, self.path)
                else:
                    Path(self.path).unlink(missing_ok=True)
                    self.finished_ok.emit(False, "Export abgebrochen")
                return
            except Exception as e:
                last = str(e)
                Path(self.path).unlink(missing_ok=True)
                if self.cancel:
                    break
        self.finished_ok.emit(False, f"Export fehlgeschlagen: {last}")

    def _export(self, codec):
        proj, fps, W, H = self.proj, self.fps, self.W, self.H
        total = max(duration(proj), 1 / fps)
        nframes = max(1, int(round(total * fps)))
        rend = Renderer(self.store, max_decoders=6)
        crf = {"standard": 23, "high": 19, "max": 15}[self.quality]
        out = av.open(self.path, "w")
        try:
            vs = out.add_stream(codec, rate=fps)
            vs.width, vs.height = W, H
            vs.pix_fmt = "yuv420p"
            if codec == "libx264":
                vs.options = {"crf": str(crf), "preset": "slow" if self.quality == "max" else "medium"}
            else:
                vs.options = {"preset": "p5", "rc": "vbr", "cq": str(crf + 2), "b": "0"}
            ast = out.add_stream("aac", rate=SR)
            try:
                ast.layout = "stereo"
            except Exception:
                pass
            ast.bit_rate = 192000
            apos = 0
            fsize = 1024
            t_start = time.monotonic()
            for i in range(nframes):
                if self.cancel:
                    return False
                img = rend.render(proj, i / fps, W, H)
                vf = av.VideoFrame.from_ndarray(qimage_to_rgb(img), format="rgb24")
                vf.pts = i
                vf.time_base = Fraction(1, fps)
                for pkt in vs.encode(vf):
                    out.mux(pkt)
                target = int((i + 1) / fps * SR)
                while apos + fsize <= target:
                    chunk = mix_audio(proj, self.store, apos / SR, fsize, block=True)
                    af = av.AudioFrame.from_ndarray(np.ascontiguousarray(chunk.T), format="fltp", layout="stereo")
                    af.sample_rate = SR
                    af.pts = apos
                    af.time_base = Fraction(1, SR)
                    for pkt in ast.encode(af):
                        out.mux(pkt)
                    apos += fsize
                if i % 6 == 0 or i == nframes - 1:
                    el = time.monotonic() - t_start
                    frac = (i + 1) / nframes
                    eta = el / frac * (1 - frac) if frac > 0 else 0
                    self.progress.emit(frac, eta, img.scaledToWidth(480, Qt.SmoothTransformation))
            for pkt in vs.encode(None):
                out.mux(pkt)
            for pkt in ast.encode(None):
                out.mux(pkt)
        finally:
            out.close()
            rend.close()
        return True
