from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from PIL import Image, ImageDraw

from portrait import AutomaticPortraitRemover, choose_removal_mode


def cutout(mask):
    """Construct a deterministic RGBA candidate from a supplied alpha mask."""
    image = Image.new("RGBA", mask.size, "red")
    image.putalpha(mask)
    return image


def silhouette():
    """Create a synthetic person silhouette for automatic-mode selection checks."""
    mask = Image.new("L", (256, 256), 0)
    ImageDraw.Draw(mask).rectangle((64, 0, 191, 230), fill=255)
    return mask


class AutomaticChoiceTests(unittest.TestCase):
    def test_missing_scalp_open_to_image_border_selects_protection(self):
        """Verify that missing scalp open to image border selects protection."""
        protected = silhouette()
        damaged = protected.copy()
        ImageDraw.Draw(damaged).rectangle((110, 0, 145, 35), fill=0)
        mode, metrics = choose_removal_mode(cutout(protected), cutout(damaged))
        self.assertEqual(mode, "protected")
        self.assertGreater(metrics["missing_core"], 0)

    def test_strong_background_residue_selects_protection(self):
        """Verify that strong background residue selects protection."""
        protected = silhouette()
        damaged = protected.copy()
        ImageDraw.Draw(damaged).rectangle((10, 110, 40, 145), fill=255)
        self.assertEqual(
            choose_removal_mode(cutout(protected), cutout(damaged))[0], "protected"
        )

    def test_partial_boundary_hair_is_retained_as_a_whole_candidate(self):
        """Verify that partial boundary hair is retained as a whole candidate."""
        protected = silhouette()
        detailed = protected.copy()
        ImageDraw.Draw(detailed).rectangle((60, 40, 63, 160), fill=100)
        mode, _ = choose_removal_mode(cutout(protected), cutout(detailed))
        self.assertEqual(mode, "fine_hair")

    def test_tiny_failed_silhouette_cannot_reject_a_larger_person(self):
        """Verify that tiny failed silhouette cannot reject a larger person."""
        weak = Image.new("L", (256, 256), 0)
        ImageDraw.Draw(weak).rectangle((100, 30, 105, 35), fill=255)
        self.assertEqual(
            choose_removal_mode(cutout(weak), cutout(silhouette()))[0], "fine_hair"
        )

    def test_one_failed_detection_uses_the_other_result(self):
        """Verify that one failed detection uses the other result."""
        result = cutout(silhouette())
        protected = SimpleNamespace(
            model_path=Path("protected.onnx"),
            remove=Mock(side_effect=ValueError("No person")),
        )
        fine = SimpleNamespace(
            model_path=Path("fine.onnx"), remove=Mock(return_value=result)
        )
        auto = AutomaticPortraitRemover(protected, fine)
        self.assertIs(auto.remove(Image.new("RGB", (256, 256))), result)
        self.assertEqual(auto.last_mode, "fine_hair")
        fine.remove.side_effect = ValueError("No person")
        with self.assertRaises(ValueError):
            auto.remove(Image.new("RGB", (256, 256)))
        self.assertIsNone(auto.last_mode)

    def test_single_available_model_is_not_run_twice(self):
        """Verify that single available model is not run twice."""
        result = cutout(silhouette())
        protected = SimpleNamespace(
            model_path=Path("same.onnx"),
            model_type="matting",
            remove=Mock(return_value=result),
        )
        fine = SimpleNamespace(model_path=Path("same.onnx"), remove=Mock())
        auto = AutomaticPortraitRemover(protected, fine)
        self.assertIs(auto.remove(Image.new("RGB", (256, 256))), result)
        self.assertEqual(auto.last_mode, "fine_hair")
        protected.remove.assert_called_once()
        fine.remove.assert_not_called()


if __name__ == "__main__":
    unittest.main()
