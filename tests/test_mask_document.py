"""Exercise non-destructive portrait erasing and bounded, stroke-level history."""

import unittest

from PIL import Image

from mask_document import MaskDocument


class MaskDocumentTests(unittest.TestCase):
    """Check pixel ownership, brush continuity, and exact reversible operations."""

    def setUp(self):
        """Create an opaque portrait with distinctive immutable RGB channels."""
        self.source = Image.new("RGBA", (100, 80), (60, 90, 120, 255))
        self.document = MaskDocument(self.source)

    def stroke(self, start=(20, 30), end=(70, 30), diameter=12):
        """Complete one continuous brush stroke for history assertions."""
        self.document.begin_stroke()
        self.document.erase_segment(start, end, diameter)
        self.document.end_stroke()

    def test_erases_continuous_segment_without_changing_source_or_rgb(self):
        """Long pointer moves leave no gaps and never change original RGB pixels."""
        before = self.source.tobytes()
        self.stroke()
        result = self.document.image()
        for x in range(20, 71):
            self.assertEqual(result.getpixel((x, 30)), (60, 90, 120, 0))
        self.assertEqual(result.getpixel((0, 0)), (60, 90, 120, 255))
        self.assertEqual(before, self.source.tobytes())

    def test_restore_reveals_ai_removed_original_pixels_and_is_reversible(self):
        """Restoration reveals hidden source RGB even when initial AI alpha was zero."""
        source = Image.new("RGBA", (100, 80), (60, 90, 120, 0))
        document = MaskDocument(source)
        before = source.tobytes()
        document.restore_segment((20, 30), (70, 30), 12)
        document.end_stroke()
        restored = document.image().tobytes()
        for x in range(20, 71):
            self.assertEqual(document.image().getpixel((x, 30)), (60, 90, 120, 255))
        self.assertEqual(document.image().getpixel((0, 0)), (60, 90, 120, 0))
        document.undo()
        self.assertEqual(document.image().tobytes(), before)
        document.redo()
        self.assertEqual(document.image().tobytes(), restored)
        self.assertEqual(source.tobytes(), before)

    def test_restore_and_erase_share_history_without_resetting_other_strokes(self):
        """Restoring one erased area leaves other erased pixels and history intact."""
        self.stroke((20, 30), (70, 30), 12)
        erased = self.document.image().tobytes()
        self.document.restore_segment((40, 30), (40, 30), 7)
        self.document.end_stroke()
        self.assertEqual(self.document.image().getpixel((40, 30))[3], 255)
        self.assertEqual(self.document.image().getpixel((20, 30))[3], 0)
        self.document.undo()
        self.assertEqual(self.document.image().tobytes(), erased)

    def test_click_and_outside_bounds_are_safe(self):
        """A click erases a circle and off-image strokes remain clipped safely."""
        self.stroke((0, 0), (0, 0), 10)
        self.assertEqual(self.document.image().getpixel((0, 0))[3], 0)
        self.stroke((-100, -100), (-90, -90), 4)
        self.assertEqual(self.document.image().getpixel((50, 50))[3], 255)

    def test_edge_has_partial_alpha_and_preserves_unaffected_partial_alpha(self):
        """Antialiased eraser edges do not threshold unrelated fine-hair opacity."""
        source = Image.new("RGBA", (100, 80), (60, 90, 120, 127))
        document = MaskDocument(source)
        document.begin_stroke()
        document.erase_segment((50, 40), (50, 40), 13)
        document.end_stroke()
        alpha = document.image().getchannel("A")
        self.assertEqual(alpha.getpixel((0, 0)), 127)
        self.assertTrue(any(0 < value < 127 for value in alpha.tobytes()))

    def test_undo_redo_restore_exact_alpha_and_group_pointer_samples(self):
        """Multiple pointer samples form one step with exact alpha restoration."""
        before = self.document.image().tobytes()
        self.document.begin_stroke()
        self.document.erase_segment((10, 10), (30, 30), 7)
        self.document.erase_segment((30, 30), (60, 10), 7)
        self.document.end_stroke()
        after = self.document.image().tobytes()
        self.assertTrue(self.document.can_undo)
        self.document.undo()
        self.assertEqual(self.document.image().tobytes(), before)
        self.assertFalse(self.document.can_undo)
        self.assertTrue(self.document.can_redo)
        self.document.redo()
        self.assertEqual(self.document.image().tobytes(), after)

    def test_new_stroke_after_undo_clears_redo(self):
        """A new edit branches history and invalidates the previous future."""
        self.stroke()
        self.document.undo()
        self.stroke((10, 60), (20, 60), 4)
        self.assertFalse(self.document.can_redo)

    def test_empty_stroke_does_not_create_history(self):
        """An untouched editor session has no artificial undo step."""
        self.document.begin_stroke()
        self.document.end_stroke()
        self.assertFalse(self.document.can_undo)

    def test_history_memory_is_bounded(self):
        """Repeated edits cannot retain unlimited alpha patches."""
        document = MaskDocument(self.source, history_limit_bytes=600)
        for y in range(10, 70, 10):
            document.begin_stroke()
            document.erase_segment((20, y), (40, y), 4)
            document.end_stroke()
        self.assertLessEqual(document.history_bytes, 600)
        self.assertEqual(document.image().getpixel((30, 10))[3], 0)

    def test_invalid_brush_values_are_rejected(self):
        """Non-finite coordinates and invalid diameters cannot corrupt the mask."""
        for start, diameter in [((float("nan"), 0), 5), ((0, 0), 0), ((0, 0), -2)]:
            with self.subTest(start=start, diameter=diameter):
                with self.assertRaises(ValueError):
                    self.document.erase_segment(start, (10, 10), diameter)


if __name__ == "__main__":
    unittest.main()
