from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from PIL import Image

from app import PortraitApp
from portrait import frame_portrait


class CropTests(unittest.TestCase):
    def test_brightness_changes_portrait_without_darkening_white_or_mutating_source(
        self,
    ):
        """Keep white padding and partial hair opacity intact when adjusting brightness."""
        source = Image.new("RGBA", (40, 20), (80, 100, 120, 128))
        original = source.tobytes()
        for brightness, expected in [
            (0.5, (147, 152, 157)),
            (1.0, (167, 177, 187)),
            (2.0, (207, 227, 247)),
        ]:
            with self.subTest(brightness=brightness):
                result = frame_portrait(source, size=(40, 40), brightness=brightness)
                # RGBA bicubic sampling may round a partially opaque RGB channel by one.
                self.assertTrue(
                    all(
                        abs(actual - target) <= 1
                        for actual, target in zip(result.getpixel((20, 20)), expected)
                    )
                )
                self.assertEqual(result.getpixel((20, 0)), (255, 255, 255))
                self.assertEqual(source.tobytes(), original)

    def test_invalid_brightness_is_rejected(self):
        """Reject out-of-range and non-finite brightness before rendering a crop."""
        source = Image.new("RGBA", (10, 10), "red")
        for brightness in (0, 2.1, float("nan"), float("inf")):
            with self.subTest(brightness=brightness):
                with self.assertRaisesRegex(ValueError, "brightness"):
                    frame_portrait(source, brightness=brightness)

    def test_zoom_and_position_crop_source_without_stretching(self):
        """Verify that zoom and position crop source without stretching."""
        source = Image.new("RGBA", (400, 200), "red")
        source.paste("blue", (200, 0, 400, 200))
        original = source.tobytes()
        fitted = frame_portrait(source)
        self.assertEqual(fitted.getpixel((600, 100)), (255, 255, 255))
        centered = frame_portrait(source, 2)
        self.assertEqual(centered.getpixel((300, 100)), (255, 0, 0))
        self.assertEqual(centered.getpixel((1000, 100)), (0, 0, 255))
        moved = frame_portrait(source, 2, (0.25, 0.25))
        self.assertEqual(moved.getpixel((600, 600)), (255, 0, 0))
        self.assertEqual(moved.getpixel((1100, 600)), (0, 0, 255))
        self.assertEqual(moved.getpixel((600, 100)), (255, 255, 255))
        self.assertEqual(source.tobytes(), original)

    def test_full_resolution_and_partial_hair_alpha_are_preserved(self):
        """Verify that full resolution and partial hair alpha are preserved."""
        source = Image.new("RGBA", (1200, 1200), (0, 0, 0, 128))
        source.paste((255, 0, 0, 255), (601, 0, 602, 1200))
        result = frame_portrait(source)
        self.assertEqual(result.mode, "RGB")
        self.assertEqual(result.size, (1200, 1200))
        self.assertEqual(result.getpixel((600, 600)), (127, 127, 127))
        self.assertEqual(result.getpixel((601, 600)), (255, 0, 0))

    def test_app_saves_selected_crop_and_resets_for_new_photo(self):
        """Verify that app saves selected crop and resets for new photo."""
        root = tk.Tk()
        root.withdraw()
        app = PortraitApp(root)
        try:
            source = Image.new("RGBA", (400, 200), "red")
            source.paste("blue", (200, 0, 400, 200))
            app.crop.set_image(source)
            app.crop.zoom.set(2)
            app.crop.offset = (0.25, 0)
            app.crop.brightness.set(0.5)
            app.crop.changed()
            self.assertEqual(app.crop.brightness_text.get(), "50%")
            expected = app.crop.export()
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "crop.png"
                with (
                    patch("app.ask_person_name", return_value="Test Person"),
                    patch("app.filedialog.asksaveasfilename", return_value=str(path)),
                ):
                    app.save()
                with Image.open(path) as saved:
                    self.assertEqual(saved.getpixel((600, 600)), (127, 0, 0))
                    self.assertEqual(saved.tobytes(), expected.tobytes())
                    self.assertEqual(saved.size, (1200, 1200))
                    self.assertAlmostEqual(saved.info["dpi"][0], 600, delta=0.01)
            app.crop.reset()
            self.assertEqual(app.crop.zoom.get(), 1)
            self.assertEqual(app.crop.offset, (0, 0))
            self.assertEqual(app.crop.brightness.get(), 1)
            app.crop.brightness.set(1.5)
            app.set_photo(Image.new("RGB", (50, 80)), None, "New photo")
            self.assertIsNone(app.crop.cutout)
            self.assertEqual(str(app.crop.slider["state"]), "disabled")
            self.assertEqual(str(app.crop.brightness_slider["state"]), "disabled")
            self.assertEqual(app.crop.brightness.get(), 1)
        finally:
            app.close()


if __name__ == "__main__":
    unittest.main()
