"""Follow this host PC's active LAN address without changing remote clients."""

import ipaddress
import json
import msvcrt
from pathlib import Path
import socket

from deployment.common import atomic_write


def detect_lan_ip():
    # UDP connect asks Windows to select its outgoing interface; no data is sent
    # and no response or internet connection is required.
    """Ask routing for a usable local IPv4 address without sending network data."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(("192.0.2.1", 9))
            address = connection.getsockname()[0]
        parsed = ipaddress.ip_address(address)
        if not (
            parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_unspecified
            or parsed.is_multicast
        ):
            return address
    except OSError:
        pass
    return None


def sync_host_address(root):
    """Synchronize host settings under the release lock when automatic IP detection is enabled."""
    root = Path(root)
    path = root / "host_settings.json"
    settings = json.loads(path.read_text(encoding="utf-8-sig"))
    if not settings.get("auto_detect_ip", False):
        return settings
    # Use the release lock so a watcher cannot overwrite a newly allocated version
    # with settings it read before a build. A busy publisher is retried next tick.
    lock_path = root / ".host" / "publish.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return settings
        settings = json.loads(path.read_text(encoding="utf-8-sig"))
        if not settings.get("auto_detect_ip", False):
            return settings
        return _sync_locked(root, path, settings)


def _sync_locked(root, path, settings):
    """Update the active host IP and its explicitly bound local client while holding the lock."""
    address = detect_lan_ip()
    if address is None:
        return settings
    if settings["host"] != address:
        settings["host"] = address
        atomic_write(path, (json.dumps(settings, indent=2) + "\n").encode())
    # Explicit, host-only binding. A copied project must not rewrite a different
    # computer's client settings, and this binding is never part of an OTA payload.
    binding_path = root / ".host" / "host-client.json"
    if binding_path.is_file():
        binding = json.loads(binding_path.read_text())
        if binding.get("computer", "").casefold() == socket.gethostname().casefold():
            client_path = Path(binding["client_config"])
            if client_path.is_file():
                client = json.loads(client_path.read_text(encoding="utf-8-sig"))
                url = f"http://{address}:{settings['port']}"
                if client.get("host_url") != url:
                    client["host_url"] = url
                    atomic_write(
                        client_path, (json.dumps(client, indent=2) + "\n").encode()
                    )
    return settings


def watch_host_address(root, stop, interval=3):
    """Retry host address synchronization until the shutdown event is set."""
    while not stop.wait(interval):
        try:
            sync_host_address(root)
        except (OSError, ValueError, KeyError) as error:
            print(f"Could not synchronize host address: {error}", flush=True)
