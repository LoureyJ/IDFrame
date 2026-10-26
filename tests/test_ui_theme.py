"""Regression coverage for remembered appearance and state-preserving theme changes."""

import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from PIL import Image


class ThemeTests(unittest.TestCase):
    def test_keyboard_focus_reveals_controls_in_small_inspector(self):
        """Scroll a focused lower adjustment into view when the inspector overflows."""
        from app import PortraitApp

        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            root.withdraw()
            app = PortraitApp(root, preferences_path=Path(directory) / "settings.json")
            try:
                root.geometry("980x680")
                root.deiconify()
                root.update()
                app.crop.set_image(Image.new("RGBA", (400, 200), "red"))
                root.update()
                app.crop.reset_button.event_generate("<FocusIn>")
                root.update()
                canvas = app.inspector_body.canvas
                top = app.crop.reset_button.winfo_rooty()
                bottom = top + app.crop.reset_button.winfo_height()
                self.assertGreaterEqual(top, canvas.winfo_rooty())
                self.assertLessEqual(
                    bottom, canvas.winfo_rooty() + canvas.winfo_height()
                )
            finally:
                app.close()

    def test_default_window_shows_all_adjustments_without_scrolling(self):
        """Keep zoom, brightness, and reset visible together at the normal window size."""
        from app import PortraitApp

        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            root.withdraw()
            app = PortraitApp(root, preferences_path=Path(directory) / "settings.json")
            try:
                root.geometry("1240x780")
                root.deiconify()
                root.update()
                self.assertFalse(app.inspector_body.scrollbar.winfo_ismapped())
                visible_bottom = (
                    app.inspector_body.canvas.winfo_rooty()
                    + app.inspector_body.canvas.winfo_height()
                )
                self.assertLessEqual(
                    app.crop.reset_button.winfo_rooty()
                    + app.crop.reset_button.winfo_height(),
                    visible_bottom,
                )
            finally:
                app.close()

    def test_removal_modes_are_visible_radio_choices(self):
        """Expose all three removal modes directly rather than hiding them in a dropdown."""
        from tkinter import ttk
        from app import PortraitApp

        root = tk.Tk()
        root.withdraw()
        with tempfile.TemporaryDirectory() as directory:
            app = PortraitApp(root, preferences_path=Path(directory) / "settings.json")
            try:
                self.assertEqual(len(app.mode_buttons), 3)
                self.assertTrue(
                    all(
                        isinstance(button, ttk.Radiobutton)
                        for button in app.mode_buttons
                    )
                )
                app.mode_buttons[2].invoke()
                self.assertEqual(app.removal_mode.get(), "Fine hair")
            finally:
                app.close()

    def test_minimum_window_keeps_status_and_save_action_visible(self):
        """Reserve footer space and keep inspector controls inside the minimum window."""
        from app import PortraitApp

        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            root.withdraw()
            app = PortraitApp(root, preferences_path=Path(directory) / "settings.json")
            try:
                root.geometry("980x680")
                root.deiconify()
                root.update()
                for widget in (
                    app.status_label,
                    app.save_button,
                    app.crop.brightness_slider,
                ):
                    self.assertGreaterEqual(
                        widget.winfo_height(), widget.winfo_reqheight()
                    )
                    bottom = (
                        widget.winfo_rooty()
                        - root.winfo_rooty()
                        + widget.winfo_height()
                    )
                    self.assertLessEqual(bottom, root.winfo_height())
                self.assertGreater(app.before.winfo_width(), 150)
                self.assertGreater(app.crop.canvas.winfo_width(), 150)
            finally:
                app.close()

    def test_name_prompt_inherits_dark_palette(self):
        """Style the real modal prompt consistently and allow cancellation without a name."""
        from photo_naming import ask_person_name
        from ui_theme import apply_theme

        root = tk.Tk()
        root.withdraw()
        observed = []

        def inspect_and_cancel():
            """Record the modal's actual color and close it so the test can continue."""
            for widget in root.winfo_children():
                if isinstance(widget, tk.Toplevel):
                    observed.append(widget.cget("background"))
                    widget.destroy()

        try:
            apply_theme(root, "Dark")
            root.after(50, inspect_and_cancel)
            self.assertIsNone(ask_person_name(root))
            self.assertEqual(observed, ["#171b22"])
        finally:
            root.destroy()

    def test_existing_dropdown_and_interactive_states_follow_dark_palette(self):
        """Recolor already-created Tcl popups and keep hovered/disabled controls readable."""
        from tkinter import ttk
        from ui_theme import apply_theme

        root = tk.Tk()
        root.withdraw()
        try:
            combo = ttk.Combobox(root, values=("Light", "Dark"))
            apply_theme(root, "Light")
            popup = root.tk.call("ttk::combobox::PopdownWindow", str(combo))
            apply_theme(root, "Dark")
            self.assertEqual(
                root.tk.call(str(popup) + ".f.l", "cget", "-background"), "#2c3441"
            )
            style = ttk.Style(root)
            self.assertEqual(
                style.lookup("TCombobox", "background", ("active",)), "#204f55"
            )
            self.assertEqual(
                style.lookup("Horizontal.TScale", "background", ("disabled",)),
                "#222832",
            )
        finally:
            root.destroy()

    def test_preferences_default_reload_and_preserve_other_settings(self):
        """Use Light for invalid settings and retain unrelated preferences on save."""
        from ui_theme import load_theme, save_theme

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            self.assertEqual(load_theme(path), "Light")
            for value in ("broken", "[]", "null", '{"theme":"unknown"}'):
                path.write_text(value)
                self.assertEqual(load_theme(path), "Light")
            path.write_text('{"theme":"Light","other":42}')
            self.assertTrue(save_theme("Dark", path))
            self.assertEqual(load_theme(path), "Dark")
            self.assertEqual(json.loads(path.read_text())["other"], 42)

    def test_unwritable_preferences_do_not_raise(self):
        """Report preference write failure without preventing in-memory theme changes."""
        from ui_theme import save_theme

        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "ui_theme.tempfile.mkstemp", side_effect=PermissionError("denied")
            ):
                with self.assertLogs("ui_theme", level="WARNING"):
                    self.assertFalse(
                        save_theme("Dark", Path(directory) / "settings.json")
                    )

    def test_theme_switch_preserves_photo_crop_and_busy_controls(self):
        """Recolor the real interface without resetting edits or enabling busy actions."""
        from app import PortraitApp

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            root = tk.Tk()
            root.withdraw()
            app = PortraitApp(root, preferences_path=path)
            try:
                photo = Image.new("RGBA", (400, 200), "red")
                app.set_photo(photo, None, "Test portrait")
                app.crop.set_image(photo)
                app.crop.zoom.set(2)
                app.crop.offset = (0.1, -0.1)
                app.crop.brightness.set(0.5)
                expected = app.crop.export().tobytes()
                app.busy = True
                app.remove_button.configure(state="disabled")
                app.theme.set("Dark")
                app.change_theme()
                root.update_idletasks()
                self.assertEqual(root.cget("background"), "#171b22")
                self.assertEqual(app.crop.export().tobytes(), expected)
                self.assertIs(app.photo, photo)
                self.assertEqual(str(app.remove_button["state"]), "disabled")
                self.assertTrue(app.busy)
                self.assertEqual(json.loads(path.read_text())["theme"], "Dark")
                app.open_changelog()
                self.assertEqual(app.changelog_window.cget("background"), "#171b22")
                app.theme.set("Light")
                app.change_theme()
                self.assertEqual(app.changelog_window.cget("background"), "#f3f5f8")
            finally:
                app.busy = False
                app.close()

    def test_reopening_loads_saved_theme_and_keeps_exports_white(self):
        """Restore Dark on startup without recoloring the saved photograph background."""
        from app import PortraitApp

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"theme":"Dark"}')
            root = tk.Tk()
            root.withdraw()
            app = PortraitApp(root, preferences_path=path)
            try:
                self.assertEqual(app.theme.get(), "Dark")
                app.crop.set_image(Image.new("RGBA", (400, 200), "red"))
                self.assertEqual(app.crop.export().getpixel((0, 0)), (255, 255, 255))
            finally:
                app.close()


if __name__ == "__main__":
    unittest.main()
