"""Qt mode selection preserves automatic diagnostics and deliberate reprocessing."""

import unittest
from unittest.mock import Mock

from PIL import Image
import test_qt_app as fixtures


class RemovalModeTests(unittest.TestCase):
    """Exercise model selection through native radio buttons and background callbacks."""

    setUp = fixtures.QtAppTests.setUp
    tearDown = fixtures.QtAppTests.tearDown

    def test_auto_is_default_and_selected_mode_is_shown(self):
        """Auto remains the default and reports which complete candidate it chose."""
        app = self.window
        auto = Mock(last_mode="protected")
        auto.remove.return_value = Image.new("RGBA", (100, 100), "red")
        app.removers["Auto"] = auto
        self.assertEqual(app.removal_mode, "Auto")
        app.set_photo(Image.new("RGB", (100, 100)))
        app.remove()
        fixtures.wait_until(lambda: not app.busy)
        self.assertIn("Auto selected Protect person", app.status_label.text())
        self.assertEqual(app.crop.export().getpixel((600, 600)), (255, 0, 0))

    def test_switching_mode_reprocesses_and_resets_framing(self):
        """An intentional mode change runs once and starts a fresh result framing."""
        app = self.window
        for mode, color in (("Protect person", "red"), ("Fine hair", "blue")):
            app.removers[mode] = Mock()
            app.removers[mode].remove.return_value = Image.new(
                "RGBA", (100, 100), color
            )
        app.mode_buttons[1].setChecked(True)
        app.set_photo(Image.new("RGB", (100, 100)))
        app.remove()
        self.assertTrue(all(not button.isEnabled() for button in app.mode_buttons))
        fixtures.wait_until(lambda: not app.busy)
        app.crop.set_framing(zoom=2, offset=(0.2, 0.2))
        app.mode_buttons[2].setChecked(True)
        fixtures.wait_until(lambda: not app.busy)
        self.assertEqual(app.crop.export().getpixel((600, 600)), (0, 0, 255))
        self.assertEqual((app.crop.zoom, app.crop.offset), (1, (0, 0)))
        for mode in ("Protect person", "Fine hair"):
            app.removers[mode].remove.assert_called_once()
