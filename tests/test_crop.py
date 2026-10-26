from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from PIL import Image

from app import PortraitApp
from portrait import frame_portrait


class CropTests(unittest.TestCase):
    def test_zoom_and_position_crop_source_without_stretching(self):
        source = Image.new("RGBA", (400, 200), "red")
        source.paste("blue", (200, 0, 400, 200))
        original = source.tobytes()
        fitted = frame_portrait(source)
        self.assertEqual(fitted.getpixel((600, 100)), (255, 255, 255))
        centered = frame_portrait(source, 2)
        self.assertEqual(centered.getpixel((300, 100)), (255, 0, 0))
        self.assertEqual(centered.getpixel((1000, 100)), (0, 0, 255))
        moved = frame_portrait(source, 2, (.25, .25))
        self.assertEqual(moved.getpixel((600, 600)), (255, 0, 0))
        self.assertEqual(moved.getpixel((1100, 600)), (0, 0, 255))
        self.assertEqual(moved.getpixel((600, 100)), (255, 255, 255))
        self.assertEqual(source.tobytes(), original)

    def test_full_resolution_and_partial_hair_alpha_are_preserved(self):
        source = Image.new("RGBA", (1200, 1200), (0, 0, 0, 128))
        source.paste((255, 0, 0, 255), (601, 0, 602, 1200))
        result = frame_portrait(source)
        self.assertEqual(result.mode, "RGB")
        self.assertEqual(result.size, (1200, 1200))
        self.assertEqual(result.getpixel((600, 600)), (127, 127, 127))
        self.assertEqual(result.getpixel((601, 600)), (255, 0, 0))

    def test_app_saves_selected_crop_and_resets_for_new_photo(self):
        root = tk.Tk()
        root.withdraw()
        app = PortraitApp(root)
        try:
            source = Image.new("RGBA", (400, 200), "red")
            source.paste("blue", (200, 0, 400, 200))
            app.crop.set_image(source)
            app.crop.zoom.set(2)
            app.crop.offset = (.25, 0)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "crop.png"
                with patch("app.ask_person_name", return_value="Test Person"), patch("app.filedialog.asksaveasfilename", return_value=str(path)):
                    app.save()
                with Image.open(path) as saved:
                    self.assertEqual(saved.getpixel((600, 600)), (255, 0, 0))
                    self.assertEqual(saved.size, (1200, 1200))
                    self.assertAlmostEqual(saved.info["dpi"][0], 600, delta=.01)
            app.crop.reset()
            self.assertEqual(app.crop.zoom.get(), 1)
            self.assertEqual(app.crop.offset, (0, 0))
            app.set_photo(Image.new("RGB", (50, 80)), None, "New photo")
            self.assertIsNone(app.crop.cutout)
            self.assertEqual(str(app.crop.slider["state"]), "disabled")
        finally:
            app.close()


if __name__ == "__main__":
    unittest.main()
