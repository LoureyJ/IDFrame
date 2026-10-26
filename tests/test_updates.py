import base64
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from cryptography.exceptions import InvalidSignature

from deployment.common import atomic_write, canonical, digest, safe_path
from deployment.publisher import publish, signing_key
from deployment.server import handler_for
from deployment.updater import apply_update, recover, validate_url


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        self.source.mkdir()
        self.client = self.base / "client"
        (self.client / "payload").mkdir(parents=True)
        self.repo = self.base / "repository"
        self.key = self.base / "secret.pem"
        self.requests = []
        parent = handler_for(self.repo)
        requests = self.requests

        class Handler(parent):
            def do_GET(self):
                requests.append(self.path)
                super().do_GET()

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def publish(self, version="1.0.0"):
        raw, self.public, _ = publish(self.source, self.repo, self.key, version)
        return raw

    def update(self):
        return apply_update(self.client, self.url, self.public)

    def initial(self):
        (self.source / "app.py").write_text("old code")
        (self.source / "model.onnx").write_bytes(b"unchanged model")
        raw = self.publish()
        self.update()
        self.requests.clear()
        return raw

    def test_only_changed_file_downloaded_unchanged_file_not_touched(self):
        self.initial()
        model = self.client / "payload" / "model.onnx"
        timestamp = model.stat().st_mtime_ns
        (self.source / "app.py").write_text("new code")
        self.publish("1.0.1")
        self.update()
        self.assertEqual((self.client / "payload" / "app.py").read_text(), "new code")
        self.assertEqual(model.stat().st_mtime_ns, timestamp)
        self.assertEqual(self.requests, ["/manifest.json", "/blobs/" + digest(self.source / "app.py")])

    def test_no_changes_means_no_file_downloads(self):
        self.initial()
        self.update()
        self.assertEqual(self.requests, ["/manifest.json"])

    def test_download_progress_counts_bytes_across_changed_files(self):
        self.initial()
        (self.source / "app.py").write_bytes(b"updated code")
        (self.source / "new.bin").write_bytes(b"x" * (1024 * 1024 + 12))
        self.publish("1.1.4")
        events = []
        apply_update(self.client, self.url, self.public, transfer_progress=lambda done, total: events.append((done, total)))
        total = len(b"updated code") + 1024 * 1024 + 12
        self.assertEqual(events[0], (0, total))
        self.assertEqual(events[-1], (total, total))
        self.assertEqual([v[0] for v in events], sorted(v[0] for v in events))
        self.assertGreater(len(events), 3)

    def test_corrupt_blob_leaves_installed_release_untouched(self):
        previous = self.initial()
        (self.source / "app.py").write_text("new code")
        self.publish("1.0.1")
        (self.repo / "blobs" / digest(self.source / "app.py")).write_bytes(b"bad data")
        with self.assertRaises(ValueError):
            self.update()
        self.assertEqual((self.client / "payload" / "app.py").read_text(), "old code")
        self.assertEqual((self.client / "installed-manifest.json").read_bytes(), previous)

    def test_unsigned_changes_rejected(self):
        self.initial()
        path = self.repo / "manifest.json"
        data = json.loads(path.read_bytes())
        data["payload"]["version"] = "evil"
        path.write_bytes(canonical(data))
        with self.assertRaises(InvalidSignature):
            self.update()

    def test_rollback_on_install_failure(self):
        previous = self.initial()
        (self.source / "app.py").write_text("new code")
        (self.source / "added.py").write_text("new module")
        self.publish("1.0.1")
        original_replace = Path.replace

        def fail_one_replace(path, target):
            if "files" in path.parts and path.name == "app.py":
                raise PermissionError("simulated locked file")
            return original_replace(path, target)

        with patch.object(Path, "replace", fail_one_replace), self.assertRaises(PermissionError):
            self.update()
        self.assertEqual((self.client / "payload" / "app.py").read_text(), "old code")
        self.assertFalse((self.client / "payload" / "added.py").exists())
        self.assertEqual((self.client / "installed-manifest.json").read_bytes(), previous)

    def test_crash_recovery_restores_backup_and_manifest(self):
        previous = self.initial()
        transaction = self.client / ".update-transaction"
        backup = transaction / "backup" / "app.py"
        backup.parent.mkdir(parents=True)
        (self.client / "payload" / "app.py").replace(backup)
        (self.client / "payload" / "app.py").write_text("partly installed")
        journal = {"operations": [{"name": "app.py", "existed": True}],
                   "previous": base64.b64encode(previous).decode(), "committed": False}
        atomic_write(transaction / "journal.json", canonical(journal))
        recover(self.client)
        recover(self.client)
        self.assertEqual((self.client / "payload" / "app.py").read_text(), "old code")
        self.assertFalse(transaction.exists())

    def test_delete_managed_file_and_preserve_unmanaged_data(self):
        self.initial()
        personal = self.client / "payload" / "personal.txt"
        personal.write_text("keep me")
        (self.source / "app.py").unlink()
        self.publish("1.0.1")
        self.update()
        self.assertFalse((self.client / "payload" / "app.py").exists())
        self.assertEqual(personal.read_text(), "keep me")

    def test_older_release_rejected(self):
        old = self.initial()
        (self.source / "app.py").write_text("new code")
        self.publish("1.0.1")
        self.update()
        (self.repo / "manifest.json").write_bytes(old)
        with self.assertRaisesRegex(ValueError, "older release"):
            self.update()

    def test_path_traversal_and_windows_special_paths_rejected(self):
        for name in ("../outside", "/absolute", "C:/escape", "a\\b", "a/../b", "a//b", "con.txt", "aux", "a./b", "x:stream", "a\x00b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_path(self.client, name)

    def test_private_key_is_not_served(self):
        from urllib.error import HTTPError
        from urllib.request import urlopen
        self.initial()
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/../secret.pem")
        self.assertEqual(error.exception.code, 404)

    def test_signed_unsafe_path_is_rejected(self):
        self.initial()
        key, _ = signing_key(self.key)
        path = self.repo / "manifest.json"
        data = json.loads(path.read_bytes())
        entry = data["payload"]["files"].pop("app.py")
        data["payload"]["files"]["../outside.exe"] = entry
        data["signature"] = base64.b64encode(key.sign(canonical(data["payload"]))).decode()
        path.write_bytes(canonical(data))
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.update()

    def test_url_configuration(self):
        self.assertEqual(validate_url("http://192.168.1.10:8765/"), "http://192.168.1.10:8765")
        for url in ("file:///C:/private", "http://user:pass@host", "http://host/path", "http://host:99999"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)


if __name__ == "__main__":
    unittest.main()
