import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops

from deployment.branding import ICON_SIZES, generate_windows_icon


class BrandingAssetTests(unittest.TestCase):
    def test_windows_icon_is_generated_from_transparent_png_logo(self):
        source = Path(__file__).resolve().parents[1] / "assets" / "portrait-studio.png"
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "portrait-studio.ico"
            generate_windows_icon(source, target)

            with Image.open(source) as png, Image.open(target) as ico:
                self.assertEqual(ico.ico.sizes(), set(ICON_SIZES))
                for size in ICON_SIZES:
                    frame = ico.ico.getimage(size).convert("RGBA")
                    self.assertEqual(frame.size, size)
                    self.assertEqual(frame.getpixel((0, 0))[3], 0)
                expected = png.convert("RGBA").resize(
                    (256, 256), Image.Resampling.LANCZOS
                )
                actual = ico.ico.getimage((256, 256)).convert("RGBA")
                self.assertIsNone(ImageChops.difference(expected, actual).getbbox())

    def test_icon_generator_rejects_non_square_logo(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "logo.png"
            Image.new("RGBA", (16, 8)).save(source)
            with self.assertRaisesRegex(ValueError, "square PNG"):
                generate_windows_icon(source, root / "logo.ico")


if __name__ == "__main__":
    unittest.main()
