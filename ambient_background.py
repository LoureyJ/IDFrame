"""Short, occasional mesh-gradient blooms behind opaque application controls."""

import math
import random
import time

from PySide6.QtCore import QEvent, QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget


class AmbientBackground(QWidget):
    """Paint lightweight decoration without touching document or preview pixels."""

    COLORS = ("#4389ed", "#28becb", "#a17bea", "#e8b554")
    IDLE_MS = 10000
    PROCESSING_MS = 5000

    def __init__(self, parent=None, *, theme="Light"):
        """Create idle/frame timers; actual animation starts only while visible."""
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self._theme = theme
        self._random = random.Random()
        self._paused, self._active = False, False
        self._processing = False
        self._last_interaction_bloom = float("-inf")
        self._anchor = (0.5, 0.1)
        self._colors = self.COLORS[:3]
        self._duration, self._started = 0.0, 0.0
        self._watched_window = None
        self.idle_timer = QTimer(self)
        self.idle_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.idle_timer.timeout.connect(self.start_bloom)
        self.frame_timer = QTimer(self)
        self.frame_timer.setInterval(50)
        self.frame_timer.timeout.connect(self._tick)

    def set_theme(self, name):
        """Apply theme-specific intensity immediately without rebuilding any controls."""
        self._theme = name
        self.update()

    def set_paused(self, paused):
        """Suspend the effect and resume with a fresh interval."""
        self._paused = bool(paused)
        self._sync_schedule()

    def set_processing(self, processing):
        """Trigger a bloom at task start and keep it visible through completion."""
        if processing == self._processing:
            return
        self._processing = processing
        self.idle_timer.stop()
        self._sync_schedule()
        if processing:
            self.start_bloom()

    def _can_animate(self):
        """Avoid background repainting for hidden and minimized windows."""
        return not self._paused and self.isVisible() and not self.window().isMinimized()

    def _bounds(self):
        """Bound all drifting gradient lobes so frame updates repaint a limited region."""
        extent = max(self.width(), self.height()) * 0.65
        x, y = self._anchor[0] * self.width(), self._anchor[1] * self.height()
        return (
            QRectF(x - extent, y - extent, extent * 2, extent * 2)
            .toAlignedRect()
            .intersected(self.rect())
        )

    def _clear(self):
        """Discard a bloom and cancel queued animation work without catch-up bursts."""
        self.idle_timer.stop()
        self.frame_timer.stop()
        if self._active:
            self._active = False
            self.update(self._bounds())

    def _sync_schedule(self):
        """Schedule burst starts independently of their animation duration."""
        if not self._can_animate():
            self._clear()
        elif not self.idle_timer.isActive():
            self.idle_timer.start(self.PROCESSING_MS if self._processing else self.IDLE_MS)

    def start_bloom(self):
        """Start one bloom at a random location across the workspace."""
        if not self._can_animate() or self._active:
            return False
        self._anchor = (self._random.random(), self._random.random())
        self._colors = self._random.sample(self.COLORS, 3)
        self._duration = self._random.uniform(3, 5)
        self._started = time.monotonic()
        self._active = True
        self.frame_timer.start()
        self.update(self._bounds())
        return True

    def _tick(self):
        """Advance the brief burst, then return to idle without a continuous render loop."""
        if not self._can_animate():
            self._clear()
            return
        if time.monotonic() - self._started >= self._duration:
            self._active = False
            self.frame_timer.stop()
            self.update(self._bounds())
        else:
            self.update(self._bounds())

    def paintEvent(self, event):
        """Blend native radial gradients onto the theme background beneath child widgets."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().window())
        if not self._active:
            return
        progress = min(
            1.0, max(0.0, (time.monotonic() - self._started) / self._duration)
        )
        opacity = math.sin(math.pi * progress) * (
            0.80 if self._theme == "Dark" else 0.74
        )
        # Wide lobes reach the exposed workspace around opaque photo cards.
        radius = max(self.width(), self.height()) * (0.36 + 0.08 * progress)
        for index, value in enumerate(self._colors):
            phase = index * math.tau / 3 + progress * 0.5
            center = QPointF(
                self._anchor[0] * self.width() + math.cos(phase) * radius * 0.3,
                self._anchor[1] * self.height() + math.sin(phase) * radius * 0.3,
            )
            spread = radius * (1 + index * 0.08)
            color = QColor(value)
            color.setAlphaF(opacity)
            transparent = QColor(value)
            transparent.setAlpha(0)
            gradient = QRadialGradient(center, spread)
            gradient.setColorAt(0, color)
            gradient.setColorAt(0.22, color)
            gradient.setColorAt(1, transparent)
            painter.fillRect(
                QRectF(
                    center.x() - spread, center.y() - spread, spread * 2, spread * 2
                ),
                gradient,
            )

    def showEvent(self, event):
        """Watch top-level minimize/restore events and begin a new visible idle interval."""
        window = self.window()
        if self._watched_window is not window:
            if self._watched_window is not None:
                self._watched_window.removeEventFilter(self)
            self._watched_window = window
            window.installEventFilter(self)
            self.installEventFilter(self)
            for widget in self.findChildren(QWidget):
                widget.installEventFilter(self)
        super().showEvent(event)
        self._sync_schedule()

    def hideEvent(self, event):
        """Release animation timers as soon as the workspace becomes hidden."""
        self._clear()
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        """Handle visibility and respond to workspace input without consuming it."""
        if (
            watched is self._watched_window
            and event.type() == QEvent.Type.WindowStateChange
        ):
            self._sync_schedule()
        elif self._can_animate() and event.type() in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.KeyPress,
            QEvent.Type.Wheel,
        ):
            if not self._processing:
                self.idle_timer.start(self.IDLE_MS)
            now = time.monotonic()
            if now - self._last_interaction_bloom >= 5 and self.start_bloom():
                self._last_interaction_bloom = now
        return super().eventFilter(watched, event)
