from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from portrait import PortraitRemover


class FakeSession:
    def __init__(self, alpha):
        self.alpha = alpha
        self.tensor = None

    def get_inputs(self):
        return [SimpleNamespace(name="input")]

    def run(self, outputs, inputs):
        self.tensor = inputs["input"]
        return [self.alpha]


class HairMattingTests(unittest.TestCase):
    def test_invalid_removal_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "mode"):
            PortraitRemover(mode="invalid")

    def test_soft_hair_opacity_is_preserved_without_range_stretching(self):
        alpha = np.linspace(.2, .8, 64, dtype=np.float32).reshape(1, 1, 8, 8)
        model = PortraitRemover("unused.onnx", model_type="matting")
        session = FakeSession(alpha)
        model._session = session
        output = model.remove(Image.new("RGB", (200, 300), (128, 128, 128)))
        self.assertEqual(session.tensor.shape, (1, 3, 768, 512))
        self.assertEqual(session.tensor.dtype, np.float32)
        self.assertAlmostEqual(float(session.tensor[0, 0, 0, 0]), 128 / 127.5 - 1, places=5)
        self.assertEqual(output.size, (200, 300))
        minimum, maximum = output.getchannel("A").getextrema()
        self.assertGreater(minimum, 0)
        self.assertLess(maximum, 255)
        self.assertGreater(np.unique(np.asarray(output.getchannel("A"))).size, 100)
        self.assertEqual(output.getpixel((100, 150))[:3], (128, 128, 128))

    def test_nan_and_invalid_output_are_rejected(self):
        for prediction in [np.full((1, 1, 4, 4), np.nan, dtype=np.float32),
                           np.zeros((1, 2, 4, 4), dtype=np.float32)]:
            model = PortraitRemover("unused.onnx", model_type="matting")
            model._session = FakeSession(prediction)
            with self.assertRaisesRegex(ValueError, "invalid"):
                model.remove(Image.new("RGB", (100, 100)))

    def test_protected_default_and_explicit_fine_hair_with_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            legacy = Path(folder) / "u2net_human_seg.onnx"
            hair = Path(folder) / "portrait_hair.onnx"
            legacy.touch()
            with patch("portrait.LEGACY_MODEL_PATH", legacy), patch("portrait.HAIR_MODEL_PATH", hair):
                old = PortraitRemover()
                self.assertEqual(old.model_type, "segmentation")
                hair.touch()
                new = PortraitRemover(mode="fine_hair")
                self.assertEqual(new.model_path, hair)
                self.assertEqual(new.model_type, "matting")
                safe = PortraitRemover()
                self.assertEqual(safe.model_path, legacy)
                self.assertEqual(safe.model_type, "segmentation")


if __name__ == "__main__":
    unittest.main()
