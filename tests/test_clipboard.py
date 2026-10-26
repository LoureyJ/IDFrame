from concurrent.futures import Future
import io
from pathlib import Path
import struct
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from PIL import Image

from app import PortraitApp
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
    def setUp(self):
        """Create isolated fixtures and resources needed by each test."""
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = PortraitApp(self.root)

    def tearDown(self):
        """Close test resources and remove temporary fixtures after each test."""
        if self.app.future is not None and not self.app.future.done():
            self.app.future.set_result(None)
        self.app.close()

    def test_paste_resets_previous_result_and_saves_without_source_path(self):
        """Verify that paste resets previous result and saves without source path."""
        self.app.result = Image.new("RGB", (208, 208))
        photo = Image.new("RGB", (30, 50), "blue")
        with patch("app.load_clipboard_photo", return_value=(photo, None)):
            self.assertEqual(self.app.paste_photo(), "break")
        self.assertIsNone(self.app.path)
        self.assertIsNone(self.app.result)
        self.assertEqual(str(self.app.remove_button["state"]), "normal")
        self.assertEqual(str(self.app.save_button["state"]), "disabled")
        self.app.result = photo
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "pasted.png"
            with (
                patch("app.ask_person_name", return_value="Juan Dela Cruz"),
                patch(
                    "app.filedialog.asksaveasfilename", return_value=str(output)
                ) as dialog,
            ):
                self.app.save()
            self.assertEqual(
                dialog.call_args.kwargs["initialfile"], "Juan_Dela_Cruz_2x2.png"
            )
            with Image.open(output) as saved:
                self.assertEqual(saved.size, (1200, 1200))
                self.assertEqual(saved.mode, "RGB")
                self.assertAlmostEqual(saved.info["dpi"][0], 600, delta=0.01)

    def test_empty_clipboard_retains_current_photo(self):
        """Verify that empty clipboard retains current photo."""
        old = Image.new("RGB", (30, 50), "blue")
        self.app.set_photo(old, None, "Old photo")
        with (
            patch(
                "app.load_clipboard_photo", side_effect=ValueError("Copy a photo first")
            ),
            patch("app.messagebox.showinfo"),
        ):
            self.app.paste_photo()
        self.assertIs(self.app.photo, old)

    def test_paste_is_blocked_during_processing_and_shortcuts_bound(self):
        """Verify that paste is blocked during processing and shortcuts bound."""
        self.assertTrue(self.root.bind("<Control-v>"))
        self.assertTrue(self.root.bind("<Control-V>"))
        self.app.future = Future()
        with patch("app.load_clipboard_photo") as reader:
            self.assertEqual(self.app.paste_photo(), "break")
            reader.assert_not_called()

    def test_paste_waits_until_completed_result_is_consumed(self):
        """Verify that paste waits until completed result is consumed."""
        self.app.future = Future()
        self.app.future.set_result(Image.new("RGB", (208, 208)))
        self.app.busy = True
        with patch("app.load_clipboard_photo") as reader:
            self.assertEqual(self.app.paste_photo(), "break")
            reader.assert_not_called()
