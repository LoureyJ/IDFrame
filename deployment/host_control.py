"""Start, inspect, or stop this project's background OTA server."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener

from deployment.common import atomic_write, canonical
from deployment.host_network import sync_host_address

ROOT = Path(__file__).resolve().parents[1]


def probe(port):
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/health", timeout=1) as response:
            if not response.headers.get("Server", "").startswith("PortraitStudioUpdates/1"):
                raise RuntimeError(f"Port {port} belongs to a different application. Choose another port in host_settings.json.")
            return {"pid": int(response.headers["X-PortraitStudio-Pid"]),
                    "repository": response.headers["X-PortraitStudio-Repository"]}
    except HTTPError as error:
        raise RuntimeError(f"Port {port} belongs to a different server (HTTP {error.code}). Choose another port in host_settings.json.") from error
    except URLError:
        return None


def start():
    settings = sync_host_address(ROOT)
    port = settings["port"]
    repository = ROOT / ".host" / "repository"
    repository_id = hashlib.sha256(str(repository.resolve()).casefold().encode()).hexdigest()
    existing = probe(port)
    if existing:
        if existing["repository"] != repository_id:
            raise RuntimeError("A different IDFrame project is using this port.")
        atomic_write(ROOT / ".host" / "server-state.json", canonical({"pid": existing["pid"], "port": port}))
        print(f"OTA host is already running at http://{settings['host']}:{port}")
        return
    if not (repository / "manifest.json").exists():
        raise RuntimeError("No published release. Run update.bat to publish your application first.")
    log_path = ROOT / ".host" / "server.log"
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    with log_path.open("ab") as log:
        child = subprocess.Popen([sys.executable, "-u", "-m", "deployment.server", "--port", str(port)],
                                 cwd=ROOT, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                 creationflags=flags)
    for _ in range(25):
        if child.poll() is not None:
            raise RuntimeError(f"OTA host could not start. See {log_path}")
        running = probe(port)
        # Windows virtual environments may launch a second interpreter process.
        if running and running["repository"] == repository_id:
            atomic_write(ROOT / ".host" / "server-state.json", canonical({"pid": running["pid"], "port": port}))
            print(f"OTA host started at http://{settings['host']}:{port}")
            print(f"Runs in the background until stopped or this PC shuts down. Log: {log_path}")
            return
        time.sleep(0.2)
    child.terminate()
    child.wait(timeout=5)
    raise RuntimeError(f"OTA host did not become ready. See {log_path}")


def stop():
    state_path = ROOT / ".host" / "server-state.json"
    if not state_path.exists():
        print("No recorded background OTA host to stop.")
        return
    state = json.loads(state_path.read_bytes())
    running = probe(state["port"])
    repository_id = hashlib.sha256(str((ROOT / ".host" / "repository").resolve()).casefold().encode()).hexdigest()
    if running:
        if running["pid"] != state["pid"] or running["repository"] != repository_id:
            raise RuntimeError("The port now belongs to another process; it was left running.")
        import signal
        os.kill(state["pid"], signal.SIGTERM)
    state_path.unlink(missing_ok=True)
    print("IDFrame OTA host stopped.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "status"))
    args = parser.parse_args()
    try:
        if args.action == "start":
            start()
        elif args.action == "stop":
            stop()
        else:
            settings = json.loads((ROOT / "host_settings.json").read_text())
            running = probe(settings["port"])
            print("OTA host is running." if running else "OTA host is not running. Run start_host.bat.")
    except (OSError, ValueError, RuntimeError) as error:
        print(f"OTA host error: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
