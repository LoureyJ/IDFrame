"""Verify soft teacher targets, stable correction gradients, and disjoint data splits."""

import unittest
import json
from pathlib import Path
import tempfile

import torch

from distillation import corrected_teacher_alpha, distillation_loss, validate_split
from train_distillation import load_manifest


class DistillationTests(unittest.TestCase):
    """Exercise teacher supervision without private photos or heavyweight inference."""

    def test_manifest_cannot_silently_become_public_only_training(self):
        """A missing reviewed teacher/holdout partition must fail before training starts."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps({"rows": []}))
            with self.assertRaises(ValueError):
                load_manifest(path)

    def test_corrections_preserve_unknown_soft_alpha_and_detach_teacher(self):
        """Known regions override a fallible teacher while soft hair remains fractional."""
        teacher = torch.tensor([[[[0.1, 0.9, 0.25]]]], requires_grad=True)
        labels = torch.tensor([[[[255, 0, 128]]]])
        corrected = corrected_teacher_alpha(teacher, labels)
        self.assertTrue(torch.equal(corrected, torch.tensor([[[[1.0, 0.0, 0.25]]]])))
        self.assertFalse(corrected.requires_grad)
        self.assertTrue(
            torch.equal(teacher.detach(), torch.tensor([[[[0.1, 0.9, 0.25]]]]))
        )

    def test_misaligned_teacher_geometry_is_rejected(self):
        """A resized or mismatched label cannot silently supervise unrelated pixels."""
        with self.assertRaises(ValueError):
            corrected_teacher_alpha(torch.zeros(1, 1, 4, 4), torch.zeros(1, 1, 2, 2))

    def test_confident_errors_have_finite_correcting_gradients(self):
        """A fully erased person and retained object can still learn through logits."""
        logits = torch.tensor([[[[-40.0, 40.0], [-40.0, 40.0]]]], requires_grad=True)
        matte = logits.sigmoid()
        alpha = torch.tensor([[[[1.0, 0.0], [1.0, 0.0]]]])
        outputs = (matte, matte, matte)
        loss = distillation_loss(outputs, torch.zeros(1, 3, 2, 2), alpha, logits)
        loss.backward()
        self.assertTrue(torch.isfinite(loss))
        self.assertLess(logits.grad[0, 0, 0, 0].item(), 0)
        self.assertGreater(logits.grad[0, 0, 0, 1].item(), 0)

    def test_duplicate_image_bytes_cannot_cross_split(self):
        """Renaming a held-out photo cannot let it enter student training."""
        with self.assertRaises(ValueError):
            validate_split(
                [{"sample": "a", "source_sha256": "same"}],
                [{"sample": "b", "source_sha256": "same"}],
            )

    def test_disjoint_split_is_accepted(self):
        """Independent file names and hashes permit a valid training/holdout partition."""
        validate_split(
            [{"sample": "a", "source_sha256": "first"}],
            [{"sample": "b", "source_sha256": "second"}],
        )


if __name__ == "__main__":
    unittest.main()
