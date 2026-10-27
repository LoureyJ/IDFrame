"""P3M experiments must be explicit, local, reversible, and safe for current photos."""

import threading
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QDialog

import test_qt_app as fixtures
from app import PortraitApp


class P3MPreviewTests(unittest.TestCase):
    """Exercise comparison actions through the real main-window worker pipeline."""

    setUp = fixtures.QtAppTests.setUp
    tearDown = fixtures.QtAppTests.tearDown

    def prepare_portrait(self):
        """Create distinct current/candidate masks with retained print adjustments."""
        self.window.set_photo(Image.new("RGB", (100, 100), "red"))
        current = Image.new("RGBA", (100, 100), "red")
        candidate = current.copy()
        candidate.paste((255, 0, 0, 0), (40, 40, 60, 60))
        self.window.set_cutout(current)
        self.window.crop.set_framing(zoom=2, brightness=0.5)
        self.window.person_name = "Test Person"
        return current, candidate

    def test_cancel_preserves_result_and_runs_inference_off_gui_thread(self):
        """Previewing a candidate does not commit pixels or change the default model."""
        current, candidate = self.prepare_portrait()
        threads = []
        frames = []

        def infer(photo):
            """Record execution context and return a deterministic experimental mask."""
            threads.append(threading.get_ident())
            return candidate

        def inspect_comparison(dialog):
            """Check worker-rendered frames against this photo's export adjustments."""
            frames.append(
                (
                    dialog.current_view.image.width(),
                    dialog.current_view.image.pixelColor(600, 600).red(),
                    dialog.candidate_view.image.pixelColor(600, 600).getRgb()[:3],
                )
            )
            return QDialog.DialogCode.Rejected

        with (
            patch.object(self.window, "process_p3m_preview", side_effect=infer),
            patch(
                "qt_model_preview.ModelPreviewDialog.exec",
                new=inspect_comparison,
            ),
        ):
            self.window.open_p3m_preview()
            fixtures.wait_until(lambda: not self.window.busy)
        self.assertEqual(frames, [(1200, 127, (255, 255, 255))])
        self.assertEqual(len(threads), 1)
        self.assertNotEqual(threads[0], threading.get_ident())
        self.assertIs(self.window.crop.cutout, current)
        self.assertEqual(self.window.crop.zoom, 2)
        self.assertEqual(self.window.crop.brightness, 0.5)
        self.assertEqual(self.window.person_name, "Test Person")
        self.assertEqual(self.window.removal_mode, "Auto")

    def test_apply_changes_only_this_photo_and_preserves_export_adjustments(self):
        """Explicit acceptance commits the candidate while crop/light/default stay intact."""
        _, candidate = self.prepare_portrait()
        with (
            patch.object(self.window, "process_p3m_preview", return_value=candidate),
            patch(
                "qt_model_preview.ModelPreviewDialog.exec",
                return_value=QDialog.DialogCode.Accepted,
            ),
        ):
            self.window.open_p3m_preview()
            fixtures.wait_until(lambda: not self.window.busy)
        self.assertIs(self.window.crop.cutout, candidate)
        self.assertEqual(self.window.crop.zoom, 2)
        self.assertEqual(self.window.crop.brightness, 0.5)
        self.assertEqual(self.window.removal_mode, "Auto")
        self.assertIn("P3M", self.window.status_label.text())
        self.assertEqual(
            self.window.crop.export().getpixel((600, 600)), (255, 255, 255)
        )
        self.assertTrue(self.window.edit_button.isEnabled())
        self.assertTrue(self.window.save_button.isEnabled())

    def test_preview_unavailable_without_local_model_or_finished_portrait(self):
        """Installed clients without the experimental weights have no preview entry point."""
        self.assertFalse(self.window.p3m_preview_button.isEnabled())
        with patch("app.P3M_PREVIEW_MODEL", Path(self.temp.name) / "absent.onnx"):
            window = PortraitApp(
                preferences_path=Path(self.temp.name) / "other.json",
                sync_shortcuts=False,
            )
            window.show()
            fixtures.QT_APP.processEvents()
            try:
                self.assertTrue(window.p3m_preview_button.isHidden())
            finally:
                window.close()

    def test_failed_candidate_preserves_current_result_and_recovers_controls(self):
        """Inference errors cannot erase an existing result or leave the UI busy."""
        current, _ = self.prepare_portrait()
        with (
            patch.object(
                self.window,
                "process_p3m_preview",
                side_effect=ValueError("candidate failed"),
            ),
            patch("app.QMessageBox.warning") as warning,
        ):
            self.window.open_p3m_preview()
            fixtures.wait_until(lambda: not self.window.busy)
            warning.assert_called_once()
        self.assertIs(self.window.crop.cutout, current)
        self.assertTrue(self.window.save_button.isEnabled())

    def test_replaced_document_rejects_stale_comparison(self):
        """A late candidate never opens a comparison against a newer source."""
        _, candidate = self.prepare_portrait()
        release = threading.Event()

        def infer(photo):
            """Hold the old document's job until a replacement is installed."""
            release.wait(3)
            return candidate

        with (
            patch.object(self.window, "process_p3m_preview", side_effect=infer),
            patch("qt_model_preview.ModelPreviewDialog.exec") as show,
        ):
            self.window.open_p3m_preview()
            self.window.set_photo(Image.new("RGB", (80, 80), "blue"))
            release.set()
            fixtures.wait_until(lambda: not self.window.jobs.busy)
            show.assert_not_called()
        self.assertIsNone(self.window.crop.cutout)

    def test_closing_during_inference_does_not_open_comparison(self):
        """Graceful shutdown drains preview work without opening a new modal window."""
        _, candidate = self.prepare_portrait()
        release = threading.Event()

        def infer(photo):
            """Keep inference pending until the window has requested closure."""
            release.wait(3)
            return candidate

        with (
            patch.object(self.window, "process_p3m_preview", side_effect=infer),
            patch("qt_model_preview.ModelPreviewDialog.exec") as show,
        ):
            self.window.open_p3m_preview()
            self.window.close()
            release.set()
            fixtures.wait_until(lambda: not self.window.isVisible())
            show.assert_not_called()

    def test_comparison_displays_matching_white_frames_on_small_screen(self):
        """Comparison pixels use the exact current export geometry without resize jobs."""
        from qt_model_preview import ModelPreviewDialog
        from qt_preview import image_to_qt

        available = QRect(0, 0, 683, 512)
        screen = SimpleNamespace(availableGeometry=lambda: available)
        current = image_to_qt(Image.new("RGB", (1200, 1200), (127, 0, 0)))
        candidate = image_to_qt(Image.new("RGB", (1200, 1200), "white"))
        with patch("qt_model_preview.QApplication.primaryScreen", return_value=screen):
            dialog = ModelPreviewDialog(current, candidate, self.window)
        dialog.show()
        fixtures.QT_APP.processEvents()
        try:
            self.assertLessEqual(dialog.frameGeometry().width(), available.width())
            self.assertLessEqual(dialog.frameGeometry().height(), available.height())
            self.assertEqual(dialog.current_view.image.pixelColor(600, 600).red(), 127)
            self.assertEqual(
                dialog.candidate_view.image.pixelColor(600, 600).red(), 255
            )
        finally:
            dialog.reject()
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
