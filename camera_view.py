"""Layer video and guide graphics in one scene, avoiding native-window overlay issues."""

from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsItem, QGraphicsScene, QGraphicsView
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem

from portrait_guides import fit_frame, paint_guides


class CameraGuideItem(QGraphicsItem):
    """Paint a silhouette and dim outside its target frame above the live video."""

    def __init__(self, output_size, eye, headroom):
        """Keep illustration geometry separate from camera source pixels."""
        super().__init__()
        self.output_size, self.eye, self.headroom = output_size, eye, headroom
        self.bounds, self.frame = QRectF(), QRectF()
        self.setZValue(1)

    def set_bounds(self, bounds):
        """Recompute the selected aspect ratio when the camera's stream size changes."""
        self.prepareGeometryChange()
        self.bounds = bounds
        inset = bounds.adjusted(
            bounds.width() * 0.03,
            bounds.height() * 0.03,
            -bounds.width() * 0.03,
            -bounds.height() * 0.03,
        )
        self.frame = fit_frame(inset, self.output_size)
        self.update()

    def boundingRect(self):
        """Expose the exact scene region occupied by this overlay."""
        return self.bounds

    def paint(self, painter, option, widget=None):
        """Render an overlay without modifying the captured camera frame."""
        outside = QPainterPath()
        outside.setFillRule(Qt.FillRule.OddEvenFill)
        outside.addRect(self.bounds)
        outside.addRect(self.frame)
        painter.fillPath(outside, QColor(0, 0, 0, 65))
        paint_guides(painter, self.frame, eye=self.eye, headroom=self.headroom)


class CameraView(QGraphicsView):
    """Share one native graphics scene between live guides and clean still review."""

    def __init__(
        self, parent=None, *, output_size=(1200, 1200), eye=0.38, headroom=0.08
    ):
        """Compose native video, a guide layer, and a separately owned review pixmap."""
        super().__init__(parent)
        scene = QGraphicsScene(self)
        self.setScene(scene)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QColor("#10151c"))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.video_item = QGraphicsVideoItem()
        scene.addItem(self.video_item)
        self.guide_item = CameraGuideItem(output_size, eye, headroom)
        scene.addItem(self.guide_item)
        self.review_item = scene.addPixmap(QPixmap())
        self.review_item.setVisible(False)
        self._reviewing = False
        self.video_item.nativeSizeChanged.connect(self._live_size_changed)
        self._set_size(QSizeF(640, 480))

    def videoSink(self):
        """Return the native video sink consumed by the media capture session."""
        return self.video_item.videoSink()

    def _set_size(self, size):
        """Fit both source video and guides without stretching pixels or letterboxing errors."""
        if size.width() <= 0 or size.height() <= 0:
            return
        bounds = QRectF(0, 0, size.width(), size.height())
        self.video_item.setSize(size)
        self.guide_item.set_bounds(bounds)
        self.setSceneRect(bounds)
        self.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)

    def _live_size_changed(self, size):
        """Ignore delayed source-size changes while a captured still is being reviewed."""
        if not self._reviewing:
            self._set_size(size)

    def show_review(self, image):
        """Display original still pixels with every live guide and dimming layer hidden."""
        self._reviewing = True
        self.video_item.setVisible(False)
        self.guide_item.setVisible(False)
        self.review_item.setPixmap(QPixmap.fromImage(image))
        self.review_item.setVisible(True)
        self._set_size(QSizeF(image.size()))

    def show_live(self):
        """Restore the camera composition after discarding the previous still preview."""
        self._reviewing = False
        self.review_item.setVisible(False)
        self.review_item.setPixmap(QPixmap())
        self.video_item.setVisible(True)
        self.guide_item.setVisible(True)
        size = self.video_item.nativeSize()
        self._set_size(size if size.isValid() else QSizeF(640, 480))

    def resizeEvent(self, event):
        """Refit the same scene on resize without changing captured source resolution."""
        super().resizeEvent(event)
        if self.scene() is not None:
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
