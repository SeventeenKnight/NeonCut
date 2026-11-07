"""
NeonCut – Videoschnitt für Windows im NeonBoard-Stil.

Alles gratis, ohne Wasserzeichen: Export bis 4K/60 fps (auch per NVIDIA-GPU), Auto-Untertitel,
Overlay mit Greenscreen, Filter, Effekte, Übergänge, animierte Texte & Sticker, Rauschentfernung …
"""
from __future__ import annotations

import copy
import ctypes
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QDrag, QFont, QFontDatabase, QFontMetrics, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QPolygonF)
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QPlainTextEdit, QProgressBar, QPushButton,
                               QScrollArea, QScrollBar, QSlider, QSplitter, QStackedWidget, QVBoxLayout,
                               QWidget)

import engine as E
from ui_kit import (C_ACCENT, C_AUDIO, C_BG, C_BORDER, C_BORDER2, C_MUTED, C_SIDE, C_SURF2, C_TEXT,
                    C_TEXTCLIP, C_VIDEO, STYLE, Card, DialogBase, Dim, Flat, Segmented, SliderField, Surface,
                    Swatches, Toast, Toggle, alpha, app_icon_pixmap, draw_icon, fmt_time, font, icon,
                    icon_button, label, make_anim, make_arrow_png, mix, row, run_anim, styled_menu)

APP_NAME = "NeonCut"
VERSION = "1.1.0"
DATA = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
AUTOSAVE = DATA / "autosave.neoncut"
SETTINGS = DATA / "settings.json"
MODELS = DATA / "models"
FRAMES = DATA / "frames"
MIME = "application/x-neoncut-media"
C_OVERLAY = "#f59e0b"

ASPECT_LABELS = [("16:9", "16:9  ·  YouTube"), ("9:16", "9:16  ·  TikTok, Reels, Shorts"),
                 ("1:1", "1:1  ·  Instagram"), ("4:5", "4:5  ·  Instagram hoch"), ("21:9", "21:9  ·  Kino")]
ANIM_IN = [("none", "Keine"), ("fade", "Einblenden"), ("pop", "Pop"), ("slide", "Hochgleiten"),
           ("type", "Schreibmaschine")]
ANIM_OUT = [("none", "Keine"), ("fade", "Ausblenden"), ("pop", "Schrumpfen"), ("slide", "Runtergleiten")]
FONTS = ["Segoe UI", "Segoe UI Black", "Segoe UI Light", "Segoe UI Semibold", "Bahnschrift", "Impact",
         "Arial", "Arial Black", "Verdana", "Trebuchet MS", "Georgia", "Times New Roman", "Courier New",
         "Consolas", "Comic Sans MS", "Segoe Script", "Segoe Print", "Ink Free", "Gabriola", "Segoe UI Emoji"]
P_MEDIA, P_TEXT, P_STICKER, P_EFFECTS, P_FILTER, P_TRANS = range(6)


def combo(items, current, on_change):
    cb = QComboBox()
    for key, text in items:
        cb.addItem(text, key)
    i = cb.findData(current)
    cb.setCurrentIndex(max(0, i))
    cb.currentIndexChanged.connect(lambda _: on_change(cb.currentData()))
    return cb


# ════════════════════════════════════════════════════════════════════════════
#  Linke Leiste
# ════════════════════════════════════════════════════════════════════════════
class NavRail(QWidget):
    changed = Signal(int)
    ITEM = 60

    def __init__(self, items):
        super().__init__()
        self.items, self.idx, self.hover, self.hl = items, 0, -1, 0.0
        self.setFixedWidth(72)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self._a = make_anim(self, self._sh, 240)

    def _sh(self, v):
        self.hl = v
        self.update()

    def _at(self, y):
        i = int((y - 10) // self.ITEM)
        return i if 0 <= i < len(self.items) else -1

    def set_index(self, i, emit=True):
        if i < 0 or i == self.idx:
            return
        run_anim(self._a, self.hl, i)
        self.idx = i
        if emit:
            self.changed.emit(i)

    def mousePressEvent(self, e):
        self.set_index(self._at(e.position().y()))

    def mouseMoveEvent(self, e):
        h = self._at(e.position().y())
        if h != self.hover:
            self.hover = h
            self.update()

    def leaveEvent(self, e):
        self.hover = -1
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(C_SIDE))
        p.fillRect(self.width() - 1, 0, 1, self.height(), QColor(C_BORDER))
        p.setPen(Qt.NoPen)
        p.setBrush(alpha(C_ACCENT, 0.16))
        p.drawRoundedRect(QRectF(8, 10 + self.hl * self.ITEM + 3, self.width() - 17, self.ITEM - 6), 10, 10)
        p.setFont(font(11, QFont.DemiBold, self.font()))
        for i, (ic, text) in enumerate(self.items):
            y = 10 + i * self.ITEM
            active = i == self.idx
            col = QColor(C_ACCENT) if active else (QColor(C_TEXT) if i == self.hover else QColor(C_MUTED))
            draw_icon(p, ic, QRectF(self.width() / 2 - 10, y + 11, 18, 18), col)
            p.setPen(QColor(C_TEXT) if active else col)
            p.drawText(QRectF(0, y + 32, self.width() - 1, 18), Qt.AlignCenter, text)


class PanelBase(QWidget):
    def __init__(self, title, sub):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(16, 16, 14, 12)
        self.lay.setSpacing(10)
        self.lay.addWidget(label(title, "h2"))
        s = label(sub, "muted")
        s.setWordWrap(True)
        self.lay.addWidget(s)

    def scroll_grid(self):
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        g = QGridLayout(inner)
        g.setContentsMargins(0, 0, 6, 0)
        g.setSpacing(10)
        g.setAlignment(Qt.AlignTop)
        sc.setWidget(inner)
        self.lay.addWidget(sc, 1)
        return g


class MediaTile(QWidget):
    add = Signal(str)
    menu = Signal(str, object)

    def __init__(self, app, mid):
        super().__init__()
        self.app, self.mid = app, mid
        self.hover = 0.0
        self.press_pos = None
        self.setFixedHeight(112)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Doppelklick: zur Timeline  ·  Ziehen: an eine Stelle legen  ·  Rechtsklick: Overlay …")
        self._a = make_anim(self, self._sh, 140)

    def _sh(self, v):
        self.hover = v
        self.update()

    def enterEvent(self, e):
        run_anim(self._a, self.hover, 1)

    def leaveEvent(self, e):
        run_anim(self._a, self.hover, 0)

    def _plus(self):
        return QRectF(self.width() - 32, 6, 26, 26)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self._plus().contains(e.position()):
                self.add.emit(self.mid)
                return
            self.press_pos = e.position()

    def mouseMoveEvent(self, e):
        if self.press_pos is not None and (e.buttons() & Qt.LeftButton):
            if (e.position() - self.press_pos).manhattanLength() > 8:
                self.press_pos = None
                drag = QDrag(self)
                md = QMimeData()
                md.setData(MIME, self.mid.encode())
                drag.setMimeData(md)
                pm = self.grab().scaledToWidth(110, Qt.SmoothTransformation)
                drag.setPixmap(pm)
                drag.setHotSpot(pm.rect().center())
                drag.exec(Qt.CopyAction)

    def mouseReleaseEvent(self, e):
        self.press_pos = None

    def mouseDoubleClickEvent(self, e):
        self.add.emit(self.mid)

    def contextMenuEvent(self, e):
        self.menu.emit(self.mid, e.globalPos())

    def paintEvent(self, e):
        m = self.app.proj["media"].get(self.mid)
        if not m:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(0.5, 0.5, self.width() - 1, 78)
        path = QPainterPath()
        path.addRoundedRect(r, 9, 9)
        p.save()
        p.setClipPath(path)
        p.fillRect(r, QColor(C_SURF2))
        store = self.app.store
        img = store.poster.get(self.mid)
        if img is not None:
            s = max(r.width() / img.width(), r.height() / img.height())
            w, h = img.width() * s, img.height() * s
            p.drawImage(QRectF(r.center().x() - w / 2, r.center().y() - h / 2, w, h), img)
        elif m["kind"] == "audio":
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor("#0f3d33"))
            g.setColorAt(1, QColor("#13202c"))
            p.fillRect(r, g)
            pk = store.peaks.get(self.mid)
            if pk is not None and len(pk):
                n = 40
                step = r.width() / n
                p.setPen(Qt.NoPen)
                p.setBrush(alpha(C_AUDIO, 0.8))
                for i in range(n):
                    v = float(pk[int(i / n * len(pk))])
                    hh = max(2, min(1, v * 1.6) * r.height() * 0.7)
                    p.drawRoundedRect(QRectF(r.left() + i * step + 1, r.center().y() - hh / 2, step - 2, hh), 1, 1)
            else:
                draw_icon(p, "music", QRectF(r.center().x() - 12, r.center().y() - 12, 24, 24), C_AUDIO)
        else:
            draw_icon(p, "film", QRectF(r.center().x() - 12, r.center().y() - 12, 24, 24), C_MUTED)
        if self.mid in store.loading:
            p.fillRect(r, QColor(0, 0, 0, 90))
        p.fillRect(r, QColor(255, 255, 255, int(16 * self.hover)))
        p.restore()
        p.setPen(QPen(mix(C_BORDER, C_BORDER2, self.hover), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 9, 9)
        f = font(10, QFont.DemiBold, self.font())
        p.setFont(f)
        if m["kind"] != "image":
            txt = fmt_time(m["duration"], False) if m["duration"] < 3600 else \
                f"{int(m['duration'] // 3600)}:{int(m['duration'] % 3600 // 60):02d}:{int(m['duration'] % 60):02d}"
            tw = QFontMetrics(f).horizontalAdvance(txt) + 10
            chip = QRectF(r.right() - tw - 5, r.bottom() - 21, tw, 16)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 170))
            p.drawRoundedRect(chip, 5, 5)
            p.setPen(QColor("#ffffff"))
            p.drawText(chip, Qt.AlignCenter, txt)
        kind_icon = {"video": "film", "image": "image", "audio": "music"}[m["kind"]]
        chip = QRectF(r.left() + 5, r.bottom() - 21, 20, 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(chip, 5, 5)
        draw_icon(p, kind_icon, chip.adjusted(4, 2, -4, -2), "#ffffff")
        if self.hover > 0.02:
            pr = self._plus()
            p.setOpacity(self.hover)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C_ACCENT))
            p.drawEllipse(pr)
            draw_icon(p, "plus", pr.adjusted(7, 7, -7, -7), "#ffffff")
            p.setOpacity(1)
        if self.app.media_in_use(self.mid):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C_ACCENT))
            p.drawEllipse(QRectF(r.left() + 6, r.top() + 6, 8, 8))
        p.setFont(font(12, QFont.Medium, self.font()))
        p.setPen(QColor("#c9c9d6"))
        p.drawText(QRectF(2, 84, self.width() - 4, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(p.font()).elidedText(m["name"], Qt.ElideMiddle, self.width() - 4))


class EmptyDrop(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(150)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(C_BORDER2), 1.2, Qt.DashLine))
        p.drawRoundedRect(r, 12, 12)
        draw_icon(p, "folder", QRectF(r.center().x() - 13, r.top() + 34, 26, 26), C_MUTED)
        p.setFont(font(13, QFont.DemiBold, self.font()))
        p.setPen(QColor(C_TEXT))
        p.drawText(QRectF(r.left(), r.top() + 68, r.width(), 22), Qt.AlignCenter, "Dateien hier reinziehen")
        p.setFont(font(11, QFont.Normal, self.font()))
        p.setPen(QColor(C_MUTED))
        p.drawText(QRectF(r.left(), r.top() + 90, r.width(), 20), Qt.AlignCenter, "MP4 · MOV · MKV · PNG · JPG · MP3 · WAV")


class MediaPanel(PanelBase):
    def __init__(self, app):
        super().__init__("Medien", "Doppelklick oder in die Timeline ziehen. Auf die orange Spur ziehen = Overlay.")
        self.app = app
        b = QPushButton("  Importieren")
        b.setIcon(icon("plus", "#ffffff"))
        b.setObjectName("primary")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(app.import_dialog)
        self.lay.insertWidget(2, b)
        self.grid = self.scroll_grid()
        self.empty = EmptyDrop()
        self.lay.insertWidget(3, self.empty)
        self.tiles = {}

    def refresh(self):
        ids = list(self.app.proj["media"].keys())
        if list(self.tiles.keys()) != ids:
            for t in self.tiles.values():
                t.setParent(None)
                t.deleteLater()
            self.tiles = {}
            for i, mid in enumerate(ids):
                t = MediaTile(self.app, mid)
                t.add.connect(self.app.add_media_to_timeline)
                t.menu.connect(self.app.media_menu)
                self.grid.addWidget(t, i // 2, i % 2)
                self.tiles[mid] = t
        self.empty.setVisible(not ids)
        for t in self.tiles.values():
            t.update()

    def update_tile(self, mid):
        if mid in self.tiles:
            self.tiles[mid].update()


class TextPanel(PanelBase):
    def __init__(self, app):
        super().__init__("Text", "Vorlage anklicken – der Text erscheint an der Abspielposition.")
        self.app = app
        cap = QPushButton("  Auto-Untertitel erstellen")
        cap.setIcon(icon("cc", "#ffffff"))
        cap.setObjectName("primary")
        cap.setCursor(Qt.PointingHandCursor)
        cap.clicked.connect(app.auto_captions)
        self.lay.insertWidget(2, cap)
        g = self.scroll_grid()
        keys = [k for k in E.TEXT_PRESETS if k != "caption"]
        for i, key in enumerate(keys):
            c = Card(key, E.TEXT_PRESETS[key]["label"], self._painter(key), 92)
            c.clicked.connect(app.add_text)
            g.addWidget(c, i // 2, i % 2)

    @staticmethod
    def _painter(key):
        def paint(p, r, hover):
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor("#2a2440"))
            g.setColorAt(1, QColor("#14141c"))
            p.fillRect(r, g)
            tc = E.text_clip(0, key, "Aa")
            k = 520 / max(1, tc["size"])
            tc["size"] = 520
            tc["stroke_w"] = tc.get("stroke_w", 0) * k
            tc["_fx"] = k
            tc["y"] = 0
            sc = r.height() / 1080
            p.save()
            p.translate(r.topLeft())
            p.scale(sc, sc)
            E.draw_text(p, tc, 0, r.width() / sc, 1080, force=True)
            p.restore()
        return paint


class StickerPanel(PanelBase):
    def __init__(self, app):
        super().__init__("Sticker", "Anklicken – der Sticker springt an der Abspielposition ins Bild.")
        self.app = app
        g = self.scroll_grid()
        for i, emo in enumerate(E.STICKERS):
            c = Card(emo, "", self._painter(emo), 66)
            c.clicked.connect(app.add_sticker)
            g.addWidget(c, i // 4, i % 4)

    @staticmethod
    def _painter(emo):
        def paint(p, r, hover):
            p.fillRect(r, QColor("#1a1a24"))
            f = QFont("Segoe UI Emoji")
            f.setPixelSize(int(26 + 6 * hover))
            p.setFont(f)
            p.setPen(QColor("#ffffff"))
            p.drawText(r.adjusted(0, 8, 0, 8), Qt.AlignCenter, emo)
        return paint


EFFECT_COLORS = ["#7c5cff", "#3b82f6", "#06b6d4", "#10b981", "#f59e0b", "#ef4444", "#ec4899", "#8b5cf6",
                 "#14b8a6", "#f97316"]


class EffectsPanel(PanelBase):
    def __init__(self, app):
        super().__init__("Effekte", "Wird auf den ausgewählten Video- oder Overlay-Clip angewendet.")
        self.app = app
        g = self.scroll_grid()
        self.cards = {}
        for i, (key, name) in enumerate(E.EFFECTS.items()):
            c = Card(key, name, self._painter(i, key), 86)
            c.clicked.connect(app.apply_effect)
            g.addWidget(c, i // 2, i % 2)
            self.cards[key] = c

    @staticmethod
    def _painter(i, key):
        col = QColor(EFFECT_COLORS[i % len(EFFECT_COLORS)])

        def paint(p, r, hover):
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, col.darker(160))
            g.setColorAt(1, QColor("#121218"))
            p.fillRect(r, g)
            c = r.center()
            if key == "none":
                p.setPen(QPen(QColor(C_MUTED), 1.6))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(c, 12, 12)
                p.drawLine(c + QPointF(-8, 8), c + QPointF(8, -8))
                return
            s = 1 + 0.25 * hover * math.sin(time.monotonic() * 6)
            p.setPen(Qt.NoPen)
            p.setBrush(alpha(col.lighter(130), 0.9))
            p.drawRoundedRect(QRectF(c.x() - 16 * s, c.y() - 11 * s, 32 * s, 22 * s), 5, 5)
            draw_icon(p, "sparkle", QRectF(c.x() - 7, c.y() - 7, 14, 14), "#ffffff")
        return paint

    def sync(self, effect):
        for k, c in self.cards.items():
            c.set_selected(k == effect)


class FilterPanel(PanelBase):
    def __init__(self, app):
        super().__init__("Filter", "Farblooks für den ausgewählten Clip – alle gratis.")
        self.app = app
        self.amt = SliderField("Stärke", 1.0, 0, 1, 1.0, "{:.0%}", 100)
        self.amt.changed.connect(lambda v: app.modify_sel("filter_amt", lambda c: c.__setitem__("filter_amt", v)))
        self.lay.insertWidget(2, self.amt)
        g = self.scroll_grid()
        self.cards = {}
        for i, (key, (name, _)) in enumerate(E.FILTERS.items()):
            c = Card(key, name, None, 84)
            c.clicked.connect(app.apply_filter)
            g.addWidget(c, i // 2, i % 2)
            self.cards[key] = c

    def sync(self, clip):
        self.amt.set_value(clip.get("filter_amt", 1.0) if clip else 1.0)
        for k, c in self.cards.items():
            c.set_selected(clip is not None and k == clip.get("filter", "none"))

    def set_source(self, arr):
        for k, c in self.cards.items():
            c.image = None if arr is None else E.rgb_to_qimage(
                E.apply_color(arr, {"filter": k, "filter_amt": 1.0, "adj": {}}))
            c.update()


class TransitionPanel(PanelBase):
    def __init__(self, app):
        super().__init__("Übergänge", "Für den Übergang vom ausgewählten Clip zum nächsten.")
        self.app = app
        self.dur = SliderField("Dauer", 0.6, 0.1, 2.0, 0.6, "{:.1f}", 10, " s")
        self.dur.changed.connect(app.set_transition_dur)
        self.lay.insertWidget(2, self.dur)
        allb = QPushButton("Auf alle Clips anwenden")
        allb.setCursor(Qt.PointingHandCursor)
        allb.clicked.connect(app.transition_to_all)
        self.lay.insertWidget(3, allb)
        g = self.scroll_grid()
        self.cards = {}
        for i, (key, name) in enumerate(E.TRANSITIONS.items()):
            c = Card(key, name, self._painter(key), 80)
            c.clicked.connect(app.apply_transition)
            g.addWidget(c, i // 2, i % 2)
            self.cards[key] = c

    @staticmethod
    def _painter(key):
        def paint(p, r, hover):
            a, b = QColor("#3b82f6"), QColor("#a855f7")
            t = (math.sin(time.monotonic() * 2.2) * 0.5 + 0.5) if hover > 0.05 else 0.5
            if key == "none":
                p.fillRect(r, a.darker(200))
                return
            if key in ("fade", "zoom", "spin"):
                p.fillRect(r, a.darker(150))
                c = QColor(b)
                c.setAlphaF(t)
                p.fillRect(r, c)
            elif key in ("black", "white", "flash"):
                p.fillRect(r, a.darker(150) if t < 0.5 else b.darker(130))
                c = QColor(0, 0, 0) if key == "black" else QColor(255, 255, 255)
                c.setAlphaF(1 - abs(t - 0.5) * 2)
                p.fillRect(r, c)
            elif key == "slide_up":
                p.fillRect(QRectF(r.left(), r.top(), r.width(), r.height() * (1 - t)), a.darker(150))
                p.fillRect(QRectF(r.left(), r.top() + r.height() * (1 - t), r.width(), r.height() * t), b.darker(130))
            else:
                p.fillRect(QRectF(r.left(), r.top(), r.width() * (1 - t), r.height()), a.darker(150))
                p.fillRect(QRectF(r.left() + r.width() * (1 - t), r.top(), r.width() * t, r.height()), b.darker(130))
            draw_icon(p, "transition", QRectF(r.center().x() - 10, r.center().y() - 8, 20, 16), "#ffffff")
        return paint

    def sync(self, clip):
        tr = clip.get("trans", {}) if clip else {}
        self.dur.set_value(tr.get("dur", 0.6))
        for k, c in self.cards.items():
            c.set_selected(clip is not None and k == tr.get("type", "none"))


# ════════════════════════════════════════════════════════════════════════════
#  Vorschau
# ════════════════════════════════════════════════════════════════════════════
class Preview(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.img = None
        self.rects = {}
        self.drag = None
        self.setMinimumSize(320, 200)
        self.setMouseTracking(True)

    def canvas_rect(self):
        W, H = E.canvas_size(self.app.proj["aspect"])
        r = QRectF(self.rect()).adjusted(14, 14, -14, -14)
        s = min(r.width() / W, r.height() / H)
        w, h = W * s, H * s
        return QRectF(r.center().x() - w / 2, r.center().y() - h / 2, w, h)

    def render_size(self):
        r = self.canvas_rect()
        dpr = min(1.5, self.devicePixelRatioF())
        w, h = int(r.width() * dpr), int(r.height() * dpr)
        k = min(1.0, 1280 / max(1, w), 1280 / max(1, h))
        return max(16, int(w * k) // 2 * 2), max(16, int(h * k) // 2 * 2)

    def set_image(self, img, rects):
        self.img, self.rects = img, dict(rects)
        self.update()

    def _to_canvas(self, pos):
        r = self.canvas_rect()
        if not self.img:
            return None
        return QPointF((pos.x() - r.left()) / r.width() * self.img.width(),
                       (pos.y() - r.top()) / r.height() * self.img.height())

    def _hit(self, pos):
        cp = self._to_canvas(pos)
        if cp is None:
            return None
        proj = self.app.proj
        for kind in ("text", "overlay", "video"):
            for c in reversed(proj[kind]):
                if c["id"] in self.rects and self.rects[c["id"]].contains(cp):
                    return kind, c["id"]
        return None

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or not self.img:
            return
        hit = self._hit(e.position())
        if hit:
            self.app.select(*hit)
            kind, c = E.find_clip(self.app.proj, hit[1])
            self.drag = {"id": hit[1], "start": e.position(), "x": c["x"], "y": c["y"], "moved": False}
        else:
            self.app.select(None)

    def mouseMoveEvent(self, e):
        if self.drag and (e.buttons() & Qt.LeftButton):
            r = self.canvas_rect()
            d = e.position() - self.drag["start"]
            if not self.drag["moved"] and d.manhattanLength() < 3:
                return
            self.drag["moved"] = True
            nx = self.drag["x"] + d.x() / r.width()
            ny = self.drag["y"] + d.y() / r.height()
            if abs(nx) < 0.012:
                nx = 0.0
            if abs(ny) < 0.012:
                ny = 0.0
            cid = self.drag["id"]
            self.app.modify("pos:" + cid, lambda: self._set_pos(cid, nx, ny))
        else:
            self.setCursor(Qt.SizeAllCursor if self._hit(e.position()) else Qt.ArrowCursor)

    def _set_pos(self, cid, x, y):
        _, c = E.find_clip(self.app.proj, cid)
        if c:
            c["x"], c["y"] = round(x, 4), round(y, 4)

    def mouseReleaseEvent(self, e):
        if self.drag and self.drag["moved"]:
            self.app.refresh_inspector_values()
        self.drag = None

    def wheelEvent(self, e):
        sel = self.app.sel
        if not sel or not (e.modifiers() & Qt.ControlModifier):
            return
        kind, c = E.find_clip(self.app.proj, sel[1])
        f = 1.08 if e.angleDelta().y() > 0 else 1 / 1.08
        if kind == "text":
            self.app.modify("size:" + c["id"], lambda: c.__setitem__("size", max(12, min(600, c["size"] * f))))
        elif kind in ("video", "overlay"):
            self.app.modify("scale:" + c["id"], lambda: c.__setitem__("scale", max(0.05, min(5, c["scale"] * f))))
        self.app.refresh_inspector_values()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#0a0a0e"))
        r = self.canvas_rect()
        if self.img is not None:
            p.drawImage(r, self.img)
        else:
            p.fillRect(r, QColor(0, 0, 0))
        proj = self.app.proj
        if not proj["video"] and not proj["text"] and not proj["overlay"]:
            p.setFont(font(15, QFont.DemiBold, self.font()))
            p.setPen(QColor(C_TEXT))
            p.drawText(r.adjusted(0, -12, 0, -12), Qt.AlignCenter, "Importiere Medien, um loszulegen")
            p.setFont(font(12, QFont.Normal, self.font()))
            p.setPen(QColor(C_MUTED))
            p.drawText(r.adjusted(0, 22, 0, 22), Qt.AlignCenter, "Dateien einfach ins Fenster ziehen")
        sel = self.app.sel
        if sel and self.img is not None and sel[1] in self.rects and not self.app.player.playing:
            cr = self.rects[sel[1]]
            sx, sy = r.width() / self.img.width(), r.height() / self.img.height()
            rr = QRectF(r.left() + cr.left() * sx, r.top() + cr.top() * sy, cr.width() * sx, cr.height() * sy)
            p.setClipRect(r.adjusted(-2, -2, 2, 2))
            p.setPen(QPen(QColor(C_ACCENT), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRect(rr)
            p.setBrush(QColor("#ffffff"))
            for pt in (rr.topLeft(), rr.topRight(), rr.bottomLeft(), rr.bottomRight()):
                p.drawEllipse(pt, 3.5, 3.5)


class PlayButton(QWidget):
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.playing = False
        self.hover = 0.0
        self.setFixedSize(40, 40)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Abspielen / Pause (Leertaste)")
        self._a = make_anim(self, self._sh, 140)

    def _sh(self, v):
        self.hover = v
        self.update()

    def enterEvent(self, e):
        run_anim(self._a, self.hover, 1)

    def leaveEvent(self, e):
        run_anim(self._a, self.hover, 0)

    def mousePressEvent(self, e):
        self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(mix(C_ACCENT, "#9b85ff", self.hover))
        p.drawEllipse(QRectF(2, 2, 36, 36))
        draw_icon(p, "pause" if self.playing else "play", QRectF(14 if not self.playing else 13, 13, 14, 14), "#ffffff")


# ════════════════════════════════════════════════════════════════════════════
#  Timeline
# ════════════════════════════════════════════════════════════════════════════
TRACKS = [("text", 34), ("overlay", 46), ("video", 68), ("audio", 44)]


class Timeline(QWidget):
    PAD, RULER, GAP = 18, 30, 7

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.pps = 60.0
        self.x0 = 0.0
        self.drag = None
        self.hover = None
        self.scissor_hover = False
        self.snap_x = None
        self.drop = None
        self.snapping = True
        self.scrollbar = None
        self.thumb_cache = {}
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setMinimumHeight(self.total_h())
        self.setFocusPolicy(Qt.ClickFocus)

    # ── Geometrie ───────────────────────────────────────────────────────────
    def total_h(self):
        return self.RULER + sum(h + self.GAP for _, h in TRACKS) + 10

    def track(self, kind):
        y = self.RULER + self.GAP
        for k, h in TRACKS:
            if k == kind:
                return y, h
            y += h + self.GAP
        return 0, 0

    def track_at(self, y):
        for k, _ in TRACKS:
            ty, th = self.track(k)
            if ty - self.GAP / 2 <= y <= ty + th + self.GAP / 2:
                return k
        return None

    def tx(self, t):
        return self.PAD + t * self.pps - self.x0

    def xt(self, x):
        return (x - self.PAD + self.x0) / self.pps

    def content_w(self):
        return (E.duration(self.app.proj) + 20) * self.pps + self.PAD * 2

    def update_scroll(self):
        if self.scrollbar is None:
            return
        mx = max(0, int(self.content_w() - self.width()))
        self.scrollbar.blockSignals(True)
        self.scrollbar.setRange(0, mx)
        self.scrollbar.setPageStep(max(1, self.width()))
        self.x0 = min(self.x0, mx)
        self.scrollbar.setValue(int(self.x0))
        self.scrollbar.blockSignals(False)

    def set_x0(self, v):
        self.x0 = max(0.0, float(v))
        self.update()

    def zoom(self, f, anchor_x=None):
        if anchor_x is None:
            anchor_x = self.tx(self.app.playhead)
        t = self.xt(anchor_x)
        self.pps = max(0.05, min(800.0, self.pps * f))
        self.x0 = max(0.0, t * self.pps + self.PAD - anchor_x)
        self.update_scroll()
        self.update()
        self.app.zoom_changed(self.pps)

    def fit(self):
        d = max(1.0, E.duration(self.app.proj))
        self.pps = max(0.05, min(800.0, (self.width() - self.PAD * 3) / d))
        self.x0 = 0
        self.update_scroll()
        self.update()
        self.app.zoom_changed(self.pps)

    def follow(self, t):
        x = self.tx(t)
        if x > self.width() - 40 or x < 0:
            self.x0 = max(0.0, t * self.pps - self.width() * 0.25)
            self.update_scroll()

    def resizeEvent(self, e):
        self.update_scroll()

    def scissor_rect(self):
        x = self.tx(self.app.playhead)
        return QRectF(x + 8, 4, 22, 22)

    # ── Elemente ────────────────────────────────────────────────────────────
    def items(self):
        proj = self.app.proj
        res = []
        y, h = self.track("text")
        for c in proj["text"]:
            res.append(("text", c, QRectF(self.tx(c["start"]), y, c["dur"] * self.pps, h)))
        y, h = self.track("audio")
        for c in proj["audio"]:
            res.append(("audio", c, QRectF(self.tx(c["start"]), y, (c["out"] - c["in"]) * self.pps, h)))
        y, h = self.track("overlay")
        for c in proj["overlay"]:
            res.append(("overlay", c, QRectF(self.tx(c["start"]), y, E.clip_len(c) * self.pps, h)))
        y, h = self.track("video")
        for c, s, e in E.layout(proj):
            res.append(("video", c, QRectF(self.tx(s), y, (e - s) * self.pps, h)))
        return res

    def trans_points(self):
        lay = E.layout(self.app.proj)
        y, h = self.track("video")
        return [(lay[i][0], QRectF(self.tx(lay[i][2]) - 9, y + h / 2 - 9, 18, 18)) for i in range(len(lay) - 1)]

    def hit(self, pos):
        for c, r in self.trans_points():
            if r.adjusted(-1, -1, 1, 1).contains(pos):
                return "trans", c, "body", r
        for kind, c, r in reversed(self.items()):
            if r.contains(pos):
                edge = min(8.0, r.width() / 3)
                zone = "left" if pos.x() - r.left() < edge else ("right" if r.right() - pos.x() < edge else "body")
                return kind, c, zone, r
        return None

    def snap(self, t, exclude=None):
        if not self.snapping:
            self.snap_x = None
            return t
        proj = self.app.proj
        cands = [0.0, self.app.playhead]
        for c, s, e in E.layout(proj):
            if c["id"] != exclude:
                cands += [s, e]
        for kind in ("overlay", "text", "audio"):
            for c in proj[kind]:
                if c["id"] != exclude:
                    cands += list(E.span(proj, kind, c))
        best, bd = t, 9.0
        for ct in cands:
            d = abs(ct - t) * self.pps
            if d < bd:
                best, bd = ct, d
        self.snap_x = self.tx(best) if bd < 9 else None
        return best

    # ── Maus ────────────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        pos = e.position()
        if e.button() == Qt.LeftButton and self.scissor_rect().contains(pos) and not self.app.player.playing:
            self.app.split()
            return
        hit = self.hit(pos) if pos.y() > self.RULER else None
        if e.button() == Qt.RightButton:
            if hit and hit[0] != "trans":
                self.app.select(hit[0], hit[1]["id"])
                self.app.clip_menu(e.globalPosition().toPoint())
            return
        if e.button() != Qt.LeftButton:
            return
        if hit is None:
            if pos.y() > self.RULER:
                self.app.select(None)
            self.drag = {"mode": "scrub"}
            self.app.seek(max(0.0, self.xt(pos.x())))
            return
        kind, c, zone, r = hit
        if kind == "trans":
            self.app.select("video", c["id"])
            self.app.show_panel(P_TRANS)
            return
        self.app.select(kind, c["id"])
        self.drag = {"mode": "clip", "kind": kind, "zone": zone, "clip": c, "x0": pos.x(),
                     "orig": copy.deepcopy(c), "started": False, "rect": QRectF(r)}

    def mouseMoveEvent(self, e):
        pos = e.position()
        d = self.drag
        if d is None:
            sh = self.scissor_rect().contains(pos) and not self.app.player.playing
            if sh != self.scissor_hover:
                self.scissor_hover = sh
                self.update()
            hit = self.hit(pos) if pos.y() > self.RULER else None
            if sh:
                self.setCursor(Qt.PointingHandCursor)
                self.setToolTip("Hier teilen (S)")
            elif hit is None:
                self.setCursor(Qt.ArrowCursor)
                self.setToolTip("")
            elif hit[2] in ("left", "right"):
                self.setCursor(Qt.SizeHorCursor)
            else:
                self.setCursor(Qt.PointingHandCursor)
            nh = (hit[1]["id"], hit[2]) if hit else None
            if nh != self.hover:
                self.hover = nh
                self.update()
            return
        if d["mode"] == "scrub":
            self.app.seek(max(0.0, self.xt(pos.x())))
            return
        dx = pos.x() - d["x0"]
        if not d["started"]:
            if abs(dx) < 3:
                return
            d["started"] = True
            self.app.begin_change()
        dt = dx / self.pps
        c, o, kind, zone = d["clip"], d["orig"], d["kind"], d["zone"]
        proj = self.app.proj
        if kind in ("video", "overlay"):
            media = proj["media"][c["media"]]
            is_img = media["kind"] == "image"
            sp = c.get("speed", 1.0)
            start = E.span(proj, kind, c)[0] if kind == "video" else o["start"]
            olen = (o["out"] - o["in"]) / sp
            if zone == "right":
                end = self.snap(start + olen + dt, c["id"])
                if is_img:
                    c["out"] = max(E.MIN_LEN, min(3600.0, end - start))
                else:
                    c["out"] = max(c["in"] + E.MIN_LEN * sp, min(media["duration"], c["in"] + (end - start) * sp))
            elif zone == "left":
                if kind == "overlay":
                    ns = max(0.0, min(o["start"] + olen - E.MIN_LEN, self.snap(o["start"] + dt, c["id"])))
                    dd = ns - o["start"]
                    if is_img:
                        c["start"], c["out"] = ns, o["out"] - dd
                    else:
                        dd = max(-o["in"] / sp, dd)
                        c["start"], c["in"] = o["start"] + dd, o["in"] + dd * sp
                elif is_img:
                    c["out"] = max(E.MIN_LEN, o["out"] - dt)
                else:
                    c["in"] = max(0.0, min(o["out"] - E.MIN_LEN * sp, o["in"] + dt * sp))
            elif kind == "overlay":
                ns = max(0.0, self.snap(o["start"] + dt, c["id"]))
                end = self.snap(ns + olen, c["id"])
                if self.snap_x is not None and abs(end - (ns + olen)) > 1e-6:
                    ns = max(0.0, end - olen)
                c["start"] = ns
            else:
                d["ghost_dx"] = dx
                d["insert"] = self._insert_index(c["id"], d["rect"].center().x() + dx)
        elif kind == "text":
            if zone == "body":
                c["start"] = max(0.0, self.snap(o["start"] + dt, c["id"]))
                end = self.snap(c["start"] + c["dur"], c["id"])
                if self.snap_x is not None and abs(end - (c["start"] + c["dur"])) > 1e-6:
                    c["start"] = max(0.0, end - c["dur"])
            elif zone == "left":
                ns = max(0.0, min(o["start"] + o["dur"] - E.MIN_LEN, self.snap(o["start"] + dt, c["id"])))
                c["start"], c["dur"] = ns, o["start"] + o["dur"] - ns
            else:
                c["dur"] = max(E.MIN_LEN, self.snap(o["start"] + o["dur"] + dt, c["id"]) - o["start"])
        elif kind == "audio":
            mdur = proj["media"][c["media"]]["duration"]
            if zone == "body":
                c["start"] = max(0.0, self.snap(o["start"] + dt, c["id"]))
            elif zone == "left":
                dd = max(-o["in"], min((o["out"] - o["in"]) - E.MIN_LEN, dt))
                dd = max(dd, -o["start"])
                c["in"], c["start"] = o["in"] + dd, o["start"] + dd
            else:
                end = self.snap(o["start"] + (o["out"] - o["in"]) + dt, c["id"])
                c["out"] = max(o["in"] + E.MIN_LEN, min(mdur, o["in"] + end - o["start"]))
        self.app.live_changed()

    def _insert_index(self, cid, x):
        others = [x_ for x_ in E.layout(self.app.proj) if x_[0]["id"] != cid]
        t = self.xt(x)
        acc = 0.0
        for i, (c, s, e) in enumerate(others):
            d = e - s
            if t < acc + d / 2:
                return i
            acc += d
        return len(others)

    def mouseReleaseEvent(self, e):
        d = self.drag
        self.drag = None
        self.snap_x = None
        if d and d.get("mode") == "clip" and d["started"]:
            if d["kind"] == "video" and d["zone"] == "body" and "insert" in d:
                vids = self.app.proj["video"]
                c = d["clip"]
                vids.remove(c)
                vids.insert(d["insert"], c)
            self.app.end_change()
        self.update()

    def mouseDoubleClickEvent(self, e):
        y, h = self.track("text")
        if y <= e.position().y() <= y + h and self.hit(e.position()) is None:
            self.app.seek(max(0.0, self.xt(e.position().x())))
            self.app.add_text("title")

    def wheelEvent(self, e):
        dy = e.angleDelta().y() or e.angleDelta().x()
        if e.modifiers() & Qt.ControlModifier:
            self.zoom(1.15 ** (dy / 120), e.position().x())
        else:
            self.x0 = max(0.0, min(self.x0 - dy, max(0, self.content_w() - self.width())))
            self.update_scroll()
            self.update()

    def leaveEvent(self, e):
        self.hover = None
        self.scissor_hover = False
        self.update()

    # ── Drag & Drop aus der Medienleiste ────────────────────────────────────
    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if not e.mimeData().hasFormat(MIME):
            return e.ignore()
        mid = bytes(e.mimeData().data(MIME)).decode()
        m = self.app.proj["media"].get(mid)
        if not m:
            return e.ignore()
        x = e.position().x()
        tr = self.track_at(e.position().y())
        if m["kind"] == "audio":
            self.drop = ("audio", max(0.0, self.snap(self.xt(x))))
        elif tr in ("overlay", "text"):
            self.drop = ("overlay", max(0.0, self.snap(self.xt(x))))
        else:
            self.drop = ("video", self._insert_index("", x))
        e.acceptProposedAction()
        self.update()

    def dragLeaveEvent(self, e):
        self.drop = None
        self.snap_x = None
        self.update()

    def dropEvent(self, e):
        if e.mimeData().hasFormat(MIME) and self.drop:
            mid = bytes(e.mimeData().data(MIME)).decode()
            kind, v = self.drop
            if kind == "audio":
                self.app.add_media_to_timeline(mid, t=v)
            elif kind == "overlay":
                self.app.add_overlay(mid, v)
            else:
                self.app.add_media_to_timeline(mid, index=v)
            e.acceptProposedAction()
        self.drop = None
        self.snap_x = None
        self.update()

    # ── Zeichnen ────────────────────────────────────────────────────────────
    def _thumb(self, mid, t, h):
        img = self.app.store.thumb_at(mid, t)
        if img is None:
            return None
        key = (mid, img.cacheKey(), h)
        s = self.thumb_cache.get(key)
        if s is None:
            s = img.scaledToHeight(h, Qt.SmoothTransformation)
            self.thumb_cache[key] = s
            if len(self.thumb_cache) > 800:
                self.thumb_cache.clear()
        return s

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W = self.width()
        p.fillRect(self.rect(), QColor("#101016"))
        self._ruler(p, W)
        for kind, _ in TRACKS:
            y, h = self.track(kind)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#14141b"))
            p.drawRoundedRect(QRectF(4, y, W - 8, h), 8, 8)
        p.setFont(font(11, QFont.Medium, self.font()))
        p.setPen(QColor("#4c4c5c"))
        if not self.app.proj["video"]:
            y, h = self.track("video")
            p.drawText(QRectF(self.PAD + 6, y, W, h), Qt.AlignLeft | Qt.AlignVCenter,
                       "Medien hierher ziehen, um mit dem Schneiden zu beginnen")
        if not self.app.proj["overlay"]:
            y, h = self.track("overlay")
            p.drawText(QRectF(self.PAD + 6, y, W, h), Qt.AlignLeft | Qt.AlignVCenter,
                       "Overlay: Video oder Bild hierher ziehen (Bild-in-Bild, Greenscreen)")
        sel = self.app.sel[1] if self.app.sel else None
        d = self.drag
        ghost = None
        for kind, c, r in self.items():
            if r.right() < -50 or r.left() > W + 50:
                continue
            if d and d.get("mode") == "clip" and d["clip"] is c and "ghost_dx" in d:
                ghost = (kind, c, r.translated(d["ghost_dx"], -6))
                p.setOpacity(0.35)
                self._clip(p, kind, c, r, False)
                p.setOpacity(1.0)
                continue
            self._clip(p, kind, c, r, c["id"] == sel)
        for c, r in self.trans_points():
            if -20 < r.center().x() < W + 20:
                self._trans(p, c, r)
        if d and d.get("mode") == "clip" and "insert" in d:
            others = [x_ for x_ in E.layout(self.app.proj) if x_[0]["id"] != d["clip"]["id"]]
            self._indicator(p, self.tx(sum(e_ - s_ for _, s_, e_ in others[:d["insert"]])), "video")
        if ghost:
            p.setOpacity(0.9)
            self._clip(p, *ghost, True)
            p.setOpacity(1.0)
        if self.drop:
            kind, v = self.drop
            if kind in ("audio", "overlay"):
                self._indicator(p, self.tx(v), kind)
            else:
                lay = E.layout(self.app.proj)
                self._indicator(p, self.tx(sum(e_ - s_ for _, s_, e_ in lay[:v])), "video")
        if self.snap_x is not None and d:
            p.setPen(QPen(QColor("#ffd60a"), 1, Qt.DashLine))
            p.drawLine(QPointF(self.snap_x, self.RULER), QPointF(self.snap_x, self.height()))
        x = self.tx(self.app.playhead)
        if -30 < x < W + 10:
            p.setPen(QPen(QColor("#ffffff"), 1.6))
            p.drawLine(QPointF(x, 6), QPointF(x, self.height()))
            head = QPolygonF([QPointF(x - 6, 4), QPointF(x + 6, 4), QPointF(x + 6, 14), QPointF(x, 20),
                              QPointF(x - 6, 14)])
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#ffffff"))
            p.drawPolygon(head)
            if not self.app.player.playing:
                sr = self.scissor_rect()
                p.setBrush(QColor(C_ACCENT) if self.scissor_hover else QColor("#2a2545"))
                p.setPen(QPen(QColor(C_ACCENT), 1))
                p.drawEllipse(sr)
                draw_icon(p, "scissors", sr.adjusted(5, 5, -5, -5), "#ffffff")

    def _indicator(self, p, x, kind):
        y, h = self.track(kind)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C_ACCENT))
        p.drawRoundedRect(QRectF(x - 2, y - 4, 4, h + 8), 2, 2)

    def _ruler(self, p, W):
        p.fillRect(QRectF(0, 0, W, self.RULER), QColor(C_SIDE))
        steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600]
        major = next((s for s in steps if s * self.pps >= 90), 3600)
        minor = major / (5 if major in (1, 10, 60, 600, 0.5, 5, 3600) else 4 if major in (2, 120) else
                         3 if major in (15, 30, 900, 1800) else 5)
        t0 = max(0.0, math.floor(self.xt(0) / minor) * minor)
        t1 = self.xt(W)
        p.setFont(font(10, QFont.Medium, self.font()))
        t = t0
        n = 0
        while t <= t1 and n < 2000:
            x = self.tx(t)
            is_major = abs(t / major - round(t / major)) < 1e-6
            p.setPen(QPen(QColor("#4a4a5c") if is_major else QColor("#2c2c38"), 1))
            p.drawLine(QPointF(x, self.RULER - (10 if is_major else 5)), QPointF(x, self.RULER))
            if is_major:
                p.setPen(QColor(C_MUTED))
                txt = fmt_time(t, major < 1) if t < 3600 else f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}"
                p.drawText(QRectF(x + 4, 2, 80, 16), Qt.AlignLeft | Qt.AlignVCenter, txt)
            t += minor
            n += 1
        p.fillRect(QRectF(0, self.RULER - 1, W, 1), QColor(C_BORDER))

    def _clip(self, p, kind, c, r, selected):
        proj = self.app.proj
        hov = self.hover and self.hover[0] == c["id"]
        rr = r.adjusted(1, 0, -1, 0)
        if rr.width() < 2:
            return
        path = QPainterPath()
        path.addRoundedRect(rr, 7, 7)
        p.save()
        p.setClipPath(path)
        f_lbl = font(11, QFont.DemiBold, self.font())
        if kind in ("video", "overlay"):
            m = proj["media"].get(c["media"], {})
            p.fillRect(rr, QColor("#1a2540") if kind == "video" else QColor("#3a2a10"))
            wave_h = (14 if kind == "video" else 10) if m.get("has_audio") else 0
            th = int(rr.height() - wave_h)
            tw = max(20, th * max(1, m.get("w", 16)) / max(1, m.get("h", 9)))
            x = rr.left()
            Wd = self.width()
            if x < -tw:
                x += math.floor((-tw - x) / tw) * tw
            while x < rr.right() and x < Wd:
                if x + tw > 0:
                    src = c["in"] + ((x - rr.left()) / self.pps) * c.get("speed", 1.0)
                    img = self._thumb(c["media"], src, th)
                    if img is not None:
                        p.drawImage(QPointF(x, rr.top()), img)
                x += tw
            if wave_h:
                wy = rr.bottom() - wave_h
                p.fillRect(QRectF(rr.left(), wy, rr.width(), wave_h), QColor("#0f1730") if kind == "video" else QColor("#241a08"))
                pk = self.app.store.peaks.get(c["media"])
                muted = c.get("mute") or (kind == "video" and proj.get("mute_video"))
                if pk is not None and not muted:
                    self._wave(p, pk, QRectF(rr.left(), wy + 1, rr.width(), wave_h - 2), c["in"],
                               c.get("speed", 1.0), alpha("#93c5fd" if kind == "video" else "#fcd34d", 0.75),
                               c.get("volume", 1.0))
                elif muted:
                    draw_icon(p, "mute", QRectF(rr.left() + 6, wy + 2, 12, wave_h - 4), C_MUTED)
            g = QLinearGradient(0, rr.top(), 0, rr.top() + 22)
            g.setColorAt(0, QColor(0, 0, 0, 170))
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(QRectF(rr.left(), rr.top(), rr.width(), 22), g)
            info = fmt_time(E.clip_len(c))
            if abs(c.get("speed", 1.0) - 1) > 0.01:
                info += f"  ·  {c['speed']:.2g}x"
            if abs(c.get("volume", 1.0) - 1) > 0.01 and m.get("has_audio"):
                info += f"  ·  {c['volume']:.0%}"
            if c.get("filter", "none") != "none":
                info += "  ·  " + E.FILTERS[c["filter"]][0]
            if c.get("effect", "none") != "none":
                info += "  ·  " + E.EFFECTS[c["effect"]]
            if c.get("chroma", {}).get("on"):
                info += "  ·  Greenscreen"
            p.setFont(f_lbl)
            p.setPen(QColor("#ffffff"))
            p.drawText(QRectF(rr.left() + 8, rr.top() + 2, rr.width() - 14, 16), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(f_lbl).elidedText(f"{m.get('name', '?')}   {info}", Qt.ElideRight,
                                                      int(max(0, rr.width() - 14))))
            col = QColor(C_VIDEO if kind == "video" else C_OVERLAY)
        elif kind == "text":
            col = QColor(C_TEXTCLIP)
            p.fillRect(rr, alpha(col, 0.32))
            draw_icon(p, "smile" if c.get("sticker") else ("cc" if c.get("auto") else "text"),
                      QRectF(rr.left() + 8, rr.center().y() - 6, 12, 12), "#e9d5ff")
            p.setFont(QFont("Segoe UI Emoji", 10) if c.get("sticker") else f_lbl)
            p.setPen(QColor("#f3e8ff"))
            txt = c["text"].replace("\n", " ")
            p.drawText(QRectF(rr.left() + 26, rr.top(), rr.width() - 32, rr.height()), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(p.font()).elidedText(txt, Qt.ElideRight, int(max(0, rr.width() - 32))))
        else:
            col = QColor(C_AUDIO)
            p.fillRect(rr, QColor("#0f2e28"))
            pk = self.app.store.peaks.get(c["media"])
            if pk is not None:
                self._wave(p, pk, rr.adjusted(0, 16, 0, -2), c["in"], 1.0, alpha("#34d399", 0.85), c.get("volume", 1.0))
            m = proj["media"].get(c["media"], {})
            p.setFont(f_lbl)
            p.setPen(QColor("#d1fae5"))
            name = m.get("name", "?") + (f"  ·  {c['volume']:.0%}" if abs(c.get("volume", 1) - 1) > 0.01 else "")
            p.drawText(QRectF(rr.left() + 8, rr.top() + 1, rr.width() - 14, 15), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(f_lbl).elidedText(name, Qt.ElideRight, int(max(0, rr.width() - 14))))
        p.restore()
        if selected:
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rr.adjusted(1, 1, -1, -1), 7, 7)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#ffffff"))
            hh = rr.height() * 0.5
            p.drawRoundedRect(QRectF(rr.left() + 1, rr.center().y() - hh / 2, 5, hh), 2, 2)
            p.drawRoundedRect(QRectF(rr.right() - 6, rr.center().y() - hh / 2, 5, hh), 2, 2)
        else:
            p.setPen(QPen(alpha(col, 0.9 if hov else 0.5), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rr.adjusted(0.5, 0.5, -0.5, -0.5), 7, 7)

    def _wave(self, p, pk, r, src_in, speed, col, vol):
        x0 = max(r.left(), -3.0)
        x1 = min(r.right(), float(self.width()))
        if x1 <= x0:
            return
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        x = x0 - ((x0 - r.left()) % 3)
        while x < x1:
            t = src_in + ((x - r.left()) / self.pps) * speed
            k0 = int(t * 50)
            k1 = max(k0 + 1, int((t + 3 / self.pps * speed) * 50))
            if 0 <= k0 < len(pk):
                v = min(1.0, float(pk[k0:k1].max()) * vol * 1.4)
                h = max(1.0, v * r.height())
                p.drawRect(QRectF(x, r.center().y() - h / 2, 2, h))
            x += 3

    def _trans(self, p, c, r):
        typ = c.get("trans", {}).get("type", "none")
        p.save()
        p.translate(r.center())
        p.rotate(45)
        s = 7.5
        p.setPen(QPen(QColor("#ffffff") if typ != "none" else QColor(C_BORDER2), 1.2))
        p.setBrush(QColor(C_ACCENT) if typ != "none" else QColor(C_SURF2))
        p.drawRoundedRect(QRectF(-s, -s, 2 * s, 2 * s), 3, 3)
        p.restore()
        if typ == "none":
            draw_icon(p, "plus", r.adjusted(5.5, 5.5, -5.5, -5.5), C_MUTED)
        else:
            draw_icon(p, "transition", r.adjusted(4.5, 5.5, -4.5, -5.5), "#ffffff")


class TrackHeaders(QWidget):
    def __init__(self, app, tl: Timeline):
        super().__init__()
        self.app, self.tl = app, tl
        self.setFixedWidth(52)

    def mousePressEvent(self, e):
        y, h = self.tl.track("video")
        if y <= e.position().y() <= y + h:
            self.app.toggle_mute_video()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#101016"))
        p.fillRect(self.width() - 1, 0, 1, self.height(), QColor(C_BORDER))
        for kind, ic, col in (("text", "text", C_TEXTCLIP), ("overlay", "layers", C_OVERLAY),
                              ("video", "film", C_VIDEO), ("audio", "music", C_AUDIO)):
            y, h = self.tl.track(kind)
            r = QRectF(8, y, self.width() - 16, h)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#17171f"))
            p.drawRoundedRect(r, 8, 8)
            draw_icon(p, ic, QRectF(r.center().x() - 7, r.center().y() - 7 - (8 if kind == "video" else 0), 14, 14), col)
            if kind == "video":
                muted = self.app.proj.get("mute_video")
                draw_icon(p, "mute" if muted else "volume",
                          QRectF(r.center().x() - 7, r.center().y() + 4, 14, 12), "#ef4444" if muted else C_MUTED)
        self.setToolTip("Klick auf das Lautsprecher-Symbol: Originalton aller Clips an/aus")


# ════════════════════════════════════════════════════════════════════════════
#  Eigenschaften
# ════════════════════════════════════════════════════════════════════════════
class Inspector(QWidget):
    TABS = {"video": ["Basis", "Bild", "Farbe", "Audio"], "image": ["Basis", "Bild", "Farbe"],
            "overlay": ["Basis", "Bild", "Overlay", "Farbe"], "overlay_img": ["Basis", "Bild", "Overlay", "Farbe"],
            "text": ["Text", "Stil", "Animation"], "sticker": ["Sticker"], "audio": ["Audio"]}
    TITLES = {"video": "Video-Clip", "image": "Bild-Clip", "overlay": "Overlay", "overlay_img": "Overlay-Bild",
              "text": "Text", "sticker": "Sticker", "audio": "Audio"}

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setFixedWidth(330)
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(16, 16, 16, 12)
        self.v.setSpacing(10)
        self.title = label("Projekt", "h2")
        self.v.addWidget(self.title)
        self.tabs_holder = QVBoxLayout()
        self.v.addLayout(self.tabs_holder)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.v.addWidget(self.scroll, 1)
        self.tab_idx = {}
        self.fields = {}
        self.kind = None
        self.cid = None
        self.tabs = None
        self.text_edit = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C_SIDE))
        p.fillRect(0, 0, 1, self.height(), QColor(C_BORDER))

    def rebuild(self):
        sel = self.app.sel
        kind, c = E.find_clip(self.app.proj, sel[1]) if sel else (None, None)
        sub = kind
        if c is not None and kind in ("video", "overlay"):
            if self.app.proj["media"].get(c["media"], {}).get("kind") == "image":
                sub = "image" if kind == "video" else "overlay_img"
        if c is not None and kind == "text" and c.get("sticker"):
            sub = "sticker"
        if self.tabs is not None:
            self.tabs.setParent(None)
            self.tabs.deleteLater()
            self.tabs = None
        self.kind, self.cid = sub, (c["id"] if c else None)
        self.fields = {}
        self.text_edit = None
        if c is None:
            self.title.setText("Projekt")
            self._set_content(self._project())
            return
        self.title.setText(self.TITLES[sub])
        tabs = self.TABS[sub]
        idx = min(self.tab_idx.get(sub, 0), len(tabs) - 1)
        if len(tabs) > 1:
            self.tabs = Segmented(tabs, idx)
            self.tabs.changed.connect(lambda i: (self.tab_idx.__setitem__(sub, i), self.rebuild()))
            self.tabs_holder.addWidget(self.tabs)
        builder = {"Basis": self._basis, "Bild": self._bild, "Farbe": self._farbe, "Audio": self._audio,
                   "Text": self._text, "Stil": self._stil, "Animation": self._anim, "Overlay": self._overlay,
                   "Sticker": self._sticker}[tabs[idx]]
        self._set_content(builder(c))

    def _set_content(self, w):
        old = self.scroll.takeWidget()
        if old:
            old.deleteLater()
        self.scroll.setWidget(w)

    def _page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 6, 0)
        lay.setSpacing(14)
        lay.setAlignment(Qt.AlignTop)
        return w, lay

    def _slider(self, lay, key, title, get, setv, lo, hi, default, fmt="{:.0f}", factor=100, suffix=""):
        f = SliderField(title, get(), lo, hi, default, fmt, factor, suffix)
        cid = self.cid
        f.changed.connect(lambda v: self.app.modify(f"{key}:{cid}", lambda: setv(v)))
        lay.addWidget(f)
        self.fields[key] = (f, get)
        return f

    def _toggle_row(self, lay, title, desc, get, setv, key):
        t = Toggle(get())
        cid = self.cid
        t.toggled.connect(lambda on: self.app.modify(f"{key}:{cid}", lambda: setv(on)))
        h = QHBoxLayout()
        v = QVBoxLayout()
        v.setSpacing(0)
        v.addWidget(label(title, "h3"))
        if desc:
            d = label(desc, "muted")
            d.setWordWrap(True)
            v.addWidget(d)
        h.addLayout(v, 1)
        h.addWidget(t, 0, Qt.AlignTop)
        lay.addLayout(h)
        return t

    def _combo(self, lay, title, items, get, setv, key):
        lay.addWidget(label(title, "h3"))
        cid = self.cid
        cb = combo(items, get(), lambda v: self.app.modify(f"{key}:{cid}", lambda: setv(v)))
        lay.addWidget(cb)
        return cb

    def _swatch(self, lay, title, get, setv, key, allow_none=False):
        lay.addWidget(label(title, "h3"))
        cid = self.cid
        s = Swatches(get(), allow_none=allow_none)
        s.picked.connect(lambda col: self.app.modify(f"{key}:{cid}", lambda: setv(col)))
        lay.addWidget(s)

    def _button(self, lay, text, ic, cb):
        b = QPushButton("  " + text)
        if ic:
            b.setIcon(icon(ic))
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(cb)
        lay.addWidget(b)
        return b

    def refresh_values(self):
        for key, (f, get) in self.fields.items():
            try:
                f.set_value(get())
            except Exception:
                pass

    def _volume(self, lay, c):
        m = self.app.proj["media"].get(c["media"], {})
        if not m.get("has_audio"):
            return
        self._slider(lay, "volume", "Lautstärke", lambda: c["volume"],
                     lambda v: c.__setitem__("volume", v), 0, 3, 1.0, "{:.0%}", 100)
        self._toggle_row(lay, "Stumm", None, lambda: c.get("mute", False), lambda on: c.__setitem__("mute", on), "mute")

    # ── Seiten ──────────────────────────────────────────────────────────────
    def _project(self):
        w, lay = self._page()
        proj = self.app.proj
        hint = label("Wähle einen Clip in der Timeline, um ihn zu bearbeiten.", "muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addWidget(label("Format", "h3"))
        lay.addWidget(combo(ASPECT_LABELS, proj["aspect"], self.app.set_aspect))
        lay.addWidget(label("Hintergrund (wenn das Video nicht ausfüllt)", "h3"))
        lay.addWidget(combo([("blur", "Unscharf"), ("black", "Schwarz"), ("color", "Farbe")], proj["bg"],
                            lambda v: self.app.modify("bg", lambda: (proj.__setitem__("bg", v), self.rebuild()))))
        if proj["bg"] == "color":
            s = Swatches(proj.get("bg_color", "#000000"))
            s.picked.connect(lambda col: self.app.modify("bgc", lambda: proj.__setitem__("bg_color", col or "#000000")))
            lay.addWidget(s)
        info = Surface(12)
        il = QVBoxLayout(info)
        il.setContentsMargins(14, 12, 14, 12)
        il.setSpacing(4)
        il.addWidget(label("TASTENKÜRZEL", "section"))
        for k, d in (("Leertaste", "Abspielen / Pause"), ("S", "Am weißen Strich teilen"),
                     ("Q / W", "Links / rechts vom Strich löschen"), ("Entf", "Löschen"),
                     ("Strg + Z / Y", "Rückgängig / Wiederholen"), ("Strg + D", "Duplizieren"),
                     ("← / →", "Ein Bild zurück / vor"), ("Strg + Mausrad", "Timeline zoomen"),
                     ("Strg + E", "Exportieren")):
            h = QHBoxLayout()
            kl = label(k, "h3")
            kl.setFixedWidth(104)
            dl = label(d, "muted")
            dl.setWordWrap(True)
            h.addWidget(kl)
            h.addWidget(dl, 1)
            il.addLayout(h)
        lay.addWidget(info)
        return w

    def _basis(self, c):
        w, lay = self._page()
        m = self.app.proj["media"][c["media"]]
        self._volume(lay, c)
        if m["kind"] == "image":
            self._slider(lay, "dur", "Dauer", lambda: c["out"] - c["in"],
                         lambda v: c.__setitem__("out", c["in"] + v), 0.5, 30, 3.0, "{:.1f}", 10, " s")
        else:
            self._slider(lay, "speed", "Geschwindigkeit", lambda: c["speed"],
                         lambda v: c.__setitem__("speed", max(0.1, v)), 0.1, 4.0, 1.0, "{:.2f}", 100, "x")
        self._slider(lay, "opacity", "Deckkraft", lambda: c["opacity"],
                     lambda v: c.__setitem__("opacity", v), 0, 1, 1.0, "{:.0%}", 100)
        self._slider(lay, "fade_in", "Einblenden", lambda: c["fade_in"],
                     lambda v: c.__setitem__("fade_in", v), 0, 3, 0, "{:.1f}", 10, " s")
        self._slider(lay, "fade_out", "Ausblenden", lambda: c["fade_out"],
                     lambda v: c.__setitem__("fade_out", v), 0, 3, 0, "{:.1f}", 10, " s")
        self._combo(lay, "Effekt", list(E.EFFECTS.items()), lambda: c.get("effect", "none"),
                    lambda v: c.__setitem__("effect", v), "effect")
        if self.kind in ("video", "image"):
            self._combo(lay, "Übergang zum nächsten Clip", list(E.TRANSITIONS.items()),
                        lambda: c["trans"]["type"], lambda v: c["trans"].__setitem__("type", v), "trans")
            self._slider(lay, "tdur", "Übergangsdauer", lambda: c["trans"]["dur"],
                         lambda v: c["trans"].__setitem__("dur", v), 0.1, 2.0, 0.6, "{:.1f}", 10, " s")
        return w

    def _bild(self, c):
        w, lay = self._page()
        self._slider(lay, "scale", "Skalierung", lambda: c["scale"],
                     lambda v: c.__setitem__("scale", v), 0.05, 4, 1.0, "{:.0%}", 100)
        self._slider(lay, "x", "Position X", lambda: c["x"], lambda v: c.__setitem__("x", v), -1, 1, 0, "{:+.0%}", 100)
        self._slider(lay, "y", "Position Y", lambda: c["y"], lambda v: c.__setitem__("y", v), -1, 1, 0, "{:+.0%}", 100)
        self._slider(lay, "rot", "Drehung", lambda: c["rot"], lambda v: c.__setitem__("rot", v), -180, 180, 0,
                     "{:.0f}", 1, "°")
        self._toggle_row(lay, "Spiegeln", "Horizontal spiegeln", lambda: c.get("flip", False),
                         lambda on: c.__setitem__("flip", on), "flip")
        h = QHBoxLayout()
        for txt, sc in (("Einpassen", 1.0), ("Füllen", None)):
            b = QPushButton(txt)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, sc=sc: self.app.fit_clip(c["id"], sc))
            h.addWidget(b)
        lay.addLayout(h)
        lay.addWidget(label("Tipp: In der Vorschau ziehen = verschieben, Strg + Mausrad = Größe.", "muted"))
        return w

    def _overlay(self, c):
        w, lay = self._page()
        self._combo(lay, "Mischmodus", [(k, v[0]) for k, v in E.BLENDS.items()], lambda: c.get("blend", "normal"),
                    lambda v: c.__setitem__("blend", v), "blend")
        ck = c.setdefault("chroma", {"on": False, "color": "#00ff00", "tol": 0.3, "soft": 0.12})
        self._toggle_row(lay, "Greenscreen entfernen", "Macht eine Farbe durchsichtig (Chroma-Key)",
                         lambda: ck["on"], lambda on: ck.__setitem__("on", on), "chroma_on")
        self._swatch(lay, "Schlüsselfarbe", lambda: ck["color"], lambda v: ck.__setitem__("color", v or "#00ff00"),
                     "chroma_col")
        h = QHBoxLayout()
        for txt, col in (("Grün", "#00ff00"), ("Blau", "#0047ff")):
            b = QPushButton(txt)
            b.clicked.connect(lambda _=False, col=col: (self.app.modify("chroma_col:" + c["id"],
                                                                         lambda: ck.update(color=col, on=True)),
                                                         self.rebuild()))
            h.addWidget(b)
        lay.addLayout(h)
        self._slider(lay, "chroma_tol", "Toleranz", lambda: ck["tol"], lambda v: ck.__setitem__("tol", v),
                     0, 1, 0.3, "{:.0f}", 100)
        self._slider(lay, "chroma_soft", "Kante weich", lambda: ck["soft"], lambda v: ck.__setitem__("soft", v),
                     0.01, 0.6, 0.12, "{:.0f}", 100)
        return w

    def _farbe(self, c):
        w, lay = self._page()
        self._combo(lay, "Filter", [(k, v[0]) for k, v in E.FILTERS.items()], lambda: c.get("filter", "none"),
                    lambda v: c.__setitem__("filter", v), "filter")
        self._slider(lay, "filter_amt", "Filterstärke", lambda: c["filter_amt"],
                     lambda v: c.__setitem__("filter_amt", v), 0, 1, 1.0, "{:.0%}", 100)
        adj = c["adj"]
        for key, title in (("bright", "Helligkeit"), ("contrast", "Kontrast"), ("sat", "Sättigung"),
                           ("temp", "Temperatur")):
            self._slider(lay, "adj_" + key, title, lambda k=key: adj[k], lambda v, k=key: adj.__setitem__(k, v),
                         -1, 1, 0, "{:+.0f}", 100)
        self._slider(lay, "adj_vignette", "Vignette", lambda: adj["vignette"],
                     lambda v: adj.__setitem__("vignette", v), 0, 1, 0, "{:.0f}", 100)
        self._button(lay, "Farbe zurücksetzen", None, lambda: (self.app.modify("reset_color", lambda: (
            adj.update(bright=0.0, contrast=0.0, sat=0.0, temp=0.0, vignette=0.0),
            c.update(filter="none", filter_amt=1.0))), self.rebuild()))
        return w

    def _audio(self, c):
        w, lay = self._page()
        if "start" in c and "media" in c and self.kind == "audio":
            self._slider(lay, "volume", "Lautstärke", lambda: c["volume"],
                         lambda v: c.__setitem__("volume", v), 0, 3, 1.0, "{:.0%}", 100)
        else:
            self._volume(lay, c)
        self._toggle_row(lay, "Rauschen entfernen", "Brummen, Wind und Hintergrundrauschen herausfiltern",
                         lambda: c.get("denoise", False), lambda on: c.__setitem__("denoise", on), "denoise")
        if self.kind == "audio":
            self._slider(lay, "fade_in", "Einblenden", lambda: c["fade_in"],
                         lambda v: c.__setitem__("fade_in", v), 0, 5, 0, "{:.1f}", 10, " s")
            self._slider(lay, "fade_out", "Ausblenden", lambda: c["fade_out"],
                         lambda v: c.__setitem__("fade_out", v), 0, 5, 0, "{:.1f}", 10, " s")
        else:
            self._button(lay, "Ton abtrennen", "music", self.app.detach_audio)
            lay.addWidget(label("Legt den Ton als eigenen Clip auf die Musikspur.", "muted"))
        return w

    def _text(self, c):
        w, lay = self._page()
        ed = QPlainTextEdit(c["text"])
        ed.setFixedHeight(84)
        cid = c["id"]
        ed.textChanged.connect(lambda: self.app.modify("text:" + cid, lambda: c.__setitem__("text", ed.toPlainText())))
        lay.addWidget(ed)
        self.text_edit = ed
        fams = set(QFontDatabase.families())
        fonts = [(f, f) for f in FONTS if f in fams] or [("Segoe UI", "Segoe UI")]
        if c["font"] not in [f for f, _ in fonts]:
            fonts.insert(0, (c["font"], c["font"]))
        self._combo(lay, "Schriftart", fonts, lambda: c["font"], lambda v: c.__setitem__("font", v), "font")
        self._toggle_row(lay, "Fett", None, lambda: c.get("bold", True), lambda on: c.__setitem__("bold", on), "bold")
        self._toggle_row(lay, "Kursiv", None, lambda: c.get("italic", False),
                         lambda on: c.__setitem__("italic", on), "italic")
        self._slider(lay, "size", "Größe", lambda: c["size"], lambda v: c.__setitem__("size", v), 12, 400, 96,
                     "{:.0f}", 1)
        self._swatch(lay, "Farbe", lambda: c["color"], lambda v: c.__setitem__("color", v or "#ffffff"), "color")
        self._slider(lay, "x", "Position X", lambda: c["x"], lambda v: c.__setitem__("x", v), -0.5, 0.5, 0,
                     "{:+.0%}", 100)
        self._slider(lay, "y", "Position Y", lambda: c["y"], lambda v: c.__setitem__("y", v), -0.5, 0.5, 0,
                     "{:+.0%}", 100)
        self._slider(lay, "tdur", "Dauer", lambda: c["dur"], lambda v: c.__setitem__("dur", v), 0.3, 30, 3,
                     "{:.1f}", 10, " s")
        if c.get("auto"):
            self._button(lay, "Stil auf alle Untertitel übertragen", "cc", lambda: self.app.caption_style_to_all(c))
        return w

    def _sticker(self, c):
        w, lay = self._page()
        self._slider(lay, "size", "Größe", lambda: c["size"], lambda v: c.__setitem__("size", v), 40, 900, 240,
                     "{:.0f}", 1)
        self._slider(lay, "x", "Position X", lambda: c["x"], lambda v: c.__setitem__("x", v), -0.5, 0.5, 0,
                     "{:+.0%}", 100)
        self._slider(lay, "y", "Position Y", lambda: c["y"], lambda v: c.__setitem__("y", v), -0.5, 0.5, 0,
                     "{:+.0%}", 100)
        self._slider(lay, "tdur", "Dauer", lambda: c["dur"], lambda v: c.__setitem__("dur", v), 0.3, 30, 3,
                     "{:.1f}", 10, " s")
        self._combo(lay, "Animation rein", ANIM_IN[:4], lambda: c.get("anim_in", "none"),
                    lambda v: c.__setitem__("anim_in", v), "anim_in")
        self._combo(lay, "Animation raus", ANIM_OUT, lambda: c.get("anim_out", "none"),
                    lambda v: c.__setitem__("anim_out", v), "anim_out")
        return w

    def _stil(self, c):
        w, lay = self._page()
        self._swatch(lay, "Kontur", lambda: c.get("stroke", "#000000"),
                     lambda v: c.__setitem__("stroke", v or "#000000"), "stroke")
        self._slider(lay, "stroke_w", "Konturstärke", lambda: c.get("stroke_w", 0),
                     lambda v: c.__setitem__("stroke_w", v), 0, 20, 0, "{:.0f}", 1)
        self._toggle_row(lay, "Hintergrund-Kasten", "Farbiger Kasten hinter dem Text", lambda: c.get("box", False),
                         lambda on: c.__setitem__("box", on), "box")
        self._swatch(lay, "Kastenfarbe", lambda: c.get("box_color", "#000000"),
                     lambda v: c.__setitem__("box_color", v or "#000000"), "box_color")
        self._slider(lay, "box_alpha", "Kasten-Deckkraft", lambda: c.get("box_alpha", 0.6),
                     lambda v: c.__setitem__("box_alpha", v), 0, 1, 0.6, "{:.0%}", 100)
        self._swatch(lay, "Leuchten", lambda: c.get("glow") or "none", lambda v: c.__setitem__("glow", v), "glow",
                     allow_none=True)
        self._toggle_row(lay, "Schatten", None, lambda: c.get("shadow", False),
                         lambda on: c.__setitem__("shadow", on), "shadow")
        return w

    def _anim(self, c):
        w, lay = self._page()
        self._combo(lay, "Animation rein", ANIM_IN, lambda: c.get("anim_in", "none"),
                    lambda v: c.__setitem__("anim_in", v), "anim_in")
        self._combo(lay, "Animation raus", ANIM_OUT, lambda: c.get("anim_out", "none"),
                    lambda v: c.__setitem__("anim_out", v), "anim_out")
        lay.addWidget(label("Tipp: Spiel die Stelle ab, um die Animation zu sehen.", "muted"))
        return w


# ════════════════════════════════════════════════════════════════════════════
#  Dialoge
# ════════════════════════════════════════════════════════════════════════════
class ExportDialog(DialogBase):
    RES = [(720, "720p  (HD)"), (1080, "1080p  (Full HD)"), (1440, "1440p  (2K)"), (2160, "2160p  (4K)")]

    def __init__(self, app):
        super().__init__(app, "Video exportieren", 560)
        self.app = app
        self.job = None
        self.stack = QStackedWidget()
        self.body.addWidget(self.stack)
        self.stack.addWidget(self._settings_page())
        self.stack.addWidget(self._progress_page())
        self.stack.addWidget(self._done_page())

    def _settings_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        st = self.app.settings
        out_dir = st.get("export_dir") or str(Path.home() / "Videos")
        name = "".join(ch for ch in self.app.proj["name"] if ch not in '\\/:*?"<>|').strip() or "NeonCut"
        lay.addWidget(label("SPEICHERN UNTER", "section"))
        self.path = QLineEdit(str(Path(out_dir) / f"{name}.mp4"))
        b = QPushButton("…")
        b.setFixedWidth(40)
        b.clicked.connect(self._browse)
        lay.addLayout(row(self.path, b, stretch_first=True))
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(6)
        self.res = combo(self.RES, st.get("res", 1080), lambda _: self._info())
        self.fps = combo([(f, f"{f} fps") for f in (24, 25, 30, 50, 60)], st.get("fps", 30), lambda _: self._info())
        self.q = combo([("standard", "Standard"), ("high", "Hoch"), ("max", "Maximal")], st.get("quality", "high"),
                       lambda _: None)
        self.enc = combo([("auto", "Automatisch (Grafikkarte, falls möglich)"), ("h264_nvenc", "NVIDIA-Grafikkarte"),
                          ("libx264", "Prozessor (x264)")], st.get("encoder", "auto"), lambda _: None)
        for i, (t, wdg) in enumerate((("AUFLÖSUNG", self.res), ("BILDRATE", self.fps), ("QUALITÄT", self.q),
                                      ("ENCODER", self.enc))):
            g.addWidget(label(t, "section"), (i // 2) * 2, i % 2)
            g.addWidget(wdg, (i // 2) * 2 + 1, i % 2)
        lay.addLayout(g)
        self.info = label("", "muted")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self._info()
        lay.addSpacing(6)
        cancel = QPushButton("Abbrechen")
        cancel.clicked.connect(self.reject)
        go = QPushButton("  Exportieren")
        go.setIcon(icon("export", "#ffffff"))
        go.setObjectName("primary")
        go.clicked.connect(self._start)
        lay.addLayout(row(None, cancel, go))
        return w

    def _info(self):
        W, H = E.canvas_size(self.app.proj["aspect"], self.res.currentData())
        self.info.setText(f"{W} × {H}  ·  {fmt_time(E.duration(self.app.proj))}  ·  MP4 (H.264 + AAC)  ·  "
                          "ohne Wasserzeichen")

    def _browse(self):
        p, _ = QFileDialog.getSaveFileName(self, "Speichern unter", self.path.text(), "MP4-Video (*.mp4)")
        if p:
            self.path.setText(p if p.lower().endswith(".mp4") else p + ".mp4")

    def _progress_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.prev = QLabel()
        self.prev.setFixedHeight(270)
        self.prev.setAlignment(Qt.AlignCenter)
        self.prev.setStyleSheet(f"background: #0a0a0e; border-radius: 10px; border: 1px solid {C_BORDER};")
        lay.addWidget(self.prev)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        lay.addWidget(self.bar)
        self.status = label("Starte …", "muted")
        cancel = QPushButton("Abbrechen")
        cancel.clicked.connect(self._cancel)
        lay.addLayout(row(self.status, None, cancel))
        return w

    def _done_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.done_title = label("Fertig!", "h1")
        self.done_text = label("", "muted")
        self.done_text.setWordWrap(True)
        lay.addWidget(self.done_title)
        lay.addWidget(self.done_text)
        lay.addSpacing(8)
        self.b_folder = QPushButton("  Im Ordner zeigen")
        self.b_folder.setIcon(icon("folder"))
        self.b_folder.clicked.connect(lambda: subprocess.Popen(["explorer", "/select,", str(Path(self.out_path))]))
        self.b_play = QPushButton("  Abspielen")
        self.b_play.setIcon(icon("play"))
        self.b_play.clicked.connect(lambda: os.startfile(self.out_path))
        close = QPushButton("Schließen")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        lay.addLayout(row(self.b_folder, self.b_play, None, close))
        return w

    def _start(self):
        path = Path(self.path.text().strip())
        if not path.suffix:
            path = path.with_suffix(".mp4")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.info.setText("Ordner kann nicht erstellt werden.")
            return
        st = self.app.settings
        st.update(export_dir=str(path.parent), res=self.res.currentData(), fps=self.fps.currentData(),
                  quality=self.q.currentData(), encoder=self.enc.currentData())
        self.app.save_settings()
        W, H = E.canvas_size(self.app.proj["aspect"], self.res.currentData())
        self.out_path = str(path)
        self.job = E.ExportJob(self.app.proj, self.app.store, path, W, H, self.fps.currentData(),
                               self.q.currentData(), self.enc.currentData())
        self.job.progress.connect(self._progress)
        self.job.finished_ok.connect(self._finished)
        self.stack.setCurrentIndex(1)
        self.title_lbl.setText("Exportiere …")
        self.t_start = time.monotonic()
        self.job.start()

    def _progress(self, frac, eta, img):
        self.bar.setValue(int(frac * 1000))
        self.status.setText(f"{frac:.0%}  ·  noch ca. {fmt_time(eta, False)}")
        self.prev.setPixmap(QPixmap.fromImage(img).scaled(self.prev.width() - 4, 266, Qt.KeepAspectRatio,
                                                          Qt.SmoothTransformation))

    def _finished(self, ok, msg):
        self.stack.setCurrentIndex(2)
        el = time.monotonic() - self.t_start
        if ok:
            enc = "Grafikkarte" if self.job.used_encoder == "h264_nvenc" else "Prozessor"
            size = Path(msg).stat().st_size / 1e6 if Path(msg).exists() else 0
            self.title_lbl.setText("Export abgeschlossen")
            self.done_title.setText("Fertig!")
            self.done_text.setText(f"{msg}\n{size:.1f} MB  ·  in {fmt_time(el, False)} ({enc})")
        else:
            self.title_lbl.setText("Export")
            self.done_title.setText("Nicht exportiert")
            self.done_text.setText(msg)
            self.b_folder.hide()
            self.b_play.hide()

    def _cancel(self):
        if self.job and self.job.isRunning():
            self.job.cancel = True
            self.status.setText("Breche ab …")

    def reject(self):
        if self.job and self.job.isRunning():
            self._cancel()
            return
        super().reject()


class CaptionDialog(DialogBase):
    LANGS = [("auto", "Automatisch erkennen"), ("de", "Deutsch"), ("en", "Englisch"), ("es", "Spanisch"),
             ("fr", "Französisch"), ("it", "Italienisch"), ("tr", "Türkisch"), ("pl", "Polnisch"),
             ("pt", "Portugiesisch"), ("nl", "Niederländisch"), ("ru", "Russisch"), ("ar", "Arabisch")]
    STYLES = [("caption", "Fett mit Kontur"), ("subtitle", "Mit Kasten"), ("yellow", "Gelb (Highlight)"),
              ("meme", "Meme"), ("neon", "Neon")]

    def __init__(self, app):
        super().__init__(app, "Auto-Untertitel", 520)
        self.app = app
        self.job = None
        self.stack = QStackedWidget()
        self.body.addWidget(self.stack)
        st = app.settings
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        d = label("NeonCut hört sich den Ton an und schreibt die Untertitel automatisch – komplett auf deinem "
                  "PC, kostenlos und ohne Upload.", "muted")
        d.setWordWrap(True)
        lay.addWidget(d)
        has_sel = bool(app.sel and app.sel[0] in ("video", "overlay", "audio"))
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(6)
        self.scope = combo([("all", "Ganzes Projekt"), ("sel", "Nur ausgewählter Clip")],
                           "sel" if has_sel else "all", lambda _: None)
        self.lang = combo(self.LANGS, st.get("cap_lang", "auto"), lambda _: None)
        self.model = combo([(k, f"{v[0]}  ·  {v[2]} MB" + ("" if E.model_ready(MODELS, k) else " Download"))
                            for k, v in E.WHISPER_MODELS.items()], st.get("cap_model", "base"), lambda _: None)
        self.style = combo(self.STYLES, st.get("cap_style", "caption"), lambda _: None)
        for i, (t, wdg) in enumerate((("BEREICH", self.scope), ("SPRACHE", self.lang), ("GENAUIGKEIT", self.model),
                                      ("STIL", self.style))):
            g.addWidget(label(t, "section"), (i // 2) * 2, i % 2)
            g.addWidget(wdg, (i // 2) * 2 + 1, i % 2)
        lay.addLayout(g)
        self.replace = Toggle(True)
        h = QHBoxLayout()
        h.addWidget(label("Bisherige Auto-Untertitel ersetzen", "h3"), 1)
        h.addWidget(self.replace)
        lay.addLayout(h)
        self.err = label("", "muted")
        self.err.setWordWrap(True)
        lay.addWidget(self.err)
        cancel = QPushButton("Abbrechen")
        cancel.clicked.connect(self.reject)
        go = QPushButton("  Untertitel erstellen")
        go.setIcon(icon("cc", "#ffffff"))
        go.setObjectName("primary")
        go.clicked.connect(self._start)
        lay.addSpacing(4)
        lay.addLayout(row(None, cancel, go))
        self.stack.addWidget(w)
        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        l2.setContentsMargins(0, 0, 0, 0)
        l2.setSpacing(12)
        self.status = label("Starte …", "muted")
        self.status.setWordWrap(True)
        l2.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        l2.addWidget(self.bar)
        stop = QPushButton("Abbrechen")
        stop.clicked.connect(self._cancel)
        l2.addLayout(row(None, stop))
        self.stack.addWidget(w2)

    def _start(self):
        if not E.whisper_available():
            self.err.setText("Die Spracherkennung ist in dieser Version nicht enthalten.")
            return
        items = self.app.caption_items(self.scope.currentData())
        if not items:
            self.err.setText("Kein Clip mit Ton gefunden.")
            return
        st = self.app.settings
        st.update(cap_lang=self.lang.currentData(), cap_model=self.model.currentData(),
                  cap_style=self.style.currentData())
        self.app.save_settings()
        lang = None if self.lang.currentData() == "auto" else self.lang.currentData()
        self.job = E.CaptionJob(MODELS, self.model.currentData(), items, lang)
        self.job.status.connect(lambda t, f: (self.status.setText(t), self.bar.setValue(int(f * 1000))))
        self.job.finished_ok.connect(self._done)
        self.stack.setCurrentIndex(1)
        self.job.start()

    def _done(self, ok, msg, lines):
        if ok:
            self.app.apply_captions(lines, self.style.currentData(), self.replace.on)
            self.accept()
        else:
            self.stack.setCurrentIndex(0)
            self.err.setText("Fehler: " + msg if msg != "Abgebrochen" else "Abgebrochen.")

    def _cancel(self):
        if self.job and self.job.isRunning():
            self.job.cancel = True
            self.status.setText("Breche ab …")

    def reject(self):
        if self.job and self.job.isRunning():
            self._cancel()
            return
        super().reject()


# ════════════════════════════════════════════════════════════════════════════
#  Hauptfenster
# ════════════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        DATA.mkdir(parents=True, exist_ok=True)
        self.settings = self._load_settings()
        self.store = E.MediaStore()
        self.store.ready.connect(self._media_ready)
        self.renderer = E.Renderer(self.store)
        self.thumb_renderer = E.Renderer(self.store, max_decoders=2)
        self.player = E.Player(self.store)
        self.player.gain = self.settings.get("preview_volume", 1.0)
        self.proj = E.new_project()
        self.proj_path = None
        self.sel = None
        self.playhead = 0.0
        self.undo_stack, self.redo_stack = [], []
        self._last_key, self._last_t = None, 0.0
        self.dirty = False
        self.need_render = True
        self.player.proj = self.proj

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QPixmap(app_icon_pixmap()))
        self.resize(1500, 940)
        self.setMinimumSize(1180, 740)
        self.setAcceptDrops(True)
        self._build()

        if AUTOSAVE.exists() and "--fresh" not in sys.argv:
            try:
                self._load_project_file(AUTOSAVE, quiet=True)
                self.proj_path = self.settings.get("last_path") or None
            except Exception:
                pass
        self._after_project_loaded()

        self.timer = QTimer(self, interval=15, timeout=self._tick)
        self.timer.start()
        self.autosave_timer = QTimer(self, interval=15000, timeout=self.autosave)
        self.autosave_timer.start()
        self.filter_timer = QTimer(self, singleShot=True, interval=180, timeout=self._update_filter_thumbs)
        QApplication.instance().installEventFilter(self)

    # ── UI ──────────────────────────────────────────────────────────────────
    def _build(self):
        root = Flat(C_BG)
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._topbar())

        split = QSplitter(Qt.Vertical)
        split.setHandleWidth(5)
        split.setStyleSheet(f"QSplitter::handle {{ background: {C_BG}; }} QSplitter::handle:hover {{ background: {C_ACCENT}; }}")
        upper = QWidget()
        uh = QHBoxLayout(upper)
        uh.setContentsMargins(0, 0, 0, 0)
        uh.setSpacing(0)
        self.nav = NavRail([("film", "Medien"), ("text", "Text"), ("smile", "Sticker"), ("sparkle", "Effekte"),
                            ("filter", "Filter"), ("transition", "Übergänge")])
        self.nav.changed.connect(self.show_panel)
        uh.addWidget(self.nav)
        left = Flat(C_SIDE, C_BORDER, "right")
        left.setFixedWidth(300)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.panels = QStackedWidget()
        self.media_panel = MediaPanel(self)
        self.text_panel = TextPanel(self)
        self.sticker_panel = StickerPanel(self)
        self.effects_panel = EffectsPanel(self)
        self.filter_panel = FilterPanel(self)
        self.trans_panel = TransitionPanel(self)
        for pnl in (self.media_panel, self.text_panel, self.sticker_panel, self.effects_panel, self.filter_panel,
                    self.trans_panel):
            self.panels.addWidget(pnl)
        ll.addWidget(self.panels)
        uh.addWidget(left)

        center = QWidget()
        cv = QVBoxLayout(center)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        self.preview = Preview(self)
        cv.addWidget(self.preview, 1)
        tb = QHBoxLayout()
        tb.setContentsMargins(18, 4, 18, 10)
        self.time_lbl = label("00:00.0", "time")
        self.time_lbl.setStyleSheet(f"color: {C_ACCENT};")
        self.total_lbl = label("/ 00:00.0", "time")
        self.total_lbl.setStyleSheet(f"color: {C_MUTED};")
        self.play_btn = PlayButton()
        self.play_btn.clicked.connect(self.toggle_play)
        tb.addWidget(self.time_lbl)
        tb.addSpacing(4)
        tb.addWidget(self.total_lbl)
        tb.addStretch()
        tb.addWidget(icon_button("start", "Zum Anfang (Pos1)", lambda: self.seek(0)))
        tb.addSpacing(6)
        tb.addWidget(self.play_btn)
        tb.addSpacing(6)
        tb.addWidget(icon_button("end", "Zum Ende (Ende)", lambda: self.seek(E.duration(self.proj))))
        tb.addStretch()
        self.vol_btn = icon_button("volume", "Vorschau stumm schalten", self._toggle_preview_mute)
        tb.addWidget(self.vol_btn)
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 150)
        self.vol_slider.setValue(int(self.player.gain * 100))
        self.vol_slider.setFixedWidth(100)
        self.vol_slider.setToolTip("Lautstärke der Vorschau (ändert nicht das exportierte Video)")
        self.vol_slider.valueChanged.connect(self._preview_volume)
        tb.addWidget(self.vol_slider)
        cv.addLayout(tb)
        uh.addWidget(center, 1)
        self.inspector = Inspector(self)
        uh.addWidget(self.inspector)
        split.addWidget(upper)

        lower = Flat(C_SIDE, C_BORDER, "top")
        lv = QVBoxLayout(lower)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        lv.addWidget(self._timeline_toolbar())
        th = QHBoxLayout()
        th.setContentsMargins(0, 0, 0, 0)
        th.setSpacing(0)
        self.timeline = Timeline(self)
        self.headers = TrackHeaders(self, self.timeline)
        th.addWidget(self.headers)
        th.addWidget(self.timeline, 1)
        lv.addLayout(th, 1)
        self.hbar = QScrollBar(Qt.Horizontal)
        self.hbar.valueChanged.connect(self.timeline.set_x0)
        self.timeline.scrollbar = self.hbar
        lv.addWidget(self.hbar)
        split.addWidget(lower)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([590, 340])
        v.addWidget(split, 1)
        self.dim = Dim(root)
        self._toast = Toast(root)

    def _topbar(self):
        bar = Flat(C_SIDE, C_BORDER, "bottom")
        bar.setFixedHeight(56)
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(8)
        ic = QLabel()
        pm = app_icon_pixmap(64)
        pm.setDevicePixelRatio(2)
        ic.setPixmap(pm)
        ic.setFixedSize(32, 32)
        h.addWidget(ic)
        h.addWidget(label("NeonCut", "h3"))
        h.addSpacing(18)
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("title")
        self.name_edit.setFixedWidth(260)
        self.name_edit.setFocusPolicy(Qt.ClickFocus)
        self.name_edit.editingFinished.connect(self._rename)
        self.name_edit.returnPressed.connect(lambda: self.timeline.setFocus())
        h.addWidget(self.name_edit)
        h.addStretch()
        self.undo_btn = icon_button("undo", "Rückgängig (Strg+Z)", self.undo)
        self.redo_btn = icon_button("redo", "Wiederholen (Strg+Y)", self.redo)
        h.addWidget(self.undo_btn)
        h.addWidget(self.redo_btn)
        h.addSpacing(6)
        fb = QPushButton("Datei")
        fb.setObjectName("ghost")
        fb.setCursor(Qt.PointingHandCursor)
        fb.clicked.connect(lambda: self._file_menu(fb))
        h.addWidget(fb)
        h.addSpacing(6)
        ex = QPushButton("  Exportieren")
        ex.setIcon(icon("export", "#ffffff"))
        ex.setObjectName("primary")
        ex.setCursor(Qt.PointingHandCursor)
        ex.clicked.connect(self.export)
        h.addWidget(ex)
        return bar

    def _tool(self, text, ic, tip, cb):
        b = QPushButton(("  " + text) if text else "")
        b.setIcon(icon(ic))
        b.setObjectName("ghost")
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(cb)
        return b

    def _timeline_toolbar(self):
        w = QWidget()
        w.setFixedHeight(44)
        h = QHBoxLayout(w)
        h.setContentsMargins(10, 4, 14, 0)
        h.setSpacing(2)
        h.addWidget(self._tool("Teilen", "scissors", "Am weißen Strich teilen (S)", self.split))
        h.addWidget(self._tool("", "start", "Alles links vom Strich löschen (Q)", lambda: self.trim_at_playhead("left")))
        h.addWidget(self._tool("", "end", "Alles rechts vom Strich löschen (W)", lambda: self.trim_at_playhead("right")))
        h.addWidget(self._tool("", "dup", "Duplizieren (Strg+D)", self.duplicate))
        h.addWidget(self._tool("", "trash", "Löschen (Entf)", self.delete))
        for _ in range(1):
            sep = QWidget()
            sep.setFixedSize(1, 20)
            sep.setStyleSheet(f"background: {C_BORDER};")
            h.addSpacing(6)
            h.addWidget(sep)
            h.addSpacing(6)
        h.addWidget(self._tool("Standbild", "freeze", "Aktuelles Bild als Standbild einfügen", self.freeze_frame))
        h.addWidget(self._tool("Ton abtrennen", "music", "Ton des Clips auf die Musikspur legen", self.detach_audio))
        h.addWidget(self._tool("Text", "plus", "Text hinzufügen", lambda: self.add_text("title")))
        h.addWidget(self._tool("Untertitel", "cc", "Auto-Untertitel erstellen", self.auto_captions))
        h.addStretch()
        self.snap_btn = QPushButton()
        self.snap_btn.setCheckable(True)
        self.snap_btn.setChecked(True)
        self.snap_btn.setObjectName("ghost")
        self.snap_btn.setIcon(icon("magnet", C_ACCENT))
        self.snap_btn.setFixedSize(32, 32)
        self.snap_btn.setToolTip("Einrasten an Kanten und Abspielposition")
        self.snap_btn.toggled.connect(self._snap_toggled)
        h.addWidget(self.snap_btn)
        h.addSpacing(8)
        h.addWidget(icon_button("zoom_out", "Herauszoomen", lambda: self.timeline.zoom(1 / 1.3)))
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(0, 1000)
        self.zoom_slider.setFixedWidth(130)
        self.zoom_slider.valueChanged.connect(self._zoom_slider)
        h.addWidget(self.zoom_slider)
        h.addWidget(icon_button("zoom_in", "Hineinzoomen", lambda: self.timeline.zoom(1.3)))
        fit = QPushButton("Einpassen")
        fit.setObjectName("ghost")
        fit.setCursor(Qt.PointingHandCursor)
        fit.clicked.connect(lambda: self.timeline.fit())
        h.addWidget(fit)
        return w

    def _snap_toggled(self, on):
        self.timeline.snapping = on
        self.snap_btn.setIcon(icon("magnet", C_ACCENT if on else C_MUTED))

    def _zoom_slider(self, v):
        pps = 0.05 * (800 / 0.05) ** (v / 1000)
        self.timeline.zoom(pps / self.timeline.pps)

    def zoom_changed(self, pps):
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(math.log(max(pps, 0.05) / 0.05) / math.log(800 / 0.05) * 1000))
        self.zoom_slider.blockSignals(False)

    def _preview_volume(self, v):
        self.player.gain = v / 100
        self.settings["preview_volume"] = v / 100
        self.vol_btn.setIcon(icon("mute" if v == 0 else "volume", C_TEXT))

    def _toggle_preview_mute(self):
        if self.vol_slider.value() > 0:
            self._vol_before = self.vol_slider.value()
            self.vol_slider.setValue(0)
        else:
            self.vol_slider.setValue(getattr(self, "_vol_before", 100) or 100)

    def show_panel(self, i):
        self.nav.set_index(i, emit=False)
        self.panels.setCurrentIndex(i)
        if i == P_FILTER:
            self._update_filter_thumbs()

    def toast(self, text):
        self._toast.show_msg(text)

    # ── Projekt ─────────────────────────────────────────────────────────────
    def _load_settings(self):
        try:
            return json.loads(SETTINGS.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_settings(self):
        try:
            SETTINGS.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _load_project_file(self, path, quiet=False):
        data = E.fix_project(json.loads(Path(path).read_text(encoding="utf-8")))
        missing = [m["name"] for m in data["media"].values() if not Path(m["path"]).exists()]
        self.player.pause()
        self.proj = data
        self.player.proj = data
        self.sel = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        for m in data["media"].values():
            if Path(m["path"]).exists():
                self.store.load(m)
        if missing and not quiet:
            self.toast("Fehlende Dateien: " + ", ".join(missing[:3]))

    def _after_project_loaded(self):
        self.name_edit.setText(self.proj["name"])
        self.playhead = min(self.playhead, E.duration(self.proj))
        self.player.seek(self.playhead)
        self.media_panel.refresh()
        self.inspector.rebuild()
        self.timeline.update_scroll()
        QTimer.singleShot(50, self.timeline.fit)
        self.on_changed(structural=True)

    def new_project(self):
        self.autosave()
        self.player.pause()
        self.proj = E.new_project()
        self.player.proj = self.proj
        self.proj_path = None
        self.settings["last_path"] = None
        self.sel = None
        self.playhead = 0.0
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._after_project_loaded()

    def open_project(self):
        p, _ = QFileDialog.getOpenFileName(self, "Projekt öffnen", self.settings.get("project_dir", str(Path.home())),
                                           "NeonCut-Projekt (*.neoncut)")
        if p:
            self.open_path(p)

    def open_path(self, p):
        try:
            self._load_project_file(p)
        except Exception as e:
            self.toast(f"Konnte nicht geöffnet werden: {e}")
            return
        self.proj_path = p
        self.settings["last_path"] = p
        self.settings["project_dir"] = str(Path(p).parent)
        self.playhead = 0.0
        self._after_project_loaded()
        self.toast("Projekt geöffnet")

    def save_project(self, as_new=False):
        if not self.proj_path or as_new:
            name = "".join(ch for ch in self.proj["name"] if ch not in '\\/:*?"<>|').strip() or "Projekt"
            start = str(Path(self.settings.get("project_dir", str(Path.home() / "Videos"))) / f"{name}.neoncut")
            p, _ = QFileDialog.getSaveFileName(self, "Projekt speichern", start, "NeonCut-Projekt (*.neoncut)")
            if not p:
                return
            self.proj_path = p
            self.settings["last_path"] = p
            self.settings["project_dir"] = str(Path(p).parent)
            self.save_settings()
        try:
            Path(self.proj_path).write_text(json.dumps(self.proj, ensure_ascii=False, indent=1), encoding="utf-8")
            self.dirty = False
            self.toast("Projekt gespeichert")
        except OSError as e:
            self.toast(f"Speichern fehlgeschlagen: {e}")

    def autosave(self):
        try:
            AUTOSAVE.write_text(json.dumps(self.proj, ensure_ascii=False), encoding="utf-8")
            self.save_settings()
        except OSError:
            pass

    def _rename(self):
        n = self.name_edit.text().strip() or "Unbenanntes Projekt"
        if n != self.proj["name"]:
            self.modify("name", lambda: self.proj.__setitem__("name", n))

    def _file_menu(self, btn):
        m = styled_menu(self)
        m.addAction("Neues Projekt\tStrg+N", self.new_project)
        m.addAction("Projekt öffnen …\tStrg+O", self.open_project)
        m.addAction("Speichern\tStrg+S", self.save_project)
        m.addAction("Speichern unter …\tStrg+Umschalt+S", lambda: self.save_project(True))
        m.addSeparator()
        m.addAction("Medien importieren …\tStrg+I", self.import_dialog)
        m.addAction("Aktuelles Bild als PNG speichern …", self.save_frame)
        m.addAction("Exportieren …\tStrg+E", self.export)
        m.addSeparator()
        m.addAction(f"Über NeonCut {VERSION}", lambda: self.toast(f"NeonCut {VERSION} – gratis, ohne Wasserzeichen"))
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    # ── Änderungen & Rückgängig ─────────────────────────────────────────────
    def begin_change(self, key=None):
        now = time.monotonic()
        if key is None or key != self._last_key or now - self._last_t > 1.2:
            self.undo_stack.append(json.dumps(self.proj))
            if len(self.undo_stack) > 200:
                self.undo_stack.pop(0)
            self.redo_stack.clear()
        self._last_key, self._last_t = key, now
        self.dirty = True

    def end_change(self):
        self._last_key = None
        self.on_changed(structural=True)

    def modify(self, key, fn):
        self.begin_change(key)
        fn()
        self.on_changed()

    def modify_sel(self, field, fn):
        c = self.selected_visual()
        if c:
            self.modify(f"{field}:{c['id']}", lambda: fn(c))
            self.inspector.refresh_values()

    def live_changed(self):
        self.need_render = True
        self.timeline.update()
        self.inspector.refresh_values()

    def on_changed(self, structural=False):
        self.need_render = True
        self.timeline.update()
        self.timeline.update_scroll()
        self.headers.update()
        self.total_lbl.setText("/ " + fmt_time(E.duration(self.proj)))
        self.undo_btn.setEnabled(bool(self.undo_stack))
        self.redo_btn.setEnabled(bool(self.redo_stack))
        self.setWindowTitle(f"{self.proj['name']} – {APP_NAME}")
        if structural:
            self.media_panel.refresh()
        self._sync_panels()

    def _restore(self, data):
        self.proj = E.fix_project(json.loads(data))
        self.player.proj = self.proj
        if self.sel and E.find_clip(self.proj, self.sel[1])[1] is None:
            self.sel = None
        self.name_edit.setText(self.proj["name"])
        self.inspector.rebuild()
        self.on_changed(structural=True)

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(json.dumps(self.proj))
            self._restore(self.undo_stack.pop())
            self._last_key = None

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(json.dumps(self.proj))
            self._restore(self.redo_stack.pop())
            self._last_key = None

    # ── Auswahl ─────────────────────────────────────────────────────────────
    def select(self, kind, cid=None):
        new = (kind, cid) if kind else None
        if new != self.sel:
            self.sel = new
            self._last_key = None
            self.inspector.rebuild()
            self._sync_panels()
            self.filter_timer.start()
            self.timeline.update()
            self.need_render = True

    def selected_video(self):
        if self.sel and self.sel[0] == "video":
            return E.find_clip(self.proj, self.sel[1])[1]
        return None

    def selected_visual(self):
        if self.sel and self.sel[0] in ("video", "overlay"):
            return E.find_clip(self.proj, self.sel[1])[1]
        return None

    def _sync_panels(self):
        c = self.selected_visual()
        self.effects_panel.sync(c.get("effect") if c else None)
        self.filter_panel.sync(c)
        self.trans_panel.sync(self.selected_video())

    def refresh_inspector_values(self):
        self.inspector.refresh_values()

    def _update_filter_thumbs(self):
        if self.panels.currentIndex() != P_FILTER:
            return
        c = self.selected_visual()
        item = None
        if c:
            kind = self.sel[0]
            s, e = E.span(self.proj, kind, c)
            item = (c, s, e)
        else:
            lay = E.layout(self.proj)
            item = next((x for x in lay if x[1] <= self.playhead < x[2]), lay[0] if lay else None)
        if item is None:
            self.filter_panel.set_source(None)
            return
        clip, s, e = item
        m = self.proj["media"][clip["media"]]
        t = min(max(self.playhead, s), e - 0.01) if s <= self.playhead < e else s + 0.3 * (e - s)
        src = clip["in"] + (t - s) * clip.get("speed", 1.0)
        h = 90
        w = max(2, int(h * m["w"] / max(1, m["h"])) // 2 * 2)
        self.filter_panel.set_source(self.thumb_renderer._frame(m, "thumb:" + clip["id"], src, w, h))

    # ── Medien ──────────────────────────────────────────────────────────────
    def import_dialog(self):
        exts = " ".join("*" + e for e in sorted(E.ALL_EXT))
        paths, _ = QFileDialog.getOpenFileNames(self, "Medien importieren",
                                                self.settings.get("import_dir", str(Path.home() / "Videos")),
                                                f"Medien ({exts})")
        if paths:
            self.settings["import_dir"] = str(Path(paths[0]).parent)
            self.import_files(paths)

    def import_files(self, paths):
        files = []
        for p in map(Path, paths):
            if p.is_dir():
                files += sorted(f for f in p.iterdir() if f.suffix.lower() in E.ALL_EXT)
            elif p.suffix.lower() in E.ALL_EXT:
                files.append(p)
        if not files:
            self.toast("Keine unterstützten Dateien")
            return
        was_empty = not self.proj["video"]
        added, bad = [], []
        self.begin_change()
        for f in files:
            try:
                m = E.probe(f)
            except Exception:
                bad.append(f.name)
                continue
            self.proj["media"][m["id"]] = m
            self.store.load(m)
            added.append(m)
        if was_empty and added:
            vis = [m for m in added if m["kind"] in ("video", "image")]
            if vis:
                ratio = vis[0]["w"] / max(1, vis[0]["h"])
                self.proj["aspect"] = min(E.ASPECTS, key=lambda k: abs(math.log(E.ASPECTS[k][0] / E.ASPECTS[k][1] / ratio)))
            for m in added:
                if m["kind"] in ("video", "image"):
                    self.proj["video"].append(E.video_clip(m))
                else:
                    self.proj["audio"].append(E.audio_clip(m, 0.0))
            QTimer.singleShot(60, self.timeline.fit)
        self.on_changed(structural=True)
        msg = f"{len(added)} Datei{'en' if len(added) != 1 else ''} importiert"
        if was_empty and added:
            msg += " und in die Timeline gelegt"
        if bad:
            msg += f"  ·  {len(bad)} nicht lesbar"
        self.toast(msg)

    def media_in_use(self, mid):
        return any(c["media"] == mid for k in ("video", "overlay", "audio") for c in self.proj[k])

    def add_media_to_timeline(self, mid, index=None, t=None):
        m = self.proj["media"].get(mid)
        if not m:
            return
        self.begin_change()
        if m["kind"] == "audio":
            c = E.audio_clip(m, self.playhead if t is None else t)
            self.proj["audio"].append(c)
            self.sel = ("audio", c["id"])
        else:
            c = E.video_clip(m)
            if index is None:
                self.proj["video"].append(c)
            else:
                self.proj["video"].insert(index, c)
            self.sel = ("video", c["id"])
        self.inspector.rebuild()
        self.end_change()

    def add_overlay(self, mid, t=None):
        m = self.proj["media"].get(mid)
        if not m or m["kind"] == "audio":
            return
        self.begin_change()
        c = E.overlay_clip(m, self.playhead if t is None else t)
        self.proj["overlay"].append(c)
        self.sel = ("overlay", c["id"])
        self.inspector.rebuild()
        self.end_change()
        self.toast("Overlay eingefügt – in der Vorschau verschieben, unter „Overlay“ Greenscreen entfernen")

    def media_menu(self, mid, pos):
        m = self.proj["media"].get(mid)
        menu = styled_menu(self)
        menu.addAction("Zur Timeline hinzufügen", lambda: self.add_media_to_timeline(mid))
        if m["kind"] != "audio":
            menu.addAction("Als Overlay hinzufügen (Bild-in-Bild)", lambda: self.add_overlay(mid))
        menu.addAction("Im Explorer zeigen", lambda: subprocess.Popen(["explorer", "/select,", m["path"]]))
        menu.addSeparator()
        menu.addAction("Aus Projekt entfernen", lambda: self.remove_media(mid))
        menu.exec(pos)

    def remove_media(self, mid):
        self.begin_change()
        for k in ("video", "overlay", "audio"):
            self.proj[k] = [c for c in self.proj[k] if c["media"] != mid]
        self.proj["media"].pop(mid, None)
        if self.sel and E.find_clip(self.proj, self.sel[1])[1] is None:
            self.sel = None
            self.inspector.rebuild()
        self.end_change()

    def _media_ready(self, mid):
        self.media_panel.update_tile(mid)
        self.timeline.update()
        self.need_render = True
        if self.panels.currentIndex() == P_FILTER:
            self.filter_timer.start()

    # ── Bearbeiten ──────────────────────────────────────────────────────────
    def add_text(self, preset="title"):
        c = E.text_clip(self.playhead, preset)
        self.begin_change()
        self.proj["text"].append(c)
        self.sel = ("text", c["id"])
        self.inspector.tab_idx["text"] = 0
        self.inspector.rebuild()
        self.end_change()
        if self.inspector.text_edit:
            self.inspector.text_edit.setFocus()
            self.inspector.text_edit.selectAll()

    def add_sticker(self, emoji):
        c = E.sticker_clip(self.playhead, emoji)
        self.begin_change()
        self.proj["text"].append(c)
        self.sel = ("text", c["id"])
        self.inspector.rebuild()
        self.end_change()

    def apply_effect(self, key):
        c = self.selected_visual()
        if not c:
            self.toast("Wähle zuerst einen Video-Clip in der Timeline")
            return
        self.modify("effect:" + c["id"], lambda: c.__setitem__("effect", key))
        self.inspector.rebuild()

    def apply_filter(self, key):
        c = self.selected_visual()
        if not c:
            self.toast("Wähle zuerst einen Video-Clip in der Timeline")
            return
        self.modify("filter:" + c["id"], lambda: c.__setitem__("filter", key))
        self.inspector.rebuild()

    def _trans_target(self):
        c = self.selected_video()
        lay = E.layout(self.proj)
        if c is None:
            best = None
            for i in range(len(lay) - 1):
                d = abs(lay[i][2] - self.playhead)
                if best is None or d < best[0]:
                    best = (d, lay[i][0])
            return best[1] if best else None
        if lay and lay[-1][0] is c:
            return None
        return c

    def apply_transition(self, key):
        c = self._trans_target()
        if c is None:
            self.toast("Wähle einen Clip, auf den noch ein weiterer folgt")
            return
        self.modify("trans:" + c["id"], lambda: c["trans"].__setitem__("type", key))
        if not self.sel:
            self.select("video", c["id"])
        self.inspector.rebuild()

    def set_transition_dur(self, v):
        c = self._trans_target()
        if c is not None:
            self.modify("tdur:" + c["id"], lambda: c["trans"].__setitem__("dur", v))

    def transition_to_all(self):
        c = self._trans_target()
        tr = dict(c["trans"]) if c else {"type": "fade", "dur": 0.6}
        if tr["type"] == "none":
            tr["type"] = "fade"
        self.begin_change()
        for x in self.proj["video"][:-1]:
            x["trans"] = dict(tr)
        self.end_change()
        self.toast(f"„{E.TRANSITIONS[tr['type']]}“ auf alle Clips angewendet")

    def fit_clip(self, cid, sc):
        _, c = E.find_clip(self.proj, cid)
        m = self.proj["media"][c["media"]]
        W, H = E.canvas_size(self.proj["aspect"])
        if sc is None:
            sc = max(W / m["w"], H / m["h"]) / min(W / m["w"], H / m["h"])
        self.modify("fit:" + cid, lambda: c.update(scale=sc, x=0.0, y=0.0, rot=0.0))
        self.inspector.refresh_values()

    def set_aspect(self, a):
        self.modify("aspect", lambda: self.proj.__setitem__("aspect", a))

    def toggle_mute_video(self):
        on = not self.proj.get("mute_video")
        self.modify("mute_video", lambda: self.proj.__setitem__("mute_video", on))
        self.toast("Originalton der Clips aus" if on else "Originalton der Clips an")

    def _target_at_playhead(self, kinds=("video", "overlay", "text", "audio")):
        t = self.playhead
        if self.sel:
            kind, c = E.find_clip(self.proj, self.sel[1])
            if c is not None and kind in kinds:
                s, e = E.span(self.proj, kind, c)
                if s + E.MIN_LEN < t < e - E.MIN_LEN:
                    return kind, c
        for c, s, e in E.layout(self.proj):
            if s + E.MIN_LEN < t < e - E.MIN_LEN:
                return "video", c
        return None

    def _split_clip(self, kind, c, t):
        s, e = E.span(self.proj, kind, c)
        local = t - s
        c2 = copy.deepcopy(c)
        c2["id"] = E.new_id()
        if kind in ("video", "overlay"):
            m = self.proj["media"][c["media"]]
            if m["kind"] == "image":
                c["out"] = c["in"] + local
                c2["in"], c2["out"] = 0.0, e - t
            else:
                cut = c["in"] + local * c.get("speed", 1.0)
                c["out"], c2["in"] = cut, cut
            c["fade_out"], c2["fade_in"] = 0.0, 0.0
            if kind == "video":
                c["trans"] = {"type": "none", "dur": c["trans"]["dur"]}
                self.proj["video"].insert(self.proj["video"].index(c) + 1, c2)
            else:
                c2["start"] = t
                self.proj["overlay"].append(c2)
        elif kind == "text":
            c["dur"] = local
            c2["start"], c2["dur"] = t, e - t
            self.proj["text"].append(c2)
        else:
            c["out"] = c["in"] + local
            c2["start"], c2["in"] = t, c["out"]
            c["fade_out"], c2["fade_in"] = 0.0, 0.0
            self.proj["audio"].append(c2)
        return c2

    def split(self):
        target = self._target_at_playhead()
        if target is None:
            self.toast("Am weißen Strich liegt kein Clip – schieb ihn zuerst auf einen Clip")
            return
        kind, c = target
        self.begin_change()
        c2 = self._split_clip(kind, c, self.playhead)
        self.sel = (kind, c2["id"])
        self.inspector.rebuild()
        self.end_change()

    def trim_at_playhead(self, side):
        target = self._target_at_playhead()
        if target is None:
            self.toast("Am weißen Strich liegt kein Clip")
            return
        kind, c = target
        t = self.playhead
        s, e = E.span(self.proj, kind, c)
        local = t - s
        self.begin_change()
        if kind in ("video", "overlay"):
            m = self.proj["media"][c["media"]]
            sp = c.get("speed", 1.0)
            if side == "left":
                if m["kind"] == "image":
                    c["out"] = c["in"] + (e - t)
                else:
                    c["in"] += local * sp
                if kind == "overlay":
                    c["start"] = t
            else:
                c["out"] = c["in"] + local * (1 if m["kind"] == "image" else sp)
        elif kind == "text":
            if side == "left":
                c["start"], c["dur"] = t, e - t
            else:
                c["dur"] = local
        else:
            if side == "left":
                c["in"] += local
                c["start"] = t
            else:
                c["out"] = c["in"] + local
        if kind == "video" and side == "left":
            self.playhead = s
            self.player.seek(s)
        self.end_change()

    def delete(self):
        if not self.sel:
            return
        kind, c = E.find_clip(self.proj, self.sel[1])
        if c is None:
            return
        self.begin_change()
        self.proj[kind].remove(c)
        self.sel = None
        self.inspector.rebuild()
        self.end_change()

    def duplicate(self):
        if not self.sel:
            return
        kind, c = E.find_clip(self.proj, self.sel[1])
        if c is None:
            return
        self.begin_change()
        c2 = copy.deepcopy(c)
        c2["id"] = E.new_id()
        if kind == "video":
            self.proj["video"].insert(self.proj["video"].index(c) + 1, c2)
        else:
            c2["start"] = E.span(self.proj, kind, c)[1]
            self.proj[kind].append(c2)
        self.sel = (kind, c2["id"])
        self.inspector.rebuild()
        self.end_change()

    def freeze_frame(self):
        target = self._target_at_playhead(("video",))
        lay = E.layout(self.proj)
        if target is None:
            item = next((x for x in lay if x[1] <= self.playhead < x[2]), None)
            if item is None:
                self.toast("Stell den weißen Strich auf einen Video-Clip")
                return
            target = ("video", item[0])
        kind, c = target
        m = self.proj["media"][c["media"]]
        if m["kind"] != "video":
            self.toast("Standbilder gehen nur bei Video-Clips")
            return
        s, e = E.span(self.proj, kind, c)
        t = self.playhead
        img = E.source_frame(m, c["in"] + (t - s) * c.get("speed", 1.0))
        if img is None:
            self.toast("Bild konnte nicht gelesen werden")
            return
        FRAMES.mkdir(parents=True, exist_ok=True)
        path = FRAMES / f"standbild_{E.new_id()}.png"
        img.save(str(path))
        fm = E.probe(path)
        fm["name"] = f"Standbild {fmt_time(t)}"
        self.begin_change()
        self.proj["media"][fm["id"]] = fm
        self.store.load(fm)
        fc = E.video_clip(fm)
        fc["out"] = 2.0
        vids = self.proj["video"]
        if s + E.MIN_LEN < t < e - E.MIN_LEN:
            self._split_clip("video", c, t)
            vids.insert(vids.index(c) + 1, fc)
        else:
            vids.insert(vids.index(c) + (1 if t >= e - E.MIN_LEN else 0), fc)
        self.sel = ("video", fc["id"])
        self.inspector.rebuild()
        self.end_change()
        self.toast("Standbild (2 s) eingefügt")

    def detach_audio(self):
        c = self.selected_visual()
        if c is None:
            self.toast("Wähle zuerst einen Video-Clip")
            return
        m = self.proj["media"][c["media"]]
        if not m.get("has_audio"):
            self.toast("Dieser Clip hat keinen Ton")
            return
        if abs(c.get("speed", 1.0) - 1) > 0.01:
            self.toast("Ton abtrennen geht nur bei normaler Geschwindigkeit (1x)")
            return
        s, e = E.span(self.proj, self.sel[0], c)
        self.begin_change()
        ac = E.audio_clip(m, s)
        ac.update(**{"in": c["in"], "out": c["out"], "volume": c.get("volume", 1.0), "denoise": c.get("denoise", False)})
        self.proj["audio"].append(ac)
        c["mute"] = True
        self.sel = ("audio", ac["id"])
        self.inspector.rebuild()
        self.end_change()
        self.toast("Ton abgetrennt – er liegt jetzt auf der grünen Musikspur")

    def clip_menu(self, pos):
        m = styled_menu(self)
        m.addAction("Am weißen Strich teilen\tS", self.split)
        m.addAction("Duplizieren\tStrg+D", self.duplicate)
        kind = self.sel[0] if self.sel else None
        if kind in ("video", "overlay"):
            m.addAction("Ton abtrennen", self.detach_audio)
        if kind == "video":
            m.addAction("Standbild einfügen", self.freeze_frame)
        m.addSeparator()
        m.addAction("Löschen\tEntf", self.delete)
        m.exec(pos)

    # ── Untertitel ──────────────────────────────────────────────────────────
    def auto_captions(self):
        if E.duration(self.proj) <= 0:
            self.toast("Importiere zuerst ein Video mit Ton")
            return
        if self.player.playing:
            self.toggle_play()
        self.dim.fade(True)
        CaptionDialog(self).exec()
        self.dim.fade(False)

    def caption_items(self, scope):
        items = []
        sel_id = self.sel[1] if self.sel else None
        aud = E.audible(self.proj)
        if scope == "sel" and sel_id:
            aud = [a for a in aud if a[1]["id"] == sel_id]
        elif any(a[0] != "audio" for a in aud):
            aud = [a for a in aud if a[0] != "audio"]
        for kind, c, s, e, speed in aud:
            m = self.proj["media"][c["media"]]
            items.append((m["path"], c["in"], c["in"] + (e - s) * speed, s, speed))
        return items

    def apply_captions(self, lines, style, replace):
        self.begin_change()
        if replace:
            self.proj["text"] = [t for t in self.proj["text"] if not t.get("auto")]
        H_ratio = E.ASPECTS[self.proj["aspect"]]
        for s, e, text in lines:
            c = E.text_clip(s, style, text)
            c["dur"] = max(0.3, e - s)
            c["auto"] = True
            c["anim_in"] = "pop" if style in ("caption", "yellow") else "fade"
            c["anim_out"] = "none"
            if style != "meme":
                c["y"] = 0.3 if H_ratio[0] >= H_ratio[1] else 0.18
            if H_ratio[0] < H_ratio[1]:
                c["size"] = c["size"] * 0.75
            self.proj["text"].append(c)
        self.end_change()
        self.toast(f"{len(lines)} Untertitel erstellt" if lines else "Keine Sprache erkannt")

    def caption_style_to_all(self, src):
        keys = ("font", "bold", "italic", "size", "color", "stroke", "stroke_w", "box", "box_color", "box_alpha",
                "glow", "shadow", "x", "y", "anim_in", "anim_out")
        self.begin_change()
        n = 0
        for t in self.proj["text"]:
            if t.get("auto") and t is not src:
                t.update({k: copy.deepcopy(src[k]) for k in keys if k in src})
                n += 1
        self.end_change()
        self.toast(f"Stil auf {n} Untertitel übertragen")

    # ── Wiedergabe ──────────────────────────────────────────────────────────
    def toggle_play(self):
        if self.player.playing:
            self.player.pause()
            self.playhead = self.player.pos
        else:
            if E.duration(self.proj) <= 0:
                return
            self.player.seek(self.playhead)
            self.player.play()
        self.play_btn.playing = self.player.playing
        self.play_btn.update()
        self.timeline.update()
        self.need_render = True

    def seek(self, t):
        t = max(0.0, min(t, max(0.0, E.duration(self.proj))))
        self.playhead = t
        self.player.seek(t)
        self.need_render = True
        self.timeline.update()
        self.filter_timer.start()

    def _tick(self):
        if self.player.playing:
            self.player.tick()
            t = self.player.current()
            d = E.duration(self.proj)
            if t >= d:
                self.player.pause()
                self.player.seek(d)
                t = d
                self.play_btn.playing = False
                self.play_btn.update()
            self.playhead = t
            self.timeline.follow(t)
            self.timeline.update()
            self._render(t)
        elif self.need_render:
            self._render(self.playhead)
        self.time_lbl.setText(fmt_time(self.playhead) if self.playhead < 3600 else
                              f"{int(self.playhead // 3600)}:{fmt_time(self.playhead % 3600)}")

    def _render(self, t):
        self.need_render = False
        W, H = self.preview.render_size()
        try:
            img = self.renderer.render(self.proj, t, W, H, preview=True)
        except Exception as e:
            img = None
            print("render error:", e)
        if img is not None:
            self.preview.set_image(img, self.renderer.rects)

    # ── Export ──────────────────────────────────────────────────────────────
    def export(self):
        if E.duration(self.proj) <= 0:
            self.toast("Die Timeline ist leer")
            return
        if self.player.playing:
            self.toggle_play()
        self.autosave()
        self.dim.fade(True)
        ExportDialog(self).exec()
        self.dim.fade(False)

    def save_frame(self):
        W, H = E.canvas_size(self.proj["aspect"], 1080)
        name = "".join(ch for ch in self.proj["name"] if ch not in '\\/:*?"<>|').strip() or "NeonCut"
        p, _ = QFileDialog.getSaveFileName(self, "Bild speichern",
                                           str(Path(self.settings.get("export_dir", str(Path.home() / "Pictures")))
                                               / f"{name} {fmt_time(self.playhead, False).replace(':', '-')}.png"),
                                           "PNG-Bild (*.png)")
        if p:
            r = E.Renderer(self.store, 2)
            r.render(self.proj, self.playhead, W, H).save(p)
            r.close()
            self.toast("Bild gespeichert")

    # ── Ereignisse ──────────────────────────────────────────────────────────
    def eventFilter(self, obj, ev):
        if ev.type() != QEvent.KeyPress or not self.isActiveWindow():
            return False
        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QPlainTextEdit)):
            return False
        k, mods = ev.key(), ev.modifiers()
        ctrl = bool(mods & Qt.ControlModifier)
        shift = bool(mods & Qt.ShiftModifier)
        if isinstance(fw, QComboBox) and k in (Qt.Key_Up, Qt.Key_Down):
            return False
        step = 1.0 if shift else 1 / 30
        actions = {
            (Qt.Key_Space, False): self.toggle_play,
            (Qt.Key_S, False): self.split, (Qt.Key_B, True): self.split,
            (Qt.Key_Q, False): lambda: self.trim_at_playhead("left"),
            (Qt.Key_W, False): lambda: self.trim_at_playhead("right"),
            (Qt.Key_Delete, False): self.delete, (Qt.Key_Backspace, False): self.delete,
            (Qt.Key_Z, True): self.redo if shift else self.undo, (Qt.Key_Y, True): self.redo,
            (Qt.Key_D, True): self.duplicate,
            (Qt.Key_Left, False): lambda: self.seek(self.playhead - step),
            (Qt.Key_Right, False): lambda: self.seek(self.playhead + step),
            (Qt.Key_Home, False): lambda: self.seek(0), (Qt.Key_End, False): lambda: self.seek(E.duration(self.proj)),
            (Qt.Key_S, True): (lambda: self.save_project(True)) if shift else self.save_project,
            (Qt.Key_O, True): self.open_project, (Qt.Key_N, True): self.new_project,
            (Qt.Key_E, True): self.export, (Qt.Key_I, True): self.import_dialog,
            (Qt.Key_Plus, True): lambda: self.timeline.zoom(1.3), (Qt.Key_Minus, True): lambda: self.timeline.zoom(1 / 1.3),
            (Qt.Key_Escape, False): lambda: self.select(None),
        }
        fn = actions.get((k, ctrl))
        if fn:
            fn()
            return True
        return False

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.import_files(paths)

    def showEvent(self, e):
        super().showEvent(e)
        try:
            hwnd = int(self.winId())
            dwm = ctypes.windll.dwmapi
            dark = ctypes.c_int(1)
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)
            cap = ctypes.c_int(0x00181212)
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cap), 4)
        except Exception:
            pass

    def closeEvent(self, e):
        self.player.pause()
        self.autosave()
        if self.proj_path and self.dirty:
            try:
                Path(self.proj_path).write_text(json.dumps(self.proj, ensure_ascii=False, indent=1), encoding="utf-8")
            except OSError:
                pass
        self.renderer.close()
        self.thumb_renderer.close()
        super().closeEvent(e)


def selftest(media, out):
    """Prüft die fertige exe ohne Fenster: Dekodieren, Rendern, Ton, Spracherkennung."""
    res = {}
    try:
        store = E.MediaStore()
        proj = E.new_project()
        for p in media:
            m = E.probe(p)
            proj["media"][m["id"]] = m
            store.load(m)
            (proj["audio"].append(E.audio_clip(m, 0)) if m["kind"] == "audio" else proj["video"].append(E.video_clip(m)))
        img = E.Renderer(store).render(proj, 0.5, 640, 360)
        res["render"] = [img.width(), img.height()]
        import numpy as np
        res["audio_peak"] = float(np.abs(E.mix_audio(proj, store, 0.5, 48000)).max())
        res["whisper"] = E.whisper_available()
        wav = next((p for p in media if p.lower().endswith(".wav")), None)
        if res["whisper"] and wav and E.model_ready(MODELS, "base"):
            from faster_whisper import WhisperModel
            mdl = WhisperModel(str(MODELS / "base"), device="cpu", compute_type="int8")
            segs, info = mdl.transcribe(E.decode_range(wav, 0, 8), word_timestamps=True)
            res["text"] = " ".join(s.text.strip() for s in segs)
    except Exception as e:
        import traceback
        res["error"] = traceback.format_exc()
    Path(out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    if "--selftest" in sys.argv:
        from PySide6.QtGui import QGuiApplication
        _app = QGuiApplication(sys.argv)  # noqa: F841
        i = sys.argv.index("--selftest")
        selftest(sys.argv[i + 2:], sys.argv[i + 1])
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NeonCut.Editor")
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    DATA.mkdir(parents=True, exist_ok=True)
    arrow = make_arrow_png(DATA / "arrow.png")
    app.setStyleSheet(STYLE.replace("ARROW_PNG", Path(arrow).as_posix()))
    app.setWindowIcon(QPixmap(app_icon_pixmap()))
    w = MainWindow()
    w.show()
    skip = {sys.argv.index("--screenshot") + 1} if "--screenshot" in sys.argv else set()
    args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and i not in skip and Path(a).exists()]
    projects = [a for a in args if a.lower().endswith(".neoncut")]
    media = [a for a in args if not a.lower().endswith(".neoncut")]
    if projects:
        QTimer.singleShot(200, lambda: w.open_path(projects[0]))
    elif media:
        QTimer.singleShot(200, lambda: w.import_files(media))
    if "--screenshot" in sys.argv:
        out = sys.argv[sys.argv.index("--screenshot") + 1]
        QTimer.singleShot(2500, lambda: (w.grab().save(out), w.close(), app.quit()))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
