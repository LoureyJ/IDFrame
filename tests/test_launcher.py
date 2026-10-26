import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from deployment.launcher import create_update_dialog
from deployment.publisher import publish
from launcher_refresh import refresh_launcher


class LauncherRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "client"
        self.payload = self.root / "payload"
        self.payload.mkdir(parents=True)
        self.candidate = self.payload / "PortraitLauncher.exe"
        self.candidate.write_bytes(b"signed windowed launcher")
        self.target = self.root / "PortraitStudio.exe"
        self.target.write_bytes(b"original launcher")
        raw, self.public, _ = publish(self.payload, self.base / "repo", self.base / "key.pem", "1.1.4")
        (self.root / "installed-manifest.json").write_bytes(raw)

    def tearDown(self):
        self.temporary.cleanup()

    def test_signed_launcher_waits_for_session_lock_and_replaces_atomically(self):
        lock = io.BytesIO()
        try_lock = Mock(side_effect=[None, None, lock])
        with patch("launcher_refresh.time.sleep"):
            self.assertTrue(refresh_launcher(self.root, self.public, try_lock, timeout=2))
        self.assertTrue(lock.closed)
        self.assertEqual(self.target.read_bytes(), self.candidate.read_bytes())
        self.assertFalse(list(self.root.glob(".launcher-refresh-*.exe")))
        self.assertFalse(refresh_launcher(self.root, self.public, Mock()))

    def test_tampered_candidate_cannot_replace_launcher(self):
        self.candidate.write_bytes(b"tampered")
        try_lock = Mock()
        with self.assertRaisesRegex(ValueError, "verification"):
            refresh_launcher(self.root, self.public, try_lock)
        try_lock.assert_not_called()
        self.assertEqual(self.target.read_bytes(), b"original launcher")

    def test_locked_executable_is_retried_and_timeout_preserves_original(self):
        try_lock = Mock(side_effect=lambda root: io.BytesIO())
        with patch("launcher_refresh.os.replace", side_effect=PermissionError), patch("launcher_refresh.time.sleep"), patch("launcher_refresh.time.monotonic", side_effect=[0, 0, 2]):
            self.assertFalse(refresh_launcher(self.root, self.public, try_lock, timeout=1))
        self.assertEqual(self.target.read_bytes(), b"original launcher")
        self.assertFalse(list(self.root.glob(".launcher-refresh-*.exe")))


class UpdateDialogTests(unittest.TestCase):
    def test_centered_dialog_has_logo_heading_and_progress_below(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "payload/assets"
            assets.mkdir(parents=True)
            shutil.copy2(Path(__file__).resolve().parents[1] / "assets/portrait-studio.png", assets)
            window, status, progress = create_update_dialog(root)
            try:
                window.update()
                width, height = window.winfo_width(), window.winfo_height()
                expected = f"+{(window.winfo_screenwidth()-width)//2}+{(window.winfo_screenheight()-height)//2}"
                self.assertTrue(window.geometry().endswith(expected), window.geometry())
                self.assertEqual(window.title(), "Checking Updates")
                self.assertIsNotNone(window.logo)
                self.assertEqual(str(progress["mode"]), "indeterminate")
                self.assertGreater(progress.winfo_y(), 150)
                self.assertIn("Connecting", status.get())
            finally:
                window.destroy()


if __name__ == "__main__":
    unittest.main()
