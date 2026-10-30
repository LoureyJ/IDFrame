"""Photo-size presets keep print dimensions, preview geometry and naming in sync."""

from pathlib import Path
from unittest.mock import patch
import unittest

import numpy as np
from PIL import Image, ImageDraw
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest

import test_qt_app as fixtures
from photo_sizes import PHOTO_SIZES
from photo_naming import portrait_filename


class PhotoSizeInterfaceTests(unittest.TestCase):
    """Exercise real selectors, non-square preview transforms and PNG exports."""

    setUp = fixtures.QtAppTests.setUp
    tearDown = fixtures.QtAppTests.tearDown

    def test_presets_export_correct_size_filename_and_keep_adjustments(self):
        """Every format saves its stated 600-DPI size without resetting edits."""
        window = self.window
        self.assertEqual(window.size_combo.currentData(), "2x2")
        source = Image.new("RGBA", (200, 300), "red")
        source.putpixel((100, 150), (255, 0, 0, 0))
        window.set_cutout(source)
        window.crop.set_framing(
            zoom=1.4, offset=(0.05, -0.03), brightness=0.75, rotation=12
        )
        for key, pixels in [
            ("2x2", (1200, 1200)),
            ("1x1", (600, 600)),
            ("passport", (827, 1063)),
        ]:
            with self.subTest(key=key):
                window.size_combo.setCurrentIndex(window.size_combo.findData(key))
                self.assertEqual(PHOTO_SIZES[key].pixels, pixels)
                self.assertEqual(window.crop.export().size, pixels)
                self.assertEqual(window.crop.rotation, 12)
                self.assertEqual(window.crop.brightness, 0.75)
                self.assertEqual(window.crop.zoom, 1.4)
                self.assertEqual(window.crop.offset, (0.05, -0.03))
                self.assertEqual(window.crop.cutout.tobytes(), source.tobytes())
                expected = window.crop.export()
                path = Path(self.temp.name) / portrait_filename("Juan", key)
                with (
                    patch("app.ask_person_name", return_value="Juan"),
                    patch(
                        "app.QFileDialog.getSaveFileName",
                        return_value=(str(path), "PNG"),
                    ),
                ):
                    window.save()
                    self.assertFalse(window.size_combo.isEnabled())
                    fixtures.wait_until(lambda: not window.busy)
                with Image.open(path) as saved:
                    self.assertEqual(saved.size, pixels)
                    self.assertEqual(saved.mode, "RGB")
                    self.assertAlmostEqual(saved.info["dpi"][0], 600, delta=1)
                    self.assertEqual(saved.tobytes(), expected.tobytes())
                self.assertIn(str(pixels[0]), window.export_label.text())
        self.assertEqual(portrait_filename("Juan"), "Juan_2x2.png")
        self.assertEqual(portrait_filename("Juan", "1x1"), "Juan_1x1.png")
        self.assertEqual(
            portrait_filename("Juan", "passport"), "Juan_Passport_35x45mm.png"
        )
        with self.assertRaises(ValueError):
            portrait_filename("Juan", "../bad")
        window.reset_button.click()
        self.assertEqual(window.size_combo.currentData(), "passport")
        window.set_photo(Image.new("RGB", (100, 100)), None, "Next")
        self.assertEqual(window.size_combo.currentData(), "passport")
        self.assertEqual(window.crop.output_size, (827, 1063))

    def test_passport_preview_and_export_agree_and_drag_uses_frame_height(self):
        """A tall preview shares print geometry and maps vertical dragging correctly."""
        window = self.window
        source = Image.new("RGBA", (200, 300))
        ImageDraw.Draw(source).ellipse((124, 144, 136, 156), fill="red")
        window.set_cutout(source)
        window.size_combo.setCurrentIndex(window.size_combo.findData("passport"))
        window.crop.set_framing(zoom=1.3, offset=(0.02, 0.04), rotation=15)
        fixtures.wait_until(lambda: not window.jobs.busy)
        frame = window.crop.frame_rect()
        self.assertAlmostEqual(frame.width() / frame.height(), 827 / 1063, places=5)
        preview = window.crop.grab().toImage()
        reds = [
            (x, y)
            for y in range(preview.height())
            for x in range(preview.width())
            if (color := preview.pixelColor(x, y)).red() > 220 and color.green() < 30
        ]
        output = np.array(window.crop.export())
        ys, xs = np.where((output[:, :, 0] > 220) & (output[:, :, 1] < 30))
        point = np.mean(reds, axis=0)
        self.assertAlmostEqual(
            point[0], frame.left() + xs.mean() / 827 * frame.width(), delta=2
        )
        self.assertAlmostEqual(
            point[1], frame.top() + ys.mean() / 1063 * frame.height(), delta=2
        )
        previous = window.crop.offset
        start = frame.center().toPoint()
        end = start + QPointF(0, 20).toPoint()
        QTest.mousePress(window.crop, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(window.crop, end)
        QTest.mouseRelease(window.crop, Qt.MouseButton.LeftButton, pos=end)
        self.assertAlmostEqual(
            window.crop.offset[1] - previous[1], 20 / frame.height(), places=4
        )


if __name__ == "__main__":
    unittest.main()
