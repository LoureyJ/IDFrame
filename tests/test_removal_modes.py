import time
import tkinter as tk
import unittest
from unittest.mock import Mock

from PIL import Image

from app import PortraitApp


class RemovalModeTests(unittest.TestCase):
    def test_auto_is_default_and_selected_mode_is_shown(self):
        """Verify that auto is default and selected mode is shown."""
        root = tk.Tk()
        root.withdraw()
        app = PortraitApp(root)
        try:
            auto = Mock(last_mode="protected")
            auto.remove.return_value = Image.new("RGBA", (100, 100), "red")
            app.removers["Auto"] = auto
            self.assertEqual(app.removal_mode.get(), "Auto")
            app.set_photo(Image.new("RGB", (100, 100)), None, "Test photo")
            app.remove()
            deadline = time.monotonic() + 3
            while app.busy and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            self.assertFalse(app.busy)
            self.assertIn("Auto selected Protect person", app.status.get())
            self.assertEqual(app.crop.export().getpixel((600, 600)), (255, 0, 0))
        finally:
            app.close()

    def test_switching_mode_reprocesses_and_resets_framing(self):
        """Verify that switching mode reprocesses and resets framing."""
        root = tk.Tk()
        root.withdraw()
        app = PortraitApp(root)
        try:
            app.removers = {"Protect person": Mock(), "Fine hair": Mock()}
            self.assertEqual(app.removal_mode.get(), "Auto")
            app.removal_mode.set("Protect person")
            app.removers["Protect person"].remove.return_value = Image.new(
                "RGBA", (100, 100), "red"
            )
            app.removers["Fine hair"].remove.return_value = Image.new(
                "RGBA", (100, 100), "blue"
            )
            app.set_photo(Image.new("RGB", (100, 100)), None, "Test photo")

            def finish():
                """Pump Tk events until processing finishes and verify controls are restored."""
                deadline = time.monotonic() + 3
                while app.busy and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.01)
                self.assertFalse(app.busy)
                self.assertTrue(
                    all(str(button["state"]) == "normal" for button in app.mode_buttons)
                )

            self.assertEqual(app.removal_mode.get(), "Protect person")
            app.remove()
            self.assertTrue(
                all(str(button["state"]) == "disabled" for button in app.mode_buttons)
            )
            finish()
            self.assertEqual(app.crop.export().getpixel((600, 600)), (255, 0, 0))
            app.crop.zoom.set(2)
            app.crop.offset = (0.2, 0.2)
            app.removal_mode.set("Fine hair")
            app.mode_changed()
            self.assertIsNone(app.crop.cutout)
            finish()
            self.assertEqual(app.crop.export().getpixel((600, 600)), (0, 0, 255))
            self.assertEqual(app.crop.zoom.get(), 1)
            self.assertEqual(app.crop.offset, (0, 0))
            app.removers["Protect person"].remove.assert_called_once()
            app.removers["Fine hair"].remove.assert_called_once()
        finally:
            app.close()


if __name__ == "__main__":
    unittest.main()
