"""Paint cached portraits through Qt transforms; resize never resamples full sources."""

import math

from PIL import Image, ImageOps
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QImage, QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget

from portrait import frame_portrait, MIN_BRIGHTNESS, MAX_BRIGHTNESS


def image_to_qt(image):
    """Return an owning QImage so no borrowed Pillow byte buffer can expire."""
    rgba = image.convert("RGBA")
    return QImage(
        rgba.tobytes(),
        rgba.width,
        rgba.height,
        rgba.width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()


def qt_to_image(image):
    """Copy clipboard pixels into a Pillow image independently of Qt buffer lifetime."""
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombytes(
        "RGBA",
        (rgba.width(), rgba.height()),
        bytes(rgba.bits()),
        "raw",
        "RGBA",
        rgba.bytesPerLine(),
    )


class PhotoPreview(QWidget):
    """Keep crop geometry in normalized coordinates while painting cached image data."""

    framing_changed = Signal()

    def __init__(self, jobs, parent=None, *, framing=True):
        """Initialize a latest-only preview pipeline and optional crop interaction."""
        super().__init__(parent)
        self.jobs = jobs
        self.framing = framing
        self.cutout = None
        self.zoom, self.offset, self.brightness = 1.0, (0.0, 0.0), 1.0
        self.rotation = 0.0
        self.display = QImage()
        self.prepare_count = 0
        self._generation = 0
        self._active = False
        self._pending = None
        self._thumbnail = None
        self._drag = None
        self.setMinimumSize(100, 100)
        self.setCursor(
            Qt.CursorShape.OpenHandCursor if framing else Qt.CursorShape.ArrowCursor
        )

    def set_image(self, cutout, *, reset=True):
        """Replace document pixels and schedule one bounded display preparation job."""
        self.cutout = cutout
        self._thumbnail = None
        self.display = QImage()
        if reset:
            self.zoom, self.offset, self.brightness = 1.0, (0.0, 0.0), 1.0
            self.rotation = 0.0
        self._request()
        self.framing_changed.emit()
        self.update()

    def _request(self):
        """Replace pending work instead of enqueuing every intermediate slider state."""
        self._generation += 1
        self._pending = (
            (self._generation, self.cutout, self.brightness, self._thumbnail)
            if self.cutout is not None
            else None
        )
        self._start_pending()

    def _start_pending(self):
        """Prepare at most one image while retaining only the newest pending request."""
        if self._active or self._pending is None:
            return
        generation, source, brightness, thumbnail = self._pending
        self._pending = None
        self._active = True
        self.prepare_count += 1

        def prepare():
            """Resize once and adjust bounded cached pixels outside the GUI thread."""
            cached = (
                thumbnail
                if thumbnail is not None
                else ImageOps.contain(
                    source, (1600, 1600), Image.Resampling.LANCZOS
                ).convert("RGBA")
            )
            adjusted = cached
            if brightness != 1:
                levels = [min(255, int(value * brightness)) for value in range(256)]
                adjusted = cached.convert("RGB").point(levels * 3)
                adjusted.putalpha(cached.getchannel("A"))
            return cached, image_to_qt(adjusted)

        def ready(value, error):
            """Ignore obsolete pixels, then start only the newest requested state."""
            self._active = False
            if generation == self._generation and error is None:
                self._thumbnail, self.display = value
                self.update()
            self._start_pending()

        self.jobs.submit(prepare, ready)

    def set_framing(self, *, zoom=None, offset=None, brightness=None, rotation=None):
        """Clamp interactive adjustments and avoid rerendering pixels for pan or zoom."""
        if rotation is not None:
            if not math.isfinite(rotation):
                raise ValueError("Invalid portrait rotation")
            self.rotation = max(-180.0, min(180.0, float(rotation)))
        if zoom is not None:
            self.zoom = max(1.0, min(8.0, float(zoom)))
        if offset is not None:
            self.offset = tuple(float(value) for value in offset)
        if self.cutout is not None:
            maximum = max(self.cutout.size)
            limits = tuple(
                (1 + self.zoom * dimension / maximum) / 2 - 0.02
                for dimension in self.cutout.size
            )
            self.offset = tuple(
                max(-limit, min(limit, value))
                for limit, value in zip(limits, self.offset)
            )
        if brightness is not None:
            value = max(MIN_BRIGHTNESS, min(MAX_BRIGHTNESS, float(brightness)))
            if value != self.brightness:
                self.brightness = value
                self._request()
        self.framing_changed.emit()
        self.update()

    def reset(self):
        """Reset crop, rotation and lighting while preserving applied alpha corrections."""
        self.set_framing(zoom=1, offset=(0.0, 0.0), brightness=1, rotation=0)

    def frame_rect(self):
        """Locate the centered square print frame within the available widget area."""
        side = max(1, min(self.width(), self.height()) - 16)
        return QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)

    def paintEvent(self, event):
        """Draw cached pixels with native Qt scaling and no full-source conversion."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), self.palette().alternateBase())
        if self.display.isNull():
            painter.setPen(self.palette().placeholderText().color())
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                (
                    "Your 2 × 2 portrait will appear here"
                    if self.framing
                    else "Open or paste a portrait photo"
                ),
            )
            return
        frame = (
            self.frame_rect()
            if self.framing
            else QRectF(self.rect()).adjusted(8, 8, -8, -8)
        )
        painter.setClipRect(frame)
        if self.framing:
            painter.fillRect(frame, QColor("white"))
        scale = (
            min(
                frame.width() / self.display.width(),
                frame.height() / self.display.height(),
            )
            * self.zoom
        )
        width, height = self.display.width() * scale, self.display.height() * scale
        center = frame.center() + QPointF(
            self.offset[0] * frame.width(), self.offset[1] * frame.height()
        )
        painter.save()
        painter.translate(center)
        painter.rotate(self.rotation)
        painter.drawImage(QRectF(-width / 2, -height / 2, width, height), self.display)
        painter.restore()
        if self.framing and self.rotation != 0:
            # A level reference belongs only to the preview, never the saved photo.
            y = frame.top() + frame.height() * 0.38
            painter.setPen(QPen(QColor("#2479bb"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(frame.left(), y), QPointF(frame.right(), y))

    def mousePressEvent(self, event):
        """Start crop panning without mutating any image pixels."""
        if (
            self.framing
            and self.cutout is not None
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._drag = event.position(), self.offset
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        """Map a pointer delta into normalized print-frame offsets."""
        if self._drag is not None:
            start, offset = self._drag
            delta = event.position() - start
            side = self.frame_rect().width()
            self.set_framing(
                offset=(offset[0] + delta.x() / side, offset[1] + delta.y() / side)
            )

    def mouseReleaseEvent(self, event):
        """End crop dragging and restore the resting pointer shape."""
        self._drag = None
        self.setCursor(
            Qt.CursorShape.OpenHandCursor
            if self.framing
            else Qt.CursorShape.ArrowCursor
        )

    def wheelEvent(self, event):
        """Zoom framing without scheduling image preparation or AI inference."""
        if self.framing and self.cutout is not None:
            self.set_framing(
                zoom=self.zoom * (1.1 if event.angleDelta().y() > 0 else 1 / 1.1)
            )
            event.accept()

    def export(self):
        """Render original-resolution pixels using the established print geometry."""
        if self.cutout is None:
            raise ValueError("Remove a background before saving")
        return frame_portrait(
            self.cutout,
            self.zoom,
            self.offset,
            brightness=self.brightness,
            rotation=self.rotation,
        )
