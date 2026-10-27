"""Qt application regressions for responsive state and safe background work."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect, QPoint

from app import PortraitApp

QT_APP = QApplication.instance() or QApplication([])


def wait_until(predicate, timeout=5):
    """Deliver queued Qt signals until a worker result reaches its GUI owner."""
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        QT_APP.processEvents()
        time.sleep(0.005)
    QT_APP.processEvents()
    if not predicate():
        raise AssertionError("Timed out waiting for Qt work")


class QtAppTests(unittest.TestCase):
    """Keep current photo features correct while replacing the GUI framework."""

    def setUp(self):
        """Create a real Qt window with isolated preferences and no shortcut changes."""
        self.temp = tempfile.TemporaryDirectory()
        self.window = PortraitApp(
            preferences_path=Path(self.temp.name) / "prefs.json", sync_shortcuts=False
        )
        self.window.show()
        QT_APP.processEvents()

    def tearDown(self):
        """Drain owned jobs before disposing the Qt window and fixture files."""
        wait_until(lambda: not self.window.jobs.busy)
        self.window.close()
        QT_APP.processEvents()
        self.temp.cleanup()

    def test_theme_and_resize_preserve_photo_and_do_not_rebuild_preview(self):
        """Repeated appearance/geometry changes reuse prepared image data."""
        source = Image.new("RGBA", (1600, 1200), "red")
        self.window.set_photo(source.convert("RGB"), None, "Fixture")
        self.window.set_cutout(source)
        self.window.crop.set_framing(zoom=2, offset=(0.1, -0.2), brightness=0.75)
        wait_until(lambda: not self.window.jobs.busy)
        count = self.window.crop.prepare_count
        for number in range(50):
            self.window.change_theme("Dark" if number % 2 else "Light")
            self.window.resize(1000 + number % 3 * 30, 700 + number % 2 * 20)
            QT_APP.processEvents()
        self.assertEqual(self.window.crop.prepare_count, count)
        self.assertEqual(self.window.crop.zoom, 2)
        self.assertEqual(self.window.crop.offset, (0.1, -0.2))
        self.assertEqual(self.window.crop.brightness, 0.75)
        self.assertEqual(self.window.photo.size, (1600, 1200))

    def test_new_photo_clears_result_and_adjustments(self):
        """A new source cannot inherit the previous portrait's mask or framing."""
        self.window.set_cutout(Image.new("RGBA", (100, 100), "red"))
        self.window.crop.set_framing(zoom=3, brightness=0.5)
        self.window.set_photo(Image.new("RGB", (70, 100)), None, "New")
        self.assertIsNone(self.window.crop.cutout)
        self.assertEqual(self.window.crop.zoom, 1)
        self.assertFalse(self.window.save_button.isEnabled())
        self.assertFalse(self.window.edit_button.isEnabled())

    def test_background_removal_and_error_recover_controls(self):
        """Worker completion and failure both restore usable input controls."""
        self.window.set_photo(Image.new("RGB", (100, 100)), None, "Ready")
        with patch.object(
            self.window, "process", return_value=Image.new("RGBA", (100, 100), "red")
        ):
            self.window.remove()
            self.assertFalse(self.window.open_button.isEnabled())
            wait_until(lambda: not self.window.busy)
        self.assertTrue(self.window.edit_button.isEnabled())
        self.assertTrue(self.window.save_button.isEnabled())
        with (
            patch.object(self.window, "process", side_effect=ValueError("bad photo")),
            patch("app.QMessageBox.warning"),
        ):
            self.window.remove()
            wait_until(lambda: not self.window.busy)
        self.assertTrue(self.window.open_button.isEnabled())

    def test_stale_result_does_not_replace_new_document(self):
        """An obsolete callback cannot apply its mask to a different source."""
        generation = self.window.generation
        self.window.set_photo(Image.new("RGB", (60, 80)), None, "New")
        self.window.accept_removal(generation, Image.new("RGBA", (10, 10)), None)
        self.assertIsNone(self.window.crop.cutout)

    def test_adjusted_export_and_name_collisions(self):
        """Applied framing saves white 600-DPI RGB PNG without overwriting a file."""
        source = Image.new("RGBA", (100, 50), (100, 120, 140, 255))
        self.window.set_cutout(source)
        self.window.crop.set_framing(brightness=0.5)
        path = Path(self.temp.name) / "Person_2x2.png"
        path.write_bytes(b"existing")
        with (
            patch("app.ask_person_name", return_value="Person"),
            patch("app.QFileDialog.getSaveFileName", return_value=(str(path), "PNG")),
        ):
            self.window.save()
            wait_until(lambda: not self.window.busy)
        self.assertEqual(path.read_bytes(), b"existing")
        with Image.open(path.with_name("Person_2x2_002.png")) as saved:
            self.assertEqual(saved.size, (1200, 1200))
            self.assertEqual(saved.mode, "RGB")
            self.assertAlmostEqual(saved.info["dpi"][0], 600, delta=1)
            self.assertEqual(saved.getpixel((0, 0)), (255, 255, 255))
            self.assertEqual(saved.getpixel((600, 600)), (50, 60, 70))

    def test_small_window_has_save_action_and_radio_modes(self):
        """Small layouts retain the primary action and visible mode selection."""
        self.window.resize(900, 600)
        QT_APP.processEvents()
        self.assertEqual(
            [button.text().split("\n")[0] for button in self.window.mode_buttons],
            ["Auto", "Protect person", "Fine hair"],
        )
        self.assertTrue(self.window.save_button.isVisible())
        self.assertTrue(self.window.status_label.isVisible())

    def test_scaled_screen_contains_window_and_save_geometry(self):
        """Small logical desktops retain a bounded frame and reachable Save button."""
        available = QRect(0, 0, 683, 512)
        screen = SimpleNamespace(availableGeometry=lambda: available)
        with patch("app.QApplication.primaryScreen", return_value=screen):
            window = PortraitApp(
                preferences_path=Path(self.temp.name) / "small.json",
                sync_shortcuts=False,
            )
        window.show()
        QT_APP.processEvents()
        try:
            self.assertLessEqual(window.frameGeometry().width(), available.width())
            self.assertLessEqual(window.frameGeometry().height(), available.height())
            for button in (
                window.save_button,
                window.open_button,
                window.paste_button,
                window.edit_button,
                *window.theme_buttons.values(),
            ):
                action = QRect(button.mapTo(window, QPoint()), button.size())
                self.assertTrue(
                    window.rect().contains(action),
                    (button.text(), window.rect(), action),
                )
            self.assertGreater(action.width(), 60)
            self.assertGreater(action.height(), 20)
        finally:
            window.close()

    def test_close_defers_without_blocking_the_gui(self):
        """A close request drains owned workers instead of blocking or killing them."""
        release = threading.Event()
        self.window._work(lambda: release.wait(3), lambda value: None, "Fixture")
        start = time.monotonic()
        self.window.close()
        self.assertLess(time.monotonic() - start, 0.25)
        self.assertTrue(self.window.isVisible())
        release.set()
        wait_until(lambda: not self.window.isVisible())
        self.assertFalse(self.window.jobs.busy)

    def test_rapid_brightness_changes_keep_only_latest_pending_render(self):
        """Intermediate slider values cannot create an unbounded rendering queue."""
        self.window.set_cutout(Image.new("RGBA", (1600, 1200), (100, 120, 140, 255)))
        for number in range(100):
            self.window.crop.set_framing(brightness=0.5 + number / 100)
        self.window.crop.set_framing(brightness=0.5)
        wait_until(lambda: not self.window.jobs.busy)
        self.assertLessEqual(self.window.crop.prepare_count, 2)
        self.assertEqual(self.window.crop.display.pixelColor(10, 10).red(), 50)

    def test_cancelled_name_leaves_document_untouched(self):
        """Cancelling the name prompt does not start exporting or open another dialog."""
        source = Image.new("RGBA", (100, 100), "red")
        self.window.set_cutout(source)
        with (
            patch("app.ask_person_name", return_value=None),
            patch("app.QFileDialog.getSaveFileName") as dialog,
        ):
            self.window.save()
            dialog.assert_not_called()
        self.assertIs(self.window.crop.cutout, source)
        self.assertFalse(self.window.busy)

    def test_panning_keeps_some_of_the_portrait_inside_the_frame(self):
        """Dragging or zooming out cannot silently leave an entirely blank print."""
        self.window.set_cutout(Image.new("RGBA", (100, 50), "red"))
        self.window.crop.set_framing(zoom=8, offset=(10, 10))
        self.window.crop.set_framing(zoom=1)
        self.assertLessEqual(abs(self.window.crop.offset[0]), 0.98)
        self.assertLessEqual(abs(self.window.crop.offset[1]), 0.73)


if __name__ == "__main__":
    unittest.main()
