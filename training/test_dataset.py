"""Training-only regressions; run using .training-venv's Python."""

from pathlib import Path
import tempfile
import unittest

from PIL import Image

import torch

from adapt_modnet import (
    balanced_scribble_loss,
    discover_photos,
    guidance_mask,
    preview_path,
    tensor_from_photo,
)


class DatasetTests(unittest.TestCase):
    def test_nested_formats_and_duplicate_names_keep_distinct_previews(self):
        """Verify that nested formats and duplicate names keep distinct previews."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in [
                "same.jpg",
                "camo/same.jpg",
                "low qual/same.jpg",
                "low qual/same.avif",
            ]:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            (root / "notes.txt").touch()
            photos = discover_photos(root)
            self.assertEqual(len(photos), 4)
            self.assertEqual(
                discover_photos(root, recursive=False), [root / "same.jpg"]
            )
            outputs = [preview_path(p, root, root / "out") for p in photos]
            self.assertEqual(len(set(outputs)), 4)
            self.assertIn(root / "out/low qual/same.avif.png", outputs)

    def test_avif_decodes_with_training_preprocessing(self):
        """Verify that avif decodes with training preprocessing."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "portrait.avif"
            Image.new("RGB", (120, 90), (120, 80, 60)).save(path)
            tensor = tensor_from_photo(path)
            self.assertEqual(tuple(tensor.shape), (1, 3, 384, 512))
            self.assertGreaterEqual(float(tensor.min()), -1)
            self.assertLessEqual(float(tensor.max()), 1)

    def test_unknown_edges_are_not_supervised_and_flip_matches_photo(self):
        """Verify that unknown edges are not supervised and flip matches photo."""
        entry = {"foreground": [[25, 50, 10]], "background": [[75, 50, 10]]}
        normal = guidance_mask((100, 80), entry)
        flipped = guidance_mask((100, 80), entry, flip=True)
        self.assertTrue(torch.equal(normal.flip(-1), flipped))
        self.assertEqual(int(normal[0, 0, 40, 25]), 255)
        self.assertEqual(int(normal[0, 0, 40, 75]), 0)
        self.assertEqual(int(normal[0, 0, 0, 0]), 128)
        prediction = torch.full(normal.shape, 0.5, requires_grad=True)
        balanced_scribble_loss(prediction, normal).backward()
        self.assertEqual(float(prediction.grad[0, 0, 0, 0]), 0)
        self.assertLess(float(prediction.grad[0, 0, 40, 25]), 0)
        self.assertGreater(float(prediction.grad[0, 0, 40, 75]), 0)


if __name__ == "__main__":
    unittest.main()
