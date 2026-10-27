"""Appearance regressions for the Qt application and compatible stored preferences."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QLineEdit, QDialogButtonBox, QScrollArea

import test_qt_app as fixtures
from ui_theme import PALETTES, load_theme, save_theme


class ThemeTests(unittest.TestCase):
    """Retain visible controls, photo state, and persisted Light/Dark behavior."""

    setUp = fixtures.QtAppTests.setUp
    tearDown = fixtures.QtAppTests.tearDown

    def test_preferences_default_reload_and_preserve_other_settings(self):
        """Malformed settings default to Light and valid unrelated keys survive saves."""
        path = Path(self.temp.name) / "other.json"
        self.assertEqual(load_theme(path), "Light")
        path.write_text("malformed")
        self.assertEqual(load_theme(path), "Light")
        path.write_text(json.dumps({"existing": 5}))
        self.assertTrue(save_theme("Dark", path))
        self.assertEqual(load_theme(path), "Dark")
        self.assertEqual(json.loads(path.read_text())["existing"], 5)

    def test_unwritable_preferences_do_not_raise(self):
        """A filesystem error cannot break appearance switching or photo processing."""
        with patch("ui_theme.os.replace", side_effect=OSError("read only")):
            self.assertFalse(save_theme("Dark", Path(self.temp.name) / "readonly.json"))

    def test_theme_switch_preserves_photo_crop_and_busy_controls(self):
        """Recolor controls without losing adjustments or enabling an active operation."""
        self.window.set_photo(Image.new("RGB", (100, 100)))
        self.window.set_cutout(Image.new("RGBA", (100, 100), "red"))
        self.window.crop.set_framing(zoom=2, brightness=0.5)
        self.window._set_busy(True)
        self.window.change_theme("Dark")
        self.assertFalse(self.window.save_button.isEnabled())
        self.assertFalse(self.window.open_button.isEnabled())
        self.assertEqual(self.window.crop.zoom, 2)
        self.assertEqual(self.window.crop.brightness, 0.5)
        self.window._set_busy(False)

    def test_reopening_loads_saved_theme_and_keeps_exports_white(self):
        """Persist Dark independently of photo pixels or white export compositing."""
        from app import PortraitApp

        self.window.change_theme("Dark")
        other = PortraitApp(
            preferences_path=self.window.preferences_path, sync_shortcuts=False
        )
        try:
            self.assertEqual(other.theme, "Dark")
            other.set_cutout(Image.new("RGBA", (100, 50), "red"))
            self.assertEqual(other.crop.export().getpixel((0, 0)), (255, 255, 255))
        finally:
            fixtures.wait_until(lambda: not other.jobs.busy)
            other.close()

    def test_name_prompt_inherits_dark_palette_and_validates_names(self):
        """Qt modal naming uses the current palette and rejects unsafe filenames."""
        from qt_dialogs import ask_person_name

        self.window.change_theme("Dark")
        observed = []

        def inspect_dialog():
            """Capture dialog state and always close it so failures cannot stall tests."""
            dialog = QApplication.activeModalWidget()
            if dialog is None:
                return
            try:
                entry = dialog.findChild(QLineEdit)
                buttons = dialog.findChild(QDialogButtonBox)
                entry.setText("invalid/name")
                observed.append(
                    (
                        dialog.palette().color(QPalette.ColorRole.Window).name(),
                        buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled(),
                    )
                )
                entry.setText("Juan Dela Cruz")
                observed.append(
                    buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
                )
            finally:
                dialog.reject()

        QTimer.singleShot(20, inspect_dialog)
        self.assertIsNone(ask_person_name(self.window))
        self.assertEqual(observed, [(PALETTES["Dark"]["app"], False), True])

    def test_removal_modes_are_visible_radio_choices(self):
        """All three modes remain explicit radio choices with no hidden dropdown."""
        self.assertEqual(len(self.window.mode_buttons), 3)
        self.assertTrue(
            all(
                button.isVisible() and button.isCheckable()
                for button in self.window.mode_buttons
            )
        )
        self.assertTrue(self.window.mode_buttons[0].isChecked())

    def test_minimum_window_keeps_status_and_save_action_visible(self):
        """Inspector overflow scrolls while primary Save and status stay outside it."""
        self.window.resize(860, 560)
        fixtures.QT_APP.processEvents()
        scroll = self.window.findChild(QScrollArea)
        self.assertTrue(self.window.save_button.isVisible())
        self.assertTrue(self.window.status_label.isVisible())
        self.assertFalse(scroll.isAncestorOf(self.window.save_button))

    def test_changelog_reuses_window_and_tracks_current_theme(self):
        """Repeated changelog actions reuse the same dialog and honor palette changes."""
        self.window.open_changelog()
        first = self.window.changelog_window
        self.window.change_theme("Dark")
        self.window.open_changelog()
        self.assertIs(first, self.window.changelog_window)
        self.assertEqual(
            first.palette().color(QPalette.ColorRole.Window).name(),
            PALETTES["Dark"]["app"],
        )
        first.close()


if __name__ == "__main__":
    unittest.main()
