"""Compare cached current/P3M export frames without changing the selected model."""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class ComparisonView(QWidget):
    """Paint a prepared square export without resampling original portrait pixels."""

    def __init__(self, image, parent=None):
        """Retain the owning worker-created QImage for all subsequent repaints."""
        super().__init__(parent)
        self.image = image
        self.setMinimumSize(100, 100)

    def paintEvent(self, event):
        """Fit the cached image into a square while preserving print proportions."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().alternateBase())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        side = max(1, min(self.width(), self.height()) - 16)
        frame = QRectF(
            (self.width() - side) / 2, (self.height() - side) / 2, side, side
        )
        painter.drawImage(frame, self.image)


class ModelPreviewDialog(QDialog):
    """Require an explicit choice before an experimental result replaces a cutout."""

    def __init__(self, current, candidate, parent=None):
        """Build a bounded two-column comparison using identical export adjustments."""
        super().__init__(parent)
        self.setWindowTitle("IDFrame — P3M test preview")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        available = QApplication.primaryScreen().availableGeometry()
        width, height = available.width() - 16, available.height() - 40
        self.setMinimumSize(min(620, width), min(400, height))
        self.resize(min(1080, width), min(720, height))
        layout = QVBoxLayout(self)
        explanation = QLabel(
            "Compare the same crop and brightness. Your default removal model stays unchanged."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        columns = QHBoxLayout()
        self.current_view, self.candidate_view = ComparisonView(
            current
        ), ComparisonView(candidate)
        for title, view in (
            ("Current result", self.current_view),
            ("P3M · Experimental", self.candidate_view),
        ):
            column = QVBoxLayout()
            column.addWidget(QLabel(title))
            column.addWidget(view, 1)
            columns.addLayout(column, 1)
        layout.addLayout(columns, 1)
        warning = QLabel(
            "P3M can erase parts of faces or clothing in difficult photos. Applying replaces current cleanup edits. Check the result, then use Edit and Save in the main window."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        buttons = QDialogButtonBox()
        keep = buttons.addButton("Keep current", QDialogButtonBox.ButtonRole.RejectRole)
        use = buttons.addButton(
            "Use P3M for this photo", QDialogButtonBox.ButtonRole.AcceptRole
        )
        use.setProperty("accent", True)
        use.setAutoDefault(False)
        keep.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
