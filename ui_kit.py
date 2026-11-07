"""NeonCut – Design-System (gleicher Stil wie NeonBoard) und Basis-Widgets."""
from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import (QColorDialog, QDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                               QMenu, QPushButton, QSlider, QVBoxLayout, QWidget)

C_BG = "#0e0e12"
C_SIDE = "#121218"
C_SURF = "#17171f"
C_SURF2 = "#1e1e29"
C_BORDER = "#262631"
C_BORDER2 = "#363645"
C_TEXT = "#ededf2"
C_MUTED = "#8b8b9b"
C_ACCENT = "#7c5cff"
C_VIDEO = "#3b82f6"
C_TEXTCLIP = "#a855f7"
C_AUDIO = "#10b981"
SWATCHES = ["#ffffff", "#000000", "#ffd60a", "#ff3fd8", "#7c5cff", "#3b82f6",
            "#06b6d4", "#10b981", "#f97316", "#ef4444"]

STYLE = f"""
* {{ font-family: 'Segoe UI Variable Text', 'Segoe UI'; color: {C_TEXT}; font-size: 13px; }}
QToolTip {{ background: {C_SURF2}; color: {C_TEXT}; border: 1px solid {C_BORDER2}; padding: 6px 8px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {C_BORDER2}; border-radius: 2px; min-height: 40px; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {C_BORDER2}; border-radius: 2px; min-width: 40px; }}
QScrollBar::handle:hover {{ background: #4a4a5c; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QLineEdit, QPlainTextEdit {{ background: {C_SURF2}; border: 1px solid {C_BORDER}; border-radius: 10px;
             padding: 7px 10px; selection-background-color: {C_ACCENT}; }}
QLineEdit:hover, QPlainTextEdit:hover {{ border-color: {C_BORDER2}; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {C_ACCENT}; }}
QLineEdit#title {{ background: transparent; border: 1px solid transparent; font-size: 14px; font-weight: 600; }}
QLineEdit#title:hover {{ border-color: {C_BORDER}; }}
QLineEdit#title:focus {{ border-color: {C_ACCENT}; background: {C_SURF2}; }}
QPushButton {{ background: {C_SURF2}; border: 1px solid {C_BORDER}; border-radius: 10px;
               padding: 7px 13px; font-weight: 600; }}
QPushButton:hover {{ background: #262634; border-color: {C_BORDER2}; }}
QPushButton:pressed {{ background: #2c2c3c; }}
QPushButton:disabled {{ color: #5a5a6c; }}
QPushButton#primary {{ background: {C_ACCENT}; border: 1px solid {C_ACCENT}; color: white; }}
QPushButton#primary:hover {{ background: #8d71ff; border-color: #8d71ff; }}
QPushButton#primary:pressed {{ background: #6c4cf0; }}
QPushButton#ghost {{ background: transparent; border: 1px solid transparent; color: {C_MUTED}; padding: 6px 8px; }}
QPushButton#ghost:hover {{ background: {C_SURF2}; color: {C_TEXT}; }}
QPushButton#ghost:disabled {{ color: #44444f; }}
QPushButton#danger {{ color: #fca5a5; }}
QComboBox {{ background: {C_SURF2}; border: 1px solid {C_BORDER}; border-radius: 10px; padding: 6px 10px; }}
QComboBox:hover {{ border-color: {C_BORDER2}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url(ARROW_PNG); width: 12px; height: 12px; margin-right: 10px; }}
QComboBox QAbstractItemView {{ background: {C_SURF2}; border: 1px solid {C_BORDER2}; outline: none; padding: 4px;
                               selection-background-color: #2e2a4a; }}
QSlider {{ min-height: 18px; }}
QSlider::groove:horizontal {{ height: 4px; background: {C_BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {C_ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: white; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QSlider::handle:horizontal:hover {{ background: #ddd6fe; }}
QMenu {{ background: {C_SURF2}; border: 1px solid {C_BORDER2}; border-radius: 10px; padding: 5px; }}
QMenu::item {{ padding: 7px 26px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: #2e2a4a; }}
QMenu::item:disabled {{ color: #55556a; }}
QMenu::separator {{ height: 1px; background: {C_BORDER}; margin: 4px 6px; }}
QProgressBar {{ background: {C_BORDER}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {C_ACCENT}; border-radius: 4px; }}
QLabel#h1 {{ font-family: 'Segoe UI Variable Display', 'Segoe UI'; font-size: 22px; font-weight: 700; }}
QLabel#h2 {{ font-family: 'Segoe UI Variable Display', 'Segoe UI'; font-size: 16px; font-weight: 700; }}
QLabel#h3 {{ font-size: 13px; font-weight: 600; }}
QLabel#muted {{ color: {C_MUTED}; }}
QLabel#section {{ color: {C_MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QLabel#value {{ color: {C_MUTED}; font-size: 12px; font-weight: 600; }}
QLabel#time {{ font-family: 'Cascadia Mono', 'Consolas'; font-size: 13px; font-weight: 600; }}
"""


def alpha(c, a):
    c = QColor(c)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


def mix(c1, c2, t):
    c1, c2 = QColor(c1), QColor(c2)
    t = max(0.0, min(1.0, t))
    return QColor(int(c1.red() + (c2.red() - c1.red()) * t),
                  int(c1.green() + (c2.green() - c1.green()) * t),
                  int(c1.blue() + (c2.blue() - c1.blue()) * t))


def make_anim(owner, setter, ms=180, curve=QEasingCurve.OutCubic):
    a = QVariantAnimation(owner)
    a.setDuration(ms)
    a.setEasingCurve(curve)
    a.valueChanged.connect(setter)
    return a


def run_anim(a, start, end):
    a.stop()
    a.setStartValue(float(start))
    a.setEndValue(float(end))
    a.start()


def font(px, weight=QFont.Normal, base=None):
    f = QFont(base) if base else QFont()
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


def fmt_time(t, frac=True):
    t = round(max(0.0, t), 1 if frac else 0)
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:04.1f}" if frac else f"{int(m):02d}:{int(s):02d}"


def label(text, obj=None):
    l = QLabel(text)
    if obj:
        l.setObjectName(obj)
    return l


def styled_menu(parent):
    m = QMenu(parent)
    m.setWindowFlags(m.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    m.setAttribute(Qt.WA_TranslucentBackground)
    return m


# ── Icons ───────────────────────────────────────────────────────────────────
def draw_icon(p: QPainter, kind, r: QRectF, color, filled=False):
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    col = QColor(color)
    pen = QPen(col, 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    cx, cy = r.center().x(), r.center().y()

    def line(x1, y1, x2, y2):
        p.drawLine(QPointF(x + w * x1, y + h * y1), QPointF(x + w * x2, y + h * y2))

    if kind == "film":
        p.drawRoundedRect(QRectF(x, y + h * 0.15, w, h * 0.7), 2.5, 2.5)
        line(0.28, 0.15, 0.28, 0.85)
        line(0.72, 0.15, 0.72, 0.85)
    elif kind == "text":
        line(0.15, 0.18, 0.85, 0.18)
        line(0.5, 0.18, 0.5, 0.85)
        line(0.35, 0.85, 0.65, 0.85)
    elif kind == "sparkle":
        path = QPainterPath()
        path.moveTo(cx, y)
        path.quadTo(cx, cy, x + w, cy)
        path.quadTo(cx, cy, cx, y + h)
        path.quadTo(cx, cy, x, cy)
        path.quadTo(cx, cy, cx, y)
        p.drawPath(path)
    elif kind == "filter":
        rr = w * 0.27
        for ox, oy in ((-0.17, -0.12), (0.17, -0.12), (0, 0.17)):
            p.drawEllipse(QPointF(cx + ox * w, cy + oy * h), rr, rr)
    elif kind == "transition":
        p.drawRoundedRect(QRectF(x, y + h * 0.2, w * 0.55, h * 0.6), 2, 2)
        p.drawRoundedRect(QRectF(x + w * 0.45, y + h * 0.2, w * 0.55, h * 0.6), 2, 2)
    elif kind == "music":
        line(0.38, 0.75, 0.38, 0.12)
        line(0.38, 0.12, 0.85, 0.02)
        line(0.85, 0.02, 0.85, 0.65)
        p.drawEllipse(QPointF(x + w * 0.26, y + h * 0.78), w * 0.13, w * 0.13)
        p.drawEllipse(QPointF(x + w * 0.73, y + h * 0.68), w * 0.13, w * 0.13)
    elif kind in ("undo", "redo"):
        def X(v):
            return x + w * (v if kind == "undo" else 1 - v)
        path = QPainterPath()
        path.moveTo(X(0.2), y + h * 0.38)
        path.lineTo(X(0.62), y + h * 0.38)
        path.cubicTo(X(0.98), y + h * 0.38, X(0.98), y + h * 0.88, X(0.62), y + h * 0.88)
        path.lineTo(X(0.35), y + h * 0.88)
        p.drawPath(path)
        p.drawLine(QPointF(X(0.2), y + h * 0.38), QPointF(X(0.4), y + h * 0.18))
        p.drawLine(QPointF(X(0.2), y + h * 0.38), QPointF(X(0.4), y + h * 0.58))
    elif kind in ("split", "scissors"):
        p.drawEllipse(QPointF(x + w * 0.27, y + h * 0.78), w * 0.15, h * 0.15)
        p.drawEllipse(QPointF(x + w * 0.73, y + h * 0.78), w * 0.15, h * 0.15)
        line(0.36, 0.66, 0.74, 0.04)
        line(0.64, 0.66, 0.26, 0.04)
    elif kind == "layers":
        for k in (0.0, 0.3):
            path = QPainterPath()
            path.moveTo(cx, y + h * (0.1 + k))
            path.lineTo(x + w, y + h * (0.32 + k))
            path.lineTo(cx, y + h * (0.54 + k))
            path.lineTo(x, y + h * (0.32 + k))
            path.closeSubpath()
            p.drawPath(path)
    elif kind == "smile":
        p.drawEllipse(r.adjusted(w * 0.05, h * 0.05, -w * 0.05, -h * 0.05))
        p.drawArc(QRectF(x + w * 0.28, y + h * 0.3, w * 0.44, h * 0.42), -20 * 16, -140 * 16)
        p.setBrush(col)
        p.drawEllipse(QPointF(x + w * 0.36, y + h * 0.38), w * 0.04, h * 0.04)
        p.drawEllipse(QPointF(x + w * 0.64, y + h * 0.38), w * 0.04, h * 0.04)
    elif kind == "cc":
        p.drawRoundedRect(QRectF(x, y + h * 0.15, w, h * 0.7), 3, 3)
        f = QFont()
        f.setPixelSize(max(6, int(h * 0.42)))
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(x, y + h * 0.15, w, h * 0.7), Qt.AlignCenter, "CC")
    elif kind == "camera":
        p.drawRoundedRect(QRectF(x, y + h * 0.25, w, h * 0.62), 3, 3)
        line(0.32, 0.25, 0.4, 0.1)
        line(0.4, 0.1, 0.6, 0.1)
        line(0.6, 0.1, 0.68, 0.25)
        p.drawEllipse(QPointF(cx, y + h * 0.56), w * 0.18, h * 0.18)
    elif kind == "freeze":
        for a in (0, 60, 120):
            rad = math.radians(a)
            dx_, dy_ = math.cos(rad) * w * 0.45, math.sin(rad) * h * 0.45
            p.drawLine(QPointF(cx - dx_, cy - dy_), QPointF(cx + dx_, cy + dy_))
    elif kind == "trash":
        line(0.12, 0.22, 0.88, 0.22)
        line(0.38, 0.22, 0.42, 0.06)
        line(0.62, 0.22, 0.58, 0.06)
        path = QPainterPath()
        path.moveTo(x + w * 0.2, y + h * 0.22)
        path.lineTo(x + w * 0.27, y + h)
        path.lineTo(x + w * 0.73, y + h)
        path.lineTo(x + w * 0.8, y + h * 0.22)
        p.drawPath(path)
    elif kind == "play":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        path = QPainterPath()
        path.moveTo(x + w * 0.22, y + h * 0.1)
        path.lineTo(x + w * 0.22, y + h * 0.9)
        path.lineTo(x + w * 0.9, y + h * 0.5)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "pause":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(x + w * 0.2, y + h * 0.1, w * 0.2, h * 0.8), 1.5, 1.5)
        p.drawRoundedRect(QRectF(x + w * 0.6, y + h * 0.1, w * 0.2, h * 0.8), 1.5, 1.5)
    elif kind in ("start", "end"):
        p.setBrush(col)
        if kind == "start":
            line(0.15, 0.15, 0.15, 0.85)
            path = QPainterPath()
            path.moveTo(x + w * 0.85, y + h * 0.15)
            path.lineTo(x + w * 0.85, y + h * 0.85)
            path.lineTo(x + w * 0.3, y + h * 0.5)
        else:
            line(0.85, 0.15, 0.85, 0.85)
            path = QPainterPath()
            path.moveTo(x + w * 0.15, y + h * 0.15)
            path.lineTo(x + w * 0.15, y + h * 0.85)
            path.lineTo(x + w * 0.7, y + h * 0.5)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "plus":
        line(0.5, 0.12, 0.5, 0.88)
        line(0.12, 0.5, 0.88, 0.5)
    elif kind == "export":
        line(0.5, 0.05, 0.5, 0.62)
        line(0.28, 0.27, 0.5, 0.05)
        line(0.72, 0.27, 0.5, 0.05)
        path = QPainterPath()
        path.moveTo(x + w * 0.1, y + h * 0.5)
        path.lineTo(x + w * 0.1, y + h * 0.92)
        path.lineTo(x + w * 0.9, y + h * 0.92)
        path.lineTo(x + w * 0.9, y + h * 0.5)
        p.drawPath(path)
    elif kind == "folder":
        path = QPainterPath()
        path.moveTo(x, y + h * 0.2)
        path.lineTo(x + w * 0.38, y + h * 0.2)
        path.lineTo(x + w * 0.5, y + h * 0.34)
        path.lineTo(x + w, y + h * 0.34)
        path.lineTo(x + w, y + h * 0.88)
        path.lineTo(x, y + h * 0.88)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "image":
        p.drawRoundedRect(QRectF(x, y + h * 0.12, w, h * 0.76), 2.5, 2.5)
        path = QPainterPath()
        path.moveTo(x + w * 0.1, y + h * 0.78)
        path.lineTo(x + w * 0.38, y + h * 0.45)
        path.lineTo(x + w * 0.58, y + h * 0.65)
        path.lineTo(x + w * 0.72, y + h * 0.52)
        path.lineTo(x + w * 0.9, y + h * 0.78)
        p.drawPath(path)
        p.drawEllipse(QPointF(x + w * 0.72, y + h * 0.32), w * 0.07, w * 0.07)
    elif kind == "zoom_in" or kind == "zoom_out":
        p.drawEllipse(QPointF(x + w * 0.42, y + h * 0.42), w * 0.32, w * 0.32)
        line(0.66, 0.66, 0.92, 0.92)
        line(0.28, 0.42, 0.56, 0.42)
        if kind == "zoom_in":
            line(0.42, 0.28, 0.42, 0.56)
    elif kind == "volume":
        p.setBrush(col)
        path = QPainterPath()
        path.moveTo(x, y + h * 0.36)
        path.lineTo(x + w * 0.22, y + h * 0.36)
        path.lineTo(x + w * 0.48, y + h * 0.12)
        path.lineTo(x + w * 0.48, y + h * 0.88)
        path.lineTo(x + w * 0.22, y + h * 0.64)
        path.lineTo(x, y + h * 0.64)
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(x + w * 0.4, y + h * 0.25, w * 0.4, h * 0.5), -50 * 16, 100 * 16)
    elif kind == "mute":
        draw_icon(p, "volume", QRectF(x, y, w * 0.85, h), color)
        line(0.65, 0.35, 0.95, 0.65)
        line(0.95, 0.35, 0.65, 0.65)
    elif kind == "magnet":
        p.drawArc(QRectF(x + w * 0.12, y + h * 0.3, w * 0.76, h * 0.66), 0, -180 * 16)
        line(0.12, 0.63, 0.12, 0.12)
        line(0.88, 0.63, 0.88, 0.12)
        line(0.12, 0.3, 0.3, 0.3)
        line(0.7, 0.3, 0.88, 0.3)
    elif kind == "dup":
        p.drawRoundedRect(QRectF(x, y + h * 0.3, w * 0.7, h * 0.7), 2, 2)
        p.drawRoundedRect(QRectF(x + w * 0.3, y, w * 0.7, h * 0.7), 2, 2)
    elif kind == "check":
        line(0.15, 0.55, 0.4, 0.8)
        line(0.4, 0.8, 0.88, 0.22)
    p.restore()


def icon(kind, color=C_TEXT, size=16):
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    draw_icon(p, kind, QRectF(4, 4, size * 2 - 8, size * 2 - 8), color)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


def app_icon_pixmap(size=256):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 256
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor("#8b6dff"))
    g.setColorAt(1, QColor("#5b3ff0"))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 60 * s, 60 * s)
    p.setBrush(QColor(255, 255, 255, 245))
    path = QPainterPath()
    path.moveTo(92 * s, 70 * s)
    path.lineTo(92 * s, 186 * s)
    path.lineTo(190 * s, 128 * s)
    path.closeSubpath()
    p.drawPath(path)
    pen = QPen(QColor("#5b3ff0"), 14 * s)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(70 * s, 196 * s), QPointF(196 * s, 60 * s))
    pen = QPen(QColor(255, 255, 255), 7 * s)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(70 * s, 196 * s), QPointF(196 * s, 60 * s))
    p.end()
    return pm


def make_arrow_png(path):
    pm = QPixmap(24, 24)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(C_MUTED), 2.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    pp = QPainterPath()
    pp.moveTo(6, 9)
    pp.lineTo(12, 15)
    pp.lineTo(18, 9)
    p.drawPath(pp)
    p.end()
    pm.save(str(path))
    return path


# ── Widgets ─────────────────────────────────────────────────────────────────
class Surface(QFrame):
    def __init__(self, radius=12, bg=C_SURF, border=C_BORDER):
        super().__init__()
        self.radius, self.bg, self.border = radius, QColor(bg), QColor(border)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(self.bg)
        p.setPen(QPen(self.border, 1) if self.border.alpha() else Qt.NoPen)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self.radius, self.radius)


class Flat(QWidget):
    def __init__(self, color, border=None, side="right"):
        super().__init__()
        self.color, self.border, self.side = QColor(color), border, side

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), self.color)
        if self.border:
            c = QColor(self.border)
            if self.side == "right":
                p.fillRect(self.width() - 1, 0, 1, self.height(), c)
            elif self.side == "left":
                p.fillRect(0, 0, 1, self.height(), c)
            elif self.side == "bottom":
                p.fillRect(0, self.height() - 1, self.width(), 1, c)
            elif self.side == "top":
                p.fillRect(0, 0, self.width(), 1, c)


class Toggle(QWidget):
    toggled = Signal(bool)

    def __init__(self, on=False):
        super().__init__()
        self.on = on
        self.k = 1.0 if on else 0.0
        self.setFixedSize(36, 20)
        self.setCursor(Qt.PointingHandCursor)
        self._a = make_anim(self, self._sk, 170)

    def _sk(self, v):
        self.k = v
        self.update()

    def set_on(self, on, emit=True):
        self.on = on
        run_anim(self._a, self.k, 1.0 if on else 0.0)
        if emit:
            self.toggled.emit(on)

    def mousePressEvent(self, e):
        self.set_on(not self.on)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.NoPen)
        p.setBrush(mix("#33333f", C_ACCENT, self.k))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QRectF(r.left() + 3 + (r.width() - d - 6) * self.k, r.top() + 3, d, d))


class SliderField(QWidget):
    """Beschriftung + Wert + Slider für Fließkommawerte. Doppelklick = Standardwert."""
    changed = Signal(float)

    def __init__(self, title, value, lo, hi, default=None, fmt="{:.0f}", factor=100, suffix=""):
        super().__init__()
        self.lo, self.hi, self.factor, self.fmt, self.suffix = lo, hi, factor, fmt, suffix
        self.default = value if default is None else default
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        top = QHBoxLayout()
        top.addWidget(label(title, "h3"))
        top.addStretch()
        self.val = label("", "value")
        top.addWidget(self.val)
        v.addLayout(top)
        self.s = QSlider(Qt.Horizontal)
        self.s.setRange(int(lo * factor), int(hi * factor))
        self.s.setValue(int(round(value * factor)))
        self.s.setCursor(Qt.PointingHandCursor)
        self.s.valueChanged.connect(self._ch)
        v.addWidget(self.s)
        self._show(value)
        self.setToolTip("Doppelklick zum Zurücksetzen")

    def _show(self, x):
        self.val.setText(self.fmt.format(x) + self.suffix)

    def _ch(self, iv):
        x = iv / self.factor
        self._show(x)
        self.changed.emit(x)

    def set_value(self, x):
        self.s.blockSignals(True)
        self.s.setValue(int(round(x * self.factor)))
        self.s.blockSignals(False)
        self._show(x)

    def mouseDoubleClickEvent(self, e):
        self.s.setValue(int(round(self.default * self.factor)))


class Swatches(QWidget):
    picked = Signal(str)

    def __init__(self, current, colors=SWATCHES, allow_none=False):
        super().__init__()
        self.colors = (["none"] if allow_none else []) + list(colors) + ["custom"]
        self.current = current or "none"
        self.setFixedHeight(28)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(len(self.colors) * 24)

    def _rects(self):
        n = len(self.colors)
        step = min(26.0, self.width() / n)
        return [QRectF(i * step + 1, 2, step - 4, step - 4) for i in range(n)]

    def mousePressEvent(self, e):
        for c, r in zip(self.colors, self._rects()):
            if r.adjusted(-2, -2, 2, 2).contains(e.position()):
                if c == "custom":
                    col = QColorDialog.getColor(QColor(self.current if self.current != "none" else "#ffffff"),
                                                self, "Farbe wählen")
                    if not col.isValid():
                        return
                    c = col.name()
                self.current = c
                self.update()
                self.picked.emit("" if c == "none" else c)
                return

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for c, r in zip(self.colors, self._rects()):
            sel = c.lower() == str(self.current).lower()
            cr = r.adjusted(3, 3, -3, -3)
            if c == "none":
                p.setPen(QPen(QColor(C_MUTED), 1.4))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(cr)
                p.drawLine(QPointF(cr.left() + 3, cr.bottom() - 3), QPointF(cr.right() - 3, cr.top() + 3))
            elif c == "custom":
                g = QLinearGradient(cr.topLeft(), cr.bottomRight())
                g.setColorAt(0, QColor("#ff3fd8"))
                g.setColorAt(0.5, QColor("#ffd60a"))
                g.setColorAt(1, QColor("#06b6d4"))
                p.setPen(Qt.NoPen)
                p.setBrush(g)
                p.drawEllipse(cr)
            else:
                p.setPen(QPen(QColor(C_BORDER2), 1))
                p.setBrush(QColor(c))
                p.drawEllipse(cr)
            if sel:
                p.setPen(QPen(QColor(C_ACCENT), 2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(r)
        if self.current not in self.colors and self.current != "none":
            pass


class Segmented(QWidget):
    changed = Signal(int)

    def __init__(self, items, index=0):
        super().__init__()
        self.items, self.idx, self.hover = items, index, -1
        self.hl = float(index)
        self.setFixedHeight(32)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self._a = make_anim(self, self._sh, 220)

    def _sh(self, v):
        self.hl = v
        self.update()

    def _at(self, x):
        return max(0, min(len(self.items) - 1, int(x / (self.width() / len(self.items)))))

    def set_index(self, i, emit=True):
        if i != self.idx:
            run_anim(self._a, self.hl, i)
            self.idx = i
            if emit:
                self.changed.emit(i)

    def mousePressEvent(self, e):
        self.set_index(self._at(e.position().x()))

    def mouseMoveEvent(self, e):
        self.hover = self._at(e.position().x())
        self.update()

    def leaveEvent(self, e):
        self.hover = -1
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(C_BORDER), 1))
        p.setBrush(QColor(C_SURF))
        p.drawRoundedRect(r, 9, 9)
        w = r.width() / len(self.items)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2a2545"))
        p.drawRoundedRect(QRectF(r.left() + self.hl * w + 3, r.top() + 3, w - 6, r.height() - 6), 7, 7)
        p.setFont(font(12, QFont.DemiBold, self.font()))
        for i, t in enumerate(self.items):
            p.setPen(QColor(C_TEXT) if i == self.idx or i == self.hover else QColor(C_MUTED))
            p.drawText(QRectF(r.left() + i * w, r.top(), w, r.height()), Qt.AlignCenter, t)


class Card(QWidget):
    """Klickbare Auswahlkarte für Filter/Effekte/Übergänge/Text-Vorlagen."""
    clicked = Signal(str)

    def __init__(self, key, title, painter_fn=None, height=86):
        super().__init__()
        self.key, self.title, self.painter_fn = key, title, painter_fn
        self.selected = False
        self.hover = 0.0
        self.sel = 0.0
        self.image = None
        self.setFixedHeight(height)
        self.setCursor(Qt.PointingHandCursor)
        self._ha = make_anim(self, self._s("hover"), 140)
        self._sa = make_anim(self, self._s("sel"), 180)

    def _s(self, attr):
        def f(v):
            setattr(self, attr, v)
            self.update()
        return f

    def set_selected(self, on):
        if on != self.selected:
            self.selected = on
            run_anim(self._sa, self.sel, 1.0 if on else 0.0)

    def enterEvent(self, e):
        run_anim(self._ha, self.hover, 1)

    def leaveEvent(self, e):
        run_anim(self._ha, self.hover, 0)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.key)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        prev = QRectF(r.left(), r.top(), r.width(), r.height() - 22)
        path = QPainterPath()
        path.addRoundedRect(prev, 9, 9)
        p.save()
        p.setClipPath(path)
        p.fillRect(prev, QColor(C_SURF2))
        if self.image is not None and not self.image.isNull():
            img = self.image
            s = max(prev.width() / img.width(), prev.height() / img.height())
            w, h = img.width() * s, img.height() * s
            p.drawImage(QRectF(prev.center().x() - w / 2, prev.center().y() - h / 2, w, h), img)
        elif self.painter_fn:
            self.painter_fn(p, prev, self.hover)
        p.fillRect(prev, QColor(255, 255, 255, int(14 * self.hover)))
        p.restore()
        p.setPen(QPen(mix(C_BORDER, C_ACCENT, self.sel), 1 + self.sel))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(prev.adjusted(0.5, 0.5, -0.5, -0.5), 9, 9)
        p.setFont(font(12, QFont.DemiBold, self.font()))
        p.setPen(QColor(C_TEXT) if self.selected else QColor("#c4c4d0"))
        fm = QFontMetrics(p.font())
        p.drawText(QRectF(r.left() + 2, prev.bottom() + 3, r.width() - 4, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(self.title, Qt.ElideRight, int(r.width() - 4)))


class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setStyleSheet(f"background: {C_SURF2}; border: 1px solid {C_BORDER2}; border-radius: 10px;"
                           "padding: 9px 16px; font-weight: 600;")
        self.eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.eff)
        self.eff.setOpacity(0)
        self.hide()
        self.base_y = 0
        self._a = make_anim(self, self._step, 200)
        self._timer = QTimer(self, singleShot=True, timeout=lambda: run_anim(self._a, 1, 0))
        self._a.finished.connect(lambda: self.hide() if self.eff.opacity() < 0.05 else None)

    def _step(self, v):
        self.eff.setOpacity(v)
        self.move(self.x(), int(self.base_y + 8 * (1 - v)))

    def show_msg(self, text, ms=2600):
        par = self.parentWidget()
        self.setText(text)
        self.adjustSize()
        self.base_y = 70
        self.move((par.width() - self.width()) // 2, self.base_y)
        self.show()
        self.raise_()
        run_anim(self._a, self.eff.opacity(), 1)
        self._timer.start(ms)


class Dim(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.v = 0.0
        self.hide()
        self._a = make_anim(self, self._sv, 200)
        self._a.finished.connect(lambda: self.hide() if self.v < 0.01 else None)

    def _sv(self, v):
        self.v = v
        self.update()

    def fade(self, on):
        if on:
            self.setGeometry(self.parentWidget().rect())
            self.show()
            self.raise_()
        run_anim(self._a, self.v, 1.0 if on else 0.0)

    def paintEvent(self, e):
        QPainter(self).fillRect(self.rect(), QColor(5, 5, 8, int(170 * self.v)))


class DialogBase(QDialog):
    def __init__(self, parent, title, width=480):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.card = Surface(16, "#16161e", C_BORDER2)
        outer.addWidget(self.card)
        self.body = QVBoxLayout(self.card)
        self.body.setContentsMargins(26, 22, 26, 22)
        self.body.setSpacing(10)
        self.title_lbl = label(title, "h2")
        self.body.addWidget(self.title_lbl)
        self.body.addSpacing(4)
        self.setFixedWidth(width)
        self.setWindowOpacity(0)
        self._fa = make_anim(self, self.setWindowOpacity, 180)

    def showEvent(self, e):
        super().showEvent(e)
        g = self.parentWidget().window().frameGeometry()
        self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)
        run_anim(self._fa, 0, 1)


def row(*widgets, spacing=8, stretch_first=False):
    h = QHBoxLayout()
    h.setSpacing(spacing)
    for i, w in enumerate(widgets):
        if w is None:
            h.addStretch()
        elif isinstance(w, int):
            h.addSpacing(w)
        else:
            h.addWidget(w, 1 if (stretch_first and i == 0) else 0)
    return h


def icon_button(kind, tip, cb, size=32, obj="ghost"):
    b = QPushButton()
    b.setObjectName(obj)
    b.setIcon(icon(kind, C_TEXT, 16))
    b.setFixedSize(size, size)
    b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    b.clicked.connect(cb)
    return b
