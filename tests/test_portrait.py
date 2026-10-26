from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from portrait import PortraitRemover, format_portrait, load_photo, save_portrait


class PortraitTests(unittest.TestCase):
    def test_export_dimensions_dpi_white_and_no_alpha(self):
        """Verify that export dimensions dpi white and no alpha."""
        cutout = Image.new("RGBA", (100, 200), (0, 0, 0, 0))
        cutout.paste((230, 20, 40, 255), (25, 25, 75, 175))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "portrait.png"
            save_portrait(cutout, path)
            with Image.open(path) as saved:
                self.assertEqual(saved.size, (1200, 1200))
                self.assertEqual(saved.mode, "RGB")
                self.assertEqual(saved.getpixel((0, 0)), (255, 255, 255))
                self.assertEqual(saved.getpixel((600, 600)), (230, 20, 40))
                for dpi in saved.info["dpi"]:
                    self.assertAlmostEqual(dpi, 600, delta=0.01)
                self.assertAlmostEqual(
                    saved.width / saved.info["dpi"][0], 2, delta=0.001
                )
                self.assertAlmostEqual(
                    saved.height / saved.info["dpi"][1], 2, delta=0.001
                )

    def test_wide_image_preserves_shape_and_white_padding(self):
        """Verify that wide image preserves shape and white padding."""
        output = format_portrait(Image.new("RGBA", (400, 200), "red"))
        self.assertEqual(output.getpixel((600, 299)), (255, 255, 255))
        self.assertEqual(output.getpixel((600, 300)), (255, 0, 0))
        self.assertEqual(output.getpixel((600, 899)), (255, 0, 0))
        self.assertEqual(output.getpixel((600, 900)), (255, 255, 255))

    def test_soft_edges_are_composited_on_white(self):
        """Verify that soft edges are composited on white."""
        result = format_portrait(Image.new("RGBA", (208, 208), (0, 0, 0, 128)))
        self.assertEqual(result.getpixel((600, 600)), (127, 127, 127))

    def test_missing_model_never_downloads(self):
        """Verify that missing model never downloads."""
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("urllib.request.urlopen", side_effect=AssertionError("Network used")),
        ):
            remover = PortraitRemover(Path(folder) / "missing.onnx")
            with self.assertRaisesRegex(FileNotFoundError, "setup.bat"):
                remover.remove(Image.new("RGB", (10, 10)))

    def test_empty_cutout_rejected(self):
        """Verify that empty cutout rejected."""
        with self.assertRaises(ValueError):
            format_portrait(Image.new("RGBA", (20, 20)))

    def test_input_orientation_and_original_preserved(self):
        """Verify that input orientation and original preserved."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.jpg"
            source = Image.new("RGB", (20, 40), "blue")
            exif = source.getexif()
            exif[274] = 6
            source.save(path, exif=exif)
            before = path.read_bytes()
            self.assertEqual(load_photo(path).size, (40, 20))
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
