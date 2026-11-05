"""Shared positioning aids; geometry is illustrative, not a PRC measurement standard."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen

PRC_REMINDERS = (
    "PRC/LERIS: 2×2, plain white background, collared attire, "
    "photo within 6 months. Keep face and ears clear; avoid glasses and shadows."
)
GUIDE_HELP = (
    "Positioning aid only; not a compliance check or official measured template. "
    "Drag the right-edge dots to adjust headroom and eye level. Guides are not printed."
)


def fit_frame(bounds, output_size):
    """Fit the selected print aspect ratio into a source or display rectangle."""
    scale = min(bounds.width() / output_size[0], bounds.height() / output_size[1])
    width, height = output_size[0] * scale, output_size[1] * scale
    return QRectF(
        bounds.center().x() - width / 2, bounds.center().y() - height / 2, width, height
    )


def paint_guides(painter, frame, *, eye=0.38, headroom=0.08, handles=False):
    """Draw a full head/shoulder outline and level references only onto the view."""

    def point(x, y):
        """Map normalized guide coordinates into the current print frame."""
        return QPointF(
            frame.left() + x * frame.width(), frame.top() + y * frame.height()
        )

    chin = min(0.70, eye + (eye - headroom))
    outline = QPainterPath(point(0.08, 0.98))
    outline.cubicTo(point(0.12, 0.85), point(0.30, 0.82), point(0.39, 0.74))
    outline.lineTo(point(0.39, chin))
    outline.cubicTo(
        point(0.23, chin - 0.07), point(0.24, headroom), point(0.50, headroom)
    )
    outline.cubicTo(point(0.76, headroom), point(0.77, chin - 0.07), point(0.61, chin))
    outline.lineTo(point(0.61, 0.74))
    outline.cubicTo(point(0.70, 0.82), point(0.88, 0.85), point(0.92, 0.98))
    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for color, width in (
        (QColor(255, 255, 255, 190), 3.5),
        (QColor(36, 121, 187, 190), 1.5),
    ):
        pen = QPen(color, width)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawPath(outline)
    pen = QPen(QColor(36, 121, 187, 190), 1, Qt.PenStyle.DashLine)
    pen.setCosmetic(True)
    painter.setPen(pen)
    for y in (headroom, eye):
        painter.drawLine(point(0.02, y), point(0.98, y))
    painter.drawLine(point(0.5, 0.02), point(0.5, 0.98))
    if handles:
        painter.setBrush(QColor("white"))
        pen.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        # Draw in device coordinates so handles remain usable at every zoom level.
        for y in (headroom, eye):
            painter.drawEllipse(
                QPointF(frame.right() - 10, frame.top() + y * frame.height()), 4, 4
            )
    painter.restore()
