import io
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from photo_clipboard import load_clipboard_photo


def image_data(fmt, mode="RGB", color="red"):
    """Encode an in-memory image as clipboard test bytes."""
    stream = io.BytesIO()
    Image.new(mode, (30, 50), color).save(stream, fmt)
    data = stream.getvalue()
    return data[14:] if fmt == "BMP" else data


class ClipboardTests(unittest.TestCase):
    def test_png_image_and_transparency(self):
        """Verify that png image and transparency."""
        data = image_data("PNG", "RGBA", (0, 0, 0, 128))
        with patch(
            "photo_clipboard._read_windows_clipboard", return_value=("png", data)
        ):
            photo, path = load_clipboard_photo()
        self.assertEqual(photo.size, (30, 50))
        self.assertEqual(photo.mode, "RGB")
        self.assertEqual(photo.getpixel((0, 0)), (127, 127, 127))
        self.assertIsNone(path)

    def test_windows_dib_image(self):
        """Verify that windows dib image."""
        with patch(
            "photo_clipboard._read_windows_clipboard",
            return_value=("DIB", image_data("BMP")),
        ):
            photo, path = load_clipboard_photo()
        self.assertEqual(photo.getpixel((0, 0)), (255, 0, 0))
        self.assertIsNone(path)

    def test_copied_file_list_skips_non_images(self):
        """Verify that copied file list skips non images."""
        with tempfile.TemporaryDirectory() as folder:
            text = Path(folder) / "notes.txt"
            text.write_text("not an image")
            original = Path(folder) / "portrait.png"
            Image.new("RGB", (30, 50), "blue").save(original)
            header = struct.pack("<IiiII", 20, 0, 0, 0, 1)
            data = header + (str(text) + "\0" + str(original) + "\0\0").encode(
                "utf-16le"
            )
            with patch(
                "photo_clipboard._read_windows_clipboard", return_value=("file", data)
            ):
                photo, path = load_clipboard_photo()
            self.assertEqual(path, original)
            self.assertEqual(photo.getpixel((0, 0)), (0, 0, 255))

    def test_empty_unsupported_or_malformed_clipboard(self):
        """Verify that empty unsupported or malformed clipboard."""
        for value in (
            (None, None),
            ("text", b"hello"),
            ("file", b"short"),
            ("png", b"invalid"),
        ):
            with (
                self.subTest(value=value),
                patch("photo_clipboard._read_windows_clipboard", return_value=value),
            ):
                with self.assertRaises((ValueError, OSError)):
                    load_clipboard_photo()


class ClipboardAppTests(unittest.TestCase):
    """Use Qt clipboard fixtures without modifying the user's real clipboard."""

    def setUp(self):
        """Create a Qt application window with isolated preferences."""
        import test_qt_app as fixtures

        self.fixtures = fixtures
        fixtures.QtAppTests.setUp(self)
        self.app = self.window

    def tearDown(self):
        """Drain worker callbacks and release the test window."""
        self.fixtures.QtAppTests.tearDown(self)

    def test_paste_resets_previous_result_and_saves_without_source_path(self):
        """Native image paste clears prior edits and retains person-based saving."""
        from types import SimpleNamespace
        from qt_preview import image_to_qt

        photo = Image.new("RGB", (30, 50), "blue")
        mime = SimpleNamespace(hasImage=lambda: True)
        clipboard = SimpleNamespace(
            mimeData=lambda: mime, image=lambda: image_to_qt(photo)
        )
        self.app.set_cutout(Image.new("RGBA", (40, 40), "red"))
        with patch("app.QApplication.clipboard", return_value=clipboard):
            self.app.paste_photo()
            self.fixtures.wait_until(lambda: not self.app.busy)
        self.assertIsNone(self.app.path)
        self.assertIsNone(self.app.result)
        self.assertTrue(self.app.remove_button.isEnabled())
        self.assertFalse(self.app.save_button.isEnabled())
        self.app.set_cutout(photo.convert("RGBA"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pasted.png"
            with (
                patch("app.ask_person_name", return_value="Juan Dela Cruz"),
                patch(
                    "app.QFileDialog.getSaveFileName", return_value=(str(path), "PNG")
                ) as dialog,
            ):
                self.app.save()
                self.fixtures.wait_until(lambda: not self.app.busy)
            self.assertEqual(dialog.call_args.args[2], "Juan_Dela_Cruz_2x2.png")
            with Image.open(path) as saved:
                self.assertEqual(saved.size, (1200, 1200))
                self.assertEqual(saved.mode, "RGB")

    def test_empty_clipboard_retains_current_photo(self):
        """Unsupported clipboard data leaves the current portrait intact."""
        from types import SimpleNamespace

        old = Image.new("RGB", (30, 50), "blue")
        self.app.set_photo(old)
        mime = SimpleNamespace(hasImage=lambda: False, hasUrls=lambda: False)
        with (
            patch(
                "app.QApplication.clipboard",
                return_value=SimpleNamespace(mimeData=lambda: mime),
            ),
            patch("app.QMessageBox.information"),
        ):
            self.app.paste_photo()
        self.assertIs(self.app.photo, old)

    def test_paste_is_blocked_during_processing_and_shortcuts_bound(self):
        """Busy operations suppress paste while the native shortcut stays registered."""
        self.assertFalse(self.app.paste_shortcut.key().isEmpty())
        self.app._set_busy(True)
        with patch("app.QApplication.clipboard") as reader:
            self.app.paste_photo()
            reader.assert_not_called()
        self.app._set_busy(False)

    def test_paste_waits_until_completed_result_is_consumed(self):
        """A finished worker cannot enable paste before its GUI callback is delivered."""
        import time

        self.app._work(lambda: None, lambda value: None, "Fixture")
        time.sleep(0.03)
        with patch("app.QApplication.clipboard") as reader:
            self.app.paste_photo()
            reader.assert_not_called()
        self.fixtures.wait_until(lambda: not self.app.busy)

    def test_large_clipboard_conversion_runs_off_the_gui_thread(self):
        """Only clipboard acquisition touches Qt's GUI thread; pixel conversion is work."""
        from types import SimpleNamespace
        import threading
        from qt_preview import image_to_qt, qt_to_image

        snapshot = image_to_qt(Image.new("RGB", (200, 300), "blue"))
        mime = SimpleNamespace(hasImage=lambda: True)
        clipboard = SimpleNamespace(mimeData=lambda: mime, image=lambda: snapshot)
        observed = []

        def convert(image):
            """Record the conversion thread while executing the real pixel copy."""
            observed.append(threading.get_ident())
            return qt_to_image(image)

        with (
            patch("app.QApplication.clipboard", return_value=clipboard),
            patch("app.qt_to_image", side_effect=convert),
        ):
            self.app.paste_photo()
            self.fixtures.wait_until(lambda: not self.app.busy)
        self.assertEqual(len(observed), 1)
        self.assertNotEqual(observed[0], threading.get_ident())
