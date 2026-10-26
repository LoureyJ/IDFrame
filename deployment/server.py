"""Read-only LAN update server. Never serves source files, keys, or client photos."""

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import shutil
import threading
from urllib.parse import urlsplit
from deployment.host_network import sync_host_address, watch_host_address

ROOT = Path(__file__).resolve().parents[1]


def handler_for(repository):
    """Create a read-only HTTP handler bound to one update repository."""
    repository = Path(repository).resolve()
    repository_id = hashlib.sha256(str(repository).casefold().encode()).hexdigest()

    class Handler(BaseHTTPRequestHandler):
        server_version = "PortraitStudioUpdates/1"
        sys_version = ""

        def do_GET(self):
            """Serve only the health endpoint, signed manifest, or checksum-addressed blobs."""
            path = urlsplit(self.path).path
            if path == "/manifest.json":
                target = repository / "manifest.json"
                mime = "application/json"
            elif re.fullmatch(r"/blobs/[0-9a-f]{64}", path):
                target = repository / "blobs" / path.rsplit("/", 1)[1]
                mime = "application/octet-stream"
            elif path == "/health":
                content = b"IDFrame update host is running\n"
                self.send_response(200)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("X-PortraitStudio-Pid", str(os.getpid()))
                self.send_header("X-PortraitStudio-Repository", repository_id)
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                self.send_error(404)
                return
            try:
                with target.open("rb") as source:
                    self.send_response(200)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Length", str(target.stat().st_size))
                    self.send_header(
                        "Cache-Control",
                        (
                            "no-store"
                            if path == "/manifest.json"
                            else "public, max-age=31536000, immutable"
                        ),
                    )
                    self.end_headers()
                    shutil.copyfileobj(source, self.wfile, length=1024 * 1024)
            except FileNotFoundError:
                self.send_error(404)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


def main():
    """Start the LAN server and address watcher, cleaning both up at shutdown."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int)
    parser.add_argument(
        "--repository", type=Path, default=ROOT / ".host" / "repository"
    )
    args = parser.parse_args()
    settings = sync_host_address(ROOT)
    port = args.port or settings["port"]
    if not (args.repository / "manifest.json").is_file():
        parser.error("No published release. Run build_installer.bat first.")
    print(f"Host URL: http://{settings['host']}:{port}", flush=True)
    print(
        "Serving OTA updates. Use stop_host.bat to stop a background host, or Ctrl+C in a console. Photos never pass through this server.",
        flush=True,
    )
    server = ThreadingHTTPServer((args.bind, port), handler_for(args.repository))
    stop = threading.Event()
    watcher = threading.Thread(
        target=watch_host_address, args=(ROOT, stop), daemon=True
    )
    watcher.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        watcher.join(timeout=1)
        server.server_close()


if __name__ == "__main__":
    main()
