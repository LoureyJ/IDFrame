"""Separate Qt alpha cleanup editor with precise source-space erasing and history."""

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QLabel,
    QDialogButtonBox,
    QApplication,
)

from mask_document import MaskDocument
from qt_preview import image_to_qt


class EraserView(QWidget):
    """Paint cached pixels and translate pointer actions to original alpha coordinates."""

    history_changed = Signal()

    def __init__(self, document, parent=None):
        """Create a private editable image cache and independent viewing transform."""
        super().__init__(parent)
        self.document = document
        self.pixels = image_to_qt(document.image())
        self.scale_factor = 1.0
        self.pan = QPointF()
        self.diameter = max(
            1, min(40, min(self.pixels.width(), self.pixels.height()) / 5)
        )
        self._auto_fit = True
        self._pointer = None
        self._previous = None
        self._pan_start = None
        self._space = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(200, 150)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def fit_image(self):
        """Fit the full portrait without changing mask pixels or edit history."""
        self.scale_factor = max(
            0.001,
            min(
                (self.width() - 24) / self.pixels.width(),
                (self.height() - 24) / self.pixels.height(),
            ),
        )
        self.pan = QPointF()
        self._auto_fit = True
        self.update()

    def resizeEvent(self, event):
        """Refit cached pixels only while the user has not chosen a custom view."""
        if self._auto_fit:
            self.fit_image()
        self.update()

    def _anchor(self):
        """Locate the top-left image corner in viewport coordinates."""
        return (
            QPointF(
                (self.width() - self.pixels.width() * self.scale_factor) / 2,
                (self.height() - self.pixels.height() * self.scale_factor) / 2,
            )
            + self.pan
        )

    def source_to_view(self, point):
        """Map a source pixel to the current zoomed and panned viewport."""
        return self._anchor() + point * self.scale_factor

    def view_to_source(self, point):
        """Invert the exact paint transform so erasing follows the displayed cursor."""
        return (point - self._anchor()) / self.scale_factor

    def _refresh_patch(self, bounds):
        """Replace only changed cached pixels, including fully transparent erasures."""
        if bounds is None:
            return
        patch = image_to_qt(self.document.image(bounds))
        painter = QPainter(self.pixels)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(QPointF(bounds[0], bounds[1]), patch)
        painter.end()
        self.update()

    def erase_at(self, start, end, *, source_coordinates=False):
        """Apply an interpolated brush segment at either viewport or source coordinates."""
        if not source_coordinates:
            start, end = self.view_to_source(start), self.view_to_source(end)
        # Bound each supersampled brush allocation even after a large pointer jump.
        delta = end - start
        steps = max(
            1, int(max(abs(delta.x()), abs(delta.y())) / max(32, self.diameter * 2)) + 1
        )
        for step in range(steps):
            first, last = start + delta * (step / steps), start + delta * (
                (step + 1) / steps
            )
            bounds = self.document.erase_segment(
                (first.x(), first.y()), (last.x(), last.y()), self.diameter
            )
            self._refresh_patch(bounds)

    def finish_stroke(self):
        """Commit one pointer gesture as one reversible edit operation."""
        self.document.end_stroke()
        self._previous = None
        self.history_changed.emit()

    def undo(self):
        """Restore the previous alpha patch and update history controls."""
        self.finish_stroke()
        self._refresh_patch(self.document.undo())
        self.history_changed.emit()

    def redo(self):
        """Reapply the next alpha patch and update history controls."""
        self.finish_stroke()
        self._refresh_patch(self.document.redo())
        self.history_changed.emit()

    def paintEvent(self, event):
        """Scale existing cached pixels through Qt and overlay the actual brush diameter."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), self.palette().alternateBase())
        anchor = self._anchor()
        bounds = QRectF(
            anchor.x(),
            anchor.y(),
            self.pixels.width() * self.scale_factor,
            self.pixels.height() * self.scale_factor,
        )
        painter.fillRect(bounds, QColor("white"))
        painter.drawImage(bounds, self.pixels)
        if self._pointer is not None and self._pan_start is None:
            radius = self.diameter * self.scale_factor / 2
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("white"), 3))
            painter.drawEllipse(self._pointer, radius, radius)
            painter.setPen(QPen(QColor("#17243b"), 1))
            painter.drawEllipse(self._pointer, radius, radius)

    def mousePressEvent(self, event):
        """Start erasing with left-click or panning with middle/Space-drag."""
        self.setFocus()
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._space
        ):
            self._pan_start = event.position(), QPointF(self.pan)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.LeftButton:
            self._previous = event.position()
            self.erase_at(self._previous, self._previous)

    def mouseMoveEvent(self, event):
        """Keep the pointer preview live and interpolate each stroke or pan delta."""
        self._pointer = event.position()
        if self._pan_start is not None:
            start, origin = self._pan_start
            self.pan = origin + event.position() - start
            self._auto_fit = False
        elif self._previous is not None:
            self.erase_at(self._previous, event.position())
            self._previous = event.position()
        self.update()

    def mouseReleaseEvent(self, event):
        """Finish the current edit gesture without creating history for panning."""
        if self._previous is not None:
            self.finish_stroke()
        self._pan_start = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def leaveEvent(self, event):
        """Hide the brush circle when the pointer leaves the editor viewport."""
        self._pointer = None
        self.update()

    def wheelEvent(self, event):
        """Zoom around the pointer while keeping its source pixel anchored."""
        self.finish_stroke()
        source = self.view_to_source(event.position())
        multiplier = 1.15 ** (event.angleDelta().y() / 120)
        self.scale_factor = max(0.01, min(32.0, self.scale_factor * multiplier))
        self.pan += event.position() - self.source_to_view(source)
        self._auto_fit = False
        self.update()
        event.accept()

    def keyPressEvent(self, event):
        """Use Space as a temporary hand tool without changing edit mode."""
        if event.key() == Qt.Key.Key_Space:
            self._space = True
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Release the temporary hand tool after Space is released."""
        if event.key() == Qt.Key.Key_Space:
            self._space = False
            event.accept()
        else:
            super().keyReleaseEvent(event)


class CleanupEditor(QDialog):
    """Own an isolated editing session that is committed only through Apply."""

    def __init__(self, cutout, parent=None):
        """Create a resizable editor with eraser, brush size, and reversible history."""
        super().__init__(parent)
        self.setWindowTitle("IDFrame — Edit portrait")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        available = QApplication.primaryScreen().availableGeometry()
        width, height = available.width() - 16, available.height() - 40
        self.setMinimumSize(min(650, width), min(440, height))
        self.resize(min(1000, width), min(740, height))
        self.document = MaskDocument(cutout)
        self.view = EraserView(self.document)
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Eraser size"))
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(1, max(10, min(500, max(cutout.size) // 4)))
        self.size_slider.setValue(round(self.view.diameter))
        self.size_slider.setAccessibleName("Eraser diameter in source pixels")
        toolbar.addWidget(self.size_slider, 1)
        self.size_label = QLabel()
        toolbar.addWidget(self.size_label)
        self.undo_button, self.redo_button = QPushButton("Undo"), QPushButton("Redo")
        self.undo_button.clicked.connect(self.view.undo)
        self.redo_button.clicked.connect(self.view.redo)
        toolbar.addWidget(self.undo_button)
        toolbar.addWidget(self.redo_button)
        fit = QPushButton("Fit")
        fit.clicked.connect(self.view.fit_image)
        toolbar.addWidget(fit)
        layout.addLayout(toolbar)
        layout.addWidget(self.view, 1)
        instructions = QLabel(
            "Drag to erase · Wheel to zoom · Middle-drag or Space-drag to pan · Original photo preserved"
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self.accept
        )
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.size_slider.valueChanged.connect(self.set_brush_size)
        self.view.history_changed.connect(self._update_history)
        self.shortcuts = []
        for sequence, action in (
            ("Ctrl+Z", self.view.undo),
            ("Ctrl+Y", self.view.redo),
            ("Ctrl+Shift+Z", self.view.redo),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(action)
            self.shortcuts.append(shortcut)
        self.set_brush_size(self.size_slider.value())
        self._update_history()

    def set_brush_size(self, value):
        """Set diameter in original pixels and immediately redraw the brush indicator."""
        self.view.diameter = value
        self.size_label.setText(str(value) + " px")
        self.view.update()

    def _update_history(self):
        """Enable Undo and Redo only when their corresponding patch histories exist."""
        self.undo_button.setEnabled(self.document.can_undo)
        self.redo_button.setEnabled(self.document.can_redo)

    def edited_image(self):
        """Return an independent cutout for the caller to commit after acceptance."""
        return self.document.image()

    def accept(self):
        """Finish any active stroke before committing this editor session."""
        self.view.finish_stroke()
        super().accept()
