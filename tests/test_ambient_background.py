"""Ambient blooms stay visible in both themes without changing portrait work."""

import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

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
                    anchors = ((0.1, 0.1), (0.9, 0.1), (0.5, 0.5), (0.1, 0.9), (0.9, 0.9))
                    for anchor in anchors:
                        with self.subTest(anchor=anchor):
                            canvas._anchor = anchor
                            blooming = np.array(qt_to_image(canvas.grab().toImage()))
                            difference = np.abs(blooming.astype(int) - baseline.astype(int))
                            changed = difference[:, :, :3].max(axis=2) >= 25
                            self.assertGreater(
                                np.count_nonzero(changed), 0.01 * changed.size
                            )
                    self.assertEqual(window.crop.grab().toImage(), before)
                self.assertEqual(window.crop.export().tobytes(), exported)
                self.assertEqual(window.save_button.geometry(), geometry)
                self.assertEqual(window.crop.prepare_count, prepared)

    def test_processing_triggers_animation_but_hidden_windows_stop_it(self):
        """Processing immediately starts a burst while hiding/minimizing still stops repainting."""
        window = self.window
        canvas = window.background
        window._set_busy(True)
        self.assertTrue(canvas.frame_timer.isActive())
        self.assertTrue(canvas.idle_timer.isActive())
        self.assertEqual(canvas.idle_timer.interval(), 5000)
        self.assertFalse(canvas.start_bloom())
        window._set_busy(False)
        self.assertTrue(canvas.frame_timer.isActive())
        self.assertTrue(canvas.idle_timer.isActive())
        self.assertEqual(canvas.idle_timer.interval(), 10000)
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
        self.assertTrue(canvas.idle_timer.isActive())
        self.assertGreaterEqual(canvas._duration, 3)
        self.assertLessEqual(canvas._duration, 5)
        with patch("ambient_background.time.monotonic", return_value=56):
            canvas._tick()
        self.assertFalse(canvas.frame_timer.isActive())
        self.assertTrue(canvas.idle_timer.isActive())
        self.assertEqual(canvas.idle_timer.interval(), 10000)

    def test_idle_timer_fires_without_manual_start_and_interactions_trigger_bursts(self):
        """Exercise the real timeout signal rather than testing only manually started blooms."""
        canvas = self.window.background
        self.assertEqual(canvas.idle_timer.interval(), 10000)
        canvas.idle_timer.setInterval(30)
        fixtures.wait_until(lambda: canvas.frame_timer.isActive())
        canvas.set_paused(True)
        canvas.set_paused(False)
        QTest.mouseClick(self.window.theme_buttons['Dark'], Qt.MouseButton.LeftButton)
        self.assertTrue(canvas.frame_timer.isActive())

    def test_busy_worker_keeps_burst_visible_after_fast_completion(self):
        """A brief operation must not erase its activity burst as soon as the worker returns."""
        self.window._work(lambda: 'done', lambda result: None, 'Processing fixture')
        self.assertTrue(self.window.background.frame_timer.isActive())
        fixtures.wait_until(lambda: not self.window.busy)
        self.assertTrue(self.window.background.frame_timer.isActive())

    def test_processing_effects_replace_idle_bloom_and_render_in_both_themes(self):
        """Actions remain visible and visually distinct even after fast completion."""
        canvas = self.window.background
        for theme in ("Light", "Dark"):
            with self.subTest(theme=theme):
                self.window.change_theme(theme)
                canvas.set_paused(True)
                baseline = np.array(qt_to_image(canvas.grab().toImage()), dtype=int)
                canvas.set_paused(False)
                self.assertTrue(canvas.start_bloom())
                frames = []
                for action in ("paste", "remove", "save"):
                    with patch("ambient_background.time.monotonic", return_value=100):
                        canvas.set_processing(True, action)
                        canvas.set_processing(False)
                    with patch("ambient_background.time.monotonic", return_value=101.2):
                        frame = np.array(qt_to_image(canvas.grab().toImage()), dtype=int)
                    for reference in (baseline, *frames):
                        changed = np.abs(frame - reference)[:, :, :3].max(axis=2) >= 25
                        self.assertGreater(np.count_nonzero(changed), 0.01 * changed.size)
                    frames.append(frame)


if __name__ == "__main__":
    unittest.main()
