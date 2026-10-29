"""Manual straightening contracts across preview, source edits and print export."""

import math
from pathlib import Path
from unittest.mock import patch
import unittest

import numpy as np
from PIL import Image, ImageDraw

import test_qt_app as fixtures
from portrait import frame_portrait


class RotationExportTests(unittest.TestCase):
    """Check print geometry independently of the interactive preview renderer."""

    def test_clockwise_rotation_with_zoom_position_and_brightness(self):
        """Known source markers land at independently computed output coordinates."""
        source = Image.new("RGBA", (200, 120))
        ImageDraw.Draw(source).ellipse((136, 56, 144, 64), fill="red")
        original = source.tobytes()
        for degrees in (-180, -90, -30, -12.5, 0, 12.5, 30, 90, 180):
            with self.subTest(degrees=degrees):
                result = frame_portrait(
                    source, 1.2, (0.05, -0.05), rotation=degrees, brightness=0.5
                )
                angle = math.radians(degrees)
                x = round(660 + 40 * 7.2 * math.cos(angle))
                y = round(540 + 40 * 7.2 * math.sin(angle))
                self.assertEqual(result.getpixel((x, y)), (127, 0, 0))
                self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(source.tobytes(), original)

    def test_invalid_rotation_is_rejected(self):
        """Non-finite and out-of-range rotation cannot reach the affine renderer."""
        for value in (-181, 181, float("nan"), float("inf")):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "rotation"),
            ):
                frame_portrait(Image.new("RGBA", (20, 20), "red"), rotation=value)


class RotationInterfaceTests(unittest.TestCase):
    """Exercise the new slider through the real Qt document and save paths."""

    setUp = fixtures.QtAppTests.setUp
    tearDown = fixtures.QtAppTests.tearDown

    def test_rotation_preview_matches_export_and_reuses_cached_pixels(self):
        """Both rotation signs move a marker alike without image preparation jobs."""
        source = Image.new("RGBA", (200, 120))
        ImageDraw.Draw(source).ellipse((134, 54, 146, 66), fill="red")
        self.window.set_cutout(source)
        fixtures.wait_until(lambda: not self.window.jobs.busy)
        count = self.window.crop.prepare_count
        for degrees in (-25, 25):
            self.window.rotation_slider.setValue(degrees * 10)
            self.window.crop.set_framing(zoom=1.2, offset=(0.05, -0.05))
            fixtures.QT_APP.processEvents()
            preview = self.window.crop.grab().toImage()
            pixels = np.array(self.window.crop.export())
            ys, xs = np.where((pixels[:, :, 0] > 220) & (pixels[:, :, 1] < 30))
            frame = self.window.crop.frame_rect()
            expected_x = frame.left() + xs.mean() / 1200 * frame.width()
            expected_y = frame.top() + ys.mean() / 1200 * frame.height()
            reds = [
                (x, y)
                for y in range(preview.height())
                for x in range(preview.width())
                if (color := preview.pixelColor(x, y)).red() > 220
                and color.green() < 30
            ]
            self.assertTrue(reds)
            self.assertAlmostEqual(np.mean(reds, axis=0)[0], expected_x, delta=2)
            self.assertAlmostEqual(np.mean(reds, axis=0)[1], expected_y, delta=2)
            self.assertEqual(self.window.crop.rotation, degrees)
        self.assertEqual(self.window.crop.prepare_count, count)
        self.assertEqual(self.window.rotation_label.text(), "25.0°")

    def test_rotation_save_edit_reset_and_new_photo(self):
        """Saving includes rotation; cleanup preserves it; resets and new photos clear it."""
        source = Image.new("RGBA", (200, 120), "red")
        self.window.set_cutout(source)
        self.window.rotation_slider.setValue(155)
        edited = source.copy()
        edited.putpixel((100, 60), (255, 0, 0, 0))
        self.window.apply_edits(edited)
        self.assertEqual(self.window.crop.rotation, 15.5)
        expected = self.window.crop.export()
        path = Path(self.temp.name) / "Rotated_2x2.png"
        with (
            patch("app.ask_person_name", return_value="Rotated"),
            patch("app.QFileDialog.getSaveFileName", return_value=(str(path), "PNG")),
        ):
            self.window.save()
            self.assertFalse(self.window.rotation_slider.isEnabled())
            fixtures.wait_until(lambda: not self.window.busy)
        self.assertTrue(self.window.rotation_slider.isEnabled())
        with Image.open(path) as saved:
            self.assertEqual(saved.tobytes(), expected.tobytes())
            self.assertAlmostEqual(saved.info["dpi"][0], 600, delta=1)
        self.window.reset_button.click()
        self.assertEqual(self.window.crop.rotation, 0)
        self.assertEqual(self.window.rotation_slider.value(), 0)
        self.assertEqual(self.window.crop.cutout.getpixel((100, 60))[3], 0)
        self.window.rotation_slider.setValue(-200)
        self.window.set_photo(Image.new("RGB", (30, 40)), None, "New")
        self.assertEqual(self.window.crop.rotation, 0)
        self.assertFalse(self.window.rotation_slider.isEnabled())

    def test_level_guide_is_preview_only(self):
        """The alignment line is visible after rotation but never printed."""
        self.window.set_cutout(Image.new("RGBA", (200, 200), "red"))
        self.window.rotation_slider.setValue(120)
        fixtures.wait_until(lambda: not self.window.jobs.busy)
        preview = self.window.crop.grab().toImage()
        frame = self.window.crop.frame_rect()
        y = round(frame.top() + frame.height() * 0.38)
        blues = [
            preview.pixelColor(x, row).blue()
            for row in range(y - 1, y + 2)
            for x in range(
                round(frame.center().x()) - 20, round(frame.center().x()) + 20
            )
        ]
        self.assertGreater(max(blues), 100)
        saved = np.array(self.window.crop.export())
        self.assertFalse(
            np.any((saved[:, :, 2] > saved[:, :, 0]) & (saved[:, :, 0] < 200))
        )


if __name__ == "__main__":
    unittest.main()
