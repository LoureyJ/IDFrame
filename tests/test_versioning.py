import json
from pathlib import Path
import tempfile
import unittest

from deployment.versioning import prepare_version


class VersioningTests(unittest.TestCase):
    def setUp(self):
        """Create isolated fixtures and resources needed by each test."""
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.settings = self.root / "host_settings.json"
        self.settings.write_text(
            json.dumps({"host": "127.0.0.1", "port": 8766, "version": "1.1.0"})
        )

    def tearDown(self):
        """Close test resources and remove temporary fixtures after each test."""
        self.temporary.cleanup()

    def test_changed_code_increments_once_and_unchanged_retries_reuse_version(self):
        """Verify that changed code increments once and unchanged retries reuse version."""
        self.assertEqual(prepare_version(self.root, "code-a"), "1.1.0")
        self.assertEqual(prepare_version(self.root, "code-b"), "1.1.1")
        self.assertEqual(prepare_version(self.root, "code-b"), "1.1.1")
        self.assertEqual(prepare_version(self.root, "code-c"), "1.1.2")
        self.assertIn('VERSION = "1.1.2"', (self.root / "app_version.py").read_text())
        self.assertEqual(json.loads(self.settings.read_text())["version"], "1.1.2")

    def test_explicit_newer_version_is_respected(self):
        """Verify that explicit newer version is respected."""
        prepare_version(self.root, "code-a")
        data = json.loads(self.settings.read_text())
        data["version"] = "1.2.0"
        self.settings.write_text(json.dumps(data))
        self.assertEqual(prepare_version(self.root, "code-b"), "1.2.0")

    def test_version_cannot_move_backwards(self):
        """Verify that version cannot move backwards."""
        prepare_version(self.root, "code-a")
        data = json.loads(self.settings.read_text())
        data["version"] = "1.0.0"
        self.settings.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "backwards"):
            prepare_version(self.root, "code-b")

    def test_bootstrap_uses_existing_installer_version_and_bumps(self):
        """Verify that bootstrap uses existing installer version and bumps."""
        repository = self.root / "build" / "installer-repository"
        repository.mkdir(parents=True)
        (repository / "manifest.json").write_text(
            json.dumps({"payload": {"version": "1.1.0"}})
        )
        self.assertEqual(prepare_version(self.root, "new-code"), "1.1.1")

    def test_preparation_never_publishes_or_rewrites_unchanged_client_version(self):
        """Verify that preparation never publishes or rewrites unchanged client version."""
        prepare_version(self.root, "code-a")
        version_file = self.root / "app_version.py"
        before = version_file.stat().st_mtime_ns
        prepare_version(self.root, "code-a")
        self.assertEqual(version_file.stat().st_mtime_ns, before)
        self.assertFalse(
            (self.root / ".host" / "repository" / "manifest.json").exists()
        )

    def test_real_code_hash_does_not_loop_on_generated_version_file(self):
        """Verify that real code hash does not loop on generated version file."""
        code = self.root / "app.py"
        code.write_text("value = 1")
        self.assertEqual(prepare_version(self.root), "1.1.0")
        self.assertEqual(prepare_version(self.root), "1.1.0")
        code.write_text("value = 2")
        self.assertEqual(prepare_version(self.root), "1.1.1")
        self.assertEqual(prepare_version(self.root), "1.1.1")


if __name__ == "__main__":
    unittest.main()
