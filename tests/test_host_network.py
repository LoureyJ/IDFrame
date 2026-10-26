import json
import msvcrt
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from deployment.host_network import detect_lan_ip, sync_host_address


class HostNetworkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".host").mkdir()
        self.settings = self.root / "host_settings.json"
        self.settings.write_text(json.dumps({"host": "192.168.1.10", "port": 8766,
                                             "version": "1.1.9", "auto_detect_ip": True}))
        self.client = self.root / "client.json"
        self.client.write_text(json.dumps({"host_url": "http://127.0.0.1:8766", "keep": "value"}))
        self.binding = self.root / ".host/host-client.json"
        self.binding.write_text(json.dumps({"computer": socket.gethostname(), "client_config": str(self.client)}))

    def tearDown(self):
        self.temporary.cleanup()

    def test_changes_follow_active_ip_preserving_version_and_client_fields(self):
        with patch("deployment.host_network.detect_lan_ip", side_effect=["192.168.83.169", "192.168.208.169"]):
            for address in ["192.168.83.169", "192.168.208.169"]:
                settings = sync_host_address(self.root)
                self.assertEqual(settings["host"], address)
                self.assertEqual(settings["version"], "1.1.9")
                client = json.loads(self.client.read_text())
                self.assertEqual(client["host_url"], f"http://{address}:8766")
                self.assertEqual(client["keep"], "value")

    def test_offline_keeps_previous_address_and_unchanged_sync_keeps_timestamps(self):
        with patch("deployment.host_network.detect_lan_ip", return_value=None):
            self.assertEqual(sync_host_address(self.root)["host"], "192.168.1.10")
        with patch("deployment.host_network.detect_lan_ip", return_value="192.168.83.169"):
            sync_host_address(self.root)
            timestamps = (self.settings.stat().st_mtime_ns, self.client.stat().st_mtime_ns)
            sync_host_address(self.root)
            self.assertEqual(timestamps, (self.settings.stat().st_mtime_ns, self.client.stat().st_mtime_ns))

    def test_other_computer_binding_is_not_modified(self):
        self.binding.write_text(json.dumps({"computer": "another-computer", "client_config": str(self.client)}))
        original = self.client.read_bytes()
        with patch("deployment.host_network.detect_lan_ip", return_value="192.168.83.169"):
            sync_host_address(self.root)
        self.assertEqual(self.client.read_bytes(), original)

    def test_publisher_lock_prevents_stale_settings_write(self):
        with (self.root / ".host/publish.lock").open("w+b") as lock:
            lock.write(b"0")
            lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            with patch("deployment.host_network.detect_lan_ip", return_value="192.168.83.169") as detect:
                self.assertEqual(sync_host_address(self.root)["host"], "192.168.1.10")
                detect.assert_not_called()

    def test_route_detection_sends_no_data_and_rejects_link_local(self):
        with patch("deployment.host_network.socket.socket") as factory:
            connection = factory.return_value.__enter__.return_value
            connection.getsockname.return_value = ("192.168.83.169", 12345)
            self.assertEqual(detect_lan_ip(), "192.168.83.169")
            connection.send.assert_not_called()
            connection.sendto.assert_not_called()
            connection.getsockname.return_value = ("169.254.1.1", 12345)
            self.assertIsNone(detect_lan_ip())


if __name__ == "__main__":
    unittest.main()
