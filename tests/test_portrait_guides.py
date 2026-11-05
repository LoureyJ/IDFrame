"""Positioning overlays are adjustable, visible in both themes and never exported."""

import unittest
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtGui import QImage, QColor

import test_qt_app as fixtures
from qt_preview import qt_to_image


class PortraitGuideTests(unittest.TestCase):
    """Check guide drawing independently of photo-editing state."""

    setUp = fixtures.QtAppTests.setUp
    tearDown = fixtures.QtAppTests.tearDown

    def test_toggle_and_drag_guides_do_not_change_export_or_framing(self):
        """Headroom and eye handles move only guide geometry, not portrait pixels."""
        window = self.window
        window.set_cutout(Image.new("RGBA", (200, 200), "red"))
        fixtures.wait_until(lambda: not window.jobs.busy)
        before = window.crop.export().tobytes()
        offset = window.crop.offset
        for theme in ("Light", "Dark"):
            window.change_theme(theme)
            window.guide_checkbox.setChecked(True)
            shown = window.crop.grab().toImage()
            window.guide_checkbox.setChecked(False)
            self.assertNotEqual(shown, window.crop.grab().toImage())
            self.assertEqual(window.crop.export().tobytes(), before)
        window.guide_checkbox.setChecked(True)
        frame = window.crop.frame_rect()
        for kind, initial in [
            ("eye", window.crop.guide_eye),
            ("headroom", window.crop.guide_headroom),
        ]:
            point = QPoint(
                round(frame.right() - 10), round(frame.top() + initial * frame.height())
            )
            QTest.mousePress(window.crop, Qt.MouseButton.LeftButton, pos=point)
            QTest.mouseMove(window.crop, point + QPoint(0, 10))
            QTest.mouseRelease(
                window.crop, Qt.MouseButton.LeftButton, pos=point + QPoint(0, 10)
            )
            value = getattr(window.crop, "guide_" + kind)
            self.assertGreater(value, initial)
        self.assertEqual(window.crop.offset, offset)
        self.assertEqual(window.crop.export().tobytes(), before)

    def test_camera_graphics_layer_and_review_hide_all_overlays(self):
        """Native camera view uses the selected aspect ratio and clean still review."""
        from camera_view import CameraView

        view = CameraView(output_size=(827, 1063))
        view.resize(640, 480)
        view.show()
        fixtures.QT_APP.processEvents()
        image = QImage(640, 480, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))
        view.show_review(image)
        clean = np.array(qt_to_image(view.grab().toImage())).astype(int)
        self.assertFalse(
            np.any((clean[:, :, 2] > clean[:, :, 0] + 20) & (clean[:, :, 2] > 100))
        )
        view.show_live()
        live = np.array(qt_to_image(view.grab().toImage())).astype(int)
        self.assertTrue(
            np.any((live[:, :, 2] > live[:, :, 0] + 20) & (live[:, :, 2] > 100))
        )
        self.assertAlmostEqual(
            view.guide_item.frame.width() / view.guide_item.frame.height(), 827 / 1063
        )
        self.assertTrue(view.guide_item.isVisible())
        view.show_review(image)
        self.assertFalse(view.guide_item.isVisible())
        view.close()
        view.deleteLater()


if __name__ == "__main__":
    unittest.main()
