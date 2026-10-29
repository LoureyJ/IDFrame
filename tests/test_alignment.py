"""Offline alignment preserves documents and handles uncertain detections safely."""

import math
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

import test_qt_app as fixtures
from alignment import OfflineAligner
from download_model import download_alignment_model


def face(roll=0, score=0.98):
    """Create a known eye line and anatomically upright nose/mouth landmarks."""
    y = 30 + 40 * math.tan(math.radians(roll))
    return {
        "points": np.array(
            [[30.0, 30.0], [70.0, y], [50.0, 60.0], [35.0, 80.0], [65.0, 80.0]]
        ),
        "score": score,
    }


class AlignmentTests(unittest.TestCase):
    """Check sign, quarter turns and fail-closed behavior without model downloads."""

    def test_sideways_orientation_and_roll_are_combined(self):
        """A 90-degree coarse correction includes the remaining eye-line tilt."""
        aligner = OfflineAligner()
        with patch.object(aligner, "_detect", side_effect=[[], [face(10)], [], []]):
            self.assertAlmostEqual(aligner.estimate(Image.new("RGB", (100, 100))), -100)

    def test_no_face_or_multiple_people_leave_angle_unchanged(self):
        """An uncertain image must never manufacture an automatic correction."""
        aligner = OfflineAligner()
        for results in ([[], [], [], []], [[face(), face()]]):
            with patch.object(aligner, "_detect", side_effect=results):
                self.assertIsNone(aligner.estimate(Image.new("RGB", (100, 100))))

    def test_missing_model_has_actionable_offline_error(self):
        """A missing local detector reports setup instructions without a network call."""
        aligner = OfflineAligner(model_path="missing-alignment-model.onnx")
        with self.assertRaisesRegex(FileNotFoundError, "setup"):
            aligner.estimate(Image.new("RGB", (100, 100)))

    def test_setup_verifies_alignment_model_and_preserves_good_file_on_failure(self):
        """Setup installs verified bytes once and never activates a corrupt download."""
        content = b"verified test detector"
        expected = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "face_alignment.onnx"
            with (
                patch("alignment.MODEL_PATH", target),
                patch("alignment.MODEL_SHA256", expected),
            ):
                with patch(
                    "download_model.urlopen", return_value=io.BytesIO(content)
                ) as network:
                    download_alignment_model()
                    download_alignment_model()
                    network.assert_called_once()
                self.assertEqual(target.read_bytes(), content)
                # An old, unrecognized detector must survive a failed replacement.
                target.write_bytes(b"previous version")
                with patch(
                    "download_model.urlopen", return_value=io.BytesIO(b"corrupt")
                ):
                    with self.assertRaisesRegex(RuntimeError, "checksum"):
                        download_alignment_model()
                self.assertEqual(target.read_bytes(), b"previous version")
                self.assertFalse(target.with_suffix(".download").exists())


class AlignmentInterfaceTests(unittest.TestCase):
    """Exercise the top-row action through Qt worker completion and document state."""

    setUp = fixtures.QtAppTests.setUp
    tearDown = fixtures.QtAppTests.tearDown

    def test_toolbar_order_colors_and_alignment_preserve_edits(self):
        """Explicit alignment changes only rotation and stays idle until clicked."""
        window = self.window
        source = Image.new("RGBA", (100, 100), "red")
        source.putpixel((50, 50), (255, 0, 0, 0))
        window.set_cutout(source)
        window.crop.set_framing(zoom=2, offset=(0.1, 0.1), brightness=0.5, rotation=90)
        buttons = [
            window.open_button,
            window.paste_button,
            window.auto_skew_button,
            window.edit_button,
        ]
        self.assertEqual(len({b.property("actionColor") for b in buttons}), 4)
        fixtures.QT_APP.processEvents()
        self.assertEqual([b.x() for b in buttons], sorted(b.x() for b in buttons))
        with patch.object(window.aligner, "estimate", return_value=-95) as estimate:
            fixtures.QT_APP.processEvents()
            estimate.assert_not_called()
            window.auto_skew_button.click()
            self.assertFalse(window.auto_skew_button.isEnabled())
            fixtures.wait_until(lambda: not window.busy)
            window.auto_skew_button.click()
            fixtures.wait_until(lambda: not window.busy)
        self.assertEqual(window.crop.rotation, -95)
        self.assertEqual(window.crop.zoom, 2)
        self.assertEqual(window.crop.offset, (0.1, 0.1))
        self.assertEqual(window.crop.brightness, 0.5)
        self.assertEqual(window.crop.cutout.tobytes(), source.tobytes())
        self.assertEqual(window.rotation_slider.minimum(), -1800)
        self.assertEqual(window.rotation_slider.maximum(), 1800)
        with patch.object(window.aligner, "estimate", return_value=None):
            window.auto_skew_button.click()
            fixtures.wait_until(lambda: not window.busy)
        self.assertEqual(window.crop.rotation, -95)


if __name__ == "__main__":
    unittest.main()
