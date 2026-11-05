"""Ambient blooms stay visible in both themes without changing portrait work."""

import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

import test_qt_app as fixtures
from qt_preview import qt_to_image


class AmbientBackgroundTests(unittest.TestCase):
    """Exercise rendered effects and their processing/window lifecycle."""

    setUp = fixtures.QtAppTests.setUp
    tearDown = fixtures.QtAppTests.tearDown

    def test_bloom_renders_in_both_themes_without_touching_photos_or_layout(self):
        """Visible background color changes leave opaque preview and output pixels intact."""
        window = self.window
        window.set_cutout(Image.new("RGBA", (300, 400), (70, 100, 130, 255)))
        window.crop.set_framing(zoom=1.4, rotation=12, brightness=0.8)
        fixtures.wait_until(lambda: not window.jobs.busy)
        canvas = window.background
        for theme in ("Light", "Dark"):
            with self.subTest(theme=theme):
                window.change_theme(theme)
                canvas.set_paused(True)
                baseline = np.array(qt_to_image(canvas.grab().toImage()))
                before = window.crop.grab().toImage()
                exported = window.crop.export().tobytes()
                geometry = window.save_button.geometry()
                prepared = window.crop.prepare_count
                canvas.set_paused(False)
                canvas._random.seed(7)
                with patch("ambient_background.time.monotonic", return_value=100):
                    self.assertTrue(canvas.start_bloom())
                with patch(
                    "ambient_background.time.monotonic",
                    return_value=100 + canvas._duration / 2,
                ):
                    blooming = np.array(qt_to_image(canvas.grab().toImage()))
                    self.assertEqual(window.crop.grab().toImage(), before)
                difference = np.abs(blooming.astype(int) - baseline.astype(int))
                self.assertGreater(difference[:, :, :3].max(), 8)
                self.assertEqual(window.crop.export().tobytes(), exported)
                self.assertEqual(window.save_button.geometry(), geometry)
                self.assertEqual(window.crop.prepare_count, prepared)

    def test_processing_hidden_and_minimized_windows_stop_animation(self):
        """No frame timer continues through processing, hiding or minimizing."""
        window = self.window
        canvas = window.background
        self.assertTrue(canvas.start_bloom())
        window._set_busy(True)
        self.assertFalse(canvas.frame_timer.isActive())
        self.assertFalse(canvas.idle_timer.isActive())
        self.assertFalse(canvas.start_bloom())
        window._set_busy(False)
        self.assertTrue(canvas.idle_timer.isActive())
        window.showMinimized()
        fixtures.QT_APP.processEvents()
        self.assertFalse(canvas.idle_timer.isActive())
        self.assertFalse(canvas.frame_timer.isActive())
        window.showNormal()
        fixtures.QT_APP.processEvents()
        self.assertTrue(canvas.idle_timer.isActive())
        window.hide()
        self.assertFalse(canvas.frame_timer.isActive())
        self.assertFalse(canvas.idle_timer.isActive())
        window.show()
        fixtures.QT_APP.processEvents()
        self.assertTrue(canvas.idle_timer.isActive())

    def test_finished_bloom_returns_to_idle_without_queuing_animations(self):
        """Only short bursts repaint; the idle period has no frame timer."""
        canvas = self.window.background
        with patch("ambient_background.time.monotonic", return_value=50):
            canvas.start_bloom()
        self.assertTrue(canvas.frame_timer.isActive())
        self.assertFalse(canvas.idle_timer.isActive())
        self.assertGreaterEqual(canvas._duration, 3)
        self.assertLessEqual(canvas._duration, 5)
        with patch("ambient_background.time.monotonic", return_value=56):
            canvas._tick()
        self.assertFalse(canvas.frame_timer.isActive())
        self.assertTrue(canvas.idle_timer.isActive())
        self.assertGreaterEqual(canvas.idle_timer.interval(), 8000)
        self.assertLessEqual(canvas.idle_timer.interval(), 15000)


if __name__ == "__main__":
    unittest.main()
