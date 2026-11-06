"""Receive one photo over a short-lived, token-protected LAN connection."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import secrets
import socket
import threading
import time

from PIL import Image

from lan_address import detect_lan_ip
from portrait import load_photo

MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 32_000_000
UPLOAD_SECONDS = 60

UPLOAD_PAGE = b"""<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Send photo to IDFrame</title>
<style>
body{font:1.1rem system-ui;margin:2rem auto;padding:0 1rem;max-width:28rem}
input,button{font:inherit;margin:0 0 1rem;max-width:100%}
button{padding:.65rem 1rem}
</style>
<h1>Send photo to IDFrame</h1>
<p>Choose one JPEG, PNG or WebP photo, up to 20 MB.</p>
<form>
<label for="photo">Photo</label><br>
<input id="photo" type="file" accept="image/*" required><br>
<button id="send" type="submit">Send photo</button>
</form>
<p id="status" role="status"></p>
<script>
const photo = document.getElementById("photo");
const send = document.getElementById("send");
const message = document.getElementById("status");
document.querySelector("form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = photo.files[0];
  if (!file) return;
  if (file.size > 20 * 1024 * 1024) {
    message.textContent = "Choose a photo smaller than 20 MB.";
    return;
  }
  send.disabled = photo.disabled = true;
  message.textContent = "Sending photo...";
  try {
    const response = await fetch(location.pathname, {method: "POST", body: file});
    message.textContent = await response.text();
    if (response.ok) return;
  } catch (_) {
    message.textContent = "Could not reach IDFrame. Ask for a new QR code if it expired.";
  }
  send.disabled = photo.disabled = false;
});
</script></html>
"""


class _Receiver(ThreadingHTTPServer):
    """Limit concurrent sockets and close outstanding connections with the session."""

    timeout = 0.2

    def __init__(self, address, handler):
        self.connections = set()
        self.connections_lock = threading.Lock()
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        """Bound the number of active request threads."""
        with self.connections_lock:
            full = len(self.connections) >= 8
            if not full:
                self.connections.add(request)
        if full:
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.shutdown_request(request)
            raise

    def shutdown_request(self, request):
        """Release one socket when its handler finishes."""
        with self.connections_lock:
            self.connections.discard(request)
        super().shutdown_request(request)

    def server_close(self):
        """Interrupt stalled reads when closing the listener."""
        super().server_close()
        with self.connections_lock:
            for connection in self.connections:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass


class PhoneTransfer:
    """Own one receive window and arbitrate upload, expiry, and cancellation."""

    def __init__(self, *, lifetime=300, address=None):
        self.lifetime = lifetime
        self.address = address
        self.deadline = 0
        self.path = "/receive/" + secrets.token_urlsafe(32)
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._uploading = False
        self._accepted = False

    def close(self):
        """Cancel the receiver and reject any work still decoding."""
        with self._lock:
            self._closed.set()

    def _available(self):
        """Check whether the session can accept a photo while holding its lock."""
        return not (self._closed.is_set() or self._accepted or time.monotonic() >= self.deadline)

    def run(self, ready, received, expired):
        """Serve until cancelled, expired, or the phone receives its success response."""
        address = self.address or detect_lan_ip()
        if not address:
            raise OSError("IDFrame could not find a local network connection.")
        with _Receiver((address, 0), self._handler(received)) as server:
            self.deadline = time.monotonic() + self.lifetime
            if not self._closed.is_set():
                ready(f"http://{address}:{server.server_port}{self.path}")
            while not self._closed.is_set() and time.monotonic() < self.deadline:
                server.handle_request()
            with self._lock:
                finishing = self._accepted and not self._closed.is_set()
                timed_out = not self._closed.is_set() and not self._accepted
                if not finishing:
                    self._closed.set()
            if finishing:
                # A photo accepted before expiry gets time to send its reply.
                self._closed.wait(timeout=3)
        if timed_out:
            expired()

    def _handler(self, received):
        """Create handlers scoped to this token and success callback."""
        session = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                """Bound idle reads and writes on every accepted socket."""
                self.request.settimeout(2)
                super().setup()

            def log_message(self, *_):
                """Keep the private upload URL out of logs."""

            def handle(self):
                """Treat a phone disconnect as an ordinary end of the request."""
                try:
                    super().handle()
                except (ConnectionError, TimeoutError):
                    pass

            def respond(self, code, body, content_type="text/plain; charset=utf-8"):
                """Send a bounded response with caching and referrals disabled."""
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                """Show the picker only while its exact session URL is valid."""
                with session._lock:
                    available = self.path == session.path and session._available()
                if available:
                    self.respond(200, UPLOAD_PAGE, "text/html; charset=utf-8")
                else:
                    self.respond(404, b"This QR code is unavailable.")

            def do_POST(self):
                """Validate the body and publish the winning photo after acknowledging it."""
                if self.path != session.path:
                    self.respond(404, b"This QR code is unavailable.")
                    return
                lengths = self.headers.get_all("Content-Length", [])
                length = lengths[0] if len(lengths) == 1 else ""
                if (self.headers.get("Transfer-Encoding") is not None
                        or not length.isascii() or not length.isdecimal() or len(length) > 8):
                    self.respond(400, b"Invalid upload. Choose a photo and try again.")
                    return
                size = int(length)
                if not 0 < size <= MAX_BYTES:
                    self.respond(413, b"Choose a non-empty photo up to 20 MB.")
                    return
                with session._lock:
                    available = session._available()
                    busy = session._uploading
                    if available and not busy:
                        session._uploading = True
                if not available:
                    self.respond(410, b"This QR code is unavailable.")
                    return
                if busy:
                    self.respond(409, b"Another upload is in progress. Try again shortly.")
                    return
                try:
                    self.receive_photo(size)
                finally:
                    with session._lock:
                        session._uploading = False

            def receive_photo(self, size):
                """Read a complete image within the session and upload deadlines."""
                deadline = min(session.deadline, time.monotonic() + UPLOAD_SECONDS)
                data = BytesIO()
                try:
                    while data.tell() < size:
                        if session._closed.is_set() or time.monotonic() >= deadline:
                            raise TimeoutError
                        chunk = self.rfile.read1(min(64 * 1024, size - data.tell()))
                        if not chunk:
                            raise EOFError
                        data.write(chunk)
                except (TimeoutError, EOFError):
                    self.respond(408, b"Upload interrupted. Try again.")
                    return
                data.seek(0)
                try:
                    photo = load_photo(data, formats=("JPEG", "PNG", "WEBP"), max_pixels=MAX_PIXELS)
                except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
                    self.respond(415, b"Choose a readable JPEG, PNG or WebP photo up to 32 megapixels.")
                    return
                with session._lock:
                    accepted = session._available()
                    if accepted:
                        session._accepted = True
                if not accepted:
                    self.respond(410, b"This QR code is unavailable.")
                    return
                try:
                    self.respond(200, b"Photo received by IDFrame.")
                finally:
                    try:
                        received(photo)
                    finally:
                        session.close()

        return Handler
