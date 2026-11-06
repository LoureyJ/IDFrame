"""Exercise the LAN receiver over real loopback HTTP and sockets."""

from http.client import HTTPConnection
from io import BytesIO
import queue
import socket
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from PIL import Image

from phone_transfer import MAX_BYTES, PhoneTransfer


class PhoneTransferTests(unittest.TestCase):
    def start(self, lifetime=10):
        self.session = PhoneTransfer(lifetime=lifetime, address="127.0.0.1")
        ready, self.photos, self.expired = queue.Queue(), queue.Queue(), threading.Event()
        self.worker = threading.Thread(
            target=self.session.run, args=(ready.put, self.photos.put, self.expired.set),
            daemon=True,
        )
        self.worker.start()
        self.addCleanup(self.stop)
        self.url = urlsplit(ready.get(timeout=3))

    def stop(self):
        self.session.close()
        self.worker.join(timeout=3)
        self.assertFalse(self.worker.is_alive())

    def request(self, method, body=None, *, path=None, headers=None):
        connection = HTTPConnection(self.url.hostname, self.url.port, timeout=4)
        try:
            connection.request(method, path or self.url.path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    @staticmethod
    def photo_bytes():
        image = BytesIO()
        Image.new("RGBA", (13, 17), (0, 0, 0, 0)).save(image, format="PNG")
        return image.getvalue()

    def test_only_valid_winning_upload_reaches_callback(self):
        self.start()
        self.assertEqual(self.request("GET", path="/receive/wrong")[0], 404)
        self.assertEqual(self.request("POST", self.photo_bytes(), path="/receive/wrong")[0], 404)
        self.assertIn(b"Send photo", self.request("GET")[1])
        self.assertEqual(self.request("POST", b"invalid image")[0], 415)
        self.assertEqual(self.request("POST", b"", headers={"Content-Length": str(MAX_BYTES + 1)})[0], 413)
        self.assertEqual(self.request("POST", self.photo_bytes())[0], 200)
        photo = self.photos.get(timeout=3)
        self.assertEqual((photo.mode, photo.size, photo.getpixel((0, 0))), ("RGB", (13, 17), (255, 255, 255)))
        self.worker.join(timeout=3)
        self.assertFalse(self.worker.is_alive())
        with self.assertRaises(OSError):
            self.request("POST", self.photo_bytes())
        self.assertTrue(self.photos.empty())

    def test_concurrent_upload_and_cancellation_during_decode(self):
        self.start()
        decoding, release = threading.Event(), threading.Event()

        def decode(*args, **kwargs):
            decoding.set()
            release.wait(timeout=4)
            return Image.new("RGB", (13, 17))

        completed = threading.Event()

        def upload():
            try:
                self.request("POST", self.photo_bytes())
            except OSError:
                pass  # Closing the receiver interrupts its response.
            finally:
                completed.set()

        with patch("phone_transfer.load_photo", side_effect=decode):
            thread = threading.Thread(target=upload, daemon=True)
            thread.start()
            try:
                self.assertTrue(decoding.wait(timeout=3))
                self.assertEqual(self.request("POST", self.photo_bytes())[0], 409)
                self.session.close()
            finally:
                release.set()
            self.assertTrue(completed.wait(timeout=4))
        self.assertTrue(self.photos.empty())

    def test_stalled_upload_releases_slot(self):
        self.start()
        with socket.create_connection((self.url.hostname, self.url.port), timeout=4) as sock:
            sock.sendall(f"POST {self.url.path} HTTP/1.0\r\nContent-Length: 99\r\n\r\nx".encode())
            self.assertIn(b" 408 ", sock.recv(4096))
        self.assertEqual(self.request("POST", self.photo_bytes())[0], 200)

    def test_expiry_closes_listener(self):
        self.start(lifetime=0.25)
        self.assertTrue(self.expired.wait(timeout=3))
        with self.assertRaises(OSError):
            self.request("POST", self.photo_bytes())

    def test_upload_accepted_before_expiry_can_send_confirmation(self):
        handler_factory = PhoneTransfer._handler

        def delay_success(session, received):
            handler = handler_factory(session, received)
            respond = handler.respond

            def respond_after_expiry(instance, code, body, *args):
                if code == 200:
                    session.deadline = 0
                    # Give the listener time to notice expiry before sending the reply.
                    threading.Event().wait(0.4)
                return respond(instance, code, body, *args)

            handler.respond = respond_after_expiry
            return handler

        with patch.object(PhoneTransfer, "_handler", delay_success):
            self.start()
        self.assertEqual(self.request("POST", self.photo_bytes())[0], 200)
        self.assertEqual(self.photos.get(timeout=3).size, (13, 17))
        self.assertFalse(self.expired.is_set())
