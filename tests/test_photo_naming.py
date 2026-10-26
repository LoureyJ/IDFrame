from pathlib import Path
import tempfile
import unittest

from PIL import Image

from photo_naming import available_photo_path, portrait_filename
from portrait import save_portrait


class PhotoNamingTests(unittest.TestCase):
    def test_person_names_preserve_unicode_and_reject_unsafe_paths(self):
        self.assertEqual(portrait_filename("  María   Dela Cruz  "), "María_Dela_Cruz_2x2.png")
        self.assertEqual(portrait_filename("CON.Smith"), "Photo_CON.Smith_2x2.png")
        for name in ["", "...", "Juan/Smith", "Juan\\Smith", "Juan:Smith", 'Juan"Smith', "x" * 101]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                portrait_filename(name)

    def test_existing_person_photos_receive_incremented_suffixes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / portrait_filename("Juan Dela Cruz")
            self.assertEqual(available_photo_path(path), path)
            path.write_bytes(b"first portrait")
            second = path.with_name("Juan_Dela_Cruz_2x2_002.png")
            self.assertEqual(available_photo_path(path), second)
            second.write_bytes(b"second portrait")
            self.assertEqual(available_photo_path(path).name, "Juan_Dela_Cruz_2x2_003.png")
            self.assertEqual(path.read_bytes(), b"first portrait")

    def test_no_overwrite_save_protects_file_created_after_name_check(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Juan_2x2.png"
            self.assertEqual(available_photo_path(path), path)
            path.write_bytes(b"another process created this photo")
            with self.assertRaises(FileExistsError):
                save_portrait(Image.new("RGB", (10, 10), "red"), path, overwrite=False)
            self.assertEqual(path.read_bytes(), b"another process created this photo")
            self.assertEqual(list(Path(directory).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
