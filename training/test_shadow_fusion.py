"""Check person protection and soft hair in experimental shadow-mask fusion."""

import unittest
import numpy as np
from PIL import Image
from shadow_fusion import fuse_shadow_masks


class ShadowFusionTests(unittest.TestCase):
    """Exercise fusion independently of private photographs or heavyweight models."""

    def test_empty_masks_are_rejected(self):
        """Empty images cannot define a valid source-space person or shadow mask."""
        with self.assertRaises(ValueError):
            fuse_shadow_masks(
                Image.new("L", (0, 0)), Image.new("L", (0, 0)), Image.new("L", (0, 0))
            )

    def test_uncertain_shadow_does_not_erase_extra_soft_hair(self):
        """Fractional hair beyond the protected estimate survives an uncertain shadow."""
        result = fuse_shadow_masks(
            Image.new("L", (100, 100), 128),
            Image.new("L", (100, 100), 20),
            Image.new("L", (100, 100), 100),
        )
        self.assertEqual(result.getpixel((50, 50)), 128)

    def test_shadow_cannot_remove_protected_person_core(self):
        """A confident broad person interior survives even a fully positive shadow map."""
        person = np.zeros((100, 100), dtype=np.uint8)
        person[20:80, 20:80] = 255
        fine = Image.fromarray(person)
        shadow = Image.new("L", (100, 100), 255)
        result = np.asarray(fuse_shadow_masks(fine, fine, shadow))
        self.assertEqual(result[50, 50], 255)

    def test_protect_core_repairs_a_missing_person_interior(self):
        """The protected model restores a hole inside a confidently detected person."""
        p = np.zeros((100, 100), dtype=np.uint8)
        p[20:80, 20:80] = 255
        m = p.copy()
        m[45:55, 45:55] = 0
        result = np.asarray(
            fuse_shadow_masks(
                Image.fromarray(m), Image.fromarray(p), Image.new("L", (100, 100), 255)
            )
        )
        self.assertEqual(result[50, 50], 255)

    def test_detected_shadow_outside_person_support_is_removed(self):
        """A shadow outside the protected silhouette does not inherit person protection."""
        p = np.zeros((100, 100), dtype=np.uint8)
        p[20:80, 20:60] = 255
        m = p.copy()
        m[35:65, 75:90] = 255
        result = np.asarray(
            fuse_shadow_masks(
                Image.fromarray(m), Image.fromarray(p), Image.new("L", (100, 100), 255)
            )
        )
        self.assertEqual(result[50, 82], 0)

    def test_soft_detail_without_detected_shadow_remains_exact(self):
        """A non-shadow fine-hair alpha must not be binarized or range-stretched."""
        a = np.tile(np.arange(100, dtype=np.uint8), (100, 1))
        original = Image.fromarray(a)
        result = fuse_shadow_masks(
            original, Image.new("L", (100, 100)), Image.new("L", (100, 100))
        )
        np.testing.assert_array_equal(np.asarray(result), a)
        np.testing.assert_array_equal(np.asarray(original), a)

    def test_mismatched_geometry_is_rejected(self):
        """Unaligned model outputs must never supervise unrelated source pixels."""
        with self.assertRaises(ValueError):
            fuse_shadow_masks(
                Image.new("L", (10, 10)),
                Image.new("L", (20, 20)),
                Image.new("L", (10, 10)),
            )


if __name__ == "__main__":
    unittest.main()
