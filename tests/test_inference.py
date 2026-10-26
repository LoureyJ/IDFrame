"""Integration smoke test using the installed model with network access blocked."""
import socket
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from portrait import MODEL_PATH, PortraitRemover, format_portrait


@unittest.skipUnless(MODEL_PATH.is_file(), "Run download_model.py to install the model")
class OfflineInferenceTests(unittest.TestCase):
    def test_local_model_produces_white_2x2_photo_without_network(self):
        # Synthetic input checks the real ONNX pipeline, not portrait accuracy.
        image = Image.new("RGB", (240, 320), "#6484a8")
        drawing = ImageDraw.Draw(image)
        drawing.ellipse((75, 25, 165, 145), fill="#dda888")
        drawing.rectangle((95, 125, 145, 175), fill="#dda888")
        drawing.ellipse((35, 155, 205, 410), fill="#27313e")
        with patch.object(socket, "socket", side_effect=AssertionError("Network access attempted")):
            cutout = PortraitRemover().remove(image)
        self.assertEqual(cutout.size, image.size)
        self.assertEqual(cutout.mode, "RGBA")
        output = format_portrait(cutout)
        self.assertEqual(output.size, (1200, 1200))
        self.assertEqual(output.mode, "RGB")
        self.assertEqual(output.getpixel((0, 0)), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
