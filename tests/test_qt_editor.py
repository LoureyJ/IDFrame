"""Editor sessions preserve original pixels and map the brush through view transforms."""

import unittest
from unittest.mock import patch
from types import SimpleNamespace

from PIL import Image
from PySide6.QtCore import QPointF, QRect, QPoint
from PySide6.QtWidgets import QDialog, QDialogButtonBox
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

import test_qt_app as fixtures
from qt_editor import CleanupEditor


class EditorTests(unittest.TestCase):
    """Exercise a real separate Qt editor against the existing application fixture."""

    setUp = fixtures.QtAppTests.setUp
    tearDown = fixtures.QtAppTests.tearDown

    def test_restore_button_reveals_original_pixels_and_supports_history(self):
        """The Restore tool paints original RGB, with the shared size and undo/redo."""
        source = Image.new("RGBA", (100, 80), (60, 90, 120, 0))
        editor = CleanupEditor(source, self.window)
        editor.size_slider.setValue(8)
        editor.restore_button.click()
        self.assertTrue(editor.restore_button.isChecked())
        self.assertFalse(editor.erase_button.isChecked())
        editor.view.paint_at(QPointF(40, 30), QPointF(60, 30), source_coordinates=True)
        editor.view.finish_stroke()
        self.assertEqual(editor.edited_image().getpixel((50, 30)), (60, 90, 120, 255))
        editor.undo_button.click()
        self.assertEqual(editor.edited_image().getpixel((50, 30))[3], 0)
        editor.redo_button.click()
        self.assertEqual(editor.edited_image().getpixel((50, 30))[3], 255)
        editor.erase_button.click()
        editor.view.paint_at(QPointF(50, 30), QPointF(50, 30), source_coordinates=True)
        editor.accept()
        self.assertEqual(editor.edited_image().getpixel((50, 30))[3], 0)
        self.assertEqual(source.getpixel((50, 30)), (60, 90, 120, 0))
        editor.deleteLater()

    def test_restore_mouse_click_applies_to_portrait_without_resetting_framing(self):
        """A real Restore click repairs AI alpha and commits while keeping adjustments."""
        source = Image.new("RGBA", (100, 80), (60, 90, 120, 255))
        source.putpixel((50, 40), (60, 90, 120, 0))
        self.window.set_cutout(source)
        self.window.crop.set_framing(zoom=2, offset=(0.1, 0.1), brightness=0.75)
        editor = CleanupEditor(source, self.window)
        editor.show()
        fixtures.QT_APP.processEvents()
        editor.restore_button.click()
        point = editor.view.source_to_view(QPointF(50, 40)).toPoint()
        QTest.mouseClick(editor.view, Qt.MouseButton.LeftButton, pos=point)
        editor.accept()
        self.window.apply_edits(editor.edited_image())
        self.assertEqual(self.window.crop.cutout.getpixel((50, 40)), (60, 90, 120, 255))
        self.assertEqual(self.window.crop.zoom, 2)
        self.assertEqual(self.window.crop.offset, (0.1, 0.1))
        self.assertEqual(self.window.crop.brightness, 0.75)
        self.assertEqual(source.getpixel((50, 40))[3], 0)
        editor.deleteLater()

    def test_small_screen_contains_editor_apply_action(self):
        """Editor controls remain reachable below the previous fixed minimum size."""
        available = QRect(0, 0, 600, 400)
        screen = SimpleNamespace(availableGeometry=lambda: available)
        with patch("qt_editor.QApplication.primaryScreen", return_value=screen):
            editor = CleanupEditor(Image.new("RGBA", (100, 80), "red"), self.window)
        editor.show()
        fixtures.QT_APP.processEvents()
        try:
            self.assertLessEqual(editor.frameGeometry().width(), available.width())
            self.assertLessEqual(editor.frameGeometry().height(), available.height())
            apply = editor.findChild(QDialogButtonBox).button(
                QDialogButtonBox.StandardButton.Apply
            )
            self.assertTrue(
                editor.rect().contains(
                    QRect(apply.mapTo(editor, QPoint()), apply.size())
                )
            )
        finally:
            editor.reject()
            editor.deleteLater()

    def test_editor_cancel_discards_erasures(self):
        """Cancel leaves the caller's original cutout byte-for-byte unchanged."""
        source = Image.new("RGBA", (100, 80), "red")
        original = source.tobytes()
        editor = CleanupEditor(source, self.window)
        editor.view.paint_at(QPointF(40, 30), QPointF(60, 30), source_coordinates=True)
        editor.view.finish_stroke()
        editor.reject()
        self.assertEqual(editor.result(), QDialog.DialogCode.Rejected)
        self.assertEqual(source.tobytes(), original)
        editor.deleteLater()

    def test_editor_apply_retains_crop_brightness_and_saved_mask(self):
        """Committed alpha changes appear in export without resetting adjustments."""
        source = Image.new("RGBA", (100, 100), "red")
        self.window.set_cutout(source)
        self.window.crop.set_framing(zoom=2, offset=(0.1, 0.1), brightness=0.75)
        editor = CleanupEditor(source, self.window)
        editor.view.paint_at(QPointF(50, 50), QPointF(50, 50), source_coordinates=True)
        editor.accept()
        self.window.apply_edits(editor.edited_image())
        self.assertEqual(self.window.crop.zoom, 2)
        self.assertEqual(self.window.crop.offset, (0.1, 0.1))
        self.assertEqual(self.window.crop.brightness, 0.75)
        self.assertEqual(self.window.crop.cutout.getpixel((50, 50))[3], 0)
        self.window.crop.reset()
        self.assertEqual(self.window.crop.cutout.getpixel((50, 50))[3], 0)
        editor.deleteLater()

    def test_brush_inverse_transform_and_history_buttons(self):
        """Zoom/pan map a display pointer to the matching source pixel."""
        editor = CleanupEditor(Image.new("RGBA", (200, 100), "red"), self.window)
        editor.resize(800, 600)
        editor.show()
        fixtures.QT_APP.processEvents()
        editor.view.scale_factor = 2.5
        editor.view.pan = QPointF(30, -20)
        source_point = QPointF(80, 40)
        view_point = editor.view.source_to_view(source_point)
        actual = editor.view.view_to_source(view_point)
        self.assertAlmostEqual(actual.x(), source_point.x())
        self.assertAlmostEqual(actual.y(), source_point.y())
        before = editor.edited_image().tobytes()
        editor.view.paint_at(view_point, view_point)
        editor.view.finish_stroke()
        self.assertEqual(editor.edited_image().getpixel((80, 40))[3], 0)
        self.assertTrue(editor.undo_button.isEnabled())
        editor.undo_button.click()
        self.assertEqual(editor.edited_image().tobytes(), before)
        self.assertTrue(editor.redo_button.isEnabled())
        editor.redo_button.click()
        self.assertEqual(editor.edited_image().getpixel((80, 40))[3], 0)
        editor.reject()
        editor.deleteLater()


if __name__ == "__main__":
    unittest.main()
