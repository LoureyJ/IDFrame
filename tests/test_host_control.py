import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from deployment import host_control


class HostControlTests(unittest.TestCase):
    def test_other_application_on_port_reports_conflict(self):
        error = HTTPError("http://127.0.0.1:8765/health", 404, "Not Found", {}, None)
        with patch("deployment.host_control.build_opener") as builder:
            builder.return_value.open.side_effect = error
            with self.assertRaisesRegex(RuntimeError, "different server"):
                host_control.probe(8765)

    def test_background_host_uses_reported_pid_not_venv_launcher_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "host_settings.json").write_text(json.dumps({"host": "127.0.0.1", "port": 8766}))
            repository = root / ".host" / "repository"
            repository.mkdir(parents=True)
            (repository / "manifest.json").write_text("{}")
            identity = hashlib.sha256(str(repository.resolve()).casefold().encode()).hexdigest()
            with patch.object(host_control, "ROOT", root), patch.object(host_control, "probe", side_effect=[None, {"pid": 222, "repository": identity}]), patch.object(host_control.subprocess, "Popen") as popen:
                popen.return_value.pid = 111
                popen.return_value.poll.return_value = None
                host_control.start()
            state = json.loads((root / ".host" / "server-state.json").read_bytes())
            self.assertEqual(state, {"pid": 222, "port": 8766})

    def test_stop_does_not_terminate_reused_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".host").mkdir()
            (root / ".host" / "server-state.json").write_text(json.dumps({"pid": 111, "port": 8766}))
            with patch.object(host_control, "ROOT", root), patch.object(host_control, "probe", return_value={"pid": 222, "repository": "different-project"}), patch.object(host_control.os, "kill") as kill:
                with self.assertRaisesRegex(RuntimeError, "another process"):
                    host_control.stop()
                kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
